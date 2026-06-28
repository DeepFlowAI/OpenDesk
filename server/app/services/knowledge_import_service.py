"""
Knowledge base Excel import/export service.
"""
from __future__ import annotations

import html
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.excel import build_xlsx, parse_spreadsheet
from app.models.knowledge import KnowledgeDirectory, KnowledgeDocument
from app.repositories.knowledge_repository import (
    KnowledgeDirectoryRepository,
    KnowledgeDocumentRepository,
)
from app.schemas.knowledge_import import (
    KnowledgeImportExecuteResponse,
    KnowledgeImportPreviewResponse,
    KnowledgeImportRowResult,
    KnowledgeImportSummary,
)
from app.schemas.permission import EffectivePrincipal
from app.services.knowledge_service import KnowledgeService, html_to_plain_text

KNOWLEDGE_IMPORT_MAX_FILE_SIZE = 10 * 1024 * 1024
KNOWLEDGE_IMPORT_PREVIEW_TTL_SECONDS = 900
KNOWLEDGE_IMPORT_HEADERS = [
    "id",
    "directory_path",
    "title",
    "status",
    "validity_type",
    "valid_from",
    "valid_to",
    "content_text",
    "content_html",
    "created_at",
    "updated_at",
    "updated_by",
]
_READONLY_HEADERS = {"created_at", "updated_at", "updated_by"}
_INTEGER_PATTERN = re.compile(r"^\d+(?:\.0+)?$")
_EXCEL_DATE_BASE = datetime(1899, 12, 30)


@dataclass(frozen=True)
class _ParsedImportRow:
    row_number: int
    action: str
    document_id: int | None
    directory_parts: tuple[str, ...]
    title: str
    status: str
    validity_type: str
    valid_from: datetime | None
    valid_to: datetime | None
    content_html: str
    raw_values: list[str]


@dataclass
class _PreviewBuild:
    summary: KnowledgeImportSummary
    rows: list[KnowledgeImportRowResult]
    parsed_rows: list[_ParsedImportRow]


