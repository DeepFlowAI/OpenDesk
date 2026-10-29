"""Personal export task orchestration with short database sessions."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.core.exceptions import BusinessError
from app.db.session import AsyncSessionLocal
from app.libs.export_types import available_export_types, get_export_type
from app.repositories.export_task_repository import ExportTaskRepository as Repo
from app.schemas.export_task import ExportTaskCreate, ExportTaskResponse
from app.schemas.permission import EffectivePrincipal
from app.services.permission_service import PermissionService


def export_error(code: str, status: int = 400) -> BusinessError:
    return BusinessError("Export request could not be completed", status_code=status, code=f"EXPORT_{code.upper()}")


def effective_status(task: object, now: datetime) -> str:
    if task.status == "completed" and task.expires_at <= now:
        return "expired"
    return task.status


class ExportTaskService:
    @staticmethod
    async def current(principal: EffectivePrincipal) -> EffectivePrincipal:
        async with AsyncSessionLocal() as db:
            return await PermissionService.get_current_principal(db, {
                "user_id": principal.user_id, "tenant_id": principal.tenant_id,
            })

    @staticmethod
    def response(task: object, principal: EffectivePrincipal, now: datetime) -> ExportTaskResponse:
        kind = get_export_type(task.kind)
        allowed = bool(kind and principal.has_all_permissions(list(kind.permissions)))
        status = effective_status(task, now)
        error_field = None
        if allowed and task.error_code and task.error_code.startswith("cell_limit_"):
            index = task.error_code.removeprefix("cell_limit_")
            fields = task.snapshot.get("config", {}).get("fields", [])
            if index.isdigit() and int(index) < len(fields):
                error_field = fields[int(index)].get("name")
        return ExportTaskResponse(
            id=task.id, kind=task.kind, name=task.name, business_type=task.business_type,
            summary=task.summary if allowed else task.safe_summary, status=status,
            error_code=task.error_code or ("access_changed" if status == "completed" and not allowed else None),
            error_field=error_field,
            row_count=task.row_count if status in ("completed", "expired") else None,
            file_name=task.file_name, file_size=task.file_size, created_at=task.created_at,
            expires_at=task.expires_at if status in ("completed", "expired") else None,
            scope_reduced=task.scope_reduced, can_download=status == "completed" and allowed and task.error_code != "access_changed",
            viewed=task.viewed_at is not None,
        )

    @staticmethod
    async def create(principal: EffectivePrincipal, body: ExportTaskCreate) -> ExportTaskResponse:
        digest = hashlib.sha256(json.dumps(body.model_dump(mode="json", exclude={"idempotency_key"}),
                                          sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        now = datetime.now(timezone.utc)
        # Freeze can query business data or remote metadata; never hold the owner lock over it.
        principal = await ExportTaskService.current(principal)
        async with AsyncSessionLocal() as db:
            previous = await Repo.by_key(db, principal.tenant_id, principal.user_id, body.idempotency_key)
            if previous:
                return ExportTaskService.existing_submission(previous, digest, principal, now)
        kind = get_export_type(body.kind)
        if not kind or not principal.has_all_permissions(list(kind.permissions)):
            raise export_error("permission_lost", 403)
        frozen = await kind.freeze(principal, body.config)
        if body.kind == "ticket" and frozen.config.get("language") != body.language:
            raise export_error("configuration_invalid")
        async with AsyncSessionLocal() as db:
            principal = await PermissionService.get_current_principal(db, {
                "user_id": principal.user_id, "tenant_id": principal.tenant_id,
            })
            # Legacy role resolution may commit; acquire the submission lock after it.
            if not await Repo.lock_owner(db, principal.tenant_id, principal.user_id):
                raise export_error("permission_lost", 403)
            if not principal.has_all_permissions(list(kind.permissions)):
                raise export_error("permission_lost", 403)
            previous = await Repo.by_key(db, principal.tenant_id, principal.user_id, body.idempotency_key)
            if previous:
                return ExportTaskService.existing_submission(previous, digest, principal, now)
            if await Repo.pending_count(db, principal.tenant_id, principal.user_id) >= 5:
                raise export_error("pending_limit", 409)
            task_id = uuid4()
            task = await Repo.add(db, dict(
                id=task_id, tenant_id=principal.tenant_id, employee_id=principal.user_id,
                idempotency_key=body.idempotency_key, request_hash=digest, kind=body.kind,
                name=kind.name, business_type=kind.business_type, summary=frozen.summary,
                safe_summary=frozen.safe_summary, snapshot={"config": frozen.config,
                    "principal": principal.model_dump(mode="json"), "language": body.language,
                    "timezone": body.timezone},
                storage_key=f"exports/{principal.tenant_id}/{principal.user_id}/{task_id}",
                created_at=now, updated_at=now, status="pending",
            ))
            await db.commit()
            return ExportTaskService.response(task, principal, now)

    @staticmethod
    def existing_submission(task: object, digest: str, principal: EffectivePrincipal,
                            now: datetime) -> ExportTaskResponse:
        if task.created_at <= now - timedelta(days=90):
            raise export_error("not_found", 404)
        if task.request_hash != digest:
            raise export_error("idempotency_conflict", 409)
        return ExportTaskService.response(task, principal, now)

    @staticmethod
    async def by_key(principal: EffectivePrincipal, key: UUID) -> ExportTaskResponse:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            task = await Repo.by_key(db, principal.tenant_id, principal.user_id, key)
            if not task or task.created_at <= now - timedelta(days=90):
                raise export_error("not_found", 404)
            return ExportTaskService.response(task, principal, now)

    @staticmethod
    async def status(principal: EffectivePrincipal) -> dict:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            total, unread = await Repo.counts(db, principal.tenant_id, principal.user_id, now)
        return dict(visible=bool(total or available_export_types(principal)), unread=unread, server_time=now)

    @staticmethod
    async def list_tasks(principal: EffectivePrincipal, page: int, per_page: int) -> dict:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            items, total, page = await Repo.page(db, principal.tenant_id, principal.user_id, now, page, per_page)
        if not total and not available_export_types(principal):
            raise export_error("forbidden", 403)
        return dict(items=[ExportTaskService.response(task, principal, now) for task in items],
                    total=total, page=page, per_page=per_page, pages=max(1, (total + per_page - 1) // per_page))

    @staticmethod
    async def cancel(principal: EffectivePrincipal, task_id: UUID) -> ExportTaskResponse:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            task = await Repo.get_owned(db, principal.tenant_id, principal.user_id, task_id, now)
            if not task:
                raise export_error("not_found", 404)
            if task.status == "cancelled":
                return ExportTaskService.response(task, principal, now)
            changed = await Repo.transition(db, task.id, ("pending", "running"),
                                            dict(status="cancelled", completed_at=now))
            await db.commit()
        async with AsyncSessionLocal() as db:
            task = await Repo.get_owned(db, principal.tenant_id, principal.user_id, task_id, now)
            if not task:
                raise export_error("not_found", 404)
            if not changed and task.status != "cancelled":
                raise export_error("already_completed" if task.status == "completed" else "not_cancellable", 409)
            return ExportTaskService.response(task, principal, now)

    @staticmethod
    async def viewed(principal: EffectivePrincipal, ids: list[UUID]) -> None:
        async with AsyncSessionLocal() as db:
            await Repo.mark_viewed(db, principal.tenant_id, principal.user_id, ids, datetime.now(timezone.utc))
            await db.commit()

    @staticmethod
    async def notifications(principal: EffectivePrincipal, since: datetime) -> dict:
        now = datetime.now(timezone.utc)
        # Only live polling can claim recent results; reconnects establish a new baseline.
        since = max(since, now - timedelta(seconds=15))
        async with AsyncSessionLocal() as db:
            items = await Repo.claim_notifications(db, principal.tenant_id, principal.user_id, since, now)
            await db.commit()
        return dict(items=[ExportTaskService.response(task, principal, now) for task in items], server_time=now)
