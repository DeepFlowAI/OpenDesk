"""
Bulk SMS target import: parse uploaded spreadsheets, validate rows against
template variable mapping, and insert valid recipients.
"""
from __future__ import annotations

import json
import re
import secrets

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.excel import parse_spreadsheet
from app.repositories.sms_bulk_task_repository import SmsBulkTargetRepository
from app.schemas.permission import EffectivePrincipal
from app.schemas.sms import CN_MOBILE_PATTERN
from app.schemas.sms_bulk_task import (
    SmsBulkImportExecuteResponse,
    SmsBulkImportMapping,
    SmsBulkImportParseResponse,
    SmsBulkImportRowError,
    SmsBulkImportValidateResponse,
)
from app.services.sms_bulk_task_service import TARGET_MUTABLE_STATUSES, SmsBulkTaskService

IMPORT_MAX_FILE_SIZE = 10 * 1024 * 1024
IMPORT_MAX_ROWS = 10000
IMPORT_CACHE_TTL_SECONDS = 900
IMPORT_ERROR_LIMIT = 50
IMPORT_SAMPLE_ROWS = 5

PHONE_PATTERN = re.compile(CN_MOBILE_PATTERN)
DEFAULT_VARIABLE_MAX_LENGTH = 50


def _cache_key(token: str) -> str:
    return f"sms_bulk_import:{token}"