class KnowledgeImportService:
    @staticmethod
    async def build_template(locale: str) -> tuple[bytes, str]:
        example_rows = [
            [
                "",
                "产品/退款",
                "如何申请退款",
                "published",
                "permanent",
                "",
                "",
                "客户可在订单详情提交退款申请。",
                "",
                "",
                "",
                "",
            ],
            [
                "123",
                "产品/发票",
                "发票开具规则",
                "published",
                "scheduled",
                "2026-06-01 09:00",
                "2026-12-31 18:00",
                "发票开具需提供抬头与税号。",
                "",
                "",
                "",
                "",
            ],
        ]
        workbook = build_xlsx(
            KNOWLEDGE_IMPORT_HEADERS,
            example_rows,
            sheet_name="知识文档",
            extra_sheets=[("字段说明", ["Field", "Required", "Description"], KnowledgeImportService._instruction_rows(locale))],
        )
        return workbook, f"knowledge-import-template-{datetime.now().strftime('%Y%m%d')}.xlsx"

    @staticmethod
    async def export_documents(
        db: AsyncSession,
        tenant_id: int,
        principal: EffectivePrincipal,
        *,
        directory_id: int | None = None,
        search: str | None = None,
        locale: str = "zh",
    ) -> tuple[bytes, str]:
        directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        directory_ids: list[int] | None = None
        if directory_id is not None:
            if directory_id not in {directory.id for directory in directories}:
                raise NotFoundError("Directory not found")
            directory_ids = KnowledgeService._descendant_ids(directories, directory_id)

        documents = await KnowledgeDocumentRepository.query_all(
            db,
            tenant_id,
            directory_ids=directory_ids,
            search=search.strip() if search else None,
            include_drafts=principal.has_permission("knowledge.workspace.document.edit"),
        )
        rows = [
            [
                document.id,
                KnowledgeImportService._directory_path_string(directories, document.directory_id),
                document.title,
                document.status,
                document.validity_type,
                document.valid_from,
                document.valid_to,
                document.content_plain,
                document.content_html,
                document.created_at,
                document.updated_at,
                document.updated_by_actor_name or "",
            ]
            for document in documents
        ]
        workbook = build_xlsx(
            KNOWLEDGE_IMPORT_HEADERS,
            rows,
            sheet_name="知识文档",
            extra_sheets=[("字段说明", ["Field", "Required", "Description"], KnowledgeImportService._instruction_rows(locale))],
        )
        filename = f"knowledge-export-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
        return workbook, filename

    @staticmethod
    async def preview_import(
        db: AsyncSession,
        redis: aioredis.Redis,
        tenant_id: int,
        filename: str,
        content: bytes,
        locale: str,
    ) -> KnowledgeImportPreviewResponse:
        KnowledgeImportService._validate_upload(filename, content)
        headers, raw_rows = parse_spreadsheet(content, filename)
        KnowledgeImportService._validate_headers(headers)
        preview = await KnowledgeImportService._build_preview(db, tenant_id, filename, headers, raw_rows)
        preview_token = secrets.token_urlsafe(24)
        await redis.setex(
            KnowledgeImportService._preview_key(preview_token),
            KNOWLEDGE_IMPORT_PREVIEW_TTL_SECONDS,
            json.dumps(
                {
                    "tenant_id": tenant_id,
                    "filename": filename,
                    "locale": locale,
                    "headers": headers,
                    "rows": raw_rows,
                },
                ensure_ascii=False,
            ),
        )
        return KnowledgeImportPreviewResponse(
            preview_token=preview_token,
            summary=preview.summary,
            file_headers=headers,
            rows=preview.rows,
            has_errors=preview.summary.error_rows > 0,
        )

    @staticmethod
    async def execute_import(
        db: AsyncSession,
        redis: aioredis.Redis,
        tenant_id: int,
        preview_token: str,
        actor_id: int | None,
    ) -> KnowledgeImportExecuteResponse:
        cache_raw = await redis.get(KnowledgeImportService._preview_key(preview_token))
        if not cache_raw:
            raise NotFoundError("Import preview expired, please upload again")
        cache = json.loads(cache_raw)
        if cache.get("tenant_id") != tenant_id:
            raise ValidationError("Import preview does not belong to current tenant")

        filename = str(cache.get("filename") or "import.xlsx")
        headers = [str(item) for item in cache.get("headers") or []]
        raw_rows = [[str(cell) for cell in row] for row in cache.get("rows") or []]
        preview = await KnowledgeImportService._build_preview(db, tenant_id, filename, headers, raw_rows)
        if preview.summary.error_rows > 0:
            return KnowledgeImportExecuteResponse(
                summary=preview.summary,
                rows=preview.rows,
                has_errors=True,
            )

        try:
            document_ids = await KnowledgeImportService._apply_rows(db, tenant_id, preview.parsed_rows, actor_id)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        await redis.delete(KnowledgeImportService._preview_key(preview_token))
        from app.services.knowledge_recommendation_service import KnowledgeRecommendationService

        for document_id in document_ids:
            KnowledgeRecommendationService.schedule_document_embedding_refresh(tenant_id, document_id)
        return KnowledgeImportExecuteResponse(
            summary=preview.summary,
            rows=preview.rows,
            has_errors=False,
        )

    @staticmethod
    async def _build_preview(
        db: AsyncSession,
        tenant_id: int,
        filename: str,
        headers: list[str],
        raw_rows: list[list[str]],
    ) -> _PreviewBuild:
        header_index = {header.strip(): index for index, header in enumerate(headers) if header.strip()}
        directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        directory_state = _DirectoryPreviewState(directories)
        document_ids = [
            parsed_id
            for row in raw_rows
            if (parsed_id := KnowledgeImportService._parse_id_cell(KnowledgeImportService._cell(row, header_index, "id"))) is not None
        ]
        documents_by_id = await KnowledgeDocumentRepository.get_by_ids(db, tenant_id, sorted(set(document_ids)))
        title_lookup = await KnowledgeDocumentRepository.title_lookup(db, tenant_id)

        rows: list[KnowledgeImportRowResult] = []
        parsed_rows: list[_ParsedImportRow] = []
        seen_ids: dict[int, int] = {}
        seen_targets: dict[tuple[tuple[str, ...], str], int] = {}

        for offset, raw_row in enumerate(raw_rows):
            row_number = offset + 2
            normalized_row = KnowledgeImportService._normalize_row(raw_row, len(headers))
            result, parsed = KnowledgeImportService._parse_row(
                row_number=row_number,
                row_values=normalized_row,
                header_index=header_index,
                directory_state=directory_state,
                documents_by_id=documents_by_id,
                title_lookup=title_lookup,
                seen_ids=seen_ids,
                seen_targets=seen_targets,
            )
            rows.append(result)
            if parsed is not None:
                parsed_rows.append(parsed)

        create_documents = sum(1 for row in rows if row.action == "create")
        update_documents = sum(1 for row in rows if row.action == "update")
        skipped_rows = sum(1 for row in rows if row.action == "skip")
        error_rows = sum(1 for row in rows if row.action == "error")
        return _PreviewBuild(
            summary=KnowledgeImportSummary(
                filename=filename,
                total_rows=len(raw_rows),
                create_directories=directory_state.create_count,
                create_documents=create_documents,
                update_documents=update_documents,
                skipped_rows=skipped_rows,
                error_rows=error_rows,
            ),
            rows=rows,
            parsed_rows=parsed_rows,
        )

    @staticmethod
    def _parse_row(
        *,
        row_number: int,
        row_values: list[str],
        header_index: dict[str, int],
        directory_state: "_DirectoryPreviewState",
        documents_by_id: dict[int, KnowledgeDocument],
        title_lookup: dict[tuple[int, str], int],
        seen_ids: dict[int, int],
        seen_targets: dict[tuple[tuple[str, ...], str], int],
    ) -> tuple[KnowledgeImportRowResult, _ParsedImportRow | None]:
        if not any(value.strip() for value in row_values):
            return KnowledgeImportRowResult(row_number=row_number, action="skip", message="Blank row", raw_values=row_values), None

        errors: list[str] = []
        raw_id = KnowledgeImportService._cell(row_values, header_index, "id")
        document_id = KnowledgeImportService._parse_id_cell(raw_id)
        if raw_id.strip() and document_id is None:
            errors.append("Invalid id")

        if document_id is not None:
            if document_id in seen_ids:
                errors.append(f"Duplicate id with row {seen_ids[document_id]}")
            else:
                seen_ids[document_id] = row_number

        existing = documents_by_id.get(document_id) if document_id is not None else None
        if document_id is not None and existing is None:
            errors.append("Document id does not exist in current tenant")

        directory_path = KnowledgeImportService._cell(row_values, header_index, "directory_path").strip()
        directory_parts = KnowledgeImportService._parse_directory_path(directory_path, errors)
        title = KnowledgeImportService._cell(row_values, header_index, "title").strip()
        if not title:
            errors.append("Title is required")
        elif len(title) > 120:
            errors.append("Title cannot exceed 120 characters")

        status = KnowledgeImportService._parse_status(
            KnowledgeImportService._cell(row_values, header_index, "status"),
            existing,
            errors,
        )
        validity_type = KnowledgeImportService._parse_validity_type(
            KnowledgeImportService._cell(row_values, header_index, "validity_type"),
            existing,
            errors,
        )
        valid_from = KnowledgeImportService._parse_datetime_cell(
            KnowledgeImportService._cell(row_values, header_index, "valid_from"),
            existing.valid_from if existing else None,
            errors,
            keep_existing=existing is not None,
        )
        valid_to = KnowledgeImportService._parse_datetime_cell(
            KnowledgeImportService._cell(row_values, header_index, "valid_to"),
            existing.valid_to if existing else None,
            errors,
            keep_existing=existing is not None,
        )
        content_text = KnowledgeImportService._cell(row_values, header_index, "content_text").strip()
        raw_content_html = KnowledgeImportService._cell(row_values, header_index, "content_html").strip()
        if raw_content_html:
            content_html = raw_content_html
        elif content_text:
            content_html = KnowledgeImportService._text_to_html(content_text)
        elif existing is not None:
            content_html = existing.content_html
        else:
            content_html = ""
            errors.append("Content is required")

        if validity_type == "permanent":
            valid_from = None
            valid_to = None
        else:
            try:
                KnowledgeImportService._validate_period(validity_type, valid_from, valid_to)
            except ValidationError as exc:
                errors.append(exc.message)

        if not errors and directory_parts and title:
            target_key = (directory_parts, title)
            if target_key in seen_targets:
                errors.append(f"Duplicate target with row {seen_targets[target_key]}")
            else:
                seen_targets[target_key] = row_number

            directory_id = directory_state.existing_id(directory_parts)
            conflict_id = title_lookup.get((directory_id, title)) if directory_id is not None else None
            if conflict_id is not None and conflict_id != document_id:
                errors.append("Document title already exists in target directory")

        if errors:
            return (
                KnowledgeImportRowResult(
                    row_number=row_number,
                    action="error",
                    id=document_id,
                    directory_path=directory_path or None,
                    title=title or None,
                    errors=errors,
                    raw_values=row_values,
                ),
                None,
            )

        if not directory_parts:
            raise ValidationError("Directory path is required")
        directory_state.plan(directory_parts)
        action = "update" if document_id is not None else "create"
        return (
            KnowledgeImportRowResult(
                row_number=row_number,
                action=action,
                id=document_id,
                directory_path="/".join(directory_parts),
                title=title,
                message="Ready to update" if action == "update" else "Ready to create",
                raw_values=row_values,
            ),
            _ParsedImportRow(
                row_number=row_number,
                action=action,
                document_id=document_id,
                directory_parts=directory_parts,
                title=title,
                status=status,
                validity_type=validity_type,
                valid_from=valid_from,
                valid_to=valid_to,
                content_html=content_html,
                raw_values=row_values,
            ),
        )

    @staticmethod
    async def _apply_rows(
        db: AsyncSession,
        tenant_id: int,
        rows: list[_ParsedImportRow],
        actor_id: int | None,
    ) -> list[int]:
        directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        directory_state = _DirectoryApplyState(db, tenant_id, directories, actor_id)
        documents_by_id = await KnowledgeDocumentRepository.get_by_ids(
            db,
            tenant_id,
            [row.document_id for row in rows if row.document_id is not None],
        )
        changed_document_ids: list[int] = []
        for row in rows:
            directory = await directory_state.ensure(row.directory_parts)
            content_plain = html_to_plain_text(row.content_html)
            values = KnowledgeService._validate_document_values(
                {
                    "title": row.title,
                    "directory_id": directory.id,
                    "content_html": row.content_html,
                    "content_plain": content_plain,
                    "status": row.status,
                    "validity_type": row.validity_type,
                    "valid_from": row.valid_from,
                    "valid_to": row.valid_to,
                }
            )
            if row.action == "create":
                created = await KnowledgeDocumentRepository.create_pending(
                    db,
                    {
                        **values,
                        "tenant_id": tenant_id,
                        **await KnowledgeService._actor_create(db, tenant_id, actor_id),
                    },
                )
                changed_document_ids.append(created.id)
                continue

            if row.document_id is None or row.document_id not in documents_by_id:
                raise ValidationError("Document id does not exist in current tenant")
            updated = await KnowledgeDocumentRepository.update_pending(
                db,
                documents_by_id[row.document_id],
                {
                    **values,
                    **await KnowledgeService._actor_update(db, tenant_id, actor_id),
                },
            )
            changed_document_ids.append(updated.id)
        return changed_document_ids

    @staticmethod
    def _preview_key(token: str) -> str:
        return f"knowledge_import_preview:{token}"

    @staticmethod
    def _validate_upload(filename: str, content: bytes) -> None:
        if not filename.lower().endswith(".xlsx"):
            raise ValidationError("Only .xlsx files are supported")
        if len(content) > KNOWLEDGE_IMPORT_MAX_FILE_SIZE:
            raise ValidationError("File is too large")

    @staticmethod
    def _validate_headers(headers: list[str]) -> None:
        if not headers:
            raise ValidationError("File header row is required")
        normalized = [header.strip() for header in headers if header.strip()]
        missing = [header for header in ("directory_path", "title") if header not in normalized]
        if missing:
            raise ValidationError(f"Missing required columns: {', '.join(missing)}")
        unsupported = [header for header in normalized if header not in KNOWLEDGE_IMPORT_HEADERS]
        if unsupported:
            raise ValidationError(f"Unsupported columns: {', '.join(unsupported)}")

    @staticmethod
    def _cell(row_values: list[str], header_index: dict[str, int], header: str) -> str:
        index = header_index.get(header)
        if index is None or index >= len(row_values):
            return ""
        return row_values[index].strip()

    @staticmethod
    def _normalize_row(raw_row: list[str], width: int) -> list[str]:
        values = list(raw_row[:width])
        if len(values) < width:
            values.extend([""] * (width - len(values)))
        return [str(value).strip() for value in values]

    @staticmethod
    def _parse_id_cell(value: str) -> int | None:
        raw = value.strip()
        if not raw:
            return None
        if not _INTEGER_PATTERN.match(raw):
            return None
        return int(float(raw))

    @staticmethod
    def _parse_directory_path(value: str, errors: list[str]) -> tuple[str, ...]:
        if not value:
            errors.append("Directory path is required")
            return ()
        parts = tuple(part.strip() for part in value.split("/") if part.strip())
        if not parts:
            errors.append("Directory path is required")
            return ()
        if len(parts) > 3:
            errors.append("Directory path supports up to 3 levels")
        for part in parts:
            if len(part) > 50:
                errors.append("Directory name cannot exceed 50 characters")
        return parts

    @staticmethod
    def _parse_status(value: str, existing: KnowledgeDocument | None, errors: list[str]) -> str:
        raw = value.strip()
        if not raw:
            return existing.status if existing else "draft"
        mapping = {
            "draft": "draft",
            "published": "published",
            "未发布": "draft",
            "草稿": "draft",
            "已发布": "published",
        }
        normalized = mapping.get(raw.lower()) or mapping.get(raw)
        if normalized is None:
            errors.append("Invalid status")
            return existing.status if existing else "draft"
        return normalized

    @staticmethod
    def _parse_validity_type(value: str, existing: KnowledgeDocument | None, errors: list[str]) -> str:
        raw = value.strip()
        if not raw:
            return existing.validity_type if existing else "permanent"
        mapping = {
            "permanent": "permanent",
            "scheduled": "scheduled",
            "永久": "permanent",
            "时限": "scheduled",
            "限时": "scheduled",
        }
        normalized = mapping.get(raw.lower()) or mapping.get(raw)
        if normalized is None:
            errors.append("Invalid validity type")
            return existing.validity_type if existing else "permanent"
        return normalized

    @staticmethod
    def _parse_datetime_cell(
        value: str,
        existing: datetime | None,
        errors: list[str],
        *,
        keep_existing: bool,
    ) -> datetime | None:
        raw = value.strip()
        if not raw:
            return existing if keep_existing else None
        if re.match(r"^\d+(?:\.\d+)?$", raw):
            serial = float(raw)
            if serial > 20000:
                return _EXCEL_DATE_BASE + timedelta(days=serial)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                pass
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            errors.append("Invalid datetime format")
            return existing if keep_existing else None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed

    @staticmethod
    def _validate_period(validity_type: str, valid_from: datetime | None, valid_to: datetime | None) -> None:
        KnowledgeService._validate_document_values(
            {
                "validity_type": validity_type,
                "valid_from": valid_from,
                "valid_to": valid_to,
            }
        )

    @staticmethod
    def _text_to_html(value: str) -> str:
        paragraphs = [part.strip() for part in value.replace("\r\n", "\n").split("\n") if part.strip()]
        if not paragraphs:
            return ""
        return "".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)

    @staticmethod
    def _directory_path_string(directories: list[KnowledgeDirectory], directory_id: int) -> str:
        return "/".join(item.name for item in KnowledgeService._directory_path(directories, directory_id))

    @staticmethod
    def _instruction_rows(locale: str) -> list[list[str]]:
        if locale == "en":
            return [
                ["id", "No", "Exported document ID. Keep it to update an existing article."],
                ["directory_path", "Yes", "Use / between directory levels, up to 3 levels."],
                ["title", "Yes", "1-120 characters. Unique within the target directory."],
                ["status", "No", "draft or published. Defaults to draft for new rows."],
                ["validity_type", "No", "permanent or scheduled. Defaults to permanent for new rows."],
                ["valid_from", "Conditional", "Required when validity_type is scheduled."],
                ["valid_to", "Conditional", "Required when validity_type is scheduled and must be later than valid_from."],
                ["content_text", "Conditional", "Required for new rows when content_html is empty."],
                ["content_html", "No", "Preferred when present; preserves rich text on re-import."],
                ["created_at / updated_at / updated_by", "No", "Export-only columns, ignored during import."],
            ]
        return [
            ["id", "否", "导出的文档 ID；保留该值可更新已有文档。"],
            ["directory_path", "是", "目录路径用 / 分隔，最多 3 级。"],
            ["title", "是", "1-120 个字符；同一目录下不可重名。"],
            ["status", "否", "draft / published，或 未发布 / 已发布；新建默认 draft。"],
            ["validity_type", "否", "permanent / scheduled，或 永久 / 时限；新建默认 permanent。"],
            ["valid_from", "条件必填", "validity_type 为 scheduled 时必填。"],
            ["valid_to", "条件必填", "validity_type 为 scheduled 时必填，且晚于 valid_from。"],
            ["content_text", "条件必填", "新建且 content_html 为空时必填。"],
            ["content_html", "否", "有值时优先导入，用于保留富文本结构。"],
            ["created_at / updated_at / updated_by", "否", "仅导出展示，导入时忽略。"],
        ]


