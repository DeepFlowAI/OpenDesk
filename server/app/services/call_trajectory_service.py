"""Business rules for call trajectory writes, reads, and aggregation."""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.call_event import CallEvent
from app.repositories.call_event_repository import CallEventRepository
from app.repositories.call_record_access_scope_repository import (
    CallRecordAccessScopeRepository,
)
from app.repositories.call_record_repository import CallRecordRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.call_trajectory import CallEventCreate
from app.schemas.permission import EffectivePrincipal
from app.services.call_hangup_classifier import HangupSignal, classify_hangup
from app.services.data_scope_service import DataScopeService

logger = logging.getLogger(__name__)

EVENT_CATEGORIES = frozenset(
    {
        "lifecycle", "routing", "ivr", "bot", "queue", "reception", "control",
        "transfer", "consult", "conference", "supervisor", "media", "system",
    }
)
EVENT_SOURCES = frozenset({"opendesk", "flowkit", "voicespeed", "carrier", "reconciliation"})
ACTOR_TYPES = frozenset(
    {"customer", "agent", "supervisor", "bot", "system", "carrier", "external_party"}
)
_FORBIDDEN_DETAIL_KEYS = frozenset(
    {"authorization", "credential", "credentials", "dtmf", "dtmf_digits", "digits", "password", "secret", "token"}
)


