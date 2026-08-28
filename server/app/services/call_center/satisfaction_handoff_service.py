"""Agent-to-survey handoff orchestration for live customer calls."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

from sqlalchemy import desc, select

from app.core.exceptions import ConflictError
from app.db.session import AsyncSessionLocal
from app.models.call_event import CallEvent
from app.repositories.call_record_repository import CallRecordRepository
from app.repositories.call_satisfaction_execution_repository import (
    CallSatisfactionExecutionRepository,
)
from app.repositories.satisfaction_flow_repository import SatisfactionFlowRepository
from app.services.call_center.call_control_service import (
    CallControlService,
    _clear_legs,
    _legs,
)
from app.services.call_satisfaction_execution_service import (
    CallSatisfactionExecutionService,
)
from app.services.call_trajectory_service import CallTrajectoryService


logger = logging.getLogger(__name__)
_local_locks: dict[str, asyncio.Lock] = {}


def _unavailable(reason: str, message: str) -> dict:
    return {
        "available": False,
        "reason": reason,
        "message": message,
    }


class CallSatisfactionHandoffService:
    @staticmethod
    async def _has_open_transfer(db, call_record_id: int) -> bool:
        started = (
            await db.execute(
                select(CallEvent.operation_id)
                .where(
                    CallEvent.call_record_id == call_record_id,
                    CallEvent.event_type == "transfer_started",
                    CallEvent.operation_id.is_not(None),
                )
                .order_by(desc(CallEvent.sequence_no))
                .limit(1)
            )
        ).scalar_one_or_none()
        if not started:
            return False
        terminal = (
            await db.execute(
                select(CallEvent.id)
                .where(
                    CallEvent.call_record_id == call_record_id,
                    CallEvent.operation_id == started,
                    CallEvent.event_type.in_({"transfer_completed", "transfer_failed"}),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return terminal is None

    @staticmethod
    async def get_availability(
        *, tenant_id: int, employee_id: int
    ) -> dict:
        try:
            call = await CallControlService._resolve_current_call(
                tenant_id, employee_id
            )
        except Exception:  # noqa: BLE001
            base = _unavailable("no_active_call", "当前没有可评价的人工通话")
            return {
                "call_id": None,
                "agent_invite": base,
                "auto_transfer": base,
                "flow": None,
            }

        legs = await _legs(tenant_id, employee_id)
        state_reason = None
        state_message = None
        if legs.customer_held:
            state_reason, state_message = "held", "通话保持中，暂不能进入满意度调查"
        elif legs.consult_call_id or legs.consult_state in {"ringing", "active"}:
            state_reason, state_message = "consulting", "咨询中，暂不能进入满意度调查"
        elif legs.room_id or legs.conference_participant_call_id:
            state_reason, state_message = "conference", "三方通话中，暂不能进入满意度调查"

        async with AsyncSessionLocal() as db:
            record = await CallRecordRepository.get_by_id(
                db, call.record_id, tenant_id
            )
            if record is None or record.lifecycle_status != "active":
                base = _unavailable("no_active_call", "当前没有可评价的人工通话")
                return {
                    "call_id": call.customer_call_id,
                    "agent_invite": base,
                    "auto_transfer": base,
                    "flow": None,
                }
            serving_agent_id = (
                record.last_serving_agent_id or record.initiator_agent_id
            )
            if (
                record.first_agent_connected_at is None
                or serving_agent_id != employee_id
            ):
                state_reason = "not_serving_agent"
                state_message = "当前客服不是此通话的最终接待客服"
            elif await CallSatisfactionHandoffService._has_open_transfer(
                db, record.id
            ):
                state_reason = "transferring"
                state_message = "通话转接中，暂不能进入满意度调查"

            existing = (
                await CallSatisfactionExecutionRepository.get_by_call_record_id(
                    db, record.id
                )
            )
            if existing is not None:
                state_reason = "already_started"
                state_message = "当前通话已经创建满意度调查"

            flow = await SatisfactionFlowRepository.get_active(db, tenant_id)
            version = flow.current_version if flow is not None else None
            if version is None:
                state_reason = "no_active_flow"
                state_message = "当前没有启用的满意度流程"
                flow_payload = None
                settings = {}
            else:
                settings = dict(version.settings_json)
                flow_payload = {
                    "id": flow.id,
                    "name": version.name_snapshot,
                    "version_no": version.version_no,
                }

            direction_allowed = bool(settings.get(record.direction, False))

        def trigger(kind: str) -> dict:
            if state_reason:
                return _unavailable(state_reason, state_message or "当前不可用")
            if not direction_allowed:
                return _unavailable(
                    "direction_disabled", "当前通话方向未启用满意度调查"
                )
            if not settings.get(kind, False):
                return _unavailable("trigger_disabled", "当前满意度触发方式未启用")
            return {"available": True, "reason": None, "message": None}

        return {
            "call_id": call.customer_call_id,
            "agent_invite": trigger("agent_invite"),
            "auto_transfer": trigger("auto_transfer"),
            "flow": flow_payload,
        }

    @staticmethod
    @asynccontextmanager
    async def _handoff_lock(call_id: str):
        lock = _local_locks.setdefault(call_id, asyncio.Lock())
        if lock.locked():
            raise ConflictError("满意度交接正在处理中")
        await lock.acquire()
        redis = None
        token = uuid4().hex
        redis_key = f"cc:satisfaction:handoff:{call_id}"
        redis_acquired = False
        try:
            from app.services.call_center.orchestrator import _get_redis_client

            redis = _get_redis_client()
            if redis is not None:
                redis_acquired = bool(
                    await redis.set(redis_key, token, nx=True, ex=30)
                )
                if not redis_acquired:
                    raise ConflictError("满意度交接正在处理中")
            yield
        finally:
            if redis is not None and redis_acquired:
                with suppress(Exception):
                    await redis.eval(
                        "if redis.call('get', KEYS[1]) == ARGV[1] then "
                        "return redis.call('del', KEYS[1]) else return 0 end",
                        1,
                        redis_key,
                        token,
                    )
            lock.release()
            if not lock.locked():
                _local_locks.pop(call_id, None)

    @staticmethod
    async def handoff(
        *, tenant_id: int, employee_id: int, trigger_source: str
    ) -> dict:
        availability = await CallSatisfactionHandoffService.get_availability(
            tenant_id=tenant_id, employee_id=employee_id
        )
        trigger = availability[trigger_source]
        if not trigger["available"]:
            if trigger_source == "auto_transfer":
                return {
                    "ok": False,
                    "skipped": True,
                    "reason": trigger["reason"],
                }
            raise ConflictError(trigger["message"] or "当前不能邀请评价")

        call_id = availability["call_id"]
        async with CallSatisfactionHandoffService._handoff_lock(call_id):
            availability = await CallSatisfactionHandoffService.get_availability(
                tenant_id=tenant_id, employee_id=employee_id
            )
            trigger = availability[trigger_source]
            if not trigger["available"]:
                if trigger_source == "auto_transfer":
                    return {
                        "ok": False,
                        "skipped": True,
                        "reason": trigger["reason"],
                    }
                raise ConflictError(trigger["message"] or "当前不能邀请评价")

            call = await CallControlService._resolve_current_call(
                tenant_id, employee_id
            )
            if not call.webrtc_call_id:
                if trigger_source == "auto_transfer":
                    return {"ok": False, "skipped": True, "reason": "no_agent_leg"}
                raise ConflictError("未找到当前客服媒体线路")

            prepared = await CallSatisfactionExecutionService.prepare_managed(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                trigger_source=trigger_source,
            )
            if not prepared.created:
                if prepared.status in {"in_progress", "completed", "partial", "unanswered"}:
                    return {
                        "ok": True,
                        "note": "already_started",
                        "call_id": call.customer_call_id,
                        "execution_id": prepared.execution_id,
                    }
                raise ConflictError("当前通话已经处理过满意度调查")

            from app.services.call_center.orchestrator import get_orchestrator

            orchestrator = get_orchestrator()
            previous_workflow = orchestrator.active_workflow(call.customer_call_id)
            unbridged = False
            try:
                await orchestrator.telephony.call_unbridge(
                    call.customer_call_id, call.webrtc_call_id
                )
                unbridged = True
                workflow = orchestrator.install_satisfaction_workflow(prepared)
                await workflow.start()
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Satisfaction handoff failed call_id=%s source=%s",
                    call.customer_call_id,
                    trigger_source,
                )
                orchestrator.remove_satisfaction_workflow(
                    call.customer_call_id, prepared.execution_id
                )
                orchestrator.restore_workflow(
                    call.customer_call_id, previous_workflow
                )
                await CallSatisfactionExecutionService.mark_failed_managed(
                    execution_id=prepared.execution_id,
                    reason="handoff_failed",
                )
                if trigger_source == "agent_invite" and unbridged:
                    try:
                        await orchestrator.telephony.call_bridge(
                            call.customer_call_id,
                            call.webrtc_call_id,
                            keepalive_on_peer_hangup=True,
                        )
                    except Exception as restore_exc:  # noqa: BLE001
                        logger.exception(
                            "Satisfaction handoff restore failed call_id=%s",
                            call.customer_call_id,
                        )
                        raise ConflictError(
                            "满意度调查启动失败，通话恢复失败，请立即重新呼叫客户"
                        ) from restore_exc
                    raise ConflictError(
                        "满意度调查启动失败，原通话已恢复"
                    ) from exc
                return {
                    "ok": False,
                    "skipped": False,
                    "fallback_hangup": True,
                    "reason": "handoff_failed",
                }

            await CallTrajectoryService.append_for_call_id_best_effort(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                event_id=f"opendesk:human-service-ended:{prepared.execution_id}",
                event_type="human_service_ended",
                event_category="reception",
                actor_type="agent",
                actor_id=str(employee_id),
                source="opendesk",
                call_leg_id=call.webrtc_call_id,
                participant_role="agent",
                result="succeeded",
                reason_code="satisfaction_handoff",
                details={
                    "execution_id": prepared.execution_id,
                    "trigger_source": trigger_source,
                },
            )
            await CallTrajectoryService.append_for_call_id_best_effort(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                event_id=f"opendesk:satisfaction-started:{prepared.execution_id}",
                event_type="satisfaction_started",
                event_category="ivr",
                actor_type="customer",
                source="opendesk",
                call_leg_id=call.customer_call_id,
                participant_role="customer",
                target_type="satisfaction_flow_version",
                target_id=str(prepared.flow_version_id),
                target_name_snapshot=(
                    f"{prepared.flow_name} · V{prepared.flow_version_no}"
                ),
                result="succeeded",
                details={"execution_id": prepared.execution_id},
            )
            with suppress(Exception):
                await orchestrator.telephony.call_hangup(
                    call.webrtc_call_id, reason="satisfaction_handoff"
                )
            await orchestrator.finalize_agent_call(
                tenant_id=tenant_id,
                employee_id=employee_id,
                call_id=call.customer_call_id,
                reason="satisfaction_started",
                mark_cdr_completed=False,
            )
            await _clear_legs(tenant_id, employee_id)
            return {
                "ok": True,
                "note": "satisfaction_started",
                "call_id": call.customer_call_id,
                "execution_id": prepared.execution_id,
                "flow_name": prepared.flow_name,
                "flow_version_no": prepared.flow_version_no,
            }