class _DirectoryPreviewState:
    def __init__(self, directories: list[KnowledgeDirectory]) -> None:
        self._existing = _directory_path_index(directories)
        self._planned: set[tuple[str, ...]] = set()

    @property
    def create_count(self) -> int:
        return len(self._planned)

    def existing_id(self, parts: tuple[str, ...]) -> int | None:
        directory = self._existing.get(parts)
        return directory.id if directory else None

    def plan(self, parts: tuple[str, ...]) -> None:
        for depth in range(1, len(parts) + 1):
            path = parts[:depth]
            if path not in self._existing:
                self._planned.add(path)


class _DirectoryApplyState:
    def __init__(
        self,
        db: AsyncSession,
        tenant_id: int,
        directories: list[KnowledgeDirectory],
        actor_id: int | None,
    ) -> None:
        self._db = db
        self._tenant_id = tenant_id
        self._actor_id = actor_id
        self._directories = _directory_path_index(directories)

    async def ensure(self, parts: tuple[str, ...]) -> KnowledgeDirectory:
        parent_id: int | None = None
        current: KnowledgeDirectory | None = None
        for depth in range(1, len(parts) + 1):
            path = parts[:depth]
            current = self._directories.get(path)
            if current is None:
                sort_order = await KnowledgeDirectoryRepository.max_sort_order(self._db, self._tenant_id, parent_id) + 10
                current = await KnowledgeDirectoryRepository.create_pending(
                    self._db,
                    {
                        "tenant_id": self._tenant_id,
                        "parent_id": parent_id,
                        "name": parts[depth - 1],
                        "sort_order": sort_order,
                        **await KnowledgeService._actor_create(self._db, self._tenant_id, self._actor_id),
                    },
                )
                self._directories[path] = current
            parent_id = current.id
        if current is None:
            raise ValidationError("Directory path is required")
        return current


def _directory_path_index(directories: list[KnowledgeDirectory]) -> dict[tuple[str, ...], KnowledgeDirectory]:
    by_id = {directory.id: directory for directory in directories}
    cache: dict[int, tuple[str, ...]] = {}

    def path_for(directory: KnowledgeDirectory, seen: set[int] | None = None) -> tuple[str, ...]:
        if directory.id in cache:
            return cache[directory.id]
        seen = seen or set()
        if directory.id in seen or directory.parent_id is None or directory.parent_id not in by_id:
            path = (directory.name,)
        else:
            seen.add(directory.id)
            path = (*path_for(by_id[directory.parent_id], seen), directory.name)
        cache[directory.id] = path
        return path

    return {path_for(directory): directory for directory in directories}
