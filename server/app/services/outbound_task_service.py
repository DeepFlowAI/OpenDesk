"""
Business logic for manual outbound tasks.
"""
from copy import deepcopy
from datetime import datetime, timezone
from math import ceil
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.libs.excel import parse_spreadsheet
from app.models.outbound_task import OutboundTask, OutboundTaskTarget
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.outbound_task_repository import OutboundTaskRepository
from app.services.data_scope_service import DataScopeService
from app.schemas.outbound_task import (
    BulkAssignRequest,
    BulkAssignResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    OutboundRecordCreate,
    OutboundScript,
    OutboundTaskCreate,
    OutboundTaskResponse,
    OutboundTaskStats,
    OutboundTaskUpdate,
    OutboundTargetCreate,
    OutboundTargetBulkCreateRequest,
    OutboundTargetBulkCreateResponse,
    OutboundTargetExecutionUpdate,
    OutboundTargetImportError,
    OutboundTargetImportResponse,
    OutboundTargetUpdate,
    OutboundTemplateCreate,
    OutboundTemplateScriptResponse,
    OutboundTemplateScriptUpdate,
    OutboundTemplateUpdate,
)
from app.schemas.permission import EffectivePrincipal

MANAGE_PERMISSION = "engagement.outbound_task.manage"
CREATE_PERMISSION = "engagement.outbound_task.create"
EXECUTE_PERMISSION = "engagement.outbound_task.execute"
TEMPLATE_MANAGE_PERMISSION = "engagement.outbound_task.template.manage"
TARGET_IMPORT_MAX_FILE_SIZE = 10 * 1024 * 1024
TARGET_IMPORT_MAX_ROWS = 5000
TARGET_IMPORT_ERROR_LIMIT = 100
PHONE_HEADER_ALIASES = {
    "phone_number",
    "phone",
    "mobile",
    "tel",
    "呼叫号码",
    "号码",
    "手机号",
    "手机号码",
    "联系电话",
}


def _pages(total: int, per_page: int) -> int:
    return ceil(total / per_page) if total else 0


def _dump_fields(fields: list[Any] | None) -> list[dict]:
    return [field.model_dump(mode="json") if hasattr(field, "model_dump") else field for field in (fields or [])]


def _normalize_import_header(value: str) -> str:
    return value.strip().lower().replace(" ", "").replace("_", "")


def _field_attr(field: Any, key: str, default: Any = None) -> Any:
    if isinstance(field, dict):
        return field.get(key, default)
    return getattr(field, key, default)


def _is_empty_field_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or value == []


def _merge_and_validate_field_values(
    task: OutboundTask,
    target: OutboundTaskTarget,
    field_values: dict[str, Any],
) -> dict[str, Any]:
    """Validate agent-submitted field values against task field config and return merged values."""
    editable_keys = {
        _field_attr(field, "key")
        for field in (task.fields or [])
        if _field_attr(field, "enabled", True) and _field_attr(field, "agent_editable", False)
    }
    invalid_keys = sorted(set(field_values) - editable_keys)
    if invalid_keys:
        raise ValidationError("Field is not editable", details={"field_keys": invalid_keys})
    merged_values = dict(target.field_values or {})
    merged_values.update(field_values)
    missing_required_fields = [
        _field_attr(field, "name") or _field_attr(field, "key")
        for field in (task.fields or [])
        if _field_attr(field, "enabled", True)
        and _field_attr(field, "required", False)
        and _is_empty_field_value(merged_values.get(_field_attr(field, "key")))
    ]
    if missing_required_fields:
        raise ValidationError(
            "Required field is missing",
            details={"fields": missing_required_fields},
        )
    return merged_values


