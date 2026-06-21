"""
End-user bulk import — template, preview, execute, and error report.
"""
from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, replace
from datetime import date, datetime

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.excel import build_xlsx, parse_spreadsheet
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.schemas.user_import import (
    ParsedImportUser,
    UserImportColumnMapping,
    UserImportErrorReportRequest,
    UserImportExecuteResponse,
    UserImportExecuteSummary,
    UserImportPreviewResponse,
    UserImportPreviewSummary,
    UserImportRowError,
)
from app.services.fd_field_definition_service import FdFieldDefinitionService
from app.services.system_settings_service import SystemSettingsService
from app.services.user_service import UserService

USER_IMPORT_MAX_FILE_SIZE = 10 * 1024 * 1024
USER_IMPORT_MAX_ROWS = 5000
USER_IMPORT_PREVIEW_TTL_SECONDS = 900
USER_IMPORT_ERROR_PREVIEW_LIMIT = 50
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

NON_IMPORTABLE_SYSTEM_KEYS = {
    "public_id",
    "external_id",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "avatar_color",
    "channel_id",
}

READONLY_HEADER_ALIASES = {"用户 id", "user id", "用户id"}
ORGANIZATION_HEADER = {"zh": "联系公司", "en": "Company"}
WEB_ID_HEADER = {"zh": "Web ID", "en": "Web ID"}