class SmsBulkImportService:
    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    @staticmethod
    async def parse(
        db: AsyncSession,
        redis: aioredis.Redis,
        principal: EffectivePrincipal,
        task_id: int,
        filename: str,
        content: bytes,
    ) -> SmsBulkImportParseResponse:
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        if task.status not in TARGET_MUTABLE_STATUSES:
            raise ValidationError("Recipients cannot be modified in current task status")
        if len(content) > IMPORT_MAX_FILE_SIZE:
            raise ValidationError("File is too large")

        headers, rows = parse_spreadsheet(content, filename)
        if not headers:
            raise ValidationError("Spreadsheet header is required")
        if not rows:
            raise ValidationError("No importable data rows in file")
        if len(rows) > IMPORT_MAX_ROWS:
            raise ValidationError("Too many rows to import")

        token = secrets.token_urlsafe(24)
        payload = {
            "tenant_id": principal.tenant_id,
            "task_id": task.id,
            "headers": headers,
            "rows": rows,
        }
        await redis.setex(_cache_key(token), IMPORT_CACHE_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))
        return SmsBulkImportParseResponse(
            token=token,
            headers=headers,
            sample_rows=rows[:IMPORT_SAMPLE_ROWS],
        )

    # ------------------------------------------------------------------
    # Validate / import
    # ------------------------------------------------------------------

    @staticmethod
    async def validate(
        db: AsyncSession,
        redis: aioredis.Redis,
        principal: EffectivePrincipal,
        task_id: int,
        mapping: SmsBulkImportMapping,
    ) -> SmsBulkImportValidateResponse:
        task, headers, rows = await SmsBulkImportService._load(db, redis, principal, task_id, mapping.token)
        column_indexes = SmsBulkImportService._resolve_mapping(task, headers, mapping)
        existing_phones = await SmsBulkTargetRepository.list_phones_for_task(db, task.id)
        valid_rows, duplicate, errors = SmsBulkImportService._validate_rows(
            task, rows, column_indexes, existing_phones
        )
        return SmsBulkImportValidateResponse(
            total=len(rows),
            valid=len(valid_rows),
            duplicate=duplicate,
            invalid=len(rows) - len(valid_rows) - duplicate,
            errors=errors,
        )

    @staticmethod
    async def execute(
        db: AsyncSession,
        redis: aioredis.Redis,
        principal: EffectivePrincipal,
        task_id: int,
        mapping: SmsBulkImportMapping,
    ) -> SmsBulkImportExecuteResponse:
        task, headers, rows = await SmsBulkImportService._load(db, redis, principal, task_id, mapping.token)
        column_indexes = SmsBulkImportService._resolve_mapping(task, headers, mapping)
        existing_phones = await SmsBulkTargetRepository.list_phones_for_task(db, task.id)
        valid_rows, duplicate, errors = SmsBulkImportService._validate_rows(
            task, rows, column_indexes, existing_phones
        )
        payloads = [
            {
                "tenant_id": principal.tenant_id,
                "task_id": task.id,
                "phone": phone,
                "variable_values": variable_values,
            }
            for phone, variable_values in valid_rows
        ]
        success = await SmsBulkTargetRepository.create_many(db, payloads) if payloads else 0
        await redis.delete(_cache_key(mapping.token))
        return SmsBulkImportExecuteResponse(
            success=success,
            duplicate=duplicate,
            failed=len(rows) - success - duplicate,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    async def _load(
        db: AsyncSession,
        redis: aioredis.Redis,
        principal: EffectivePrincipal,
        task_id: int,
        token: str,
    ):
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        if task.status not in TARGET_MUTABLE_STATUSES:
            raise ValidationError("Recipients cannot be modified in current task status")
        raw = await redis.get(_cache_key(token))
        if not raw:
            raise NotFoundError("Import data expired, please upload again")
        cache = json.loads(raw)
        if cache.get("tenant_id") != principal.tenant_id or cache.get("task_id") != task.id:
            raise ValidationError("Import data does not belong to this task")
        return task, cache["headers"], cache["rows"]

    @staticmethod
    def _resolve_mapping(task, headers: list[str], mapping: SmsBulkImportMapping) -> dict[str, int]:
        """Map phone/variable keys to column indexes; enforce required mappings."""
        header_index = {header: index for index, header in enumerate(headers)}
        if mapping.phone_column not in header_index:
            raise ValidationError("请选择接收号码对应的文件列")

        column_indexes = {"phone": header_index[mapping.phone_column]}
        variable_defs = {
            item["key"]: item
            for item in (task.variables or [])
            if isinstance(item, dict) and item.get("key")
        }
        for key, definition in variable_defs.items():
            column = mapping.variable_columns.get(key)
            if column and column in header_index:
                column_indexes[key] = header_index[column]
            elif definition.get("required"):
                label = definition.get("label") or key
                raise ValidationError(f"请为必填变量「{label}」映射文件列")
        return column_indexes

    @staticmethod
    def _validate_rows(
        task,
        rows: list[list[str]],
        column_indexes: dict[str, int],
        existing_phones: set[str],
    ) -> tuple[list[tuple[str, dict[str, str]]], int, list[SmsBulkImportRowError]]:
        variable_defs = {
            item["key"]: item
            for item in (task.variables or [])
            if isinstance(item, dict) and item.get("key")
        }
        valid_rows: list[tuple[str, dict[str, str]]] = []
        errors: list[SmsBulkImportRowError] = []
        seen_phones: set[str] = set()
        duplicate = 0

        for offset, row in enumerate(rows):
            row_number = offset + 2
            phone_index = column_indexes["phone"]
            phone = row[phone_index].strip() if phone_index < len(row) else ""

            reason = ""
            if not phone:
                reason = "Phone number is required"
            elif not PHONE_PATTERN.match(phone):
                reason = "Invalid phone number"

            variable_values: dict[str, str] = {}
            if not reason:
                for key, definition in variable_defs.items():
                    column_index = column_indexes.get(key)
                    value = row[column_index].strip() if column_index is not None and column_index < len(row) else ""
                    if definition.get("required") and not value:
                        reason = f"Variable '{key}' is required"
                        break
                    max_length = definition.get("max_length") or DEFAULT_VARIABLE_MAX_LENGTH
                    if value and len(value) > max_length:
                        reason = f"Variable '{key}' exceeds max length {max_length}"
                        break
                    if value:
                        variable_values[key] = value

            if reason:
                if len(errors) < IMPORT_ERROR_LIMIT:
                    errors.append(SmsBulkImportRowError(row_number=row_number, phone=phone or None, reason=reason))
                continue
            if phone in seen_phones or phone in existing_phones:
                duplicate += 1
                continue
            seen_phones.add(phone)
            valid_rows.append((phone, variable_values))

        return valid_rows, duplicate, errors