class CallTrajectoryService:
    """Coordinate append-only writes and scoped trajectory reads."""

    @staticmethod
    async def append_event(
        db: AsyncSession,
        *,
        call_record_id: int,
        payload: CallEventCreate,
        commit: bool = True,
    ) -> tuple[CallEvent, bool]:
        call_record = await CallRecordRepository.get_by_id_unscoped(db, call_record_id)
        if call_record is None:
            raise NotFoundError("Call record not found")
        _validate_taxonomy(payload)
        data = payload.model_dump()
        data["details"] = _sanitize_details(data.get("details") or {})
        event, created = await CallEventRepository.append(
            db,
            call_record=call_record,
            data=data,
            commit=False,
        )
        if created:
            await _project_event(db, call_record, payload)
        if commit:
            await db.commit()
            await db.refresh(event)
        return event, created

    @staticmethod
    async def append_for_call_id(
        db: AsyncSession,
        *,
        tenant_id: int,
        call_id: str,
        event_type: str,
        event_category: str,
        actor_type: str = "system",
        source: str = "opendesk",
        event_id: str | None = None,
        occurred_at: datetime | None = None,
        **fields: Any,
    ) -> CallEvent | None:
        """Append an internal event when a producer only has the media call ID."""
        call_record = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if call_record is None:
            return None
        payload = CallEventCreate(
            event_id=event_id or f"{source}:{event_type}:{uuid4().hex}",
            event_type=event_type,
            event_category=event_category,
            actor_type=actor_type,
            source=source,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            **fields,
        )
        row, _ = await CallTrajectoryService.append_event(
            db, call_record_id=call_record.id, payload=payload
        )
        return row

    @staticmethod
    async def append_for_call_id_best_effort(**kwargs: Any) -> None:
        """Write on a short session without allowing telemetry failure to break a call."""
        from app.db.session import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as db:
                await CallTrajectoryService.append_for_call_id(db, **kwargs)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Call trajectory append failed call_id=%s event_type=%s",
                kwargs.get("call_id"),
                kwargs.get("event_type"),
            )

    @staticmethod
    async def get_trajectory(
        db: AsyncSession,
        *,
        public_id: UUID,
        tenant_id: int,
        principal: EffectivePrincipal,
    ) -> dict[str, Any]:
        call_record = await CallRecordRepository.get_by_public_id(
            db,
            public_id,
            tenant_id,
        )
        if call_record is None:
            raise NotFoundError("Call record not found")
        await DataScopeService.assert_call_record_in_scope(db, principal, call_record)

        events = await CallEventRepository.list_for_call(db, call_record.id)
        settlement = next((event for event in reversed(events) if event.event_type == "call_ended"), None)
        warnings = _trajectory_warnings(call_record.lifecycle_status, events, settlement)
        event_responses = [_event_response_data(event) for event in events]
        return {
            "call_record_public_id": call_record.public_id,
            "call_id": call_record.call_id,
            "lifecycle_status": call_record.lifecycle_status,
            "is_live": call_record.lifecycle_status == "active",
            "is_complete": (
                call_record.lifecycle_status == "ended"
                and call_record.finalization_status == "completed"
                and not warnings
            ),
            "last_updated_at": events[-1].created_at if events else None,
            "total": len(events),
            "events": event_responses,
            "operations": _group_operations(events),
            "settlement": _event_response_data(settlement) if settlement else None,
            "warnings": warnings,
        }

    @staticmethod
    async def build_settlement_details(
        db: AsyncSession,
        *,
        call_record_id: int,
        ended_at: datetime,
        hangup_reason: str | None,
        hangup_party: str | None = None,
        hangup_details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Derive the final call settlement from immutable trajectory facts."""
        call_record = await CallRecordRepository.get_by_id_unscoped(db, call_record_id)
        if call_record is None:
            raise NotFoundError("Call record not found")
        events = await CallEventRepository.list_for_call(db, call_record_id)
        phase_durations = _phase_durations(events)
        hangup_stage = _hangup_stage(events)
        # The telephony kernel only reports a raw reason string — it has no
        # notion of business roles — so an explicit party is the exception and
        # the reason has to be classified when it is absent.
        provider_details = hangup_details or {}
        classification = classify_hangup(
            HangupSignal(
                reason=hangup_reason,
                sip_status=_optional_int(provider_details.get("sip_status")),
                sip_reason=_optional_text(provider_details.get("sip_reason")),
                sip_warning=_optional_text(provider_details.get("sip_warning")),
                sip_reason_hdr=_optional_text(provider_details.get("sip_reason_hdr")),
            )
        )
        resolved_hangup_party = hangup_party or classification.party
        if resolved_hangup_party == "unknown":
            resolved_hangup_party = _hangup_party(hangup_reason)
        reason_code = classification.code
        if (
            reason_code == "unknown"
            and hangup_party in {"customer", "agent", "supervisor", "bot"}
            and not any(
                provider_details.get(key)
                for key in ("sip_status", "sip_reason", "sip_warning", "sip_reason_hdr")
            )
        ):
            reason_code = _normalize_hangup_reason(hangup_reason, hangup_party)
        call_result = _call_result(
            call_record.direction,
            events,
            reason_code,
            resolved_hangup_party,
            phase_durations,
        )
        started_at = next(
            (event.occurred_at for event in events if event.event_type == "call_created"),
            call_record.started_at,
        )
        total_duration_ms = (
            max(0, int((ended_at - started_at).total_seconds() * 1000))
            if started_at is not None
            else None
        )
        talk_duration = phase_durations.get("talk")
        hold_duration = phase_durations.get("hold")
        consult_duration = phase_durations.get("consult")
        customer_agent_talk_duration_ms = (
            max(0, talk_duration - (hold_duration or 0) - (consult_duration or 0))
            if talk_duration is not None
            else None
        )
        required_durations = (
            total_duration_ms,
            phase_durations.get("agent_waiting"),
            customer_agent_talk_duration_ms,
        )
        projection_complete = not any(
            event.event_type == "trajectory_gap_detected" for event in events
        ) and all(value is not None for value in required_durations)
        details: dict[str, Any] = {
            "call_result": call_result,
            "hangup_party": resolved_hangup_party,
            "hangup_stage": hangup_stage,
            "hangup_reason_code": reason_code,
            "raw_hangup_reason": hangup_reason,
            "sip_status": _optional_int(provider_details.get("sip_status")),
            "sip_reason": _limited_text(provider_details.get("sip_reason")),
            "sip_warning": _limited_text(provider_details.get("sip_warning")),
            "sip_reason_hdr": _limited_text(provider_details.get("sip_reason_hdr")),
            "sip_call_id": _limited_text(provider_details.get("sip_call_id")),
            "hangup_match_strategy": classification.strategy,
            "hangup_match_score": classification.score,
            "hangup_match_margin": classification.margin,
            "hangup_classification_version": classification.version,
            "total_duration_ms": total_duration_ms,
            "customer_ring_duration_ms": (
                0
                if call_record.direction == "inbound"
                else phase_durations.get("customer_ringing")
            ),
            "agent_wait_duration_ms": phase_durations.get("agent_waiting"),
            "customer_agent_talk_duration_ms": customer_agent_talk_duration_ms,
            "phase_durations_ms": phase_durations,
            "short_abandon_threshold_ms": 5_000 if call_result == "customer_short_abandon" else None,
            "result_rule_version": 2,
            "actual_reception_type": _actual_reception_type(events),
            "projection_complete": projection_complete,
        }
        return details

    @staticmethod
    async def reconcile_open_intervals(
        db: AsyncSession,
        *,
        call_record_id: int,
        ended_at: datetime,
        commit: bool = True,
    ) -> int:
        """Close trusted open intervals with explicit synthetic end events."""
        events = await CallEventRepository.list_for_call(db, call_record_id)
        close_types = {
            "customer_ringing_started": "customer_ringing_ended",
            "ivr_entered": "ivr_exited",
            "bot_started": "bot_ended",
            "queue_entered": "queue_exited",
            "reception_started": "reception_ended",
            "hold_started": "hold_ended",
            "mute_started": "mute_ended",
            "agent_offer_started": "agent_offer_canceled",
            "consult_connected": "consult_ended",
            "conference_merged": "conference_ended",
            "recording_started": "recording_partial",
            "transcription_started": "transcription_failed",
        }
        matching_end_types = {
            start_type: _PHASE_PAIRS.get(phase, ({start_type}, {end_type}))[1]
            for start_type, end_type in close_types.items()
            for phase in [_phase_for_start(start_type)]
        }
        open_events: dict[str, list[CallEvent]] = defaultdict(list)
        for event in events:
            if event.event_type in close_types:
                open_events[event.event_type].append(event)
                continue
            for start_type, end_types in matching_end_types.items():
                if event.event_type in end_types and open_events[start_type]:
                    open_events[start_type].pop(0)
                    break

        created = 0
        for start_type, starts in open_events.items():
            for start in starts:
                duration_ms = max(0, int((ended_at - start.occurred_at).total_seconds() * 1000))
                end_type = close_types[start_type]
                payload = CallEventCreate(
                    event_id=_reconciliation_event_id(end_type, start.event_id),
                    event_type=end_type,
                    event_category=start.event_category,
                    actor_type="system",
                    source="reconciliation",
                    occurred_at=ended_at,
                    operation_id=start.operation_id,
                    call_leg_id=start.call_leg_id,
                    parent_leg_id=start.parent_leg_id,
                    participant_role=start.participant_role,
                    actor_id=start.actor_id,
                    actor_name_snapshot=start.actor_name_snapshot,
                    target_type=start.target_type,
                    target_id=start.target_id,
                    target_name_snapshot=start.target_name_snapshot,
                    queue_type=start.queue_type,
                    queue_id=start.queue_id,
                    queue_name_snapshot=start.queue_name_snapshot,
                    result="disconnected",
                    reason_code="call_ended",
                    duration_ms=duration_ms,
                    is_synthetic=True,
                    details={"synthesized_from_event_id": start.event_id},
                )
                _, was_created = await CallTrajectoryService.append_event(
                    db,
                    call_record_id=call_record_id,
                    payload=payload,
                    commit=commit,
                )
                created += int(was_created)
        await CallTrajectoryService.append_event(
            db,
            call_record_id=call_record_id,
            payload=CallEventCreate(
                event_id=f"reconciliation:trajectory-reconciled:{call_record_id}",
                event_type="trajectory_reconciled",
                event_category="system",
                actor_type="system",
                source="reconciliation",
                occurred_at=ended_at,
                result="succeeded",
                details={"synthetic_event_count": created},
            ),
            commit=commit,
        )
        return created


async def _project_event(
    db: AsyncSession,
    call_record,
    payload: CallEventCreate,
) -> None:
    """Apply list and access projections in the same transaction as the event."""
    patch: dict[str, Any] = {}
    if payload.event_type == "customer_connected":
        if call_record.customer_connected_at is None:
            patch["customer_connected_at"] = payload.occurred_at
    elif payload.event_type == "route_matched":
        voice_flow_id = payload.details.get("voice_flow_id")
        voice_flow_version_id = payload.details.get("voice_flow_version_id")
        if isinstance(voice_flow_id, int):
            patch["voice_flow_id"] = voice_flow_id
        if isinstance(voice_flow_version_id, int):
            patch["voice_flow_version_id"] = voice_flow_version_id
    elif payload.event_type == "queue_entered":
        if payload.queue_type and payload.queue_id is not None:
            patch["last_queue_type"] = payload.queue_type
            patch["last_queue_id"] = payload.queue_id
            if payload.queue_type in {"employee", "employee_group"}:
                await CallRecordAccessScopeRepository.add(
                    db,
                    tenant_id=call_record.tenant_id,
                    call_record_id=call_record.id,
                    subject_type=payload.queue_type,
                    subject_id=payload.queue_id,
                    reason="queued",
                    source_event_id=payload.source_event_id or payload.event_id,
                    commit=False,
                )
    elif payload.event_type == "reception_started":
        agent_id = _positive_int(payload.target_id or payload.actor_id)
        if agent_id is not None:
            patch["last_serving_agent_id"] = agent_id
            if call_record.first_agent_connected_at is None:
                patch["first_agent_connected_at"] = payload.occurred_at
            await CallRecordAccessScopeRepository.add(
                db,
                tenant_id=call_record.tenant_id,
                call_record_id=call_record.id,
                subject_type="employee",
                subject_id=agent_id,
                reason="served",
                source_event_id=payload.source_event_id or payload.event_id,
                commit=False,
            )
            groups = await EmployeeRepository.get_group_ids_by_employee_ids(
                db, [agent_id]
            )
            for group_id in groups.get(agent_id, []):
                await CallRecordAccessScopeRepository.add(
                    db,
                    tenant_id=call_record.tenant_id,
                    call_record_id=call_record.id,
                    subject_type="employee_group",
                    subject_id=group_id,
                    reason="served",
                    source_event_id=payload.source_event_id or payload.event_id,
                    commit=False,
                )
    elif payload.event_type == "user_associated":
        user_id = _positive_int(payload.target_id)
        if user_id is not None:
            patch["user_id"] = user_id
    elif payload.event_type == "user_disassociated":
        patch["user_id"] = None
    elif payload.event_type == "human_service_ended":
        if call_record.human_service_ended_at is None:
            patch["human_service_ended_at"] = payload.occurred_at

    if patch:
        await CallRecordRepository.update(
            db,
            call_record,
            patch,
            commit=False,
        )


def _reconciliation_event_id(end_type: str, start_event_id: str) -> str:
    """Build a stable synthetic event id that always fits the 96-char limit."""
    digest = hashlib.sha256(start_event_id.encode("utf-8")).hexdigest()[:32]
    return f"reconciliation:{end_type}:{digest}"


def _positive_int(value: object) -> int | None:
    if not isinstance(value, (int, str)):
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _validate_taxonomy(payload: CallEventCreate) -> None:
    if payload.event_category not in EVENT_CATEGORIES:
        raise ValidationError(f"Unsupported call event category: {payload.event_category}")
    if payload.source not in EVENT_SOURCES:
        raise ValidationError(f"Unsupported call event source: {payload.source}")
    if payload.actor_type not in ACTOR_TYPES:
        raise ValidationError(f"Unsupported call event actor type: {payload.actor_type}")
    if payload.occurred_at.tzinfo is None or payload.occurred_at.utcoffset() is None:
        raise ValidationError("Call event occurred_at must be timezone-aware")


def _sanitize_details(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_details(item)
            for key, item in value.items()
            if key.lower() not in _FORBIDDEN_DETAIL_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_details(item) for item in value]
    return value


def _group_operations(events: list[CallEvent]) -> list[dict[str, Any]]:
    grouped: dict[str, list[CallEvent]] = defaultdict(list)
    for event in events:
        if event.operation_id:
            grouped[event.operation_id].append(event)

    operations: list[dict[str, Any]] = []
    for operation_id, rows in grouped.items():
        start = rows[0].occurred_at
        end = rows[-1].occurred_at
        explicit_duration = next(
            (row.duration_ms for row in reversed(rows) if row.duration_ms is not None), None
        )
        operations.append(
            {
                "operation_id": operation_id,
                "event_ids": [row.event_id for row in rows],
                "started_at": start,
                "ended_at": end,
                "duration_ms": explicit_duration
                if explicit_duration is not None
                else max(0, int((end - start).total_seconds() * 1000)),
                "result": next((row.result for row in reversed(rows) if row.result), None),
            }
        )
    return operations


def _trajectory_warnings(
    lifecycle_status: str,
    events: list[CallEvent],
    settlement: CallEvent | None,
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if events and not any(event.event_type == "call_created" for event in events):
        warnings.append({"code": "missing_call_created", "message": "Call start event is missing"})
    if lifecycle_status == "ended" and events and settlement is None:
        warnings.append({"code": "missing_call_ended", "message": "Final settlement event is missing"})
    if any(event.event_type == "trajectory_gap_detected" for event in events):
        warnings.append({"code": "trajectory_gap", "message": "Part of the call trajectory may be incomplete"})
    return warnings


def _event_response_data(event: CallEvent) -> dict[str, Any]:
    data = {
        column.name: getattr(event, column.name)
        for column in CallEvent.__table__.columns
    }
    details = dict(data.get("details") or {})
    details.pop("storage_key", None)
    data["details"] = details
    return data


_PHASE_PAIRS: dict[str, tuple[set[str], set[str]]] = {
    "customer_ringing": (
        {"customer_ringing_started"},
        {"customer_connected", "customer_ringing_ended"},
    ),
    "ivr": ({"ivr_entered"}, {"ivr_exited", "ivr_failed"}),
    "bot": ({"bot_started"}, {"bot_ended"}),
    "agent_waiting": ({"queue_entered"}, {"queue_exited", "queue_timeout", "queue_limit_reached"}),
    "agent_ringing": ({"agent_offer_started"}, {"agent_offer_accepted", "agent_offer_rejected", "agent_offer_timeout", "agent_offer_canceled"}),
    "talk": ({"reception_started"}, {"reception_ended", "human_service_ended"}),
    "hold": ({"hold_started"}, {"hold_ended"}),
    "consult": ({"consult_connected"}, {"consult_ended", "consult_failed", "consult_canceled"}),
    "conference": ({"conference_merged"}, {"conference_ended", "conference_failed"}),
}


def _phase_for_start(event_type: str) -> str:
    for phase, (starts, _ends) in _PHASE_PAIRS.items():
        if event_type in starts:
            return phase
    return event_type


def _phase_durations(events: list[CallEvent]) -> dict[str, int | None]:
    return {
        phase: _sum_event_intervals(events, starts, ends)
        for phase, (starts, ends) in _PHASE_PAIRS.items()
    }


def _sum_event_intervals(
    events: list[CallEvent], starts: set[str], ends: set[str]
) -> int | None:
    open_times: list[datetime] = []
    intervals: list[tuple[datetime, datetime]] = []
    experienced = False
    for event in events:
        if event.event_type in starts:
            experienced = True
            open_times.append(event.occurred_at)
        elif event.event_type in ends and open_times:
            started_at = open_times.pop(0)
            intervals.append((started_at, max(started_at, event.occurred_at)))
    if open_times:
        return None
    if not experienced:
        return 0
    if not intervals:
        return None
    intervals.sort(key=lambda item: item[0])
    merged: list[tuple[datetime, datetime]] = []
    for started_at, ended_at in intervals:
        if not merged or started_at > merged[-1][1]:
            merged.append((started_at, ended_at))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], ended_at))
    return sum(max(0, int((end - start).total_seconds() * 1000)) for start, end in merged)


_STAGE_BY_EVENT = {
    "customer_ringing_started": "customer_ringing",
    "ivr_entered": "ivr",
    "bot_started": "bot",
    "queue_entered": "agent_waiting",
    "agent_offer_started": "agent_ringing",
    "reception_started": "in_call",
    "hold_started": "hold",
    "hold_ended": "in_call",
    "transfer_started": "transfer",
    "consult_started": "consult",
    "conference_invite_started": "conference",
}


def _hangup_stage(events: list[CallEvent]) -> str:
    stage = "pre_route"
    for event in events:
        stage = _STAGE_BY_EVENT.get(event.event_type, stage)
    return stage or "unknown"


def _hangup_party(reason: str | None) -> str:
    normalized = (reason or "").lower()
    if any(token in normalized for token in ("supervisor", "force_hangup")):
        return "supervisor"
    if any(
        token in normalized
        for token in ("busy", "unreachable", "power_off", "invalid_number", "no_answer", "sip_")
    ):
        return "carrier"
    if any(token in normalized for token in ("caller", "customer", "remote_bye", "user_hangup", "media_timeout")):
        return "customer"
    if any(token in normalized for token in ("agent_hangup", "transferred", "supervisor_takeover_end")):
        return "agent"
    if "bot" in normalized and "failed" not in normalized:
        return "bot"
    if normalized:
        return "system"
    return "unknown"


def _call_result(
    direction: str,
    events: list[CallEvent],
    reason: str | None,
    party: str,
    phase_durations: dict[str, int | None],
) -> str:
    event_types = {event.event_type for event in events}
    normalized = (reason or "").lower()
    if "reception_started" in event_types:
        return "agent_answered"
    if direction == "outbound":
        if "busy" in normalized:
            return "customer_busy"
        if any(token in normalized for token in ("unreachable", "power_off")):
            return "customer_unreachable"
        if "invalid" in normalized:
            return "invalid_number"
        if any(token in normalized for token in ("no_answer", "timeout")):
            return "customer_no_answer"
    if "queue_entered" in event_types:
        waiting = phase_durations.get("agent_waiting")
        if party == "customer" and waiting is not None and waiting <= 5_000:
            return "customer_short_abandon"
        return "agent_no_answer"
    if "bot_started" in event_types:
        if party == "customer":
            return "bot_customer_hangup"
        if any(event.event_type == "bot_ended" and event.result == "succeeded" for event in events):
            return "bot_completed"
        return "failed" if "failed" in normalized else "bot_completed"
    if "ivr_entered" in event_types and party == "customer":
        return "ivr_customer_hangup"
    if "cancel" in normalized or "call_canceled" in event_types:
        return "canceled"
    return "failed"


def _normalize_hangup_reason(reason: str | None, party: str) -> str:
    normalized = (reason or "").lower()
    exact = {
        "no_agent_online": "no_agent_online",
        "queue_timeout": "queue_timeout",
        "drain_timeout": "drain_timeout",
        "supervisor_force_hangup": "supervisor_force_hangup",
        "bridge_failed": "bridge_failed",
        "media_failed": "media_failed",
        "reconnect_failed": "reconnect_failed",
        "customer_busy": "customer_busy",
        "invalid_number": "invalid_number",
        "no_route": "no_route",
        "no_flow_version": "no_flow_version",
        "offer_expired": "agent_no_answer",
    }
    if normalized in exact:
        return exact[normalized]
    if "no_answer" in normalized:
        return "customer_no_answer" if party == "carrier" else "agent_no_answer"
    if "busy" in normalized:
        return "customer_busy"
    if any(token in normalized for token in ("power_off", "unreachable")):
        return "customer_power_off"
    if party == "customer":
        return "customer_hangup"
    if party == "agent":
        return "agent_hangup"
    if party == "supervisor":
        return "supervisor_force_hangup"
    if party == "bot":
        return "bot_completed"
    if "cancel" in normalized:
        return "canceled"
    return "normal_completed" if not normalized else "unknown"


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _limited_text(value: Any, limit: int = 500) -> str | None:
    text = _optional_text(value)
    return text[:limit] if text else None


def _actual_reception_type(events: list[CallEvent]) -> str | None:
    event_types = {event.event_type for event in events}
    had_bot = "bot_started" in event_types
    had_agent = "reception_started" in event_types
    if had_bot and had_agent:
        return "bot_agent"
    if had_agent:
        return "agent"
    if had_bot:
        return "bot"
    if "ivr_entered" in event_types:
        return "ivr"
    return None
