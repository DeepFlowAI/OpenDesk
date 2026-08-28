"""
Bulk SMS task service: template snapshots, task CRUD with state machine,
and target management (add / bulk delete / resend failed).
"""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.sms import SMS_STATUS_ENABLED
from app.models.sms_bulk_task import (
    SMS_BULK_SEND_TYPE_IMMEDIATE,
    SMS_BULK_SEND_TYPE_SCHEDULED,
    SMS_BULK_TASK_STATUS_ARCHIVED,
    SMS_BULK_TASK_STATUS_COMPLETED,
    SMS_BULK_TASK_STATUS_DRAFT,
    SMS_BULK_TASK_STATUS_PAUSED,
    SMS_BULK_TASK_STATUS_SCHEDULED,
    SMS_BULK_TASK_STATUS_SENDING,
    SMS_BULK_PAUSE_REASON_MANUAL,
    SmsBulkTask,
)
from app.repositories.sms_bulk_task_repository import SmsBulkTargetRepository, SmsBulkTaskRepository
from app.repositories.sms_repository import SmsTemplateGrantRepository
from app.schemas.permission import EffectivePrincipal
from app.schemas.sms_bulk_task import (
    SmsBulkTaskCreate,
    SmsBulkTaskStats,
    SmsBulkTaskUpdate,
    SmsBulkTargetCreate,
)
from app.services.sms_service import _render_body_snapshot, _validate_variables

MANAGE_PERMISSION = "engagement.sms_task.manage"
CREATE_PERMISSION = "engagement.sms_task.create"

EDITABLE_STATUSES = {
    SMS_BULK_TASK_STATUS_DRAFT,
    SMS_BULK_TASK_STATUS_SCHEDULED,
    SMS_BULK_TASK_STATUS_PAUSED,
}
TARGET_MUTABLE_STATUSES = {SMS_BULK_TASK_STATUS_DRAFT, SMS_BULK_TASK_STATUS_PAUSED}
RESEND_ALLOWED_STATUSES = {
    SMS_BULK_TASK_STATUS_SENDING,
    SMS_BULK_TASK_STATUS_PAUSED,
    SMS_BULK_TASK_STATUS_COMPLETED,
}


def _pages(total: int, per_page: int) -> int:
    return (total + per_page - 1) // per_page if total else 0


def _shape_stats(raw: dict[str, int]) -> SmsBulkTaskStats:
    """Aggregate raw status counts; pending covers claimed-but-unsubmitted rows."""
    return SmsBulkTaskStats(
        total=sum(raw.values()),
        pending=raw.get("pending", 0) + raw.get("sending", 0),
        submitted=raw.get("submitted", 0),
        delivered=raw.get("delivered", 0),
        failed=raw.get("failed", 0),
    )