GENDER_LABEL_TO_VALUE = {
    "男": "male",
    "male": "male",
    "女": "female",
    "female": "female",
    "未知": "unknown",
    "unknown": "unknown",
    "其他": "other",
    "other": "other",
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


class UserImportService:

    @staticmethod
    async def build_template(db: AsyncSession, tenant_id: int, locale: str) -> tuple[bytes, str]:
        columns = await UserImportService._build_import_columns(db, tenant_id, locale)
        headers = [UserImportService._column_header(column, locale) for column in columns]
        instructions = UserImportService._instruction_rows(locale)
        workbook = build_xlsx(
            headers,
            [],
            sheet_name="Users" if locale != "zh" else "用户",
            extra_sheets=[("Instructions" if locale != "zh" else "说明", ["Item", "Detail"], instructions)],
        )
        filename = f"users-import-template-{datetime.now().strftime('%Y%m%d')}.xlsx"
        return workbook, filename

    @staticmethod
    async def preview_import(
        db: AsyncSession,
        redis: aioredis.Redis,
        tenant_id: int,
        filename: str,
        content: bytes,
        locale: str,
    ) -> UserImportPreviewResponse:
        UserImportService._validate_upload(filename, content)
        file_headers, data_rows = parse_spreadsheet(content, filename)
        if not file_headers:
            raise ValidationError("File header row is required")
        if not data_rows:
            raise ValidationError("No importable data rows in file")
        if len(data_rows) > USER_IMPORT_MAX_ROWS:
            raise ValidationError("Too many rows to import")

        columns = await UserImportService._build_import_columns(db, tenant_id, locale)
        column_mappings, header_to_column, unsupported_headers = UserImportService._map_headers(
            file_headers,
            columns,
            locale,
        )
        if unsupported_headers:
            for header in unsupported_headers:
                column_mappings.append(
                    UserImportColumnMapping(
                        file_header=header,
                        status="unsupported",
                        message="Unsupported column",
                    )
                )

        org_name_map = await OrganizationRepository.get_name_id_map(db, tenant_id)
        existing_lookup = await UserRepository.get_identifier_lookup(db, tenant_id)

        errors: list[UserImportRowError] = []
        importable_users: list[ParsedImportUser] = []
        seen_emails: dict[str, int] = {}
        seen_phones: dict[str, int] = {}
        seen_web_ids: dict[str, int] = {}

        if unsupported_headers:
            errors.append(
                UserImportRowError(
                    row_number=1,
                    field="整行",
                    reason="Unsupported columns detected",
                    raw_values=file_headers,
                )
            )

        for offset, raw_row in enumerate(data_rows):
            row_number = offset + 2
            row_values = UserImportService._normalize_row(raw_row, len(file_headers))
            parsed, row_errors = UserImportService._parse_row(
                row_number=row_number,
                row_values=row_values,
                header_to_column=header_to_column,
                org_name_map=org_name_map,
                existing_lookup=existing_lookup,
                seen_emails=seen_emails,
                seen_phones=seen_phones,
                seen_web_ids=seen_web_ids,
                locale=locale,
                unsupported_headers=unsupported_headers,
            )
            if row_errors:
                errors.extend(row_errors)
            elif parsed is not None:
                importable_users.append(parsed)

        preview_token = secrets.token_urlsafe(24)
        cache_payload = {
            "tenant_id": tenant_id,
            "filename": filename,
            "locale": locale,
            "file_headers": file_headers,
            "importable_users": [item.model_dump() for item in importable_users],
            "errors": [item.model_dump() for item in errors],
        }
        await redis.setex(
            UserImportService._preview_key(preview_token),
            USER_IMPORT_PREVIEW_TTL_SECONDS,
            json.dumps(cache_payload, ensure_ascii=False),
        )

        return UserImportPreviewResponse(
            preview_token=preview_token,
            summary=UserImportPreviewSummary(
                filename=filename,
                total_rows=len(data_rows),
                importable_rows=len(importable_users),
                blocked_rows=len(data_rows) - len(importable_users),
                unsupported_columns=len(unsupported_headers),
            ),
            file_headers=file_headers,
            column_mappings=column_mappings,
            errors=errors[:USER_IMPORT_ERROR_PREVIEW_LIMIT],
            has_more_errors=len(errors) > USER_IMPORT_ERROR_PREVIEW_LIMIT,
        )

    @staticmethod
    async def execute_import(
        db: AsyncSession,
        redis: aioredis.Redis,
        tenant_id: int,
        preview_token: str,
        actor_id: int | None,
    ) -> UserImportExecuteResponse:
        cache_raw = await redis.get(UserImportService._preview_key(preview_token))
        if not cache_raw:
            raise NotFoundError("Import preview expired, please upload again")
        cache = json.loads(cache_raw)
        if cache.get("tenant_id") != tenant_id:
            raise ValidationError("Import preview does not belong to current tenant")

        importable_users = [
            ParsedImportUser.model_validate(item) for item in cache.get("importable_users") or []
        ]
        preview_errors = [UserImportRowError.model_validate(item) for item in cache.get("errors") or []]
        existing_lookup = await UserRepository.get_identifier_lookup(db, tenant_id)

        created = 0
        failed = 0
        runtime_errors: list[UserImportRowError] = []

        for item in importable_users:
            row_errors = UserImportService._validate_existing_identifiers(item, existing_lookup)
            if row_errors:
                failed += 1
                runtime_errors.extend(row_errors)
                continue
            try:
                payload = UserCreate(
                    name=item.name,
                    email=item.email,
                    phone=item.phone,
                    gender=item.gender,
                    level=item.level,
                    address=item.address,
                    remark=item.remark,
                    web_id=item.web_id,
                    organization_id=item.organization_id,
                    custom_fields=item.custom_fields,
                )
                await UserService.create_user(db, tenant_id, payload, actor_id=actor_id)
                created += 1
                UserImportService._register_existing_lookup(existing_lookup, item)
            except Exception:
                failed += 1
                runtime_errors.append(
                    UserImportRowError(
                        row_number=item.row_number,
                        identifier=UserImportService._row_identifier(item),
                        field="整行",
                        reason="Import failed",
                        raw_values=item.raw_values,
                    )
                )

        await redis.delete(UserImportService._preview_key(preview_token))
        return UserImportExecuteResponse(
            summary=UserImportExecuteSummary(
                total_rows=len(importable_users) + len(preview_errors),
                created=created,
                failed=failed,
                skipped=len(preview_errors),
            ),
            errors=runtime_errors,
        )

    @staticmethod
    def build_error_report(body: UserImportErrorReportRequest, locale: str) -> tuple[bytes, str]:
        headers = [*body.headers, "错误原因" if locale == "zh" else "Error Reason"]
        rows = [[*row.values, row.error_reason] for row in body.rows]
        content = build_xlsx(headers, rows, sheet_name="Errors")
        filename = f"users-import-errors-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
        return content, filename

    @staticmethod
    def _preview_key(token: str) -> str:
        return f"user_import_preview:{token}"

    @staticmethod
    def _validate_upload(filename: str, content: bytes) -> None:
        lower_name = filename.lower()
        if not (lower_name.endswith(".xlsx") or lower_name.endswith(".csv")):
            raise ValidationError("Unsupported file format")
        if len(content) > USER_IMPORT_MAX_FILE_SIZE:
            raise ValidationError("File is too large")

    @staticmethod
    async def _build_import_columns(db: AsyncSession, tenant_id: int, locale: str) -> list[ImportColumnDef]:
        settings = await SystemSettingsService.get_settings(db, tenant_id)
        unified = await FdFieldDefinitionService.get_unified_list(db, tenant_id, "user", locale=locale)
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
            if field_key == "organization_id" and not settings.organization_enabled:
                continue

            resolved_key = "name" if field_key == "nickname" else field_key
            header_zh = ORGANIZATION_HEADER["zh"] if resolved_key == "organization_id" else (
                "昵称" if resolved_key == "name" else item.get("name") or resolved_key
            )
            header_en = ORGANIZATION_HEADER["en"] if resolved_key == "organization_id" else (
                "Nickname" if resolved_key == "name" else item.get("name") or resolved_key
            )
            columns.append(
                ImportColumnDef(
                    field_key=resolved_key,
                    field_id=item.get("id"),
                    header_zh=str(header_zh),
                    header_en=str(header_en),
                    field_type=str(item.get("field_type") or "single_line_text"),
                    source=str(item.get("source") or "system"),
                    slot_column=item.get("slot_column"),
                    option_label_to_value=UserImportService._build_option_label_map(item),
                )
            )

        columns.append(
            ImportColumnDef(
                field_key="web_id",
                field_id=None,
                header_zh=WEB_ID_HEADER["zh"],
                header_en=WEB_ID_HEADER["en"],
                field_type="single_line_text",
                source="system",
            )
        )
        return UserImportService._dedupe_headers(columns)

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
                ["必填识别", "每行至少填写邮箱、手机号或 Web ID 之一"],
                ["多选分隔", "多选字段使用中文分号；分隔"],
                ["组织列", "联系公司须匹配已有组织名称，不会自动创建组织"],
                ["重复规则", "文件内重复或租户内已存在的标识符不可导入"],
            ]
        return [
            ["Formats", ".xlsx / .csv, up to 10MB and 5000 rows"],
            ["Identifier", "Each row needs email, phone, or Web ID"],
            ["Multi-select", "Use Chinese semicolon ； between values"],
            ["Organization", "Company column must match an existing organization"],
            ["Duplicates", "Duplicate identifiers in file or tenant are blocked"],
        ]

    @staticmethod
    def _map_headers(
        file_headers: list[str],
        columns: list[ImportColumnDef],
        locale: str,
    ) -> tuple[list[UserImportColumnMapping], dict[int, ImportColumnDef], list[str]]:
        header_lookup: dict[str, ImportColumnDef] = {}
        for column in columns:
            header_lookup[column.header_zh.strip()] = column
            header_lookup[column.header_en.strip()] = column
            header_lookup[UserImportService._column_header(column, locale).strip()] = column

        mappings: list[UserImportColumnMapping] = []
        header_to_column: dict[int, ImportColumnDef] = {}
        unsupported: list[str] = []

        for index, raw_header in enumerate(file_headers):
            header = raw_header.strip()
            if not header:
                continue
            normalized = header.lower()
            if normalized in READONLY_HEADER_ALIASES or header in {"用户 ID", "User ID"}:
                mappings.append(
                    UserImportColumnMapping(
                        file_header=header,
                        field_key="public_id",
                        field_name=header,
                        field_type="single_line_text",
                        status="unsupported",
                        message="Public ID cannot be imported",
                    )
                )
                unsupported.append(header)
                continue

            column = header_lookup.get(header)
            if column is None:
                mappings.append(
                    UserImportColumnMapping(
                        file_header=header,
                        status="unsupported",
                        message="Unrecognized column",
                    )
                )
                unsupported.append(header)
                continue

            header_to_column[index] = column
            mappings.append(
                UserImportColumnMapping(
                    file_header=header,
                    field_key=column.field_key,
                    field_id=column.field_id,
                    field_name=UserImportService._column_header(column, locale),
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
        org_name_map: dict[str, int],
        existing_lookup: dict[str, dict[str, int]],
        seen_emails: dict[str, int],
        seen_phones: dict[str, int],
        seen_web_ids: dict[str, int],
        locale: str,
        unsupported_headers: list[str],
    ) -> tuple[ParsedImportUser | None, list[UserImportRowError]]:
        if unsupported_headers:
            return None, [
                UserImportRowError(
                    row_number=row_number,
                    identifier=UserImportService._preview_identifier(row_values, header_to_column),
                    field="整行",
                    reason="Unsupported columns detected",
                    raw_values=row_values,
                )
            ]

        parsed: dict[str, object] = {}
        custom_fields: dict[str, object] = {}
        errors: list[UserImportRowError] = []

        for index, column in header_to_column.items():
            if index >= len(row_values):
                continue
            raw_value = row_values[index]
            if raw_value == "":
                continue
            field_errors = UserImportService._validate_field_value(column, raw_value)
            if field_errors:
                errors.extend(
                    UserImportRowError(
                        row_number=row_number,
                        identifier=UserImportService._preview_identifier(row_values, header_to_column),
                        field=UserImportService._column_header(column, locale),
                        reason=reason,
                        raw_values=row_values,
                    )
                    for reason in field_errors
                )
                continue

            normalized = UserImportService._normalize_field_value(column, raw_value)
            if column.source == "custom":
                custom_key = column.field_key if column.field_key else str(column.field_id)
                custom_fields[custom_key] = normalized
            elif column.field_key == "organization_id":
                org_id = org_name_map.get(str(normalized).strip())
                if org_id is None:
                    errors.append(
                        UserImportRowError(
                            row_number=row_number,
                            identifier=UserImportService._preview_identifier(row_values, header_to_column),
                            field=ORGANIZATION_HEADER[locale],
                            reason="Organization does not exist",
                            raw_values=row_values,
                        )
                    )
                else:
                    parsed["organization_id"] = org_id
            else:
                parsed[column.field_key] = normalized

        if errors:
            return None, errors

        email = parsed.get("email")
        phone = parsed.get("phone")
        web_id = parsed.get("web_id")
        if not any([email, phone, web_id]):
            return None, [
                UserImportRowError(
                    row_number=row_number,
                    identifier=UserImportService._preview_identifier(row_values, header_to_column),
                    field="整行",
                    reason="Missing identifier",
                    raw_values=row_values,
                )
            ]

        duplicate_errors = UserImportService._duplicate_errors(
            row_number=row_number,
            row_values=row_values,
            header_to_column=header_to_column,
            email=str(email) if email else None,
            phone=str(phone) if phone else None,
            web_id=str(web_id) if web_id else None,
            seen_emails=seen_emails,
            seen_phones=seen_phones,
            seen_web_ids=seen_web_ids,
            existing_lookup=existing_lookup,
        )
        if duplicate_errors:
            return None, duplicate_errors

        name = str(parsed.get("name") or "").strip()
        if not name:
            name = UserImportService._default_name(email, phone, web_id, row_number)

        return ParsedImportUser(
            row_number=row_number,
            name=name[:64],
            email=str(email) if email else None,
            phone=str(phone) if phone else None,
            web_id=str(web_id) if web_id else None,
            gender=str(parsed["gender"]) if parsed.get("gender") else None,
            level=str(parsed["level"]) if parsed.get("level") else None,
            address=str(parsed["address"]) if parsed.get("address") else None,
            remark=str(parsed["remark"]) if parsed.get("remark") else None,
            organization_id=int(parsed["organization_id"]) if parsed.get("organization_id") else None,
            custom_fields=custom_fields,
            raw_values=row_values,
        ), []

    @staticmethod
    def _validate_field_value(column: ImportColumnDef, raw_value: str) -> list[str]:
        field_type = column.field_type
        if field_type == "email" and not EMAIL_PATTERN.match(raw_value):
            return ["Invalid email format"]
        if field_type == "gender":
            if raw_value.strip() not in GENDER_LABEL_TO_VALUE and raw_value.strip().lower() not in GENDER_LABEL_TO_VALUE:
                return ["Invalid gender value"]
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
        if column.field_type == "gender":
            return GENDER_LABEL_TO_VALUE.get(raw_value.strip()) or GENDER_LABEL_TO_VALUE.get(raw_value.strip().lower())
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
    def _duplicate_errors(
        *,
        row_number: int,
        row_values: list[str],
        header_to_column: dict[int, ImportColumnDef],
        email: str | None,
        phone: str | None,
        web_id: str | None,
        seen_emails: dict[str, int],
        seen_phones: dict[str, int],
        seen_web_ids: dict[str, int],
        existing_lookup: dict[str, dict[str, int]],
    ) -> list[UserImportRowError]:
        identifier = UserImportService._preview_identifier(row_values, header_to_column)
        errors: list[UserImportRowError] = []
        matched_users: set[int] = set()

        if email:
            normalized = email.strip().lower()
            if normalized in seen_emails:
                errors.append(UserImportRowError(row_number=row_number, identifier=identifier, field="邮箱", reason="Duplicate email in file", raw_values=row_values))
            else:
                seen_emails[normalized] = row_number
            existing_id = existing_lookup["emails"].get(normalized)
            if existing_id:
                matched_users.add(existing_id)
                errors.append(UserImportRowError(row_number=row_number, identifier=identifier, field="邮箱", reason="Email already exists", raw_values=row_values))

        if phone:
            normalized = phone.strip()
            if normalized in seen_phones:
                errors.append(UserImportRowError(row_number=row_number, identifier=identifier, field="手机号", reason="Duplicate phone in file", raw_values=row_values))
            else:
                seen_phones[normalized] = row_number
            existing_id = existing_lookup["phones"].get(normalized)
            if existing_id:
                matched_users.add(existing_id)
                errors.append(UserImportRowError(row_number=row_number, identifier=identifier, field="手机号", reason="Phone number already exists", raw_values=row_values))

        if web_id:
            normalized = web_id.strip()
            if normalized in seen_web_ids:
                errors.append(UserImportRowError(row_number=row_number, identifier=identifier, field="Web ID", reason="Duplicate Web ID in file", raw_values=row_values))
            else:
                seen_web_ids[normalized] = row_number
            existing_id = existing_lookup["web_ids"].get(normalized)
            if existing_id:
                matched_users.add(existing_id)
                errors.append(UserImportRowError(row_number=row_number, identifier=identifier, field="Web ID", reason="Web ID already exists", raw_values=row_values))

        if len(matched_users) > 1:
            errors.append(
                UserImportRowError(
                    row_number=row_number,
                    identifier=identifier,
                    field="整行",
                    reason="Conflicting identifiers match different users",
                    raw_values=row_values,
                )
            )
        return errors

    @staticmethod
    def _validate_existing_identifiers(
        item: ParsedImportUser,
        existing_lookup: dict[str, dict[str, int]],
    ) -> list[UserImportRowError]:
        matched_users: set[int] = set()
        errors: list[UserImportRowError] = []
        if item.email:
            existing_id = existing_lookup["emails"].get(item.email.strip().lower())
            if existing_id:
                matched_users.add(existing_id)
                errors.append(UserImportRowError(row_number=item.row_number, identifier=UserImportService._row_identifier(item), field="邮箱", reason="Email already exists", raw_values=item.raw_values))
        if item.phone:
            existing_id = existing_lookup["phones"].get(item.phone.strip())
            if existing_id:
                matched_users.add(existing_id)
                errors.append(UserImportRowError(row_number=item.row_number, identifier=UserImportService._row_identifier(item), field="手机号", reason="Phone number already exists", raw_values=item.raw_values))
        if item.web_id:
            existing_id = existing_lookup["web_ids"].get(item.web_id.strip())
            if existing_id:
                matched_users.add(existing_id)
                errors.append(UserImportRowError(row_number=item.row_number, identifier=UserImportService._row_identifier(item), field="Web ID", reason="Web ID already exists", raw_values=item.raw_values))
        if len(matched_users) > 1:
            errors.append(
                UserImportRowError(
                    row_number=item.row_number,
                    identifier=UserImportService._row_identifier(item),
                    field="整行",
                    reason="Conflicting identifiers match different users",
                    raw_values=item.raw_values,
                )
            )
        return errors

    @staticmethod
    def _register_existing_lookup(existing_lookup: dict[str, dict[str, int]], item: ParsedImportUser) -> None:
        pseudo_id = -item.row_number
        if item.email:
            existing_lookup["emails"][item.email.strip().lower()] = pseudo_id
        if item.phone:
            existing_lookup["phones"][item.phone.strip()] = pseudo_id
        if item.web_id:
            existing_lookup["web_ids"][item.web_id.strip()] = pseudo_id

    @staticmethod
    def _default_name(email: object | None, phone: object | None, web_id: object | None, row_number: int) -> str:
        if email:
            local = str(email).split("@", 1)[0]
            if local:
                return local[:64]
        if phone:
            return str(phone)[:64]
        if web_id:
            return str(web_id)[:64]
        return f"User {row_number}"

    @staticmethod
    def _preview_identifier(row_values: list[str], header_to_column: dict[int, ImportColumnDef]) -> str | None:
        for key in ("email", "phone", "web_id", "name"):
            for index, column in header_to_column.items():
                if column.field_key != key or index >= len(row_values):
                    continue
                value = row_values[index].strip()
                if value:
                    return value
        return None

    @staticmethod
    def _row_identifier(item: ParsedImportUser) -> str | None:
        return item.email or item.phone or item.web_id or item.name
