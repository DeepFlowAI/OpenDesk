"""
Call record service — write CDR lifecycle (orchestrator) + read for history.
"""
import logging
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.enums import QueueType
from app.libs.storage.factory import create_storage_client
from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup
from app.models.user import User
from app.repositories.call_record_access_scope_repository import (
    CallRecordAccessScopeRepository,
)
from app.repositories.call_event_repository import CallEventRepository
from app.repositories.call_record_repository import CallRecordRepository
from app.repositories.call_recording_repository import CallRecordingRepository
from app.repositories.employee_group_repository import EmployeeGroupRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.schemas.call_trajectory import CallEventCreate
from app.schemas.permission import EffectivePrincipal
from app.services.call_trajectory_service import CallTrajectoryService
from app.services.call_user_association_service import CallUserAssociationService
from app.services.call_workspace_context_service import CallWorkspaceContextService
from app.services.data_scope_service import RESOURCE_CALL_RECORD, DataScopeService

logger = logging.getLogger(__name__)


async def _project_satisfaction_best_effort(
    db: AsyncSession, call_record_id: int
) -> None:
    try:
        from app.services.call_satisfaction_projection_service import (
            CallSatisfactionProjectionService,
        )

        await CallSatisfactionProjectionService.project(
            db, call_record_id=call_record_id
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to project call satisfaction call_record_id=%s",
            call_record_id,
        )


def normalize_call_number(value: str | None) -> str | None:
    """Normalize SIP/tel numbers while preserving an optional leading plus."""
    if not value:
        return None
    normalized = value.strip()
    normalized = re.sub(r"^(?:sip|sips|tel):", "", normalized, flags=re.IGNORECASE)
    normalized = normalized.split("@", 1)[0].split(";", 1)[0]
    has_plus = normalized.lstrip().startswith("+")
    digits = re.sub(r"\D+", "", normalized)
    if not digits:
        return None
    return f"+{digits}" if has_plus else digits


