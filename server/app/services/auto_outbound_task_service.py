"""
Business logic for auto outbound tasks.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.libs.excel import parse_spreadsheet
from app.models.auto_outbound import AutoOutboundTarget, AutoOutboundTask
from app.models.tenant import Tenant
from app.repositories.auto_outbound_repository import AutoOutboundRepository
from app.repositories.employee_group_repository import EmployeeGroupRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.outbound_task_repository import OutboundTaskRepository
from app.repositories.user_repository import UserRepository
from app.repositories.voice_flow_repository import VoiceFlowRepository
from app.schemas.auto_outbound import (
    AutoOutboundAgentContextRecord,
    AutoOutboundAgentContextResponse,
    AutoOutboundMonitorResponse,
    DialCapacityResponse,
    AutoOutboundRecordResponse,
    AutoOutboundTargetCreate,
    AutoOutboundTargetBulkCreateRequest,
    AutoOutboundTargetBulkCreateResponse,
    AutoOutboundTargetImportError,
    AutoOutboundTargetImportResponse,
    AutoOutboundTargetUpdate,
    AutoOutboundTaskCreate,
    AutoOutboundTaskDetailStats,
    AutoOutboundTaskListItem,
    AutoOutboundTaskResponse,
    AutoOutboundTaskStats,
    AutoOutboundTaskUpdate,
    AutoOutboundWrapupRequest,
    DailyTrendPoint,
    TerminalStateDistributionItem,
)
from app.schemas.outbound_task import OutboundTaskField
from app.schemas.permission import EffectivePrincipal
from app.services.call_user_association_service import phone_match_keys
from app.services.auto_outbound_event_service import AutoOutboundEventService

MANAGE_PERMISSION = "engagement.auto_outbound_task.manage"
CREATE_PERMISSION = "engagement.auto_outbound_task.create"
WORKSPACE_PERMISSION = "call.workspace.use"
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

LOCKED_AFTER_START_FIELDS = {
    "execution_mode",
    "voice_flow_id",
    "voice_flow_name",
    "transfer_queue_id",
    "voicespeed_agent_id",
    "voicespeed_agent_name",
    "intent_result_field_key",
    "queue_id",
    "pacing_mode",
    "dial_ratio",
    "dial_intensity",
    "abandon_rate_limit",
    "abandon_prompt",
}
TARGET_MUTATION_ALLOWED_STATUSES = {"draft", "paused", "active"}
AUTO_PAUSE_REASON_QUEUE_FINISHED = "queue_finished"
AUTO_RESUME_REASON_TARGETS_APPENDED = "targets_appended_auto_resume"


def _pages(total: int, per_page: int) -> int:
    return ceil(total / per_page) if total else 0


def _dump_fields(fields: list[Any] | None) -> list[dict]:
    return [field.model_dump(mode="json") if hasattr(field, "model_dump") else field for field in (fields or [])]


def _restore_task_orm_types(
    payload: dict,
    data: AutoOutboundTaskCreate | AutoOutboundTaskUpdate,
) -> None:
    """
    model_dump(mode="json") turns date/Decimal into JSON-safe scalars.
    Restore Python types for DATE/NUMERIC columns before ORM writes.
    Only keys present in payload are restored (create dumps all; update uses exclude_unset).
    JSONB fields (daily_time_windows, retry_policy) stay as json-compatible dicts.
    """
    if "start_date" in payload:
        payload["start_date"] = data.start_date
    if "end_date" in payload:
        payload["end_date"] = data.end_date
    if "dial_intensity" in payload:
        payload["dial_intensity"] = data.dial_intensity
    if "abandon_rate_limit" in payload:
        payload["abandon_rate_limit"] = data.abandon_rate_limit


def _values_equal(left: Any, right: Any) -> bool:
    """Compare locked-field values with Decimal/None/str normalization."""
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    if isinstance(left, Decimal) or isinstance(right, Decimal):
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except (InvalidOperation, ValueError):
            return False
    if isinstance(left, str) or isinstance(right, str):
        return str(left).strip() == str(right).strip()
    return left == right


def _normalize_import_header(value: str) -> str:
    return value.strip().lower().replace(" ", "").replace("_", "")


def _field_attr(field: Any, key: str, default: Any = None) -> Any:
    if isinstance(field, dict):
        return field.get(key, default)
    return getattr(field, key, default)


def _parse_hhmm(value: str) -> tuple[int, int] | None:
    parts = str(value or "").strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def is_out_of_daily_window(
    daily_time_windows: list[dict] | list[Any] | None,
    *,
    now: datetime | None = None,
) -> bool:
    """
    Return True when `now` (server local clock) falls outside all configured
    daily call windows. Reused by the dial engine for schedule gating.
    """
    current = now or datetime.now().astimezone()
    windows = daily_time_windows or []
    if not windows:
        return True

    current_minutes = current.hour * 60 + current.minute
    for window in windows:
        if isinstance(window, dict):
            start_raw = window.get("start")
            end_raw = window.get("end")
        else:
            start_raw = getattr(window, "start", None)
            end_raw = getattr(window, "end", None)
        start = _parse_hhmm(str(start_raw or ""))
        end = _parse_hhmm(str(end_raw or ""))
        if start is None or end is None:
            continue
        start_minutes = start[0] * 60 + start[1]
        end_minutes = end[0] * 60 + end[1]
        if start_minutes <= current_minutes < end_minutes:
            return False
    return True


def reception_target_name(task: AutoOutboundTask) -> str | None:
    """Return cached reception display name from ORM columns (agent mode has none)."""
    if task.execution_mode == "ivr":
        return task.voice_flow_name
    if task.execution_mode == "bot":
        return task.voicespeed_agent_name
    return None


class AutoOutboundTaskService:
    @staticmethod
    def _can_manage_task(principal: EffectivePrincipal, task: AutoOutboundTask) -> bool:
        return principal.has_permission(MANAGE_PERMISSION) or (
            principal.has_permission(CREATE_PERMISSION) and task.created_by_id == principal.user_id
        )

    @staticmethod
    def _assert_can_manage_task(principal: EffectivePrincipal, task: AutoOutboundTask) -> None:
        if not AutoOutboundTaskService._can_manage_task(principal, task):
            raise NotFoundError("Auto outbound task not found")

    @staticmethod
    def _assert_can_view_list(principal: EffectivePrincipal) -> None:
        if not (
            principal.has_permission(MANAGE_PERMISSION) or principal.has_permission(CREATE_PERMISSION)
        ):
            raise ForbiddenError("Permission denied")

    @staticmethod
    def _assert_workspace_use(principal: EffectivePrincipal) -> None:
        if not principal.has_permission(WORKSPACE_PERMISSION):
            raise ForbiddenError("Permission denied")

    @staticmethod
    def _wrapup_open_for_context(reception_result: Any) -> bool:
        """True for agent-context phone fallback: wrap-up not yet completed."""
        if not reception_result or not isinstance(reception_result, dict):
            return True
        if reception_result.get("auto_submitted") is True:
            return False
        if reception_result.get("submitted_by") is not None:
            return False
        if "field_values" in reception_result and reception_result.get("auto_submitted") is False:
            return False
        return True

    @staticmethod
    async def _assert_caller_number_available(
        db: AsyncSession,
        tenant_id: int,
        caller_number_id: str | None,
    ) -> None:
        """
        Validate that the selected caller number is enabled for outbound and
        belongs to the caller's tenant (global numbers with null tenant are ok).
        """
        if not caller_number_id:
            raise ValidationError("Caller number is disabled or not allowed for outbound")
        # Soft check: prefer PhoneNumber when the model is importable.
        try:
            from app.models.phone_number import PhoneNumber
        except Exception:  # pragma: no cover - defensive
            return

        number = await db.get(PhoneNumber, caller_number_id)
        if number is None:
            raise ValidationError("Caller number is disabled or not allowed for outbound")
        call_types = number.call_types or []
        if isinstance(call_types, list) and call_types and "outbound" not in call_types:
            raise ValidationError("Caller number is disabled or not allowed for outbound")
        if number.status == "disabled":
            raise ValidationError("Caller number is disabled or not allowed for outbound")
        # PhoneNumber.tenant_id stores the string tenant code (FK tenants.tenant_id).
        if number.tenant_id is not None:
            tenant = await db.get(Tenant, tenant_id)
            if tenant is None or number.tenant_id != tenant.tenant_id:
                raise ValidationError("Caller number is disabled or not allowed for outbound")

    @staticmethod
    async def _assert_voice_flow(
        db: AsyncSession,
        tenant_id: int,
        voice_flow_id: int | None,
    ) -> None:
        if voice_flow_id is None:
            return
        flow = await VoiceFlowRepository.get_by_id(db, voice_flow_id, tenant_id)
        if flow is None:
            raise ValidationError("Voice flow not found")

    @staticmethod
    async def _assert_queue_exists(
        db: AsyncSession,
        tenant_id: int,
        queue_id: int | None,
        *,
        label: str = "Queue",
    ) -> None:
        if queue_id is None:
            return
        group = await EmployeeGroupRepository.get_by_id(db, queue_id)
        if group is None or group.tenant_id != tenant_id:
            raise ValidationError(f"{label} not found")

    @staticmethod
    async def _assert_reception_refs(
        db: AsyncSession,
        tenant_id: int,
        *,
        voice_flow_id: int | None = None,
        queue_id: int | None = None,
        transfer_queue_id: int | None = None,
    ) -> None:
        await AutoOutboundTaskService._assert_voice_flow(db, tenant_id, voice_flow_id)
        await AutoOutboundTaskService._assert_queue_exists(db, tenant_id, queue_id, label="Queue")
        await AutoOutboundTaskService._assert_queue_exists(
            db, tenant_id, transfer_queue_id, label="Transfer queue"
        )

    @staticmethod
    async def _voicespeed_agent_name_map(
        db: AsyncSession,
        tenant_id: int,
    ) -> dict[str, str]:
        """Best-effort VoiceSpeed agent id→name map; empty when unavailable."""
        try:
            from app.services.open_agent_settings_service import OpenAgentSettingsService

            result = await OpenAgentSettingsService.list_voice_speed_agents(db, tenant_id)
        except Exception:  # noqa: BLE001 — display names must not fail the request
            return {}
        return {item.id: item.name for item in result.items if item.id and item.name}

    @staticmethod
    async def _lookup_voicespeed_agent_name(
        db: AsyncSession,
        tenant_id: int,
        agent_id: str,
    ) -> str | None:
        names = await AutoOutboundTaskService._voicespeed_agent_name_map(db, tenant_id)
        return names.get(agent_id)

    @staticmethod
    async def _fill_reception_target_names(
        db: AsyncSession,
        tenant_id: int,
        payload: dict,
        *,
        execution_mode: str,
    ) -> None:
        """Persist display names for ivr/bot reception targets when the client omits them."""
        if execution_mode == "ivr":
            voice_flow_id = payload.get("voice_flow_id")
            if voice_flow_id is None or payload.get("voice_flow_name"):
                return
            flow = await VoiceFlowRepository.get_by_id(db, voice_flow_id, tenant_id)
            if flow is not None and flow.name:
                payload["voice_flow_name"] = flow.name
            return
        if execution_mode == "bot":
            agent_id = payload.get("voicespeed_agent_id")
            if not agent_id or payload.get("voicespeed_agent_name"):
                return
            name = await AutoOutboundTaskService._lookup_voicespeed_agent_name(
                db, tenant_id, str(agent_id)
            )
            if name:
                payload["voicespeed_agent_name"] = name

    @staticmethod
    async def _resolve_reception_target_names(
        db: AsyncSession,
        tenant_id: int,
        tasks: list[AutoOutboundTask],
    ) -> dict[int, str | None]:
        """
        Resolve reception_target_name for list/detail responses.

        ivr → voice_flow_name (DB backfill by voice_flow_id when missing)
        bot → voicespeed_agent_name (VoiceSpeed backfill by id when missing)
        agent → employee group / queue name by queue_id
        """
        if not tasks:
            return {}

        flow_cache: dict[int, str | None] = {}
        queue_cache: dict[int, str | None] = {}
        vs_names: dict[str, str] | None = None

        async def flow_name(flow_id: int) -> str | None:
            if flow_id not in flow_cache:
                flow = await VoiceFlowRepository.get_by_id(db, flow_id, tenant_id)
                flow_cache[flow_id] = flow.name if flow is not None and flow.name else None
            return flow_cache[flow_id]

        async def queue_name(queue_id: int) -> str | None:
            if queue_id not in queue_cache:
                group = await EmployeeGroupRepository.get_by_id(db, queue_id)
                if group is not None and group.tenant_id == tenant_id and group.name:
                    queue_cache[queue_id] = group.name
                else:
                    queue_cache[queue_id] = None
            return queue_cache[queue_id]

        async def voicespeed_name(agent_id: str) -> str | None:
            nonlocal vs_names
            if vs_names is None:
                vs_names = await AutoOutboundTaskService._voicespeed_agent_name_map(db, tenant_id)
            return vs_names.get(agent_id)

        resolved: dict[int, str | None] = {}
        for task in tasks:
            if task.execution_mode == "ivr":
                name = task.voice_flow_name
                if not name and task.voice_flow_id is not None:
                    name = await flow_name(task.voice_flow_id)
                resolved[task.id] = name or None
            elif task.execution_mode == "bot":
                name = task.voicespeed_agent_name
                if not name and task.voicespeed_agent_id:
                    name = await voicespeed_name(task.voicespeed_agent_id)
                resolved[task.id] = name or None
            elif task.execution_mode == "agent":
                name = None
                if task.queue_id is not None:
                    name = await queue_name(task.queue_id)
                resolved[task.id] = name
            else:
                resolved[task.id] = None
        return resolved

    @staticmethod
    def _assert_task_allows_target_mutation(task: AutoOutboundTask) -> None:
        if task.status == "archived":
            raise ValidationError("Archived tasks cannot accept new targets")
        if task.status == "completed":
            raise ValidationError("Completed tasks cannot accept new targets")
        if task.status not in TARGET_MUTATION_ALLOWED_STATUSES:
            raise ValidationError(
                "Targets can only be added when the task is draft, paused, or active"
            )

    @staticmethod
    async def _maybe_auto_resume_after_target_append(
        db: AsyncSession,
        task_id: int,
        *,
        locked_task: AutoOutboundTask | None = None,
    ) -> bool:
        """Resume a queue-finished task once, after at least one dialable target exists."""
        task = locked_task or await AutoOutboundRepository.get_task_for_update(
            db, task_id
        )
        if (
            task is None
            or task.status != "paused"
            or task.auto_pause_reason != AUTO_PAUSE_REASON_QUEUE_FINISHED
            or not bool(task.auto_resume_on_target_append)
        ):
            return False

        from app.services.auto_outbound.tenant_time import resolve_tenant_timezone

        now = datetime.now(timezone.utc)
        tenant_timezone = await resolve_tenant_timezone(db, task.tenant_id)
        if task.end_date < now.astimezone(tenant_timezone).date():
            calling = await AutoOutboundRepository.count_targets_by_status(
                db, task.id, statuses=["calling"]
            )
            if calling == 0:
                updated = await AutoOutboundRepository.update_task(
                    db,
                    task,
                    {
                        "status": "completed",
                        "completed_at": now,
                    },
                    commit=False,
                )
                await AutoOutboundEventService.emit_task_event(
                    db,
                    task=updated,
                    event_type="auto_outbound.task.completed",
                    occurred_at=now,
                    actor={"type": "system"},
                    previous_status="paused",
                    reason="schedule_ended",
                )
            return False

        dialable = await AutoOutboundRepository.count_targets_by_status(
            db, task.id, statuses=["pending", "redial_pending"]
        )
        if dialable == 0:
            return False

        updated = await AutoOutboundRepository.update_task(
            db,
            task,
            {
                "status": "active",
                "auto_pause_reason": None,
            },
            commit=False,
        )
        await AutoOutboundEventService.emit_task_event(
            db,
            task=updated,
            event_type="auto_outbound.task.resumed",
            occurred_at=now,
            actor={"type": "system"},
            previous_status="paused",
            reason=AUTO_RESUME_REASON_TARGETS_APPENDED,
        )
        return True

    @staticmethod
    async def _lock_task_for_target_append(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
    ) -> AutoOutboundTask:
        task = await AutoOutboundRepository.get_task_for_update(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        AutoOutboundTaskService._assert_task_allows_target_mutation(task)
        return task

    @staticmethod
    async def _sanitize_user_ids(
        db: AsyncSession,
        tenant_id: int,
        user_ids: list[int | None],
    ) -> set[int]:
        """Return the subset of user_ids that exist in this tenant (one IN query)."""
        ids = sorted({user_id for user_id in user_ids if user_id is not None})
        if not ids:
            return set()
        users = await UserRepository.list_by_ids(db, tenant_id, ids)
        return {user.id for user in users}

    @staticmethod
    async def _owner_names(db: AsyncSession, owner_ids: list[int | None]) -> dict[int, str]:
        ids = sorted({owner_id for owner_id in owner_ids if owner_id is not None})
        if not ids:
            return {}
        employees = await EmployeeRepository.get_by_ids(db, ids)
        return {employee.id: employee.name for employee in employees if employee.name}

    @staticmethod
    def _answer_rate(call_count: int, answered_count: int) -> float | None:
        if call_count <= 0:
            return None
        return answered_count / call_count

    @staticmethod
    def _abandon_rate(answered_count: int, abandon_count: int) -> float | None:
        if answered_count <= 0:
            return None
        return abandon_count / answered_count

    @staticmethod
    async def _current_concurrency(task_id: int) -> int | None:
        """Redis in-flight count; None when Redis is unavailable."""
        try:
            from app.services.auto_outbound import frequency as freq

            return await freq.get_concurrency(task_id)
        except Exception:  # noqa: BLE001 — stats must not fail when Redis is down
            return None

    @staticmethod
    async def _build_task_stats(task_id: int, stats: dict | None) -> AutoOutboundTaskStats:
        stats = stats or {}
        call_count = int(stats.get("call_count", 0))
        answered_count = int(stats.get("answered_count", 0))
        abandon_count = int(stats.get("abandon_count", 0))
        answer_rate = stats.get("answer_rate")
        if answer_rate is None:
            answer_rate = AutoOutboundTaskService._answer_rate(call_count, answered_count)
        return AutoOutboundTaskStats(
            total_targets=int(stats.get("total_targets", 0)),
            finished_targets=int(stats.get("finished_targets", 0)),
            call_count=call_count,
            answered_count=answered_count,
            answer_rate=answer_rate,
            transfer_count=int(stats.get("transfer_count", 0)),
            abandon_count=abandon_count,
            abandon_rate=AutoOutboundTaskService._abandon_rate(answered_count, abandon_count),
            current_concurrency=await AutoOutboundTaskService._current_concurrency(task_id),
        )

    @staticmethod
    def _to_list_item(
        task: AutoOutboundTask,
        stats: dict,
        owner_name: str | None,
        target_name: str | None,
    ) -> AutoOutboundTaskListItem:
        call_count = int(stats.get("call_count", 0))
        answered_count = int(stats.get("answered_count", 0))
        return AutoOutboundTaskListItem(
            id=task.id,
            name=task.name,
            execution_mode=task.execution_mode,  # type: ignore[arg-type]
            reception_target_name=target_name,
            status=task.status,  # type: ignore[arg-type]
            out_of_window=is_out_of_daily_window(task.daily_time_windows),
            auto_pause_reason=task.auto_pause_reason,
            owner_name=owner_name,
            total_targets=int(stats.get("total_targets", 0)),
            finished_targets=int(stats.get("finished_targets", 0)),
            call_count=call_count,
            answered_count=answered_count,
            answer_rate=AutoOutboundTaskService._answer_rate(call_count, answered_count),
            updated_at=task.updated_at,
        )

    @staticmethod
    async def _to_response(
        db: AsyncSession,
        task: AutoOutboundTask,
        stats: dict | None = None,
    ) -> AutoOutboundTaskResponse:
        owner_names = await AutoOutboundTaskService._owner_names(db, [task.owner_id])
        target_names = await AutoOutboundTaskService._resolve_reception_target_names(
            db, task.tenant_id, [task]
        )
        target_name = target_names.get(task.id)
        response = AutoOutboundTaskResponse.model_validate(task)
        response.out_of_window = is_out_of_daily_window(task.daily_time_windows)
        response.owner_name = owner_names.get(task.owner_id) if task.owner_id else None
        response.reception_target_name = target_name
        # Surface resolved names on detail even when ORM columns were never backfilled.
        if task.execution_mode == "ivr" and not response.voice_flow_name and target_name:
            response.voice_flow_name = target_name
        elif task.execution_mode == "bot" and not response.voicespeed_agent_name and target_name:
            response.voicespeed_agent_name = target_name
        response.stats = await AutoOutboundTaskService._build_task_stats(task.id, stats)
        return response

    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        principal: EffectivePrincipal,
        page: int,
        page_size: int,
        q: str | None = None,
        status: str | None = None,
        mode: str | None = None,
    ) -> dict:
        AutoOutboundTaskService._assert_can_view_list(principal)
        creator_id = None if principal.has_permission(MANAGE_PERMISSION) else principal.user_id
        items, total = await AutoOutboundRepository.list_tasks(
            db,
            principal.tenant_id,
            page,
            page_size,
            q=q,
            status=status,
            mode=mode,
            creator_id=creator_id,
        )
        stats_by_task = await AutoOutboundRepository.task_stats(
            db, principal.tenant_id, [task.id for task in items]
        )
        owner_names = await AutoOutboundTaskService._owner_names(db, [task.owner_id for task in items])
        target_names = await AutoOutboundTaskService._resolve_reception_target_names(
            db, principal.tenant_id, items
        )
        list_items = [
            AutoOutboundTaskService._to_list_item(
                task,
                stats_by_task.get(task.id, {}),
                owner_names.get(task.owner_id) if task.owner_id else None,
                target_names.get(task.id),
            )
            for task in items
        ]
        return {
            "items": list_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": _pages(total, page_size),
        }

    @staticmethod
    async def get_task(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
    ) -> AutoOutboundTaskResponse:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        stats = (await AutoOutboundRepository.task_stats(db, principal.tenant_id, [task.id])).get(task.id, {})
        return await AutoOutboundTaskService._to_response(db, task, stats)

    @staticmethod
    async def create_task(
        db: AsyncSession,
        principal: EffectivePrincipal,
        data: AutoOutboundTaskCreate,
    ) -> AutoOutboundTaskResponse:
        if not principal.has_permission(CREATE_PERMISSION):
            raise ForbiddenError("Permission denied")
        template = await OutboundTaskRepository.get_template(db, data.template_id)
        if not template or template.tenant_id != principal.tenant_id:
            raise NotFoundError("Outbound task template not found")

        await AutoOutboundTaskService._assert_reception_refs(
            db,
            principal.tenant_id,
            voice_flow_id=data.voice_flow_id,
            queue_id=data.queue_id,
            transfer_queue_id=data.transfer_queue_id,
        )

        payload = data.model_dump(mode="json", exclude={"fields", "template_id"})
        _restore_task_orm_types(payload, data)
        payload["tenant_id"] = principal.tenant_id
        payload["template_id"] = data.template_id
        payload["template_name"] = template.name
        payload["fields"] = _dump_fields(data.fields) if data.fields is not None else deepcopy(list(template.fields or []))
        payload["created_by_id"] = principal.user_id
        payload["updated_by_id"] = principal.user_id
        payload["owner_id"] = payload.get("owner_id") or principal.user_id
        payload["status"] = "draft"
        await AutoOutboundTaskService._fill_reception_target_names(
            db,
            principal.tenant_id,
            payload,
            execution_mode=str(payload.get("execution_mode") or data.execution_mode),
        )
        task = await AutoOutboundRepository.create_task(db, payload)
        return await AutoOutboundTaskService._to_response(db, task, {})

    @staticmethod
    def _merged_update_payload(task: AutoOutboundTask, data: AutoOutboundTaskUpdate) -> dict:
        payload = data.model_dump(mode="json", exclude_unset=True, exclude={"fields"})
        _restore_task_orm_types(payload, data)
        if data.fields is not None:
            payload["fields"] = _dump_fields(data.fields)

        if task.status in {"completed", "archived"}:
            raise ValidationError("Task cannot be edited in the current status")
        if task.status != "draft":
            # Reject only when a locked field's value actually changes; identical values are ignored.
            for key in list(payload.keys()):
                if key not in LOCKED_AFTER_START_FIELDS:
                    continue
                current = getattr(task, key, None)
                if _values_equal(payload[key], current):
                    del payload[key]
                else:
                    raise ValidationError(
                        "Execution mode and reception target cannot be changed after start"
                    )

        # Validate merged reception config when mode-related fields change.
        merged = {
            "execution_mode": payload.get("execution_mode", task.execution_mode),
            "voice_flow_id": payload.get("voice_flow_id", task.voice_flow_id),
            "voicespeed_agent_id": payload.get("voicespeed_agent_id", task.voicespeed_agent_id),
            "transfer_queue_id": payload.get("transfer_queue_id", task.transfer_queue_id),
            "queue_id": payload.get("queue_id", task.queue_id),
            "pacing_mode": payload.get("pacing_mode", task.pacing_mode),
            "dial_ratio": payload.get("dial_ratio", task.dial_ratio),
            "dial_intensity": payload.get("dial_intensity", task.dial_intensity),
            "abandon_rate_limit": payload.get("abandon_rate_limit", task.abandon_rate_limit),
            "abandon_prompt": payload.get("abandon_prompt", task.abandon_prompt),
            "wrapup_seconds": payload.get("wrapup_seconds", task.wrapup_seconds),
            "start_date": payload.get("start_date", task.start_date),
            "end_date": payload.get("end_date", task.end_date),
            "daily_time_windows": payload.get("daily_time_windows", task.daily_time_windows),
            "max_concurrency": payload.get("max_concurrency", task.max_concurrency),
            "daily_per_number_limit": payload.get("daily_per_number_limit", task.daily_per_number_limit),
            "auto_resume_on_target_append": payload.get(
                "auto_resume_on_target_append", task.auto_resume_on_target_append
            ),
            "name": payload.get("name", task.name),
            "retry_policy": payload.get("retry_policy", task.retry_policy or {}),
        }
        AutoOutboundTaskCreate.model_validate(
            {
                **merged,
                "template_id": task.template_id or 0,
            }
        )
        return payload

    @staticmethod
    async def update_task(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        data: AutoOutboundTaskUpdate,
    ) -> AutoOutboundTaskResponse:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        if task.status == "archived":
            raise ValidationError("Archived tasks cannot be edited")
        payload = AutoOutboundTaskService._merged_update_payload(task, data)
        enable_auto_resume = bool(
            payload.get("auto_resume_on_target_append")
            and not bool(task.auto_resume_on_target_append)
        )
        changed_fields = AutoOutboundEventService.changed_task_fields(task, payload)
        if not changed_fields:
            stats = (
                await AutoOutboundRepository.task_stats(
                    db, principal.tenant_id, [task.id]
                )
            ).get(task.id, {})
            return await AutoOutboundTaskService._to_response(db, task, stats)
        await AutoOutboundTaskService._assert_reception_refs(
            db,
            principal.tenant_id,
            voice_flow_id=payload.get("voice_flow_id") if "voice_flow_id" in payload else None,
            queue_id=payload.get("queue_id") if "queue_id" in payload else None,
            transfer_queue_id=(
                payload.get("transfer_queue_id") if "transfer_queue_id" in payload else None
            ),
        )
        execution_mode = str(payload.get("execution_mode") or task.execution_mode)
        # When reception ids change (or mode switches), refresh persisted display names.
        if (
            "voice_flow_id" in payload
            or "voicespeed_agent_id" in payload
            or "execution_mode" in payload
        ):
            await AutoOutboundTaskService._fill_reception_target_names(
                db,
                principal.tenant_id,
                payload,
                execution_mode=execution_mode,
            )
        payload["updated_by_id"] = principal.user_id
        now = datetime.now(timezone.utc)
        updated = await AutoOutboundRepository.update_task(
            db, task, payload, commit=False
        )
        await AutoOutboundEventService.emit_task_event(
            db,
            task=updated,
            event_type="auto_outbound.task.updated",
            occurred_at=now,
            principal=principal,
            changed_fields=changed_fields,
        )
        if enable_auto_resume:
            await AutoOutboundTaskService._maybe_auto_resume_after_target_append(
                db, task.id
            )
        await db.commit()
        stats = (await AutoOutboundRepository.task_stats(db, principal.tenant_id, [updated.id])).get(updated.id, {})
        return await AutoOutboundTaskService._to_response(db, updated, stats)

    @staticmethod
    async def start_task(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
    ) -> AutoOutboundTaskResponse:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        if task.status == "completed":
            raise ValidationError("This task has ended and cannot be resumed")
        if task.status not in {"draft", "paused"}:
            raise ValidationError("Only draft or paused tasks can be started")
        if task.status == "paused":
            # Resume requires at least one dialable target (pending / redial_pending);
            # a queue-finished auto-paused task must be appended with numbers first.
            resumable = await AutoOutboundRepository.count_targets_by_status(
                db, task.id, statuses=["pending", "redial_pending"]
            )
            if resumable == 0:
                raise ValidationError("Add pending numbers before resuming the task")
        elif await AutoOutboundRepository.count_targets(db, principal.tenant_id, task.id) == 0:
            raise ValidationError("Please import outbound targets before starting the task")
        # Re-validate config completeness via create schema rules.
        AutoOutboundTaskCreate.model_validate(
            {
                "name": task.name,
                "description": task.description,
                "owner_id": task.owner_id,
                "template_id": task.template_id or 0,
                "execution_mode": task.execution_mode,
                "voice_flow_id": task.voice_flow_id,
                "voice_flow_name": task.voice_flow_name,
                "transfer_queue_id": task.transfer_queue_id,
                "voicespeed_agent_id": task.voicespeed_agent_id,
                "voicespeed_agent_name": task.voicespeed_agent_name,
                "intent_result_field_key": task.intent_result_field_key,
                "queue_id": task.queue_id,
                "pacing_mode": task.pacing_mode,
                "dial_ratio": task.dial_ratio,
                "dial_intensity": task.dial_intensity,
                "abandon_rate_limit": task.abandon_rate_limit,
                "abandon_prompt": task.abandon_prompt,
                "wrapup_seconds": task.wrapup_seconds,
                "start_date": task.start_date,
                "end_date": task.end_date,
                "daily_time_windows": task.daily_time_windows or [],
                "caller_number_id": task.caller_number_id,
                "max_concurrency": task.max_concurrency,
                "retry_policy": task.retry_policy or {},
                "daily_per_number_limit": task.daily_per_number_limit,
                "auto_resume_on_target_append": task.auto_resume_on_target_append,
            }
        )
        await AutoOutboundTaskService._assert_caller_number_available(
            db, principal.tenant_id, task.caller_number_id
        )
        await AutoOutboundTaskService._assert_reception_refs(
            db,
            principal.tenant_id,
            voice_flow_id=task.voice_flow_id,
            queue_id=task.queue_id,
            transfer_queue_id=task.transfer_queue_id,
        )
        previous_status = task.status
        now = datetime.now(timezone.utc)
        updated = await AutoOutboundRepository.update_task(
            db,
            task,
            {
                "status": "active",
                "started_at": task.started_at or now,
                "auto_pause_reason": None,
                "updated_by_id": principal.user_id,
            },
            commit=False,
        )
        await AutoOutboundEventService.emit_task_event(
            db,
            task=updated,
            event_type=(
                "auto_outbound.task.started"
                if previous_status == "draft"
                else "auto_outbound.task.resumed"
            ),
            occurred_at=now,
            principal=principal,
            previous_status=previous_status,
        )
        await db.commit()
        stats = (await AutoOutboundRepository.task_stats(db, principal.tenant_id, [updated.id])).get(updated.id, {})
        return await AutoOutboundTaskService._to_response(db, updated, stats)

    @staticmethod
    async def pause_task(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
    ) -> AutoOutboundTaskResponse:
        return await AutoOutboundTaskService._transition(db, principal, task_id, "pause")

    @staticmethod
    async def resume_task(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
    ) -> AutoOutboundTaskResponse:
        # Resume reuses start validations for caller number availability.
        return await AutoOutboundTaskService.start_task(db, principal, task_id)

    @staticmethod
    async def archive_task(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
    ) -> AutoOutboundTaskResponse:
        return await AutoOutboundTaskService._transition(db, principal, task_id, "archive")

    @staticmethod
    async def _transition(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        action: str,
    ) -> AutoOutboundTaskResponse:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)

        if action == "pause":
            if task.status != "active":
                raise ValidationError("Only active tasks can be paused")
            next_status = "paused"
        elif action == "archive":
            if task.status not in {"paused", "completed", "active"}:
                raise ValidationError("Only active, paused, or completed tasks can be archived")
            next_status = "archived"
        else:
            raise ValidationError("Unknown action")

        previous_status = task.status
        now = datetime.now(timezone.utc)
        updated = await AutoOutboundRepository.update_task(
            db,
            task,
            {
                "status": next_status,
                "auto_pause_reason": None if action == "pause" else task.auto_pause_reason,
                "updated_by_id": principal.user_id,
            },
            commit=False,
        )
        await AutoOutboundEventService.emit_task_event(
            db,
            task=updated,
            event_type=(
                "auto_outbound.task.paused"
                if action == "pause"
                else "auto_outbound.task.archived"
            ),
            occurred_at=now,
            principal=principal,
            previous_status=previous_status,
            reason="manual" if action == "pause" else None,
        )
        await db.commit()
        stats = (await AutoOutboundRepository.task_stats(db, principal.tenant_id, [updated.id])).get(updated.id, {})
        return await AutoOutboundTaskService._to_response(db, updated, stats)

    @staticmethod
    async def delete_task(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
    ) -> None:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        if task.status != "draft":
            raise ValidationError("Only draft tasks can be deleted")
        now = datetime.now(timezone.utc)
        await AutoOutboundEventService.emit_task_event(
            db,
            task=task,
            event_type="auto_outbound.task.deleted",
            occurred_at=now,
            principal=principal,
            previous_status=task.status,
        )
        await AutoOutboundRepository.delete_task(db, task, commit=False)
        await db.commit()

    @staticmethod
    def _build_result_distribution(task: AutoOutboundTask, records: list) -> dict[str, Any]:
        if task.execution_mode == "ivr":
            exits: dict[str, int] = {}
            collected_keys: dict[str, dict[str, int]] = {}
            for record in records:
                result = record.reception_result or {}
                if not isinstance(result, dict):
                    continue
                exit_key = str(result.get("exit") or "unknown")
                exits[exit_key] = exits.get(exit_key, 0) + 1
                collected = result.get("collected") or {}
                if isinstance(collected, dict):
                    for key, value in collected.items():
                        bucket = collected_keys.setdefault(str(key), {})
                        label = str(value)
                        bucket[label] = bucket.get(label, 0) + 1
            return {"exits": exits, "collected": collected_keys}

        if task.execution_mode == "bot":
            intents: dict[str, int] = {}
            handoff_count = 0
            answered = 0
            for record in records:
                if record.answered_at is not None:
                    answered += 1
                result = record.reception_result or {}
                if not isinstance(result, dict):
                    continue
                intent = result.get("intent")
                if intent is not None and str(intent).strip():
                    label = str(intent)
                    intents[label] = intents.get(label, 0) + 1
                if result.get("handoff") or result.get("transferred"):
                    handoff_count += 1
            return {
                "intents": intents,
                "handoff_count": handoff_count,
                "handoff_rate": (handoff_count / answered) if answered else None,
            }

        # agent mode
        by_agent: dict[str, dict[str, Any]] = {}
        for record in records:
            if record.agent_id is None:
                continue
            key = str(record.agent_id)
            row = by_agent.setdefault(key, {"agent_id": record.agent_id, "answered": 0, "duration_ms_sum": 0})
            row["answered"] += 1
            row["duration_ms_sum"] += int(record.duration_ms or 0)
        agents = []
        for row in by_agent.values():
            answered = int(row["answered"])
            agents.append(
                {
                    "agent_id": row["agent_id"],
                    "answered": answered,
                    "avg_duration_ms": (row["duration_ms_sum"] / answered) if answered else 0,
                }
            )
        return {"agents": agents}

    @staticmethod
    def _abandon_stats_from_counts(counts: dict[str, int], task: AutoOutboundTask) -> tuple[dict, bool]:
        answered = int(counts.get("answered", 0))
        abandoned = int(counts.get("abandoned", 0))
        rate = (abandoned / answered) if answered else None
        limit = float(task.abandon_rate_limit) if task.abandon_rate_limit is not None else None
        over = bool(
            rate is not None
            and limit is not None
            and task.pacing_mode in {"ratio", "predictive"}
            and rate > limit
        )
        return (
            {
                "answered": answered,
                "abandoned": abandoned,
                "abandon_rate": rate,
                "abandon_rate_limit": limit,
            },
            over,
        )

    @staticmethod
    async def get_stats(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
    ) -> AutoOutboundTaskDetailStats:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        daily = await AutoOutboundRepository.daily_trend(db, principal.tenant_id, task_id)
        terminal = await AutoOutboundRepository.terminal_state_distribution(
            db, principal.tenant_id, task_id
        )
        records = await AutoOutboundRepository.list_records_for_stats(
            db, principal.tenant_id, task_id
        )
        abandon_counts = await AutoOutboundRepository.abandon_counts(
            db, principal.tenant_id, task_id
        )
        abandon_stats, over = AutoOutboundTaskService._abandon_stats_from_counts(abandon_counts, task)
        return AutoOutboundTaskDetailStats(
            daily_trend=[DailyTrendPoint(**row) for row in daily],
            terminal_state_distribution=[TerminalStateDistributionItem(**row) for row in terminal],
            result_distribution=AutoOutboundTaskService._build_result_distribution(task, records),
            abandon_stats=abandon_stats,
            abandon_over_limit=over,
        )

    @staticmethod
    async def get_monitor(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
    ) -> AutoOutboundMonitorResponse:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)

        from app.services.auto_outbound import frequency as freq
        from app.services.auto_outbound.pacing import get_abandon_rate
        from app.services.auto_outbound.reception import (
            count_in_call_agents_for_queue,
            count_ready_agents_for_queue,
        )

        try:
            redis = freq._default_redis()
        except Exception:  # noqa: BLE001
            redis = None

        in_progress = 0
        if redis is not None:
            in_progress = await freq.get_concurrency(task_id, redis=redis)
        else:
            in_progress = await AutoOutboundRepository.count_in_progress_calls(
                db, principal.tenant_id, task_id
            )

        ready_agents: int | None = None
        in_call_agents: int | None = None
        queued_count: int | None = None
        no_ready = False
        if task.execution_mode == "agent" and task.queue_id:
            ready_agents = await count_ready_agents_for_queue(
                principal.tenant_id, int(task.queue_id), redis=redis
            )
            in_call_agents = await count_in_call_agents_for_queue(
                principal.tenant_id, int(task.queue_id), redis=redis
            )
            queued_count = 0
            no_ready = ready_agents == 0

        abandon_counts = await AutoOutboundRepository.abandon_counts(
            db, principal.tenant_id, task_id
        )
        abandon_stats, over = AutoOutboundTaskService._abandon_stats_from_counts(abandon_counts, task)
        # Prefer Redis window rate for live monitor when available.
        live_rate = None
        if redis is not None and task.execution_mode == "agent":
            live_rate = await get_abandon_rate(task_id, redis=redis)
        abandon_rate = live_rate if live_rate is not None else abandon_stats.get("abandon_rate")
        if (
            live_rate is not None
            and task.abandon_rate_limit is not None
            and task.pacing_mode in {"ratio", "predictive"}
        ):
            over = live_rate > float(task.abandon_rate_limit)

        from app.configs.settings import settings
        from app.services.auto_outbound.capacity import DialCapacityPlanner

        planner = DialCapacityPlanner(redis=redis)
        plan = await planner.resolve(
            {
                "id": task.id,
                "tenant_id": task.tenant_id,
                "max_concurrency": int(task.max_concurrency or 1),
                "execution_mode": task.execution_mode,
                "queue_id": task.queue_id,
                "pacing_mode": task.pacing_mode,
                "dial_ratio": task.dial_ratio,
                "dial_intensity": float(task.dial_intensity) if task.dial_intensity is not None else None,
                "abandon_rate_limit": float(task.abandon_rate_limit)
                if task.abandon_rate_limit is not None
                else None,
                "caller_number_id": task.caller_number_id,
            },
            batch_size=max(1, int(settings.AUTO_OUTBOUND_DIAL_BATCH_SIZE)),
        )

        return AutoOutboundMonitorResponse(
            in_progress_calls=in_progress,
            ready_agents=ready_agents,
            in_call_agents=in_call_agents,
            queued_count=queued_count,
            abandon_rate=abandon_rate,
            abandon_over_limit=over,
            no_ready_agents=no_ready,
            dial_capacity=DialCapacityResponse.model_validate(plan.as_dict()),
        )

    @staticmethod
    async def submit_wrapup(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        record_id: int,
        data: AutoOutboundWrapupRequest,
    ) -> AutoOutboundRecordResponse:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        record = await AutoOutboundRepository.get_record_for_task(
            db,
            tenant_id=principal.tenant_id,
            task_id=task_id,
            record_id=record_id,
            for_update=True,
        )
        if record is None:
            raise NotFoundError("Auto outbound record not found")
        if record.reception_type != "agent":
            raise ValidationError("Wrap-up is only available for agent reception records")
        if record.agent_id is None or int(record.agent_id) != int(principal.user_id):
            raise ForbiddenError("Only the assigned agent can submit wrap-up")

        previous_result = (
            dict(record.reception_result)
            if isinstance(record.reception_result, dict)
            else {}
        )
        first_manual_submit = not (
            previous_result.get("submitted_by") is not None
            or (
                "field_values" in previous_result
                and previous_result.get("auto_submitted") is False
            )
        )

        field_values = data.field_values
        if field_values is None:
            # reception_result may carry business fields directly or under field_values.
            nested = data.reception_result.get("field_values")
            field_values = nested if isinstance(nested, dict) else dict(data.reception_result or {})

        reception_result = dict(previous_result)
        reception_result.update(data.reception_result or {})
        reception_result["field_values"] = field_values
        reception_result["auto_submitted"] = False
        reception_result["submitted_by"] = principal.user_id
        submitted_at = datetime.now(timezone.utc)
        reception_result["submitted_at"] = submitted_at.isoformat()

        updated = await AutoOutboundRepository.update_record(
            db,
            record,
            {"reception_result": reception_result},
            commit=False,
        )
        target = await AutoOutboundRepository.get_target(db, record.target_id)
        if target is None:
            raise NotFoundError("Auto outbound target not found")
        merged = dict(target.field_values or {})
        changed_keys = sorted(
            key
            for key, value in field_values.items()
            if AutoOutboundEventService._json_value(merged.get(key))
            != AutoOutboundEventService._json_value(value)
        )
        if changed_keys:
            merged.update(field_values)
            target = await AutoOutboundRepository.update_target(
                db, target, {"field_values": merged}, commit=False
            )
        if first_manual_submit:
            await AutoOutboundEventService.emit_business_record_event(
                db,
                task=task,
                target=target,
                record=updated,
                event_type="auto_outbound.business_record.submitted",
                occurred_at=submitted_at,
                principal=principal,
                keys_name="submitted_keys",
                keys=list(field_values),
            )
        elif changed_keys:
            await AutoOutboundEventService.emit_business_record_event(
                db,
                task=task,
                target=target,
                record=updated,
                event_type="auto_outbound.business_record.updated",
                occurred_at=submitted_at,
                principal=principal,
                keys_name="changed_keys",
                keys=changed_keys,
            )
        await db.commit()
        return AutoOutboundRecordResponse.model_validate(updated)

    @staticmethod
    async def get_agent_context(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        *,
        call_record_id: int | None = None,
        phone_number: str | None = None,
    ) -> AutoOutboundAgentContextResponse:
        """Agent workspace context: task fields + linked call record (no manage)."""
        AutoOutboundTaskService._assert_workspace_use(principal)
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")

        record = None
        if call_record_id is not None:
            record = await AutoOutboundRepository.get_record_by_call_record_id(
                db,
                tenant_id=principal.tenant_id,
                task_id=task_id,
                call_record_id=call_record_id,
            )
            # Agents may only see their own assignment; manage can view all.
            if record is not None and not principal.has_permission(MANAGE_PERMISSION):
                if record.agent_id is None or int(record.agent_id) != int(principal.user_id):
                    raise ForbiddenError("Permission denied")
        if record is None and phone_number:
            phone = phone_number.strip()
            if phone:
                candidates = await AutoOutboundRepository.list_agent_records_for_phone(
                    db,
                    tenant_id=principal.tenant_id,
                    task_id=task_id,
                    phone_number=phone,
                    agent_id=principal.user_id,
                )
                for item in candidates:
                    if AutoOutboundTaskService._wrapup_open_for_context(item.reception_result):
                        record = item
                        break
                if record is None and candidates:
                    record = candidates[0]

        context_record: AutoOutboundAgentContextRecord | None = None
        if record is not None:
            field_values: dict[str, Any] = {}
            target = await AutoOutboundRepository.get_target(db, record.target_id)
            if target is not None and isinstance(target.field_values, dict):
                field_values.update(target.field_values)
            reception = record.reception_result if isinstance(record.reception_result, dict) else None
            if reception is not None:
                nested = reception.get("field_values")
                if isinstance(nested, dict):
                    field_values.update(nested)
            context_record = AutoOutboundAgentContextRecord(
                id=record.id,
                target_id=record.target_id,
                field_values=field_values,
                reception_result=reception,
            )

        fields: list[OutboundTaskField] = []
        for raw in task.fields or []:
            try:
                fields.append(OutboundTaskField.model_validate(raw))
            except Exception:  # noqa: BLE001 — skip malformed stored fields
                continue

        return AutoOutboundAgentContextResponse(
            task_id=task.id,
            task_name=task.name,
            template_name=task.template_name or "",
            fields=fields,
            wrapup_seconds=int(task.wrapup_seconds or 60),
            record=context_record,
        )

    @staticmethod
    async def list_targets(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        page: int,
        page_size: int,
        q: str | None = None,
        status: str | None = None,
    ) -> dict:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        items, total = await AutoOutboundRepository.list_targets(
            db, principal.tenant_id, task_id, page, page_size, q=q, status=status
        )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": _pages(total, page_size),
        }

    @staticmethod
    async def _match_user_id(
        db: AsyncSession,
        tenant_id: int,
        phone_number: str,
        users_cache: list[Any] | None = None,
    ) -> int | None:
        keys = phone_match_keys(phone_number)
        if not keys:
            return None
        users = users_cache if users_cache is not None else await UserRepository.list_with_phone(db, tenant_id)
        matches = [user for user in users if phone_match_keys(user.phone) & keys]
        if len(matches) == 1:
            return matches[0].id
        return None

    @staticmethod
    async def create_target(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        data: AutoOutboundTargetCreate,
    ):
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        AutoOutboundTaskService._assert_task_allows_target_mutation(task)
        payload = data.model_dump(mode="json")
        payload["tenant_id"] = principal.tenant_id
        payload["task_id"] = task_id
        if payload.get("user_id") is None:
            payload["user_id"] = await AutoOutboundTaskService._match_user_id(
                db, principal.tenant_id, payload["phone_number"]
            )
        valid_user_ids = await AutoOutboundTaskService._sanitize_user_ids(
            db, principal.tenant_id, [payload.get("user_id")]
        )
        if payload.get("user_id") is not None and payload["user_id"] not in valid_user_ids:
            payload["user_id"] = None
        locked_task = await AutoOutboundTaskService._lock_task_for_target_append(
            db, principal, task_id
        )
        created = await AutoOutboundRepository.create_target(
            db, payload, commit=False
        )
        task_auto_resumed = (
            await AutoOutboundTaskService._maybe_auto_resume_after_target_append(
                db, task_id, locked_task=locked_task
            )
        )
        created.task_auto_resumed = task_auto_resumed  # type: ignore[attr-defined]
        await db.commit()
        return created

    @staticmethod
    async def create_targets_bulk(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        data: AutoOutboundTargetBulkCreateRequest,
    ) -> AutoOutboundTargetBulkCreateResponse:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        AutoOutboundTaskService._assert_task_allows_target_mutation(task)

        users = await UserRepository.list_with_phone(db, principal.tenant_id)
        rows: list[dict] = []
        matched_user_ids: list[int | None] = []
        for target in data.targets:
            payload = target.model_dump(mode="json")
            payload["tenant_id"] = principal.tenant_id
            payload["task_id"] = task_id
            if payload.get("user_id") is None:
                payload["user_id"] = await AutoOutboundTaskService._match_user_id(
                    db,
                    principal.tenant_id,
                    payload["phone_number"],
                    users_cache=users,
                )
            matched_user_ids.append(payload.get("user_id"))
            rows.append(payload)

        valid_user_ids = await AutoOutboundTaskService._sanitize_user_ids(
            db, principal.tenant_id, matched_user_ids
        )
        for row in rows:
            if row.get("user_id") is not None and row["user_id"] not in valid_user_ids:
                row["user_id"] = None

        locked_task = await AutoOutboundTaskService._lock_task_for_target_append(
            db, principal, task_id
        )
        items = await AutoOutboundRepository.create_targets_bulk(
            db, rows, commit=False
        )
        task_auto_resumed = (
            await AutoOutboundTaskService._maybe_auto_resume_after_target_append(
                db, task_id, locked_task=locked_task
            )
        )
        await db.commit()
        return AutoOutboundTargetBulkCreateResponse(
            created=len(items),
            items=items,
            task_auto_resumed=task_auto_resumed,
        )

    @staticmethod
    async def import_targets(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        filename: str,
        content: bytes,
    ) -> AutoOutboundTargetImportResponse:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        AutoOutboundTaskService._assert_task_allows_target_mutation(task)
        if len(content) > TARGET_IMPORT_MAX_FILE_SIZE:
            raise ValidationError("File is too large")

        headers, rows = parse_spreadsheet(content, filename)
        if not headers:
            raise ValidationError("Spreadsheet header is required")
        if len(rows) > TARGET_IMPORT_MAX_ROWS:
            raise ValidationError("Too many rows")

        normalized_headers = [_normalize_import_header(header) for header in headers]
        phone_header_aliases = {_normalize_import_header(alias) for alias in PHONE_HEADER_ALIASES}
        phone_index = next(
            (index for index, header in enumerate(normalized_headers) if header in phone_header_aliases),
            None,
        )
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

        users = await UserRepository.list_with_phone(db, principal.tenant_id)
        today = datetime.now(timezone.utc).date()
        phone_candidates: list[str] = []
        for row in rows:
            values = [cell.strip() for cell in row]
            if not any(values):
                continue
            phone_number = values[phone_index] if phone_index < len(values) else ""
            if phone_number:
                phone_candidates.append(phone_number)
        records_today = await AutoOutboundRepository.count_records_for_numbers_on_day(
            db, principal.tenant_id, task_id, phone_candidates, today
        )
        daily_limit = int(task.daily_per_number_limit or 3)

        # One IN query for pending duplicates already in this task.
        pending_phones: set[str] = set()
        unique_candidates = sorted({phone for phone in phone_candidates if phone})
        if unique_candidates:
            pending_result = await db.execute(
                select(AutoOutboundTarget.phone_number).where(
                    AutoOutboundTarget.tenant_id == principal.tenant_id,
                    AutoOutboundTarget.task_id == task_id,
                    AutoOutboundTarget.status == "pending",
                    AutoOutboundTarget.phone_number.in_(unique_candidates),
                )
            )
            pending_phones = set(pending_result.scalars().all())

        created = 0
        task_auto_resumed = False
        total = 0
        skipped_rate_limited = 0
        errors: list[AutoOutboundTargetImportError] = []
        bulk_rows: list[dict] = []
        seen_in_file: set[str] = set()
        matched_user_ids: list[int | None] = []

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
            missing_fields = sorted(
                key for key in required_field_keys if not str(field_values.get(key) or "").strip()
            )

            reason = ""
            if not phone_number:
                reason = "Phone number is required"
            elif len(phone_number) > 64:
                reason = "Phone number must be at most 64 characters"
            elif missing_fields:
                reason = f"Required field missing: {', '.join(missing_fields)}"
            elif phone_number in seen_in_file:
                reason = "Duplicate phone number in file"
            elif phone_number in pending_phones:
                reason = "Phone number already pending in this task"
            elif records_today.get(phone_number, 0) >= daily_limit:
                skipped_rate_limited += 1
                continue

            if reason:
                if len(errors) < TARGET_IMPORT_ERROR_LIMIT:
                    errors.append(
                        AutoOutboundTargetImportError(
                            row_number=row_number,
                            phone_number=phone_number or None,
                            reason=reason,
                        )
                    )
                continue

            seen_in_file.add(phone_number)
            user_id = await AutoOutboundTaskService._match_user_id(
                db, principal.tenant_id, phone_number, users_cache=users
            )
            matched_user_ids.append(user_id)
            bulk_rows.append(
                {
                    "tenant_id": principal.tenant_id,
                    "task_id": task_id,
                    "phone_number": phone_number,
                    "user_id": user_id,
                    "field_values": field_values,
                    "status": "pending",
                    "retry_counts": {},
                }
            )

        valid_user_ids = await AutoOutboundTaskService._sanitize_user_ids(
            db, principal.tenant_id, matched_user_ids
        )
        for row in bulk_rows:
            if row.get("user_id") is not None and row["user_id"] not in valid_user_ids:
                row["user_id"] = None

        if bulk_rows:
            locked_task = await AutoOutboundTaskService._lock_task_for_target_append(
                db, principal, task_id
            )
            await AutoOutboundRepository.create_targets_bulk(
                db, bulk_rows, commit=False
            )
            created = len(bulk_rows)
            task_auto_resumed = (
                await AutoOutboundTaskService._maybe_auto_resume_after_target_append(
                    db, task_id, locked_task=locked_task
                )
            )
            await db.commit()

        return AutoOutboundTargetImportResponse(
            total=total,
            created=created,
            failed=total - created - skipped_rate_limited,
            skipped_rate_limited=skipped_rate_limited,
            errors=errors,
            task_auto_resumed=task_auto_resumed,
        )

    @staticmethod
    async def update_target(
        db: AsyncSession,
        principal: EffectivePrincipal,
        target_id: int,
        data: AutoOutboundTargetUpdate,
    ):
        target = await AutoOutboundRepository.get_target(db, target_id)
        if not target or target.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound target not found")
        task = await AutoOutboundRepository.get_task(db, target.task_id)
        if not task:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        if task.status == "archived":
            raise ValidationError("Archived tasks cannot be changed")
        payload = data.model_dump(mode="json", exclude_unset=True)
        # next_call_at must remain datetime for TIMESTAMPTZ binding
        if "next_call_at" in payload:
            payload["next_call_at"] = data.next_call_at
        changed_keys: list[str] = []
        if "field_values" in payload:
            previous_values = dict(target.field_values or {})
            next_values = dict(payload.get("field_values") or {})
            changed_keys = sorted(
                key
                for key in set(previous_values) | set(next_values)
                if AutoOutboundEventService._json_value(previous_values.get(key))
                != AutoOutboundEventService._json_value(next_values.get(key))
            )
            if not changed_keys:
                payload.pop("field_values")
        if not payload:
            return target
        if not changed_keys:
            return await AutoOutboundRepository.update_target(db, target, payload)
        updated = await AutoOutboundRepository.update_target(
            db, target, payload, commit=False
        )
        now = datetime.now(timezone.utc)
        await AutoOutboundEventService.emit_business_record_event(
            db,
            task=task,
            target=updated,
            record=None,
            event_type="auto_outbound.business_record.updated",
            occurred_at=now,
            principal=principal,
            keys_name="changed_keys",
            keys=changed_keys,
        )
        await db.commit()
        return updated

    @staticmethod
    async def mark_target_invalid(
        db: AsyncSession,
        principal: EffectivePrincipal,
        target_id: int,
    ):
        target = await AutoOutboundRepository.get_target(db, target_id)
        if not target or target.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound target not found")
        task = await AutoOutboundRepository.get_task(db, target.task_id)
        if not task:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        if task.status == "archived":
            raise ValidationError("Archived tasks cannot be changed")
        return await AutoOutboundRepository.update_target(db, target, {"status": "invalid"})

    @staticmethod
    async def delete_target(
        db: AsyncSession,
        principal: EffectivePrincipal,
        target_id: int,
    ) -> None:
        target = await AutoOutboundRepository.get_target(db, target_id)
        if not target or target.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound target not found")
        task = await AutoOutboundRepository.get_task(db, target.task_id)
        if not task:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        if task.status == "archived":
            raise ValidationError("Archived tasks cannot be changed")
        await AutoOutboundRepository.delete_target(db, target)

    @staticmethod
    async def list_records(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        page: int,
        page_size: int,
    ) -> dict:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if not task or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        AutoOutboundTaskService._assert_can_manage_task(principal, task)
        items, total = await AutoOutboundRepository.list_records(
            db, principal.tenant_id, task_id, page, page_size
        )
        agent_names = await AutoOutboundTaskService._owner_names(
            db, [item.agent_id for item in items]
        )
        public_ids = await AutoOutboundRepository.list_call_record_public_ids(
            db, principal.tenant_id, [item.call_record_id for item in items]
        )
        responses: list[AutoOutboundRecordResponse] = []
        for item in items:
            response = AutoOutboundRecordResponse.model_validate(item)
            response.agent_name = agent_names.get(item.agent_id) if item.agent_id else None
            if item.call_record_id is not None:
                response.call_record_public_id = public_ids.get(item.call_record_id)
            responses.append(response)
        return {
            "items": responses,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": _pages(total, page_size),
        }
