"""
Organization bulk import — template, preview, execute, and error report.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, replace
from datetime import date, datetime

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.excel import build_xlsx, parse_spreadsheet
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.organization import OrganizationCreate
from app.schemas.organization_import import (
    OrganizationImportColumnMapping,
    OrganizationImportErrorReportRequest,
    OrganizationImportExecuteResponse,
    OrganizationImportExecuteSummary,
    OrganizationImportPreviewResponse,
    OrganizationImportPreviewSummary,
    OrganizationImportRowError,
    ParsedImportOrganization,
)
from app.services.fd_field_definition_service import FdFieldDefinitionService
from app.services.organization_service import OrganizationService

ORG_IMPORT_MAX_FILE_SIZE = 10 * 1024 * 1024
ORG_IMPORT_MAX_ROWS = 5000
ORG_IMPORT_PREVIEW_TTL_SECONDS = 900
ORG_IMPORT_ERROR_PREVIEW_LIMIT = 50

NON_IMPORTABLE_SYSTEM_KEYS = {
    "public_id",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "user_count",
}

READONLY_HEADER_ALIASES = {
    "组织 id",
    "organization id",
    "组织id",
    "用户数量",
    "user count",
    "创建时间",
    "created at",
    "更新时间",
    "updated at",
    "创建人",
    "created by",
    "更新人",
    "updated by",
}


@dataclass(frozen=True)
class ImportColumnDef:
    field_key: str
    field_id: int | None
    header_zh: str
    header_en: str
    field_type: str
    source: str
    slot_column: str | None = None
    option_label_to_value: dict[str, str] | None = None


class OrganizationImportService:

    @staticmethod
    async def build_template(db: AsyncSession, tenant_id: int, locale: str) -> tuple[bytes, str]:
        columns = await OrganizationImportService._build_import_columns(db, tenant_id, locale)
        headers = [OrganizationImportService._column_header(column, locale) for column in columns]
        instructions = OrganizationImportService._instruction_rows(locale)
        workbook = build_xlsx(
            headers,
            [],
            sheet_name="Organizations" if locale != "zh" else "组织",
            extra_sheets=[("Instructions" if locale != "zh" else "说明", ["Item", "Detail"], instructions)],
        )
        filename = f"organizations-import-template-{datetime.now().strftime('%Y%m%d')}.xlsx"
        return workbook, filename

    @staticmethod
    async def preview_import(
        db: AsyncSession,
        redis: aioredis.Redis,
        tenant_id: int,
        filename: str,
        content: bytes,
        locale: str,
    ) -> OrganizationImportPreviewResponse:
        OrganizationImportService._validate_upload(filename, content)
        file_headers, data_rows = parse_spreadsheet(content, filename)
        if not file_headers:
            raise ValidationError("File header row is required")
        if not data_rows:
            raise ValidationError("No importable data rows in file")
        if len(data_rows) > ORG_IMPORT_MAX_ROWS:
            raise ValidationError("Too many rows to import")

        columns = await OrganizationImportService._build_import_columns(db, tenant_id, locale)
        column_mappings, header_to_column, unsupported_headers = OrganizationImportService._map_headers(
            file_headers,
            columns,
            locale,
        )
        if unsupported_headers:
            for header in unsupported_headers:
                column_mappings.append(
                    OrganizationImportColumnMapping(
                        file_header=header,
                        status="unsupported",
                        message="Unsupported column",
                    )
                )

        existing_names = await OrganizationRepository.get_name_id_map(db, tenant_id)

        errors: list[OrganizationImportRowError] = []
        importable_orgs: list[ParsedImportOrganization] = []
        seen_names: dict[str, int] = {}

        if unsupported_headers:
            errors.append(
                OrganizationImportRowError(
                    row_number=1,
                    field="整行",
                    reason="Unsupported columns detected",
                    raw_values=file_headers,
                )
            )

        for offset, raw_row in enumerate(data_rows):
            row_number = offset + 2
            row_values = OrganizationImportService._normalize_row(raw_row, len(file_headers))
            parsed, row_errors = OrganizationImportService._parse_row(
                row_number=row_number,
                row_values=row_values,
                header_to_column=header_to_column,
                existing_names=existing_names,
                seen_names=seen_names,
                locale=locale,
                unsupported_headers=unsupported_headers,
            )
            if row_errors:
                errors.extend(row_errors)
            elif parsed is not None:
                importable_orgs.append(parsed)

        preview_token = secrets.token_urlsafe(24)
        cache_payload = {
            "tenant_id": tenant_id,
            "filename": filename,
            "locale": locale,
            "file_headers": file_headers,
            "importable_orgs": [item.model_dump() for item in importable_orgs],
            "errors": [item.model_dump() for item in errors],
        }
        await redis.setex(
            OrganizationImportService._preview_key(preview_token),
            ORG_IMPORT_PREVIEW_TTL_SECONDS,
            json.dumps(cache_payload, ensure_ascii=False),
        )

        return OrganizationImportPreviewResponse(
            preview_token=preview_token,
            summary=OrganizationImportPreviewSummary(
                filename=filename,
                total_rows=len(data_rows),
                importable_rows=len(importable_orgs),
                blocked_rows=len(data_rows) - len(importable_orgs),
                unsupported_columns=len(unsupported_headers),
            ),
            file_headers=file_headers,
            column_mappings=column_mappings,
            errors=errors[:ORG_IMPORT_ERROR_PREVIEW_LIMIT],
            has_more_errors=len(errors) > ORG_IMPORT_ERROR_PREVIEW_LIMIT,
        )

    @staticmethod
    async def execute_import(
        db: AsyncSession,
        redis: aioredis.Redis,
        tenant_id: int,
        preview_token: str,
        actor_id: int | None,
    ) -> OrganizationImportExecuteResponse:
        cache_raw = await redis.get(OrganizationImportService._preview_key(preview_token))
        if not cache_raw:
            raise NotFoundError("Import preview expired, please upload again")
        cache = json.loads(cache_raw)
        if cache.get("tenant_id") != tenant_id:
            raise ValidationError("Import preview does not belong to current tenant")

        importable_orgs = [
            ParsedImportOrganization.model_validate(item) for item in cache.get("importable_orgs") or []
        ]
        preview_errors = [
            OrganizationImportRowError.model_validate(item) for item in cache.get("errors") or []
        ]
        existing_names = await OrganizationRepository.get_name_id_map(db, tenant_id)

        created = 0
        failed = 0
        runtime_errors: list[OrganizationImportRowError] = []

        for item in importable_orgs:
            normalized_name = item.name.strip()
            row_errors = OrganizationImportService._validate_existing_name(item, existing_names)
            if row_errors:
                failed += 1
                runtime_errors.extend(row_errors)
                continue
            try:
                payload = OrganizationCreate(
                    name=normalized_name,
                    description=item.description,
                    custom_fields=item.custom_fields,
                )
                await OrganizationService.create_organization(db, tenant_id, payload, actor_id=actor_id)
                created += 1
                existing_names[normalized_name] = -item.row_number
            except Exception:
                failed += 1
                runtime_errors.append(
                    OrganizationImportRowError(
                        row_number=item.row_number,
                        identifier=item.name,
                        field="整行",
                        reason="Import failed",
                        raw_values=item.raw_values,
                    )
                )

        await redis.delete(OrganizationImportService._preview_key(preview_token))
        return OrganizationImportExecuteResponse(
            summary=OrganizationImportExecuteSummary(
                total_rows=len(importable_orgs) + len(preview_errors),
                created=created,
                failed=failed,
                skipped=len(preview_errors),
            ),
            errors=runtime_errors,
        )

    @staticmethod
    def build_error_report(body: OrganizationImportErrorReportRequest, locale: str) -> tuple[bytes, str]:
        headers = [*body.headers, "错误原因" if locale == "zh" else "Error Reason"]
        rows = [[*row.values, row.error_reason] for row in body.rows]
        content = build_xlsx(headers, rows, sheet_name="Errors")
        filename = f"organizations-import-errors-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
        return content, filename

    @staticmethod
    def _preview_key(token: str) -> str:
        return f"organization_import_preview:{token}"

    @staticmethod
    def _validate_upload(filename: str, content: bytes) -> None:
        lower_name = filename.lower()
        if not (lower_name.endswith(".xlsx") or lower_name.endswith(".csv")):
            raise ValidationError("Unsupported file format")
        if len(content) > ORG_IMPORT_MAX_FILE_SIZE:
            raise ValidationError("File is too large")

    @staticmethod
    async def _build_import_columns(db: AsyncSession, tenant_id: int, locale: str) -> list[ImportColumnDef]:
        unified = await FdFieldDefinitionService.get_unified_list(db, tenant_id, "organization", locale=locale)
        columns: list[ImportColumnDef] = []

        for item in unified["items"]:
            if item.get("source") == "metadata":
                continue
            if item.get("status") != "active":
                continue
            field_key = item.get("key")
            if not field_key:
                continue
            type_config = item.get("type_config") or {}
            if type_config.get("readonly"):
                continue
            if field_key in NON_IMPORTABLE_SYSTEM_KEYS:
                continue

            header_zh = item.get("name") or field_key
            header_en = item.get("name") or field_key
            columns.append(
                ImportColumnDef(
                    field_key=field_key,
                    field_id=item.get("id"),
                    header_zh=str(header_zh),
                    header_en=str(header_en),
                    field_type=str(item.get("field_type") or "single_line_text"),
                    source=str(item.get("source") or "system"),
                    slot_column=item.get("slot_column"),
                    option_label_to_value=OrganizationImportService._build_option_label_map(item),
                )
            )

        return OrganizationImportService._dedupe_headers(columns)

    @staticmethod
    def _dedupe_headers(columns: list[ImportColumnDef]) -> list[ImportColumnDef]:
        seen: dict[str, int] = {}
        result: list[ImportColumnDef] = []
        for column in columns:
            updated = column
            for header in (column.header_zh, column.header_en):
                count = seen.get(header, 0)
                if count:
                    suffix_zh = "（系统默认）" if column.source == "system" else "（自定义）"
                    suffix_en = " (System)" if column.source == "system" else " (Custom)"
                    updated = replace(
                        updated,
                        header_zh=f"{column.header_zh}{suffix_zh}" if header == column.header_zh else updated.header_zh,
                        header_en=f"{column.header_en}{suffix_en}" if header == column.header_en else updated.header_en,
                    )
                seen[header] = count + 1
            result.append(updated)
        return result

    @staticmethod
    def _build_option_label_map(field_item: dict) -> dict[str, str] | None:
        mapping: dict[str, str] = {}
        for option in field_item.get("options") or []:
            label = option.get("label")
            value = option.get("value")
            if label is not None and value is not None:
                mapping[str(label).strip()] = str(value)
                mapping[str(value).strip().lower()] = str(value)
        type_options = (field_item.get("type_config") or {}).get("options")
        if isinstance(type_options, list):
            for option in type_options:
                if not isinstance(option, dict):
                    continue
                label = option.get("label")
                value = option.get("value")
                if label is not None and value is not None:
                    mapping[str(label).strip()] = str(value)
                    mapping[str(value).strip().lower()] = str(value)
        return mapping or None

    @staticmethod
    def _column_header(column: ImportColumnDef, locale: str) -> str:
        return column.header_zh if locale == "zh" else column.header_en

    @staticmethod
    def _instruction_rows(locale: str) -> list[list[str]]:
        if locale == "zh":
            return [
                ["支持格式", ".xlsx / .csv，最大 10MB，最多 5000 行"],
                ["必填字段", "名称必填"],
                ["多选分隔", "多选字段使用中文分号；分隔"],
                ["用户数量", "由系统统计，不支持填写"],
                ["重复规则", "文件内或租户内已存在的组织名称不可导入"],
            ]
        return [
            ["Formats", ".xlsx / .csv, up to 10MB and 5000 rows"],
            ["Required", "Name is required"],
            ["Multi-select", "Use Chinese semicolon ； between values"],
            ["User count", "Calculated by the system and cannot be imported"],
            ["Duplicates", "Duplicate organization names in file or tenant are blocked"],
        ]

    @staticmethod
    def _map_headers(
        file_headers: list[str],
        columns: list[ImportColumnDef],
        locale: str,
    ) -> tuple[list[OrganizationImportColumnMapping], dict[int, ImportColumnDef], list[str]]:
        header_lookup: dict[str, ImportColumnDef] = {}
        for column in columns:
            header_lookup[column.header_zh.strip()] = column
            header_lookup[column.header_en.strip()] = column
            header_lookup[OrganizationImportService._column_header(column, locale).strip()] = column

        mappings: list[OrganizationImportColumnMapping] = []
        header_to_column: dict[int, ImportColumnDef] = {}
        unsupported: list[str] = []

        for index, raw_header in enumerate(file_headers):
            header = raw_header.strip()
            if not header:
                continue
            normalized = header.lower()
            if normalized in READONLY_HEADER_ALIASES or header in {"组织 ID", "Organization ID"}:
                mappings.append(
                    OrganizationImportColumnMapping(
                        file_header=header,
                        field_key="public_id" if "id" in normalized else "user_count",
                        field_name=header,
                        field_type="single_line_text",
                        status="unsupported",
                        message="Column cannot be imported",
                    )
                )
                unsupported.append(header)
                continue

            column = header_lookup.get(header)
            if column is None:
                mappings.append(
                    OrganizationImportColumnMapping(
                        file_header=header,
                        status="unsupported",
                        message="Unrecognized column",
                    )
                )
                unsupported.append(header)
                continue

            header_to_column[index] = column
            mappings.append(
                OrganizationImportColumnMapping(
                    file_header=header,
                    field_key=column.field_key,
                    field_id=column.field_id,
                    field_name=OrganizationImportService._column_header(column, locale),
                    field_type=column.field_type,
                    status="mapped",
                )
            )

        return mappings, header_to_column, unsupported

    @staticmethod
    def _normalize_row(raw_row: list[str], width: int) -> list[str]:
        values = list(raw_row[:width])
        if len(values) < width:
            values.extend([""] * (width - len(values)))
        return [value.strip() for value in values]

    @staticmethod
    def _parse_row(
        *,
        row_number: int,
        row_values: list[str],
        header_to_column: dict[int, ImportColumnDef],
        existing_names: dict[str, int],
        seen_names: dict[str, int],
        locale: str,
        unsupported_headers: list[str],
    ) -> tuple[ParsedImportOrganization | None, list[OrganizationImportRowError]]:
        if unsupported_headers:
            return None, [
                OrganizationImportRowError(
                    row_number=row_number,
                    identifier=OrganizationImportService._preview_identifier(row_values, header_to_column),
                    field="整行",
                    reason="Unsupported columns detected",
                    raw_values=row_values,
                )
            ]

        parsed: dict[str, object] = {}
        custom_fields: dict[str, object] = {}
        errors: list[OrganizationImportRowError] = []

        for index, column in header_to_column.items():
            if index >= len(row_values):
                continue
            raw_value = row_values[index]
            if raw_value == "":
                continue
            field_errors = OrganizationImportService._validate_field_value(column, raw_value)
            if field_errors:
                errors.extend(
                    OrganizationImportRowError(
                        row_number=row_number,
                        identifier=OrganizationImportService._preview_identifier(row_values, header_to_column),
                        field=OrganizationImportService._column_header(column, locale),
                        reason=reason,
                        raw_values=row_values,
                    )
                    for reason in field_errors
                )
                continue

            normalized = OrganizationImportService._normalize_field_value(column, raw_value)
            if column.source == "custom":
                custom_key = column.field_key if column.field_key else str(column.field_id)
                custom_fields[custom_key] = normalized
            else:
                parsed[column.field_key] = normalized

        if errors:
            return None, errors

        name = str(parsed.get("name") or "").strip()
        if not name:
            return None, [
                OrganizationImportRowError(
                    row_number=row_number,
                    identifier=None,
                    field=OrganizationImportService._name_field_label(locale),
                    reason="Organization name is required",
                    raw_values=row_values,
                )
            ]

        duplicate_errors = OrganizationImportService._duplicate_name_errors(
            row_number=row_number,
            row_values=row_values,
            header_to_column=header_to_column,
            name=name,
            seen_names=seen_names,
            existing_names=existing_names,
            locale=locale,
        )
        if duplicate_errors:
            return None, duplicate_errors

        description = parsed.get("description")
        return ParsedImportOrganization(
            row_number=row_number,
            name=name[:128],
            description=str(description) if description else None,
            custom_fields=custom_fields,
            raw_values=row_values,
        ), []

    @staticmethod
    def _validate_field_value(column: ImportColumnDef, raw_value: str) -> list[str]:
        field_type = column.field_type
        if field_type in {"single_select", "single_select_tree"} and column.option_label_to_value:
            if raw_value.strip() not in column.option_label_to_value and raw_value.strip().lower() not in column.option_label_to_value:
                return ["Invalid option value"]
        if field_type in {"multi_select", "multi_select_tree"} and column.option_label_to_value:
            for part in [part.strip() for part in raw_value.split("；") if part.strip()]:
                if part not in column.option_label_to_value and part.lower() not in column.option_label_to_value:
                    return ["Invalid option value"]
        if field_type == "date":
            try:
                date.fromisoformat(raw_value[:10])
            except ValueError:
                return ["Invalid date format"]
        if field_type == "datetime":
            try:
                datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
            except ValueError:
                return ["Invalid datetime format"]
        if field_type == "number":
            try:
                float(raw_value)
            except ValueError:
                return ["Invalid number format"]
        return []

    @staticmethod
    def _normalize_field_value(column: ImportColumnDef, raw_value: str) -> object:
        if column.field_type in {"single_select", "single_select_tree"} and column.option_label_to_value:
            return column.option_label_to_value.get(raw_value.strip()) or column.option_label_to_value.get(raw_value.strip().lower())
        if column.field_type in {"multi_select", "multi_select_tree"} and column.option_label_to_value:
            values = []
            for part in raw_value.split("；"):
                part = part.strip()
                if not part:
                    continue
                mapped = column.option_label_to_value.get(part) or column.option_label_to_value.get(part.lower())
                if mapped is not None:
                    values.append(mapped)
            return values
        if column.field_type == "number":
            number = float(raw_value)
            return int(number) if number.is_integer() else number
        return raw_value.strip()

    @staticmethod
    def _duplicate_name_errors(
        *,
        row_number: int,
        row_values: list[str],
        header_to_column: dict[int, ImportColumnDef],
        name: str,
        seen_names: dict[str, int],
        existing_names: dict[str, int],
        locale: str,
    ) -> list[OrganizationImportRowError]:
        normalized = name.strip()
        identifier = normalized
        errors: list[OrganizationImportRowError] = []
        field_label = OrganizationImportService._name_field_label(locale)

        if normalized in seen_names:
            errors.append(
                OrganizationImportRowError(
                    row_number=row_number,
                    identifier=identifier,
                    field=field_label,
                    reason="Duplicate organization name in file",
                    raw_values=row_values,
                )
            )
        else:
            seen_names[normalized] = row_number

        if normalized in existing_names:
            errors.append(
                OrganizationImportRowError(
                    row_number=row_number,
                    identifier=identifier,
                    field=field_label,
                    reason="Organization name already exists",
                    raw_values=row_values,
                )
            )

        return errors

    @staticmethod
    def _validate_existing_name(
        item: ParsedImportOrganization,
        existing_names: dict[str, int],
    ) -> list[OrganizationImportRowError]:
        normalized = item.name.strip()
        if normalized in existing_names:
            return [
                OrganizationImportRowError(
                    row_number=item.row_number,
                    identifier=item.name,
                    field="名称",
                    reason="Organization name already exists",
                    raw_values=item.raw_values,
                )
            ]
        return []

    @staticmethod
    def _preview_identifier(row_values: list[str], header_to_column: dict[int, ImportColumnDef]) -> str | None:
        for index, column in header_to_column.items():
            if column.field_key != "name" or index >= len(row_values):
                continue
            value = row_values[index].strip()
            if value:
                return value
        return None

    @staticmethod
    def _name_field_label(locale: str) -> str:
        return "名称" if locale == "zh" else "Name"