def _task_response(task: SmsBulkTask, created_by_name: str | None) -> dict:
    return {
        "id": task.id,
        "name": task.name,
        "description": task.description,
        "status": task.status,
        "send_type": task.send_type,
        "scheduled_at": task.scheduled_at,
        "template_id": task.template_id,
        "template_name": task.template_name,
        "template_type": task.template_type,
        "sign_name": task.sign_name,
        "body": task.body,
        "variables": task.variables or [],
        "pause_reason": task.pause_reason,
        "published_at": task.published_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "created_by_id": task.created_by_id,
        "created_by_name": created_by_name,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _target_response(target) -> dict:
    return {
        "id": target.id,
        "phone": target.phone,
        "variable_values": target.variable_values or {},
        "status": target.status,
        "fail_reason": target.fail_reason,
        "submitted_at": target.submitted_at,
        "delivered_at": target.delivered_at,
        "created_at": target.created_at,
    }


class SmsBulkTaskService:
    @staticmethod
    def _can_manage_task(principal: EffectivePrincipal, task: SmsBulkTask) -> bool:
        return principal.has_permission(MANAGE_PERMISSION) or (
            principal.has_permission(CREATE_PERMISSION) and task.created_by_id == principal.user_id
        )

    @staticmethod
    def _assert_can_manage_task(principal: EffectivePrincipal, task: SmsBulkTask) -> None:
        if not SmsBulkTaskService._can_manage_task(principal, task):
            raise NotFoundError("Bulk SMS task not found")

    @staticmethod
    def _assert_entry_permission(principal: EffectivePrincipal) -> None:
        if not (principal.has_permission(MANAGE_PERMISSION) or principal.has_permission(CREATE_PERMISSION)):
            raise ForbiddenError("Permission denied")

    @staticmethod
    async def _get_task(db: AsyncSession, principal: EffectivePrincipal, task_id: int) -> SmsBulkTask:
        task = await SmsBulkTaskRepository.get_by_id(db, task_id)
        if task is None or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Bulk SMS task not found")
        return task

    @staticmethod
    async def _get_manageable_task(db: AsyncSession, principal: EffectivePrincipal, task_id: int) -> SmsBulkTask:
        task = await SmsBulkTaskService._get_task(db, principal, task_id)
        SmsBulkTaskService._assert_can_manage_task(principal, task)
        return task

    @staticmethod
    async def _snapshot_template(db: AsyncSession, *, tenant_id: int, template_id: int) -> dict:
        """Load a granted, enabled template and build its frozen snapshot fields."""
        row = await SmsTemplateGrantRepository.get_granted_template(
            db, tenant_id=tenant_id, template_id=template_id
        )
        if row is None:
            raise NotFoundError("Template not found")
        _, template, signature = row
        if template.status != SMS_STATUS_ENABLED:
            raise ValidationError("Template is unavailable")
        return {
            "template_id": template.id,
            "template_name": template.name,
            "template_type": template.type,
            "sign_name": signature.name,
            "provider_sign_name": signature.provider_sign_name,
            "body": template.body,
            "variables": template.variables or [],
            "provider": template.provider,
            "provider_template_code": template.provider_template_code,
        }

    @staticmethod
    def _validate_send_time(send_type: str, scheduled_at: datetime | None) -> None:
        if send_type == SMS_BULK_SEND_TYPE_SCHEDULED:
            if scheduled_at is None:
                raise ValidationError("scheduled_at is required when send_type is scheduled")
            if scheduled_at <= datetime.now(timezone.utc):
                raise ValidationError("Send time must be in the future")

    # ------------------------------------------------------------------
    # Template picker
    # ------------------------------------------------------------------

    @staticmethod
    async def list_available_templates(db: AsyncSession, principal: EffectivePrincipal) -> dict:
        SmsBulkTaskService._assert_entry_permission(principal)
        rows, _ = await SmsTemplateGrantRepository.list_granted_detail_for_tenant_paginated(
            db, tenant_id=principal.tenant_id, page=1, per_page=100, only_enabled=True
        )
        items = [
            {
                "id": template.id,
                "name": template.name,
                "sign_name": signature.name,
                "type": template.type,
                "variables": template.variables or [],
                "body": template.body,
            }
            for _, template, signature in rows
        ]
        return {"items": items}

    # ------------------------------------------------------------------
    # Task CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        principal: EffectivePrincipal,
        *,
        page: int = 1,
        per_page: int = 20,
        q: str | None = None,
        status: str | None = None,
    ) -> dict:
        SmsBulkTaskService._assert_entry_permission(principal)
        created_by_id = None if principal.has_permission(MANAGE_PERMISSION) else principal.user_id
        rows, total = await SmsBulkTaskRepository.list_for_tenant(
            db,
            tenant_id=principal.tenant_id,
            page=page,
            per_page=per_page,
            q=q,
            status=status,
            created_by_id=created_by_id,
        )
        stats_map = await SmsBulkTaskRepository.stats_for_tasks(db, [task.id for task, _ in rows])
        items = [
            {**_task_response(task, employee_name), "stats": _shape_stats(stats_map.get(task.id, {}))}
            for task, employee_name in rows
        ]
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": _pages(total, per_page)}

    @staticmethod
    async def create_task(db: AsyncSession, principal: EffectivePrincipal, data: SmsBulkTaskCreate) -> dict:
        if not principal.has_permission(CREATE_PERMISSION) and not principal.has_permission(MANAGE_PERMISSION):
            raise ForbiddenError("Permission denied")
        SmsBulkTaskService._validate_send_time(data.send_type, data.scheduled_at)
        snapshot = await SmsBulkTaskService._snapshot_template(
            db, tenant_id=principal.tenant_id, template_id=data.template_id
        )
        payload = {
            "tenant_id": principal.tenant_id,
            "name": data.name,
            "description": data.description,
            "status": SMS_BULK_TASK_STATUS_DRAFT,
            "send_type": data.send_type,
            "scheduled_at": data.scheduled_at if data.send_type == SMS_BULK_SEND_TYPE_SCHEDULED else None,
            "created_by_id": principal.user_id,
            "updated_by_id": principal.user_id,
            **snapshot,
        }
        task = await SmsBulkTaskRepository.create(db, payload)
        creator_name = await SmsBulkTaskRepository.get_creator_name(db, task)
        return _task_response(task, creator_name)

    @staticmethod
    async def get_task(db: AsyncSession, principal: EffectivePrincipal, task_id: int) -> dict:
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        stats_map = await SmsBulkTaskRepository.stats_for_tasks(db, [task.id])
        creator_name = await SmsBulkTaskRepository.get_creator_name(db, task)
        return {**_task_response(task, creator_name), "stats": _shape_stats(stats_map.get(task.id, {}))}

    @staticmethod
    async def update_task(
        db: AsyncSession, principal: EffectivePrincipal, task_id: int, data: SmsBulkTaskUpdate
    ) -> dict:
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        if task.status not in EDITABLE_STATUSES:
            raise ValidationError("Task cannot be edited in current status")

        payload: dict = {"updated_by_id": principal.user_id}
        if data.name is not None:
            payload["name"] = data.name
        if data.description is not None:
            payload["description"] = data.description

        next_send_type = data.send_type if data.send_type is not None else task.send_type
        next_scheduled_at = data.scheduled_at if data.scheduled_at is not None else task.scheduled_at
        if data.send_type is not None or data.scheduled_at is not None:
            SmsBulkTaskService._validate_send_time(next_send_type, next_scheduled_at)
            payload["send_type"] = next_send_type
            payload["scheduled_at"] = next_scheduled_at if next_send_type == SMS_BULK_SEND_TYPE_SCHEDULED else None

        if data.template_id is not None and data.template_id != task.template_id:
            if task.status != SMS_BULK_TASK_STATUS_DRAFT:
                raise ValidationError("Template cannot be changed after publish")
            snapshot = await SmsBulkTaskService._snapshot_template(
                db, tenant_id=principal.tenant_id, template_id=data.template_id
            )
            payload.update(snapshot)
            # Template change invalidates existing recipients; clear them.
            await SmsBulkTargetRepository.delete_for_task(db, task.id)

        task = await SmsBulkTaskRepository.update(db, task, payload)
        creator_name = await SmsBulkTaskRepository.get_creator_name(db, task)
        return _task_response(task, creator_name)

    @staticmethod
    async def delete_task(db: AsyncSession, principal: EffectivePrincipal, task_id: int) -> None:
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        if task.status != SMS_BULK_TASK_STATUS_DRAFT:
            raise ValidationError("Only draft tasks can be deleted")
        await SmsBulkTaskRepository.delete(db, task)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    @staticmethod
    async def publish_task(db: AsyncSession, principal: EffectivePrincipal, task_id: int) -> dict:
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        if task.status != SMS_BULK_TASK_STATUS_DRAFT:
            raise ValidationError("Only draft tasks can be published")
        target_count = await SmsBulkTargetRepository.count_for_task(db, task.id)
        if target_count < 1:
            raise ValidationError("Add at least one recipient before publishing")
        if task.send_type == SMS_BULK_SEND_TYPE_SCHEDULED:
            if task.scheduled_at is None or task.scheduled_at <= datetime.now(timezone.utc):
                raise ValidationError("Send time has passed; update it before publishing")
        # Re-validate and refresh the template snapshot at publish time.
        if task.template_id is None:
            raise ValidationError("Template is unavailable")
        snapshot = await SmsBulkTaskService._snapshot_template(
            db, tenant_id=principal.tenant_id, template_id=task.template_id
        )
        now = datetime.now(timezone.utc)
        next_status = (
            SMS_BULK_TASK_STATUS_SENDING
            if task.send_type == SMS_BULK_SEND_TYPE_IMMEDIATE
            else SMS_BULK_TASK_STATUS_SCHEDULED
        )
        task = await SmsBulkTaskRepository.update(
            db,
            task,
            {**snapshot, "status": next_status, "published_at": now, "updated_by_id": principal.user_id},
        )
        creator_name = await SmsBulkTaskRepository.get_creator_name(db, task)
        return _task_response(task, creator_name)

    @staticmethod
    async def pause_task(db: AsyncSession, principal: EffectivePrincipal, task_id: int) -> dict:
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        if task.status not in {SMS_BULK_TASK_STATUS_SCHEDULED, SMS_BULK_TASK_STATUS_SENDING}:
            raise ValidationError("Task cannot be paused in current status")
        task = await SmsBulkTaskRepository.update(
            db,
            task,
            {
                "status": SMS_BULK_TASK_STATUS_PAUSED,
                "pause_reason": SMS_BULK_PAUSE_REASON_MANUAL,
                "updated_by_id": principal.user_id,
            },
        )
        creator_name = await SmsBulkTaskRepository.get_creator_name(db, task)
        return _task_response(task, creator_name)

    @staticmethod
    async def resume_task(db: AsyncSession, principal: EffectivePrincipal, task_id: int) -> dict:
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        if task.status != SMS_BULK_TASK_STATUS_PAUSED:
            raise ValidationError("Task cannot be resumed in current status")
        now = datetime.now(timezone.utc)
        if task.send_type == SMS_BULK_SEND_TYPE_SCHEDULED and task.scheduled_at is not None and task.scheduled_at > now:
            next_status = SMS_BULK_TASK_STATUS_SCHEDULED
        else:
            next_status = SMS_BULK_TASK_STATUS_SENDING
        task = await SmsBulkTaskRepository.update(
            db, task, {"status": next_status, "pause_reason": None, "updated_by_id": principal.user_id}
        )
        creator_name = await SmsBulkTaskRepository.get_creator_name(db, task)
        return _task_response(task, creator_name)

    @staticmethod
    async def archive_task(db: AsyncSession, principal: EffectivePrincipal, task_id: int) -> dict:
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        if task.status not in {
            SMS_BULK_TASK_STATUS_COMPLETED,
            SMS_BULK_TASK_STATUS_PAUSED,
            SMS_BULK_TASK_STATUS_SCHEDULED,
        }:
            raise ValidationError("Task cannot be archived in current status")
        task = await SmsBulkTaskRepository.update(
            db, task, {"status": SMS_BULK_TASK_STATUS_ARCHIVED, "updated_by_id": principal.user_id}
        )
        creator_name = await SmsBulkTaskRepository.get_creator_name(db, task)
        return _task_response(task, creator_name)

    # ------------------------------------------------------------------
    # Targets
    # ------------------------------------------------------------------

    @staticmethod
    async def list_targets(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        *,
        page: int = 1,
        per_page: int = 20,
        q: str | None = None,
        status: str | None = None,
    ) -> dict:
        await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        rows, total = await SmsBulkTargetRepository.list_for_task(
            db, tenant_id=principal.tenant_id, task_id=task_id, page=page, per_page=per_page, q=q, status=status
        )
        items = [_target_response(target) for target in rows]
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": _pages(total, per_page)}

    @staticmethod
    async def get_target(db: AsyncSession, principal: EffectivePrincipal, task_id: int, target_id: int) -> dict:
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        target = await SmsBulkTargetRepository.get_by_id(db, target_id)
        if target is None or target.task_id != task.id:
            raise NotFoundError("Target not found")
        return {
            **_target_response(target),
            "body_rendered": _render_body_snapshot(task.body, target.variable_values or {}),
            "send_record_id": target.send_record_id,
            "provider_biz_id": target.provider_biz_id,
        }

    @staticmethod
    async def create_target(
        db: AsyncSession, principal: EffectivePrincipal, task_id: int, data: SmsBulkTargetCreate
    ) -> dict:
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        if task.status not in TARGET_MUTABLE_STATUSES:
            raise ValidationError("Recipients cannot be modified in current task status")
        params = _validate_variables(task.variables or [], data.variable_values)
        existing = await SmsBulkTargetRepository.get_by_phone(db, task_id=task.id, phone=data.phone)
        if existing is not None:
            raise ConflictError("Phone number already exists in this task")
        target = await SmsBulkTargetRepository.create(
            db,
            {
                "tenant_id": principal.tenant_id,
                "task_id": task.id,
                "phone": data.phone,
                "variable_values": params,
            },
        )
        return _target_response(target)

    @staticmethod
    async def bulk_delete_targets(
        db: AsyncSession, principal: EffectivePrincipal, task_id: int, target_ids: list[int]
    ) -> dict:
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        if task.status not in TARGET_MUTABLE_STATUSES:
            raise ValidationError("Recipients cannot be modified in current task status")
        deleted = await SmsBulkTargetRepository.bulk_delete_pending(db, task_id=task.id, target_ids=target_ids)
        return {"deleted": deleted, "skipped": len(target_ids) - deleted}

    @staticmethod
    async def resend_failed_targets(db: AsyncSession, principal: EffectivePrincipal, task_id: int) -> dict:
        task = await SmsBulkTaskService._get_manageable_task(db, principal, task_id)
        if task.status not in RESEND_ALLOWED_STATUSES:
            raise ValidationError("Failed recipients cannot be resent in current task status")
        reset = await SmsBulkTargetRepository.reset_failed_for_task(db, task.id)
        if reset < 1:
            raise ValidationError("No failed recipients to resend")
        # A completed task reopens so the send engine picks the reset targets up;
        # paused tasks stay paused until manually resumed.
        if task.status == SMS_BULK_TASK_STATUS_COMPLETED:
            await SmsBulkTaskRepository.update(
                db,
                task,
                {
                    "status": SMS_BULK_TASK_STATUS_SENDING,
                    "completed_at": None,
                    "updated_by_id": principal.user_id,
                },
            )
        return {"reset": reset}