class CallRecordService:

    # ─────────── Write (called from orchestrator) ───────────

    @staticmethod
    async def create_for_incoming(
        db: AsyncSession,
        tenant_id: int,
        *,
        call_id: str,
        conversation_id: str | None,
        root_call_id: str | None,
        from_number: str | None,
        to_number: str | None,
        voice_flow_id: int | None = None,
        voice_flow_version_id: int | None = None,
        identify_user: bool = True,
    ) -> dict:
        """Create the inbound CDR.

        ``identify_user`` defaults to True for callers that already run off the
        media path. The inbound orchestrator passes False and identifies in a
        background task — phone matching loads every user with a phone and must
        not delay ``call.answer`` / the first prompt.
        """
        await CallRecordRepository.lock_creation(db, tenant_id, call_id)
        existing = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if existing:
            if identify_user:
                await _best_effort_identify_user(db, tenant_id, existing)
            return _to_detail(existing, None)
        started_at = datetime.now(timezone.utc)
        row = await CallRecordRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "call_id": call_id,
                "conversation_id": conversation_id,
                "root_call_id": root_call_id or call_id,
                "direction": "inbound",
                "call_source": "inbound",
                "customer_number": normalize_call_number(from_number),
                "service_number": normalize_call_number(to_number),
                "voice_flow_id": voice_flow_id,
                "voice_flow_version_id": voice_flow_version_id,
                "lifecycle_status": "active",
                "started_at": started_at,
                "recording_status": "none",
            },
            commit=False,
        )
        event_id = f"opendesk:call-created:{row.id}"
        await CallTrajectoryService.append_event(
            db,
            call_record_id=row.id,
            payload=CallEventCreate(
                event_id=event_id,
                event_type="call_created",
                event_category="lifecycle",
                actor_type="system",
                source="opendesk",
                source_event_id=event_id,
                occurred_at=row.started_at,
                call_leg_id=row.call_id,
                participant_role="customer",
                details=_call_created_details(row, from_number, to_number),
            ),
            commit=False,
        )
        await db.commit()
        await db.refresh(row)
        if identify_user:
            await _best_effort_identify_user(db, tenant_id, row)
        return _to_detail(row, None)

    @staticmethod
    async def identify_user_for_call_managed(tenant_id: int, call_id: str) -> None:
        """Best-effort caller identification on a short-lived DB session."""
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            row = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
            if not row:
                return
            await _best_effort_identify_user(db, tenant_id, row)

    @staticmethod
    async def record_outbound_customer_connected(call_id: str) -> None:
        """Best-effort trajectory fact for the customer answering an outbound call.

        Only the customer leg owns a call record, so answers on other legs
        (for example an agent desk-phone leg) are ignored.
        """
        from app.db.session import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as db:
                row = await CallRecordRepository.get_by_call_id_unscoped(db, call_id)
                if row is None or row.direction != "outbound":
                    return
                event_id = f"flowkit:customer-connected:{call_id}"
                await CallTrajectoryService.append_event(
                    db,
                    call_record_id=row.id,
                    payload=CallEventCreate(
                        event_id=event_id,
                        event_type="customer_connected",
                        event_category="lifecycle",
                        actor_type="customer",
                        source="flowkit",
                        source_event_id=event_id,
                        occurred_at=datetime.now(timezone.utc),
                        call_leg_id=call_id,
                        participant_role="customer",
                        result="succeeded",
                    ),
                    commit=True,
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "outbound customer_connected trajectory failed call_id=%s", call_id
            )

    @staticmethod
    async def create_for_outbound(
        db: AsyncSession,
        tenant_id: int,
        *,
        call_id: str,
        conversation_id: str | None,
        root_call_id: str | None,
        from_number: str | None,
        to_number: str | None,
        agent_id: int | None = None,
        device_type: str | None = None,
        device_identifier: str | None = None,
        call_source: str = "agent_dial",
        custom_business_info: str | None = None,
        external_context: dict | None = None,
        identify_user: bool = True,
    ) -> dict:
        """Same shape as create_for_incoming but direction=outbound and the
        agent who dialed is known immediately (no queue routing). Called
        from OutboundDialService after FlowKit accepts the originate.

        ``device_type`` / ``device_identifier`` capture the agent's device at
        establishment as a permanent attribution snapshot.

        ``identify_user`` defaults to True for agent-dial paths. Auto-outbound
        passes False and identifies in a background task — phone matching
        must not delay post-answer reception / queue offer.
        """

        await CallRecordRepository.lock_creation(db, tenant_id, call_id)
        existing = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if existing:
            if identify_user:
                await _best_effort_identify_user(db, tenant_id, existing, actor_id=agent_id)
            return _to_detail(existing, None)
        del device_type, device_identifier
        started_at = datetime.now(timezone.utc)
        employee_names = (
            await _employee_name_snapshots(db, tenant_id, [agent_id])
            if agent_id is not None
            else {}
        )
        row = await CallRecordRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "call_id": call_id,
                "conversation_id": conversation_id,
                "root_call_id": root_call_id or call_id,
                "direction": "outbound",
                "call_source": call_source,
                "custom_business_info": custom_business_info,
                "external_context": external_context,
                "customer_number": normalize_call_number(to_number),
                "service_number": normalize_call_number(from_number),
                "initiator_agent_id": agent_id,
                "initiator_agent_ref_id": agent_id,
                "initiator_agent_name_snapshot": employee_names.get(agent_id),
                "lifecycle_status": "active",
                "started_at": started_at,
                "recording_status": "none",
            },
            commit=False,
        )
        created_event_id = f"opendesk:call-created:{row.id}"
        await CallTrajectoryService.append_event(
            db,
            call_record_id=row.id,
            payload=CallEventCreate(
                event_id=created_event_id,
                event_type="call_created",
                event_category="lifecycle",
                actor_type="agent" if agent_id is not None else "system",
                actor_id=str(agent_id) if agent_id is not None else None,
                actor_name_snapshot=employee_names.get(agent_id),
                source="opendesk",
                source_event_id=created_event_id,
                occurred_at=row.started_at,
                call_leg_id=row.call_id,
                participant_role="customer",
                details=_call_created_details(row, from_number, to_number),
            ),
            commit=False,
        )
        ringing_event_id = f"opendesk:customer-ringing:{row.id}"
        await CallTrajectoryService.append_event(
            db,
            call_record_id=row.id,
            payload=CallEventCreate(
                event_id=ringing_event_id,
                event_type="customer_ringing_started",
                event_category="lifecycle",
                actor_type="system",
                source="opendesk",
                source_event_id=ringing_event_id,
                occurred_at=row.started_at,
                call_leg_id=row.call_id,
                participant_role="customer",
            ),
            commit=False,
        )
        if agent_id is not None:
            await CallRecordAccessScopeRepository.add(
                db,
                tenant_id=tenant_id,
                call_record_id=row.id,
                subject_type="employee",
                subject_id=agent_id,
                reason="initiator",
                source_event_id=created_event_id,
                commit=False,
            )
        await db.commit()
        await db.refresh(row)
        if identify_user:
            await _best_effort_identify_user(db, tenant_id, row, actor_id=agent_id)
            if agent_id is not None and row.user_id is not None:
                # The record is created off the dial request, usually after the
                # desk last refreshed its call list, so tell it to reload.
                from app.constants.call_center import CcSocketEvent
                from app.services.call_center.agent_notify import emit_to_agent

                await emit_to_agent(
                    tenant_id=tenant_id,
                    employee_id=agent_id,
                    method=CcSocketEvent.CALL_RECORD_UPDATED.value,
                    payload={"call_id": call_id},
                )
        return _to_detail(row, None)

    @staticmethod
    async def mark_answered(
        db: AsyncSession, tenant_id: int, call_id: str, agent_id: int | None = None
    ) -> None:
        del agent_id
        row = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if not row:
            return
        if row.customer_connected_at is not None:
            return
        ts = datetime.now(timezone.utc)
        await CallRecordRepository.update(db, row, {"customer_connected_at": ts})

    @staticmethod
    async def mark_reception_started(
        db: AsyncSession,
        tenant_id: int,
        call_id: str,
        *,
        agent_id: int | None,
        agent_leg_id: str | None = None,
        entry_reason: str = "initial_answer",
    ) -> None:
        """Record a successful customer-agent bridge and responsibility start."""
        row = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if row is None or not getattr(row, "id", None):
            return
        ts = datetime.now(timezone.utc)
        actor_id = str(agent_id) if agent_id is not None else None
        employee_names = await _employee_name_snapshots(db, tenant_id, [agent_id])
        actor_name = employee_names.get(agent_id) if agent_id is not None else None
        bridge_event_id = (
            f"flowkit:agent-bridge-succeeded:{row.id}:{agent_id or 'unknown'}"
        )
        await CallTrajectoryService.append_event(
            db,
            call_record_id=row.id,
            payload=CallEventCreate(
                event_id=bridge_event_id,
                event_type="agent_bridge_succeeded",
                event_category="reception",
                actor_type="system",
                actor_id=actor_id,
                actor_name_snapshot=actor_name,
                target_type="employee" if actor_id else None,
                target_id=actor_id,
                target_name_snapshot=actor_name,
                result="succeeded",
                source="flowkit",
                occurred_at=ts,
                call_leg_id=agent_leg_id,
                parent_leg_id=row.call_id,
                participant_role="serving_agent",
                source_event_id=bridge_event_id,
            ),
            commit=False,
        )
        reception_event_id = (
            f"opendesk:reception-started:{row.id}:{agent_id or 'unknown'}"
        )
        await CallTrajectoryService.append_event(
            db,
            call_record_id=row.id,
            payload=CallEventCreate(
                event_id=reception_event_id,
                event_type="reception_started",
                event_category="reception",
                actor_type="agent" if actor_id else "system",
                actor_id=actor_id,
                actor_name_snapshot=actor_name,
                target_type="employee" if actor_id else None,
                target_id=actor_id,
                target_name_snapshot=actor_name,
                result="succeeded",
                source="opendesk",
                occurred_at=ts,
                call_leg_id=agent_leg_id,
                parent_leg_id=row.call_id,
                participant_role="serving_agent",
                source_event_id=reception_event_id,
                details={"entry_reason": entry_reason},
            ),
            commit=False,
        )
        await db.commit()

    @staticmethod
    async def mark_reception_transferred(
        db: AsyncSession,
        tenant_id: int,
        call_id: str,
        *,
        from_agent_id: int,
        to_agent_id: int | None,
        operation_id: str,
        target_leg_id: str | None = None,
        reason_code: str = "transfer_completed",
    ) -> None:
        """Close the current responsibility segment and optionally start the target's."""
        row = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if row is None or not getattr(row, "id", None):
            return
        ts = datetime.now(timezone.utc)
        employee_names = await _employee_name_snapshots(
            db, tenant_id, [from_agent_id, to_agent_id]
        )
        ended_event_id = f"opendesk:reception-ended:{operation_id}:{from_agent_id}"
        await CallTrajectoryService.append_event(
            db,
            call_record_id=row.id,
            payload=CallEventCreate(
                event_id=ended_event_id,
                event_type="reception_ended",
                event_category="reception",
                actor_type="agent",
                actor_id=str(from_agent_id),
                actor_name_snapshot=employee_names.get(from_agent_id),
                source="opendesk",
                occurred_at=ts,
                operation_id=operation_id,
                participant_role="serving_agent",
                result="succeeded",
                reason_code=reason_code,
                source_event_id=ended_event_id,
            ),
            commit=False,
        )
        if to_agent_id is not None:
            started_event_id = f"opendesk:reception-started:{operation_id}:{to_agent_id}"
            await CallTrajectoryService.append_event(
                db,
                call_record_id=row.id,
                payload=CallEventCreate(
                    event_id=started_event_id,
                    event_type="reception_started",
                    event_category="reception",
                    actor_type="agent",
                    actor_id=str(to_agent_id),
                    actor_name_snapshot=employee_names.get(to_agent_id),
                    source="opendesk",
                    occurred_at=ts,
                    operation_id=operation_id,
                    call_leg_id=target_leg_id,
                    parent_leg_id=row.call_id,
                    participant_role="serving_agent",
                    result="succeeded",
                    reason_code=reason_code,
                    source_event_id=started_event_id,
                    details={"entry_reason": reason_code},
                ),
                commit=False,
            )
            await CallRecordRepository.update(
                db,
                row,
                {"last_serving_agent_id": to_agent_id},
                commit=False,
            )
            await _add_agent_access_scopes(
                db,
                row,
                to_agent_id,
                reason="served",
                source_event_id=started_event_id,
            )
        await db.commit()

    @staticmethod
    async def mark_reception_transferred_managed(
        *,
        tenant_id: int,
        call_id: str,
        from_agent_id: int,
        to_agent_id: int | None,
        operation_id: str,
        target_leg_id: str | None = None,
        reason_code: str = "transfer_completed",
    ) -> None:
        """Apply a responsibility transition in a short, best-effort session."""
        from app.db.session import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as db:
                await CallRecordService.mark_reception_transferred(
                    db,
                    tenant_id,
                    call_id,
                    from_agent_id=from_agent_id,
                    to_agent_id=to_agent_id,
                    operation_id=operation_id,
                    target_leg_id=target_leg_id,
                    reason_code=reason_code,
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to record reception transition call_id=%s",
                call_id,
            )

    @staticmethod
    async def mark_completed(
        db: AsyncSession,
        tenant_id: int,
        call_id: str,
        *,
        hangup_reason: str | None = None,
        end_state: str = "completed",
        hangup_party: str | None = None,
        hangup_details: Mapping[str, Any] | None = None,
    ) -> None:
        row = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if not row:
            return
        if (
            row.lifecycle_status == "ended"
            and row.ended_event_id
            and getattr(row, "finalization_status", None) == "completed"
        ):
            await _project_satisfaction_best_effort(db, row.id)
            return
        ts = getattr(row, "ended_at", None) or datetime.now(timezone.utc)
        if not getattr(row, "id", None):
            return
        call_record_id = row.id
        ending_details = dict(hangup_details or {})
        ending_details.update(
            {
                "hangup_party": hangup_party,
                "end_state": end_state,
            }
        )
        try:
            await CallTrajectoryService.append_event(
                db,
                call_record_id=row.id,
                payload=CallEventCreate(
                    event_id=f"opendesk:call-ending:{row.id}",
                    event_type="call_ending",
                    event_category="lifecycle",
                    actor_type="system",
                    source="opendesk",
                    occurred_at=ts,
                    call_leg_id=row.call_id,
                    participant_role="customer",
                    reason_code="call_ended",
                    reason_detail=hangup_reason,
                    details=ending_details,
                ),
                commit=False,
            )
            await CallRecordRepository.update(
                db,
                row,
                {
                    "lifecycle_status": "ended",
                    "ended_at": ts,
                    "finalization_status": "pending",
                    "finalized_at": None,
                },
                commit=False,
            )
            await db.commit()
        except Exception:  # noqa: BLE001
            await db.rollback()
            logger.exception(
                "Failed to persist call ending fact call_record_id=%s",
                call_record_id,
            )
            await CallRecordService._mark_finalization_failed(
                db,
                call_record_id=call_record_id,
                ended_at=ts,
            )
            return

        await CallRecordService._finalize_pending(
            db,
            call_record_id=call_record_id,
        )

    @staticmethod
    async def retry_finalization(
        db: AsyncSession,
        *,
        call_record_id: int,
        pending_before: datetime,
        failed_before: datetime,
    ) -> bool:
        """Retry one stale pending or failed CDR after locking and rechecking it."""
        row = await CallRecordRepository.lock_by_id(db, call_record_id)
        if row is None or row.lifecycle_status != "ended":
            return False
        updated_at = row.updated_at or row.ended_at or row.started_at
        if row.finalization_status == "pending":
            if updated_at > pending_before:
                return False
        elif row.finalization_status == "failed":
            if updated_at > failed_before:
                return False
            await CallRecordRepository.update(
                db,
                row,
                {"finalization_status": "pending", "finalized_at": None},
                commit=False,
            )
            await db.commit()
        else:
            return False
        return await CallRecordService._finalize_pending(
            db,
            call_record_id=call_record_id,
        )

    @staticmethod
    async def _finalize_pending(
        db: AsyncSession,
        *,
        call_record_id: int,
    ) -> bool:
        row = await CallRecordRepository.lock_by_id(db, call_record_id)
        if row is None or row.finalization_status == "completed":
            return False
        events = await CallEventRepository.list_for_call(db, call_record_id)
        ending_event = next(
            (event for event in reversed(events) if event.event_type == "call_ending"),
            None,
        )
        ended_at = row.ended_at or (
            ending_event.occurred_at
            if ending_event is not None
            else datetime.now(timezone.utc)
        )
        ending_details = dict(getattr(ending_event, "details", None) or {})
        hangup_party = ending_details.pop("hangup_party", None)
        end_state = str(ending_details.pop("end_state", "completed"))
        hangup_reason = getattr(ending_event, "reason_detail", None)
        try:
            await CallTrajectoryService.reconcile_open_intervals(
                db,
                call_record_id=call_record_id,
                ended_at=ended_at,
                commit=False,
            )
            settlement = await CallTrajectoryService.build_settlement_details(
                db,
                call_record_id=call_record_id,
                ended_at=ended_at,
                hangup_reason=hangup_reason,
                hangup_party=hangup_party,
                hangup_details=ending_details,
            )
            ended_event_id = f"opendesk:call-ended:{call_record_id}"
            await CallTrajectoryService.append_event(
                db,
                call_record_id=call_record_id,
                payload=CallEventCreate(
                    event_id=ended_event_id,
                    event_type="call_ended",
                    event_category="lifecycle",
                    actor_type=(
                        settlement["hangup_party"]
                        if settlement["hangup_party"] != "unknown"
                        else "system"
                    ),
                    source="opendesk",
                    occurred_at=ended_at,
                    call_leg_id=row.call_id,
                    participant_role="customer",
                    result="succeeded" if end_state == "completed" else "failed",
                    reason_code=settlement["hangup_reason_code"],
                    source_event_id=ended_event_id,
                    details=settlement,
                ),
                commit=False,
            )
            finalized_at = datetime.now(timezone.utc)
            await CallRecordRepository.update(
                db,
                row,
                {
                    "lifecycle_status": "ended",
                    "ended_at": ended_at,
                    "finalization_status": (
                        "completed"
                        if settlement["projection_complete"]
                        else "incomplete"
                    ),
                    "ended_event_id": ended_event_id,
                    "result_rule_version": settlement["result_rule_version"],
                    "finalized_at": finalized_at,
                    "actual_reception_type": settlement["actual_reception_type"],
                    "call_result": settlement["call_result"],
                    "hangup_party": settlement["hangup_party"],
                    "hangup_reason_code": settlement["hangup_reason_code"],
                    "human_service_requested_at": settlement.get(
                        "human_service_requested_at"
                    ),
                    "first_agent_wait_started_at": settlement.get(
                        "first_agent_wait_started_at"
                    ),
                    "first_agent_offer_started_at": settlement.get(
                        "first_agent_offer_started_at"
                    ),
                    "bot_handoff_requested_at": settlement.get(
                        "bot_handoff_requested_at"
                    ),
                    "bot_handoff_succeeded_at": settlement.get(
                        "bot_handoff_succeeded_at"
                    ),
                    "hangup_stage": settlement.get("hangup_stage"),
                    "short_abandon_threshold_ms": settlement.get(
                        "short_abandon_threshold_ms"
                    ),
                    "total_duration_ms": settlement["total_duration_ms"],
                    "customer_ring_duration_ms": settlement[
                        "customer_ring_duration_ms"
                    ],
                    "agent_wait_duration_ms": settlement["agent_wait_duration_ms"],
                    "customer_agent_talk_duration_ms": settlement[
                        "customer_agent_talk_duration_ms"
                    ],
                },
                commit=False,
            )
            from app.services.call_queue_fact_service import CallQueueFactService
            from app.services.call_agent_fact_service import CallAgentFactService

            await CallQueueFactService.project_for_call(db, call_record_id)
            await CallAgentFactService.project_for_call(db, call_record_id)
            from app.services.call_event_publisher import CallEventPublisher

            await CallEventPublisher.publish_call_ended(db, row)
            await db.commit()
            log_extra = {
                "event": "call_hangup_classified",
                "hangup_call_id": row.call_id,
                "tenant_id": getattr(row, "tenant_id", None),
                "hangup_reason_code": settlement["hangup_reason_code"],
                "hangup_party": settlement["hangup_party"],
                "hangup_match_strategy": settlement.get("hangup_match_strategy"),
                "hangup_match_score": settlement.get("hangup_match_score"),
                "hangup_match_margin": settlement.get("hangup_match_margin"),
                "raw_hangup_reason": hangup_reason,
                "sip_status": settlement.get("sip_status"),
                "sip_reason": settlement.get("sip_reason"),
                "sip_warning": settlement.get("sip_warning"),
                "sip_reason_hdr": settlement.get("sip_reason_hdr"),
                "classification_version": settlement.get(
                    "hangup_classification_version"
                ),
            }
            log_method = (
                logger.warning
                if settlement["hangup_reason_code"] == "unknown"
                else logger.info
            )
            log_method(
                "call_hangup_classified call_id=%s code=%s strategy=%s score=%s",
                row.call_id,
                settlement["hangup_reason_code"],
                settlement.get("hangup_match_strategy"),
                settlement.get("hangup_match_score"),
                extra=log_extra,
            )
            await _project_satisfaction_best_effort(db, call_record_id)
            return True
        except Exception:  # noqa: BLE001
            await db.rollback()
            logger.exception(
                "Failed to settle call trajectory call_record_id=%s",
                call_record_id,
            )
            await CallRecordService._mark_finalization_failed(
                db,
                call_record_id=call_record_id,
                ended_at=ended_at,
            )
            return False

    @staticmethod
    async def _mark_finalization_failed(
        db: AsyncSession,
        *,
        call_record_id: int,
        ended_at: datetime,
    ) -> None:
        failed_row = await CallRecordRepository.get_by_id_unscoped(
            db, call_record_id
        )
        if failed_row is None:
            return
        await CallRecordRepository.update(
            db,
            failed_row,
            {
                "lifecycle_status": "ended",
                "ended_at": ended_at,
                "finalization_status": "failed",
                "finalized_at": None,
            },
        )

    @staticmethod
    async def bind_queue(
        db: AsyncSession,
        tenant_id: int,
        call_id: str,
        queue_type: str | int,
        queue_id: int | None = None,
    ) -> None:
        row = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if not row:
            return
        if queue_id is None:
            queue_id = int(queue_type)
            queue_type = QueueType.EMPLOYEE_GROUP.value
        else:
            queue_type = str(queue_type)

        queue_brief = await _queue_record_brief(db, tenant_id, queue_type, queue_id)
        # Keep this short: hangup reconciliation may derive ids from it, and
        # call_events.event_id is capped at 96 chars.
        event_id = f"opendesk:queue-entered:{uuid4().hex}"
        await CallRecordRepository.update(
            db,
            row,
            {"last_queue_type": queue_type, "last_queue_id": queue_id},
            commit=False,
        )
        if not getattr(row, "id", None):
            return
        await CallTrajectoryService.append_event(
            db,
            call_record_id=row.id,
            payload=CallEventCreate(
                event_id=event_id,
                event_type="queue_entered",
                event_category="queue",
                actor_type="system",
                source="opendesk",
                occurred_at=datetime.now(timezone.utc),
                queue_type=queue_type,
                queue_id=queue_id,
                queue_name_snapshot=(queue_brief or {}).get("name"),
                target_type="queue",
                target_id=str(queue_id),
                target_name_snapshot=(queue_brief or {}).get("name"),
                reason_code="normal",
                source_event_id=event_id,
            ),
            commit=False,
        )
        await CallRecordAccessScopeRepository.add(
            db,
            tenant_id=tenant_id,
            call_record_id=row.id,
            subject_type=queue_type,
            subject_id=queue_id,
            reason="queued",
            source_event_id=event_id,
            commit=False,
        )
        await db.commit()

    @staticmethod
    async def mark_bot_served(
        db: AsyncSession,
        tenant_id: int,
        call_id: str,
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> None:
        """Flag the CDR as bot-served so record lists can show a tag."""
        row = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if not row:
            return
        if not getattr(row, "id", None):
            return
        await _append_trajectory_event(
            db,
            row.id,
            CallEventCreate(
                event_id=f"voicespeed:bot-started:{row.id}:{agent_id or 'default'}",
                event_type="bot_started",
                event_category="bot",
                actor_type="bot",
                actor_id=agent_id,
                actor_name_snapshot=agent_name,
                target_type="bot",
                target_id=agent_id,
                target_name_snapshot=agent_name,
                source="voicespeed",
                occurred_at=datetime.now(timezone.utc),
                call_leg_id=row.call_id,
                participant_role="bot",
            ),
        )

    @staticmethod
    async def save_recording(
        db: AsyncSession,
        *,
        call_id: str,
        recording_id: str,
        storage_key: str | None,
        source_event_id: str,
        status: str = "completed",
        call_leg_id: str | None = None,
        phase: str | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        duration_ms: int | None = None,
    ) -> bool:
        """Upsert one recording artifact and refresh the CDR recording summary."""

        row = await CallRecordRepository.find_by_media_call_id(db, call_id)
        if row is None or not getattr(row, "id", None):
            return False
        # Lock the CDR before inserting the recording. A foreign-key insert
        # only takes a share lock; upgrading that to a row lock later deadlocks
        # when another recording or hangup finalization locks the same row.
        locked = await CallRecordRepository.lock_by_id(db, row.id)
        if locked is None:
            return False
        row = locked
        await CallRecordingRepository.upsert(
            db,
            {
                "tenant_id": row.tenant_id,
                "call_record_id": row.id,
                "recording_id": recording_id,
                "call_leg_id": call_leg_id or call_id,
                "phase": phase,
                "status": status,
                "storage_key": storage_key,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_ms": duration_ms,
                "source_event_id": source_event_id,
            },
            commit=False,
        )
        recordings = await CallRecordingRepository.list_for_call(db, row.id)
        await CallRecordRepository.update(
            db,
            row,
            {"recording_status": _aggregate_recording_status(recordings)},
            commit=False,
        )
        event_type = {
            "recording": "recording_started",
            "completed": "recording_completed",
            "partial": "recording_partial",
            "failed": "recording_failed",
        }.get(status, "recording_failed")
        await CallTrajectoryService.append_event(
            db,
            call_record_id=row.id,
            payload=CallEventCreate(
                event_id=source_event_id,
                event_type=event_type,
                event_category="media",
                actor_type="system",
                source="flowkit",
                source_event_id=source_event_id,
                occurred_at=ended_at or started_at or datetime.now(timezone.utc),
                call_leg_id=call_leg_id or call_id,
                result="succeeded" if status == "completed" else status,
                reason_code="normal" if status == "completed" else "recording_failed",
                duration_ms=duration_ms,
                details={
                    "recording_id": recording_id,
                    "phase": phase,
                    "storage_key": storage_key,
                },
            ),
            commit=False,
        )
        await db.commit()
        return True

    # ─────────── Read ───────────

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        direction: str | None = None,
        call_source: str | None = None,
        lifecycle_status: str | None = None,
        finalization_status: str | None = None,
        actual_reception_type: str | None = None,
        call_result: str | None = None,
        hangup_party: str | None = None,
        hangup_reason_code: str | None = None,
        initiator_agent_id: int | None = None,
        last_serving_agent_id: int | None = None,
        user_id: int | None = None,
        last_queue_type: str | None = None,
        last_queue_id: int | None = None,
        recording_status: str | None = None,
        satisfaction_results: list[str] | None = None,
        satisfaction_trigger_sources: list[str] | None = None,
        keyword: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        min_total_duration_ms: int | None = None,
        max_total_duration_ms: int | None = None,
        min_customer_ring_duration_ms: int | None = None,
        max_customer_ring_duration_ms: int | None = None,
        min_agent_wait_duration_ms: int | None = None,
        max_agent_wait_duration_ms: int | None = None,
        min_customer_agent_talk_duration_ms: int | None = None,
        max_customer_agent_talk_duration_ms: int | None = None,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        CallRecordService._validate_list_filters(
            start_time=start_time,
            end_time=end_time,
            duration_ranges=(
                (min_total_duration_ms, max_total_duration_ms),
                (min_customer_ring_duration_ms, max_customer_ring_duration_ms),
                (min_agent_wait_duration_ms, max_agent_wait_duration_ms),
                (
                    min_customer_agent_talk_duration_ms,
                    max_customer_agent_talk_duration_ms,
                ),
            ),
        )
        scope_predicate = (
            DataScopeService.build_call_record_predicate(principal)
            if principal is not None
            else None
        )
        rows, total = await CallRecordRepository.get_paginated(
            db,
            tenant_id,
            page=page,
            per_page=per_page,
            direction=direction,
            call_source=call_source,
            lifecycle_status=lifecycle_status,
            finalization_status=finalization_status,
            actual_reception_type=actual_reception_type,
            call_result=call_result,
            hangup_party=hangup_party,
            hangup_reason_code=hangup_reason_code,
            initiator_agent_id=initiator_agent_id,
            last_serving_agent_id=last_serving_agent_id,
            user_id=user_id,
            last_queue_type=last_queue_type,
            last_queue_id=last_queue_id,
            recording_status=recording_status,
            satisfaction_results=satisfaction_results,
            satisfaction_trigger_sources=satisfaction_trigger_sources,
            keyword=keyword,
            start_time=start_time,
            end_time=end_time,
            min_total_duration_ms=min_total_duration_ms,
            max_total_duration_ms=max_total_duration_ms,
            min_customer_ring_duration_ms=min_customer_ring_duration_ms,
            max_customer_ring_duration_ms=max_customer_ring_duration_ms,
            min_agent_wait_duration_ms=min_agent_wait_duration_ms,
            max_agent_wait_duration_ms=max_agent_wait_duration_ms,
            min_customer_agent_talk_duration_ms=min_customer_agent_talk_duration_ms,
            max_customer_agent_talk_duration_ms=max_customer_agent_talk_duration_ms,
            scope_predicate=scope_predicate,
        )
        agent_ids = sorted(
            {
                agent_id
                for row in rows
                for agent_id in (row.initiator_agent_id, row.last_serving_agent_id)
                if agent_id is not None
            }
        )
        agents = await _employee_name_snapshots(db, tenant_id, agent_ids)
        users = await _load_user_map(db, tenant_id, [r.user_id for r in rows if r.user_id])
        workspace_contexts = (
            await CallWorkspaceContextService.get_auto_outbound_contexts(
                db,
                tenant_id=tenant_id,
                call_records=rows,
            )
        )
        items = []
        for row in rows:
            queue = await _last_queue_brief(db, row)
            item = _to_list_item(
                row,
                agents,
                users.get(row.user_id) if row.user_id else None,
                queue,
            )
            item.update(workspace_contexts.get(row.id, {}))
            items.append(item)
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": items, "total": total, "page": page, "per_page": per_page, "pages": pages,
        }

    @staticmethod
    async def get_filter_options(
        db: AsyncSession,
        tenant_id: int,
        principal: EffectivePrincipal,
    ) -> dict:
        """Return agent and queue options allowed by call-record data scope."""
        scope = DataScopeService.get_scope(principal, RESOURCE_CALL_RECORD)
        if scope == "self":
            return {"agents": [], "queues": []}

        employee_ids: list[int] | None = None
        group_ids: list[int] | None = None
        if scope == "group":
            peer_ids = await DataScopeService.get_group_peer_employee_ids(
                db, principal.group_ids
            )
            employee_ids = sorted(set(peer_ids) | {principal.user_id})
            group_ids = principal.group_ids

        employees = await EmployeeRepository.list_active_filter_options(
            db,
            tenant_id,
            employee_ids,
        )
        groups = await EmployeeGroupRepository.list_filter_options(
            db,
            tenant_id,
            group_ids,
        )
        agents = [
            {
                "id": employee.id,
                "name": employee.name
                or employee.display_name
                or employee.username,
            }
            for employee in employees
        ]
        queues = [
            {
                "queue_type": "employee_group",
                "queue_id": group.id,
                "name": group.name,
            }
            for group in groups
        ]
        queues.extend(
            {
                "queue_type": "employee",
                "queue_id": employee.id,
                "name": employee.name
                or employee.display_name
                or employee.username,
            }
            for employee in employees
        )
        return {"agents": agents, "queues": queues}

    @staticmethod
    def _validate_list_filters(
        *,
        start_time: datetime | None,
        end_time: datetime | None,
        duration_ranges: tuple[tuple[int | None, int | None], ...],
    ) -> None:
        """Validate date and duration filters shared by list and export."""
        if start_time is not None and end_time is not None:
            if start_time > end_time:
                raise ValidationError("Start time cannot be later than end time")
            if end_time - start_time > timedelta(days=90):
                raise ValidationError("Date range cannot exceed 90 days")
        for minimum, maximum in duration_ranges:
            if minimum is not None and minimum < 0:
                raise ValidationError("Minimum duration cannot be negative")
            if maximum is not None and maximum < 0:
                raise ValidationError("Maximum duration cannot be negative")
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValidationError(
                    "Minimum duration cannot exceed maximum duration"
                )

    @staticmethod
    async def get_by_public_id(
        db: AsyncSession,
        public_id,
        tenant_id: int,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        row = await CallRecordRepository.get_by_public_id(db, public_id, tenant_id)
        if not row:
            raise NotFoundError("Call record not found")
        if principal is not None:
            await DataScopeService.assert_call_record_in_scope(db, principal, row)
        agent_ids = [row.initiator_agent_id, row.last_serving_agent_id]
        agents = await _employee_name_snapshots(db, tenant_id, agent_ids)
        user_map = await _load_user_map(db, tenant_id, [row.user_id] if row.user_id else [])
        candidates = await CallUserAssociationService.candidate_users(db, tenant_id, row)
        related_tickets = await TicketRepository.list_by_call_record_id(db, tenant_id, row.id)
        recordings = await _recording_items(db, row.id)
        from app.services.call_satisfaction_projection_service import (
            CallSatisfactionProjectionService,
        )

        satisfaction = await CallSatisfactionProjectionService.detail(
            db, call_record_id=row.id
        )
        return _to_detail(
            row,
            agents,
            user_map.get(row.user_id) if row.user_id else None,
            candidates,
            related_tickets,
            await _last_queue_brief(db, row),
            recordings,
            satisfaction,
        )

    @staticmethod
    async def get_scoped_row_by_public_id(
        db: AsyncSession,
        public_id,
        tenant_id: int,
        principal: EffectivePrincipal,
    ):
        row = await CallRecordRepository.get_by_public_id(db, public_id, tenant_id)
        if row is None:
            raise NotFoundError("Call record not found")
        await DataScopeService.assert_call_record_in_scope(db, principal, row)
        return row


async def _best_effort_identify_user(
    db: AsyncSession,
    tenant_id: int,
    row,
    *,
    actor_id: int | None = None,
) -> None:
    try:
        await CallUserAssociationService.identify_for_record(
            db, tenant_id, row, actor_id=actor_id
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to identify user for call_record_id=%s", row.id)


async def _load_user_map(db: AsyncSession, tenant_id: int, user_ids: list[int]) -> dict[int, User]:
    users = await UserRepository.list_by_ids(db, tenant_id, user_ids)
    return {user.id: user for user in users}


async def _employee_name_snapshots(
    db: AsyncSession,
    tenant_id: int,
    employee_ids: list[int | None],
) -> dict[int, str]:
    ids = sorted({employee_id for employee_id in employee_ids if employee_id is not None})
    employees = await EmployeeRepository.get_by_ids(db, ids)
    return {
        employee.id: (
            employee.display_name or employee.nickname or employee.name or employee.username
        )
        for employee in employees
        if employee.tenant_id == tenant_id
    }


async def _queue_record_brief(
    db: AsyncSession,
    tenant_id: int,
    queue_type: str,
    queue_id: int,
) -> dict | None:
    if queue_type == QueueType.EMPLOYEE.value:
        result = await db.execute(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.id == queue_id,
            )
        )
        employee = result.scalar_one_or_none()
        if employee is None:
            return None
        name = employee.display_name or employee.nickname or employee.name or employee.username
    elif queue_type == QueueType.EMPLOYEE_GROUP.value:
        result = await db.execute(
            select(EmployeeGroup).where(
                EmployeeGroup.tenant_id == tenant_id,
                EmployeeGroup.id == queue_id,
            )
        )
        group = result.scalar_one_or_none()
        name = group.name if group else None
    else:
        return None

    if not name:
        return None
    return {"queue_type": queue_type, "queue_id": queue_id, "name": name}


async def _add_agent_access_scopes(
    db: AsyncSession,
    row,
    agent_id: int,
    *,
    reason: str,
    source_event_id: str,
) -> None:
    await CallRecordAccessScopeRepository.add(
        db,
        tenant_id=row.tenant_id,
        call_record_id=row.id,
        subject_type="employee",
        subject_id=agent_id,
        reason=reason,
        source_event_id=source_event_id,
        commit=False,
    )
    group_ids_by_employee = await EmployeeRepository.get_group_ids_by_employee_ids(
        db, [agent_id]
    )
    for group_id in group_ids_by_employee.get(agent_id, []):
        await CallRecordAccessScopeRepository.add(
            db,
            tenant_id=row.tenant_id,
            call_record_id=row.id,
            subject_type="employee_group",
            subject_id=group_id,
            reason=reason,
            source_event_id=source_event_id,
            commit=False,
        )


def _aggregate_recording_status(recordings: list) -> str:
    statuses = {recording.status for recording in recordings}
    if "recording" in statuses:
        return "recording"
    if "partial" in statuses or ({"completed", "failed"} <= statuses):
        return "partial"
    if "completed" in statuses:
        return "completed"
    if "failed" in statuses:
        return "failed"
    return "none"


async def _last_queue_brief(db: AsyncSession, row) -> dict | None:
    if row.last_queue_type is None or row.last_queue_id is None:
        return None
    return await _queue_record_brief(
        db,
        row.tenant_id,
        row.last_queue_type,
        row.last_queue_id,
    )


async def _recording_items(db: AsyncSession, call_record_id: int) -> list[dict]:
    rows = await CallRecordingRepository.list_for_call(db, call_record_id)
    storage = None
    items: list[dict] = []
    for row in rows:
        access_url = None
        if row.storage_key and row.status in {"completed", "partial"}:
            try:
                storage = storage or create_storage_client()
                access_url = await storage.get_temporary_url(
                    row.storage_key,
                    expires_seconds=300,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to issue recording URL recording_id=%s",
                    row.recording_id,
                )
        items.append(
            {
                "recording_id": row.recording_id,
                "call_leg_id": row.call_leg_id,
                "phase": row.phase,
                "status": row.status,
                "started_at": row.started_at,
                "ended_at": row.ended_at,
                "duration_ms": row.duration_ms,
                "access_url": access_url,
            }
        )
    return items


def _to_list_item(
    row,
    agent_names: dict[int, str] | None,
    user: User | None = None,
    last_queue: dict | None = None,
) -> dict:
    agent_names = agent_names or {}
    user_brief = CallUserAssociationService.brief_user(user)
    return {
        "id": row.id,
        "public_id": row.public_id,
        "call_id": row.call_id,
        "direction": row.direction,
        "call_source": row.call_source,
        "customer_number": row.customer_number,
        "service_number": row.service_number,
        "lifecycle_status": row.lifecycle_status,
        "finalization_status": row.finalization_status,
        "actual_reception_type": row.actual_reception_type,
        "call_result": row.call_result,
        "hangup_party": row.hangup_party,
        "hangup_reason_code": row.hangup_reason_code,
        "initiator_agent_id": row.initiator_agent_id,
        "initiator_agent_name": agent_names.get(row.initiator_agent_id),
        "last_serving_agent_id": row.last_serving_agent_id,
        "last_serving_agent_name": agent_names.get(row.last_serving_agent_id),
        "user_id": row.user_id,
        "user_public_id": user_brief["public_id"] if user_brief else None,
        "user_name": user_brief["name"] if user_brief else None,
        "user_phone": user_brief["phone"] if user_brief else None,
        "user_association_status": CallUserAssociationService.status_for_record(row),
        "started_at": row.started_at,
        "customer_connected_at": row.customer_connected_at,
        "first_agent_connected_at": row.first_agent_connected_at,
        "human_service_requested_at": getattr(row, "human_service_requested_at", None),
        "first_agent_wait_started_at": getattr(row, "first_agent_wait_started_at", None),
        "first_agent_offer_started_at": getattr(row, "first_agent_offer_started_at", None),
        "bot_handoff_requested_at": getattr(row, "bot_handoff_requested_at", None),
        "bot_handoff_succeeded_at": getattr(row, "bot_handoff_succeeded_at", None),
        "ended_at": row.ended_at,
        "human_service_ended_at": row.human_service_ended_at,
        "hangup_stage": getattr(row, "hangup_stage", None),
        "short_abandon_threshold_ms": getattr(row, "short_abandon_threshold_ms", None),
        "total_duration_ms": row.total_duration_ms,
        "customer_ring_duration_ms": row.customer_ring_duration_ms,
        "agent_wait_duration_ms": row.agent_wait_duration_ms,
        "customer_agent_talk_duration_ms": row.customer_agent_talk_duration_ms,
        "satisfaction_result": row.satisfaction_result,
        "satisfaction_trigger_source": row.satisfaction_trigger_source,
        "satisfaction_primary_option_id": row.satisfaction_primary_option_id,
        "satisfaction_primary_option_label": row.satisfaction_primary_option_label,
        "satisfaction_answer_count": row.satisfaction_answer_count,
        "satisfaction_duration_ms": row.satisfaction_duration_ms,
        "recording_status": row.recording_status,
        "last_queue": last_queue,
    }


def _to_detail(
    row,
    agent_names: dict[int, str] | None,
    user: User | None = None,
    candidates: list[User] | None = None,
    related_tickets: list | None = None,
    last_queue: dict | None = None,
    recordings: list[dict] | None = None,
    satisfaction: dict | None = None,
) -> dict:
    agent_names = agent_names or {}
    user_brief = CallUserAssociationService.brief_user(user)
    return {
        "id": row.id,
        "public_id": row.public_id,
        "call_id": row.call_id,
        "conversation_id": row.conversation_id,
        "root_call_id": row.root_call_id,
        "direction": row.direction,
        "call_source": row.call_source,
        "custom_business_info": row.custom_business_info,
        "external_context": row.external_context,
        "customer_number": row.customer_number,
        "service_number": row.service_number,
        "voice_flow_id": row.voice_flow_id,
        "voice_flow_version_id": row.voice_flow_version_id,
        "initiator_agent_id": row.initiator_agent_id,
        "initiator_agent_name": agent_names.get(row.initiator_agent_id),
        "last_serving_agent_id": row.last_serving_agent_id,
        "last_serving_agent_name": agent_names.get(row.last_serving_agent_id),
        "lifecycle_status": row.lifecycle_status,
        "finalization_status": row.finalization_status,
        "result_rule_version": row.result_rule_version,
        "finalized_at": row.finalized_at,
        "actual_reception_type": row.actual_reception_type,
        "call_result": row.call_result,
        "hangup_party": row.hangup_party,
        "hangup_reason_code": row.hangup_reason_code,
        "user_id": row.user_id,
        "user_public_id": user_brief["public_id"] if user_brief else None,
        "user_name": user_brief["name"] if user_brief else None,
        "user_phone": user_brief["phone"] if user_brief else None,
        "user_association_status": CallUserAssociationService.status_for_record(row),
        "associated_user_candidates": [
            brief
            for candidate in (candidates or [])
            if (brief := CallUserAssociationService.brief_user(candidate)) is not None
        ],
        "started_at": row.started_at,
        "customer_connected_at": row.customer_connected_at,
        "first_agent_connected_at": row.first_agent_connected_at,
        "human_service_requested_at": getattr(row, "human_service_requested_at", None),
        "first_agent_wait_started_at": getattr(row, "first_agent_wait_started_at", None),
        "first_agent_offer_started_at": getattr(row, "first_agent_offer_started_at", None),
        "bot_handoff_requested_at": getattr(row, "bot_handoff_requested_at", None),
        "bot_handoff_succeeded_at": getattr(row, "bot_handoff_succeeded_at", None),
        "ended_at": row.ended_at,
        "human_service_ended_at": row.human_service_ended_at,
        "hangup_stage": getattr(row, "hangup_stage", None),
        "short_abandon_threshold_ms": getattr(row, "short_abandon_threshold_ms", None),
        "total_duration_ms": row.total_duration_ms,
        "customer_ring_duration_ms": row.customer_ring_duration_ms,
        "agent_wait_duration_ms": row.agent_wait_duration_ms,
        "customer_agent_talk_duration_ms": row.customer_agent_talk_duration_ms,
        "satisfaction_result": row.satisfaction_result,
        "satisfaction_trigger_source": row.satisfaction_trigger_source,
        "satisfaction_primary_option_id": row.satisfaction_primary_option_id,
        "satisfaction_primary_option_label": row.satisfaction_primary_option_label,
        "satisfaction_answer_count": row.satisfaction_answer_count,
        "satisfaction_duration_ms": row.satisfaction_duration_ms,
        "satisfaction": satisfaction,
        "recording_status": row.recording_status,
        "recordings": recordings or [],
        "last_queue": last_queue,
        "related_tickets": [
            {
                "id": ticket.id,
                "ticket_number": ticket.ticket_number,
            }
            for ticket in (related_tickets or [])
        ],
    }


def _call_created_details(
    row,
    raw_from_number: str | None,
    raw_to_number: str | None,
) -> dict:
    return {
        "public_id": str(row.public_id),
        "direction": row.direction,
        "call_source": row.call_source,
        "caller_number": raw_from_number,
        "callee_number": raw_to_number,
        "customer_number": row.customer_number,
        "service_number": row.service_number,
        "conversation_id": row.conversation_id,
        "root_call_id": row.root_call_id,
    }


async def _append_trajectory_event(
    db: AsyncSession,
    call_record_id: int,
    payload: CallEventCreate,
) -> None:
    try:
        await CallTrajectoryService.append_event(
            db, call_record_id=call_record_id, payload=payload
        )
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.exception(
            "Failed to append call trajectory event call_record_id=%s event_type=%s",
            call_record_id,
            payload.event_type,
        )