class OutboundTaskService:
    @staticmethod
    def _can_manage_task(principal: EffectivePrincipal, task: OutboundTask) -> bool:
        return principal.has_permission(MANAGE_PERMISSION) or (
            principal.has_permission(CREATE_PERMISSION) and task.created_by_id == principal.user_id
        )

    @staticmethod
    def _assert_can_manage_task(principal: EffectivePrincipal, task: OutboundTask) -> None:
        if not OutboundTaskService._can_manage_task(principal, task):
            raise NotFoundError("Outbound task not found")

    @staticmethod
    async def list_templates_for_tenant(
        db: AsyncSession,
        tenant_id: int,
        page: int,
        per_page: int,
        q: str | None = None,
    ) -> dict:
        items, total = await OutboundTaskRepository.list_templates(db, tenant_id, page, per_page, q)
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": _pages(total, per_page)}

    @staticmethod
    async def get_template_for_tenant(db: AsyncSession, tenant_id: int, template_id: int):
        item = await OutboundTaskRepository.get_template(db, template_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Outbound task template not found")
        return item

    @staticmethod
    async def create_template_for_tenant(
        db: AsyncSession,
        tenant_id: int,
        data: OutboundTemplateCreate,
        *,
        actor_user_id: int | None = None,
    ):
        payload = data.model_dump(mode="json")
        payload["tenant_id"] = tenant_id
        payload["created_by_id"] = actor_user_id
        payload["updated_by_id"] = actor_user_id
        return await OutboundTaskRepository.create_template(db, payload)

    @staticmethod
    async def update_template_for_tenant(
        db: AsyncSession,
        tenant_id: int,
        template_id: int,
        data: OutboundTemplateUpdate,
        *,
        actor_user_id: int | None = None,
    ):
        item = await OutboundTaskService.get_template_for_tenant(db, tenant_id, template_id)
        if data.expected_updated_at is not None and item.updated_at != data.expected_updated_at:
            raise ConflictError("Outbound task template was modified by another user")
        payload = data.model_dump(mode="json", exclude={"expected_updated_at"})
        payload["updated_by_id"] = actor_user_id
        if data.expected_updated_at is not None:
            updated = await OutboundTaskRepository.update_template_if_version(
                db,
                item,
                payload,
                data.expected_updated_at,
            )
            if updated is None:
                raise ConflictError("Outbound task template was modified by another user")
            return updated
        return await OutboundTaskRepository.update_template(db, item, payload)

    @staticmethod
    async def delete_template_for_tenant(db: AsyncSession, tenant_id: int, template_id: int) -> None:
        item = await OutboundTaskService.get_template_for_tenant(db, tenant_id, template_id)
        await OutboundTaskRepository.delete_template(db, item)

    @staticmethod
    def _script_response(item) -> OutboundTemplateScriptResponse:
        script = item.script
        if script is not None and not isinstance(script, OutboundScript):
            script = OutboundScript.model_validate(script)
        return OutboundTemplateScriptResponse(
            template_id=item.id,
            name=item.name,
            script=script,
            updated_at=item.updated_at,
        )

    @staticmethod
    async def get_template_script_for_tenant(
        db: AsyncSession,
        tenant_id: int,
        template_id: int,
    ) -> OutboundTemplateScriptResponse:
        item = await OutboundTaskService.get_template_for_tenant(db, tenant_id, template_id)
        return OutboundTaskService._script_response(item)

    @staticmethod
    async def update_template_script_for_tenant(
        db: AsyncSession,
        tenant_id: int,
        template_id: int,
        data: OutboundTemplateScriptUpdate,
        *,
        actor_user_id: int | None = None,
    ) -> OutboundTemplateScriptResponse:
        item = await OutboundTaskService.get_template_for_tenant(db, tenant_id, template_id)
        if data.expected_updated_at is not None and item.updated_at != data.expected_updated_at:
            raise ConflictError("Outbound task template was modified by another user")
        payload = {
            "script": data.script.model_dump(mode="json") if data.script is not None else None,
            "updated_by_id": actor_user_id,
        }
        if data.expected_updated_at is not None:
            updated = await OutboundTaskRepository.update_template_if_version(
                db,
                item,
                payload,
                data.expected_updated_at,
            )
            if updated is None:
                raise ConflictError("Outbound task template was modified by another user")
            return OutboundTaskService._script_response(updated)
        updated = await OutboundTaskRepository.update_template(db, item, payload)
        return OutboundTaskService._script_response(updated)

    @staticmethod
    async def list_templates(
        db: AsyncSession,
        principal: EffectivePrincipal,
        page: int,
        per_page: int,
        q: str | None = None,
    ) -> dict:
        if not (
            principal.has_permission(TEMPLATE_MANAGE_PERMISSION)
            or principal.has_permission(CREATE_PERMISSION)
        ):
            raise ForbiddenError("Permission denied")
        return await OutboundTaskService.list_templates_for_tenant(
            db, principal.tenant_id, page, per_page, q
        )

    @staticmethod
    async def create_template(db: AsyncSession, principal: EffectivePrincipal, data: OutboundTemplateCreate):
        if not principal.has_permission(TEMPLATE_MANAGE_PERMISSION):
            raise ForbiddenError("Permission denied")
        return await OutboundTaskService.create_template_for_tenant(
            db, principal.tenant_id, data, actor_user_id=principal.user_id
        )

    @staticmethod
    async def get_template(db: AsyncSession, principal: EffectivePrincipal, template_id: int):
        if not (
            principal.has_permission(TEMPLATE_MANAGE_PERMISSION)
            or principal.has_permission(CREATE_PERMISSION)
        ):
            raise ForbiddenError("Permission denied")
        return await OutboundTaskService.get_template_for_tenant(db, principal.tenant_id, template_id)

    @staticmethod
    async def update_template(db: AsyncSession, principal: EffectivePrincipal, template_id: int, data: OutboundTemplateUpdate):
        if not principal.has_permission(TEMPLATE_MANAGE_PERMISSION):
            raise ForbiddenError("Permission denied")
        return await OutboundTaskService.update_template_for_tenant(
            db, principal.tenant_id, template_id, data, actor_user_id=principal.user_id
        )

    @staticmethod
    async def delete_template(db: AsyncSession, principal: EffectivePrincipal, template_id: int) -> None:
        if not principal.has_permission(TEMPLATE_MANAGE_PERMISSION):
            raise ForbiddenError("Permission denied")
        await OutboundTaskService.delete_template_for_tenant(db, principal.tenant_id, template_id)

    @staticmethod
    async def get_template_script(db: AsyncSession, principal: EffectivePrincipal, template_id: int):
        if not (
            principal.has_permission(TEMPLATE_MANAGE_PERMISSION)
            or principal.has_permission(CREATE_PERMISSION)
        ):
            raise ForbiddenError("Permission denied")
        return await OutboundTaskService.get_template_script_for_tenant(
            db, principal.tenant_id, template_id
        )

    @staticmethod
    async def update_template_script(
        db: AsyncSession,
        principal: EffectivePrincipal,
        template_id: int,
        data: OutboundTemplateScriptUpdate,
    ):
        if not principal.has_permission(TEMPLATE_MANAGE_PERMISSION):
            raise ForbiddenError("Permission denied")
        return await OutboundTaskService.update_template_script_for_tenant(
            db, principal.tenant_id, template_id, data, actor_user_id=principal.user_id
        )

    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        principal: EffectivePrincipal,
        page: int,
        per_page: int,
        q: str | None = None,
        status: str | None = None,
        template_id: int | None = None,
    ) -> dict:
        can_manage = principal.has_permission(MANAGE_PERMISSION)
        can_create = principal.has_permission(CREATE_PERMISSION)
        if not (can_manage or can_create):
            raise ForbiddenError("Permission denied")
        creator_id = None if can_manage else principal.user_id
        items, total = await OutboundTaskRepository.list_tasks(
            db, principal.tenant_id, page, per_page, q, status, template_id, creator_id
        )
        return {
            "items": await OutboundTaskService._attach_task_stats(db, principal.tenant_id, items),
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": _pages(total, per_page),
        }

    @staticmethod
    async def _attach_task_stats(db: AsyncSession, tenant_id: int, tasks: list[OutboundTask]) -> list[OutboundTaskResponse]:
        stats_by_task = await OutboundTaskRepository.task_stats(db, tenant_id, [task.id for task in tasks])
        responses: list[OutboundTaskResponse] = []
        for task in tasks:
            response = OutboundTaskResponse.model_validate(task)
            response.stats = OutboundTaskStats(**stats_by_task.get(task.id, {}))
            responses.append(response)
        return responses

    @staticmethod
    async def get_task(db: AsyncSession, principal: EffectivePrincipal, task_id: int) -> OutboundTaskResponse:
        task = await OutboundTaskRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound task not found")
        OutboundTaskService._assert_can_manage_task(principal, task)
        return (await OutboundTaskService._attach_task_stats(db, principal.tenant_id, [task]))[0]

    @staticmethod
    async def create_task(db: AsyncSession, principal: EffectivePrincipal, data: OutboundTaskCreate) -> OutboundTaskResponse:
        if not principal.has_permission(CREATE_PERMISSION):
            raise ForbiddenError("Permission denied")
        template = await OutboundTaskRepository.get_template(db, data.template_id)
        if not template or template.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound task template not found")
        payload = data.model_dump(exclude={"publish", "fields"})
        payload["tenant_id"] = principal.tenant_id
        payload["template_name"] = template.name
        payload["fields"] = _dump_fields(data.fields) if data.fields is not None else list(template.fields or [])
        payload["script_snapshot"] = deepcopy(template.script)
        payload["created_by_id"] = principal.user_id
        payload["updated_by_id"] = principal.user_id
        payload["owner_id"] = payload.get("owner_id") or principal.user_id
        payload["status"] = "active" if data.publish else "draft"
        task = await OutboundTaskRepository.create_task(db, payload)
        return (await OutboundTaskService._attach_task_stats(db, principal.tenant_id, [task]))[0]

    @staticmethod
    async def update_task(db: AsyncSession, principal: EffectivePrincipal, task_id: int, data: OutboundTaskUpdate) -> OutboundTaskResponse:
        task = await OutboundTaskRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound task not found")
        OutboundTaskService._assert_can_manage_task(principal, task)
        if task.status == "archived":
            raise ValidationError("Archived tasks cannot be edited")
        payload = data.model_dump(exclude={"fields"}, exclude_unset=True)
        if data.fields is not None:
            payload["fields"] = _dump_fields(data.fields)
        payload["updated_by_id"] = principal.user_id
        updated = await OutboundTaskRepository.update_task(db, task, payload)
        return (await OutboundTaskService._attach_task_stats(db, principal.tenant_id, [updated]))[0]

    @staticmethod
    async def transition_task(db: AsyncSession, principal: EffectivePrincipal, task_id: int, action: str) -> OutboundTaskResponse:
        task = await OutboundTaskRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound task not found")
        OutboundTaskService._assert_can_manage_task(principal, task)
        next_status_by_action = {
            "publish": "active",
            "pause": "paused",
            "resume": "active",
            "archive": "archived",
        }
        if action == "publish":
            if task.status not in {"draft", "paused"}:
                raise ValidationError("Only draft or paused tasks can be published")
            if await OutboundTaskRepository.count_targets(db, principal.tenant_id, task.id) == 0:
                raise ValidationError("Please add outbound targets before publishing")
        elif action == "pause" and task.status != "active":
            raise ValidationError("Only active tasks can be paused")
        elif action == "resume" and task.status != "paused":
            raise ValidationError("Only paused tasks can be resumed")
        elif action == "archive" and task.status not in {"paused", "completed"}:
            raise ValidationError("Only paused or completed tasks can be archived")
        updated = await OutboundTaskRepository.update_task(
            db,
            task,
            {"status": next_status_by_action[action], "updated_by_id": principal.user_id},
        )
        return (await OutboundTaskService._attach_task_stats(db, principal.tenant_id, [updated]))[0]

    @staticmethod
    async def list_targets(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        page: int,
        per_page: int,
        q: str | None = None,
        status: str | None = None,
        assignee_id: int | None = None,
    ) -> dict:
        task = await OutboundTaskRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound task not found")
        OutboundTaskService._assert_can_manage_task(principal, task)
        items, total = await OutboundTaskRepository.list_targets(
            db, principal.tenant_id, task_id, page, per_page, q, status, assignee_id
        )
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": _pages(total, per_page)}

    @staticmethod
    async def create_target(db: AsyncSession, principal: EffectivePrincipal, task_id: int, data: OutboundTargetCreate):
        task = await OutboundTaskRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound task not found")
        OutboundTaskService._assert_can_manage_task(principal, task)
        if task.status == "archived":
            raise ValidationError("Archived tasks cannot be changed")
        payload = data.model_dump(mode="json")
        payload["tenant_id"] = principal.tenant_id
        payload["task_id"] = task_id
        return await OutboundTaskRepository.create_target(db, payload)

    @staticmethod
    async def create_targets_bulk(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        data: OutboundTargetBulkCreateRequest,
    ) -> OutboundTargetBulkCreateResponse:
        task = await OutboundTaskRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound task not found")
        OutboundTaskService._assert_can_manage_task(principal, task)
        if task.status == "archived":
            raise ValidationError("Archived tasks cannot be changed")

        rows = []
        for target in data.targets:
            payload = target.model_dump(mode="json")
            payload["tenant_id"] = principal.tenant_id
            payload["task_id"] = task_id
            rows.append(payload)
        items = await OutboundTaskRepository.create_targets_bulk(db, rows)
        return OutboundTargetBulkCreateResponse(created=len(items), items=items)

    @staticmethod
    async def import_targets(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        filename: str,
        content: bytes,
    ) -> OutboundTargetImportResponse:
        task = await OutboundTaskRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound task not found")
        OutboundTaskService._assert_can_manage_task(principal, task)
        if task.status == "archived":
            raise ValidationError("Archived tasks cannot be changed")
        if len(content) > TARGET_IMPORT_MAX_FILE_SIZE:
            raise ValidationError("File is too large")

        headers, rows = parse_spreadsheet(content, filename)
        if not headers:
            raise ValidationError("Spreadsheet header is required")
        if len(rows) > TARGET_IMPORT_MAX_ROWS:
            raise ValidationError("Too many rows")

        normalized_headers = [_normalize_import_header(header) for header in headers]
        phone_header_aliases = {_normalize_import_header(alias) for alias in PHONE_HEADER_ALIASES}
        phone_index = next((index for index, header in enumerate(normalized_headers) if header in phone_header_aliases), None)
        if phone_index is None:
            raise ValidationError("Phone number column is required")

        enabled_fields = [field for field in (task.fields or []) if _field_attr(field, "enabled", True)]
        field_lookup: dict[str, str] = {}
        required_field_keys: set[str] = set()
        for field in enabled_fields:
            field_key = str(_field_attr(field, "key", "") or "").strip()
            field_name = str(_field_attr(field, "name", "") or "").strip()
            if not field_key:
                continue
            field_lookup[_normalize_import_header(field_key)] = field_key
            if field_name:
                field_lookup[_normalize_import_header(field_name)] = field_key
            if bool(_field_attr(field, "required", False)):
                required_field_keys.add(field_key)

        field_columns = {
            index: field_lookup[header]
            for index, header in enumerate(normalized_headers)
            if index != phone_index and header in field_lookup
        }

        created = 0
        total = 0
        errors: list[OutboundTargetImportError] = []

        for row_number, row in enumerate(rows, start=2):
            values = [cell.strip() for cell in row]
            if not any(values):
                continue
            total += 1
            phone_number = values[phone_index] if phone_index < len(values) else ""
            field_values = {
                field_key: values[index]
                for index, field_key in field_columns.items()
                if index < len(values) and values[index]
            }
            missing_fields = sorted(key for key in required_field_keys if not str(field_values.get(key) or "").strip())

            reason = ""
            if not phone_number:
                reason = "Phone number is required"
            elif len(phone_number) > 64:
                reason = "Phone number must be at most 64 characters"
            elif missing_fields:
                reason = f"Required field missing: {', '.join(missing_fields)}"

            if reason:
                if len(errors) < TARGET_IMPORT_ERROR_LIMIT:
                    errors.append(OutboundTargetImportError(row_number=row_number, phone_number=phone_number or None, reason=reason))
                continue

            await OutboundTaskRepository.create_target(
                db,
                {
                    "tenant_id": principal.tenant_id,
                    "task_id": task_id,
                    "phone_number": phone_number,
                    "field_values": field_values,
                },
            )
            created += 1

        return OutboundTargetImportResponse(total=total, created=created, failed=total - created, errors=errors)

    @staticmethod
    async def update_target(db: AsyncSession, principal: EffectivePrincipal, target_id: int, data: OutboundTargetUpdate):
        target = await OutboundTaskRepository.get_target(db, target_id)
        if not target or target.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound target not found")
        task = await OutboundTaskRepository.get_task(db, target.task_id)
        if not task:
            raise NotFoundError("Outbound task not found")
        OutboundTaskService._assert_can_manage_task(principal, task)
        return await OutboundTaskRepository.update_target(db, target, data.model_dump(exclude_unset=True))

    @staticmethod
    async def bulk_assign(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        data: BulkAssignRequest,
    ) -> BulkAssignResponse:
        task = await OutboundTaskRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound task not found")
        OutboundTaskService._assert_can_manage_task(principal, task)
        if task.status == "archived":
            raise ValidationError("Archived tasks cannot be assigned")
        updated = await OutboundTaskRepository.bulk_assign(
            db, principal.tenant_id, task_id, data.target_ids, data.assignee_id, data.overwrite
        )
        return BulkAssignResponse(updated=updated)

    @staticmethod
    async def bulk_delete_targets(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        data: BulkDeleteRequest,
    ) -> BulkDeleteResponse:
        task = await OutboundTaskRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound task not found")
        OutboundTaskService._assert_can_manage_task(principal, task)
        if task.status == "archived":
            raise ValidationError("Archived tasks cannot be changed")
        deleted = await OutboundTaskRepository.bulk_delete_targets(
            db,
            principal.tenant_id,
            task_id,
            data.target_ids,
        )
        return BulkDeleteResponse(deleted=deleted)

    @staticmethod
    async def list_my_targets(
        db: AsyncSession,
        principal: EffectivePrincipal,
        page: int,
        per_page: int,
        task_id: int | None = None,
        status: str | None = None,
    ) -> dict:
        if not (principal.has_permission(EXECUTE_PERMISSION) and principal.has_permission("call.workspace.use")):
            raise ForbiddenError("Permission denied")
        items, total = await OutboundTaskRepository.list_my_targets(
            db, principal.tenant_id, principal.user_id, page, per_page, task_id, status
        )
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": _pages(total, per_page)}

    @staticmethod
    async def list_my_tasks(db: AsyncSession, principal: EffectivePrincipal) -> dict:
        if not (principal.has_permission(EXECUTE_PERMISSION) and principal.has_permission("call.workspace.use")):
            raise ForbiddenError("Permission denied")
        items = await OutboundTaskRepository.list_my_tasks_with_progress(
            db, principal.tenant_id, principal.user_id
        )
        return {"items": items}

    @staticmethod
    async def list_my_target_records(
        db: AsyncSession,
        principal: EffectivePrincipal,
        target_id: int,
    ) -> dict:
        if not (principal.has_permission(EXECUTE_PERMISSION) and principal.has_permission("call.workspace.use")):
            raise ForbiddenError("Permission denied")
        target = await OutboundTaskRepository.get_target(db, target_id)
        if not target or target.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound target not found")
        if target.assignee_id != principal.user_id:
            raise ForbiddenError("Permission denied")

        manual_records = await OutboundTaskRepository.list_records_for_target(db, principal.tenant_id, target_id)
        personal_calls = await OutboundTaskRepository.list_personal_auto_calls_for_target(
            db, principal.tenant_id, target_id
        )

        items: list[dict[str, Any]] = []
        for record in manual_records:
            items.append(
                {
                    "id": record.id,
                    "source": "manual",
                    "started_at": record.started_at,
                    "answered": record.answered,
                    "result": record.result,
                    "duration_ms": record.duration_ms,
                    "agent_id": record.agent_id,
                    "call_record_id": record.call_record_id,
                }
            )
        for call in personal_calls:
            answered = call.answered_at is not None
            duration_ms = None
            if call.answered_at is not None and call.ended_at is not None:
                duration_ms = max(int((call.ended_at - call.answered_at).total_seconds() * 1000), 0)
            items.append(
                {
                    "id": call.id,
                    "source": "personal_auto",
                    "started_at": call.started_at,
                    "answered": answered,
                    "result": None,
                    "duration_ms": duration_ms,
                    "agent_id": call.assigned_agent_id,
                    "call_record_id": call.call_record_id,
                }
            )
        items.sort(key=lambda item: item["started_at"], reverse=True)

        agent_ids = [item["agent_id"] for item in items if item["agent_id"] is not None]
        employees = await EmployeeRepository.get_by_ids(db, agent_ids)
        agent_names = {
            employee.id: (employee.display_name or employee.nickname or employee.name or employee.username)
            for employee in employees
            if employee.tenant_id == principal.tenant_id
        }

        visible_call_ids: set[int] = set()
        if principal.has_permission("call.record.view"):
            visible_call_ids = await DataScopeService.call_record_ids_in_scope(
                db,
                principal,
                [item["call_record_id"] for item in items if item["call_record_id"] is not None],
            )

        # Expose the public id needed to open the call detail drawer only for
        # records the agent is allowed to see.
        public_ids = await OutboundTaskRepository.list_call_record_public_ids(
            db, principal.tenant_id, sorted(visible_call_ids)
        )

        for item in items:
            item["agent_name"] = agent_names.get(item["agent_id"])
            item["can_view_detail"] = (
                item["call_record_id"] is not None and item["call_record_id"] in visible_call_ids
            )
            item["call_record_public_id"] = (
                public_ids.get(item["call_record_id"]) if item["can_view_detail"] else None
            )
        return {"items": items}

    @staticmethod
    async def get_my_target_script(db: AsyncSession, principal: EffectivePrincipal, target_id: int) -> dict:
        if not (principal.has_permission(EXECUTE_PERMISSION) and principal.has_permission("call.workspace.use")):
            raise ForbiddenError("Permission denied")
        target = await OutboundTaskRepository.get_target(db, target_id)
        if not target or target.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound target not found")
        if target.assignee_id != principal.user_id:
            raise ForbiddenError("Permission denied")
        task = await OutboundTaskRepository.get_task(db, target.task_id)
        if not task or task.script_snapshot is None:
            raise NotFoundError("Outbound script not found")
        return task.script_snapshot

    @staticmethod
    async def update_my_target(
        db: AsyncSession,
        principal: EffectivePrincipal,
        target_id: int,
        data: OutboundTargetExecutionUpdate,
    ) -> OutboundTaskTarget:
        if not (principal.has_permission(EXECUTE_PERMISSION) and principal.has_permission("call.workspace.use")):
            raise ForbiddenError("Permission denied")
        target = await OutboundTaskRepository.get_target(db, target_id)
        if not target or target.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound target not found")
        if target.assignee_id != principal.user_id:
            raise ForbiddenError("Permission denied")
        task = await OutboundTaskRepository.get_task(db, target.task_id)
        if not task or task.status != "active":
            raise ValidationError("Task is not executable")

        payload: dict[str, Any] = {}
        if data.status is not None:
            if data.status == "calling":
                raise ValidationError("Calling status is managed automatically")
            payload["status"] = data.status

        if data.field_values is not None:
            payload["field_values"] = _merge_and_validate_field_values(task, target, data.field_values)

        return await OutboundTaskRepository.update_target(db, target, payload)

    @staticmethod
    async def create_record(
        db: AsyncSession,
        principal: EffectivePrincipal,
        target_id: int,
        data: OutboundRecordCreate,
    ):
        if not (principal.has_permission(EXECUTE_PERMISSION) and principal.has_permission("call.workspace.use")):
            raise ForbiddenError("Permission denied")
        target = await OutboundTaskRepository.get_target(db, target_id)
        if not target or target.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound target not found")
        if target.assignee_id != principal.user_id:
            raise ForbiddenError("Permission denied")
        task = await OutboundTaskRepository.get_task(db, target.task_id)
        if not task or task.status in {"paused", "archived"}:
            raise ValidationError("Task is not executable")
        if data.target_status == "redial" and data.next_follow_up_at is None:
            raise ValidationError("next_follow_up_at is required when target_status is redial")
        merged_values = _merge_and_validate_field_values(task, target, data.field_values or {})
        started_at = data.started_at or datetime.now(timezone.utc)
        payload = data.model_dump(exclude={"target_status", "next_follow_up_at"})
        payload["tenant_id"] = principal.tenant_id
        payload["task_id"] = target.task_id
        payload["target_id"] = target.id
        payload["agent_id"] = principal.user_id
        payload["phone_number"] = target.phone_number
        payload["started_at"] = started_at

        record = await OutboundTaskRepository.create_record(db, payload)
        target_payload = {
            "status": data.target_status,
            "field_values": merged_values,
            "call_count": target.call_count + 1,
            "answered_count": target.answered_count + (1 if data.answered else 0),
            "last_called_at": started_at,
            "last_call_result": data.result,
            "next_follow_up_at": data.next_follow_up_at,
            "total_talk_duration_ms": target.total_talk_duration_ms + ((data.duration_ms or 0) if data.answered else 0),
        }
        await OutboundTaskRepository.update_target(db, target, target_payload)
        return record

    @staticmethod
    async def list_records(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        page: int,
        per_page: int,
    ) -> dict:
        task = await OutboundTaskRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound task not found")
        OutboundTaskService._assert_can_manage_task(principal, task)
        items, total = await OutboundTaskRepository.list_records(db, principal.tenant_id, task_id, page, per_page)
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": _pages(total, per_page)}
