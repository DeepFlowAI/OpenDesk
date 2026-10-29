"""Project employee reception and collaboration facts from call events."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_record import CallRecord
from app.repositories.call_agent_fact_repository import CallAgentFactRepository
from app.repositories.call_event_repository import CallEventRepository
from app.repositories.call_record_repository import CallRecordRepository


AGENT_FACT_EVENT_TYPES = frozenset(
    {
        "reception_started",
        "reception_ended",
        "human_service_ended",
        "hold_started",
        "hold_ended",
        "consult_started",
        "consult_connected",
        "consult_ended",
        "consult_failed",
        "consult_canceled",
        "transfer_started",
        "transfer_completed",
        "transfer_failed",
        "conference_merged",
        "conference_ended",
        "conference_failed",
        "call_ended",
    }
)


@dataclass
class AgentReceptionFact:
    started_event_id: str
    segment_ordinal: int
    agent_id: int | None
    agent_name_snapshot: str | None
    started_at: datetime
    entry_reason: str
    ended_event_id: str | None = None
    ended_at: datetime | None = None
    end_reason: str | None = None
    duration_ms: int | None = None
    talk_duration_ms: int | None = None
    hold_duration_ms: int | None = None
    consult_duration_ms: int | None = None
    held: bool = False
    result_reliable: bool = False


@dataclass
class AgentOperationFact:
    operation_key: str
    operation_type: str
    actor_agent_id: int | None
    actor_name_snapshot: str | None
    target_type: str | None
    target_id: str | None
    target_name_snapshot: str | None
    started_event_id: str
    started_at: datetime
    ended_event_id: str | None = None
    ended_at: datetime | None = None
    result: str | None = None
    result_reliable: bool = False


@dataclass
class _Interval:
    kind: str
    agent_id: int | None
    started_at: datetime
    ended_at: datetime | None = None


class CallAgentFactService:
    """Rebuild query facts for one call without report-time event scans."""

    @staticmethod
    async def project_for_call(db: AsyncSession, call_record_id: int) -> None:
        call_record = await CallRecordRepository.get_by_id_unscoped(db, call_record_id)
        if call_record is None:
            return
        events = await CallEventRepository.list_for_call(db, call_record_id)
        segments, operations = build_call_agent_facts(events)
        await CallAgentFactRepository.upsert_segments(
            db, [_segment_row(call_record, item) for item in segments]
        )
        await CallAgentFactRepository.upsert_operations(
            db, [_operation_row(call_record, item) for item in operations]
        )

    @staticmethod
    async def start_after_call_work(
        db: AsyncSession,
        *,
        tenant_id: int,
        call_id: str | None,
        agent_id: int,
        started_at: datetime | None = None,
    ) -> bool:
        if not call_id:
            return False
        call_record = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if call_record is None:
            return False
        # Finalization locks the parent before reception facts. Use the same
        # order so an ACW insert cannot hold a child while waiting for its parent.
        call_record = await CallRecordRepository.lock_by_id(db, call_record.id)
        if call_record is None:
            return False
        segment_id = await CallAgentFactRepository.latest_segment_id(
            db, call_record.id, agent_id
        )
        name = await _agent_snapshot(db, call_record, agent_id)
        await CallAgentFactRepository.start_after_call_work(
            db,
            {
                "tenant_id": tenant_id,
                "call_record_id": call_record.id,
                "reception_segment_id": segment_id,
                "agent_id": agent_id,
                "agent_name_snapshot": name,
                "started_at": started_at or datetime.now(timezone.utc),
                "result_reliable": False,
            },
        )
        return True

    @staticmethod
    async def close_after_call_work(
        db: AsyncSession,
        *,
        tenant_id: int,
        agent_id: int,
        call_id: str | None,
        end_reason: str,
        ended_at: datetime | None = None,
    ) -> bool:
        call_record_id = None
        if call_id:
            call_record = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
            call_record_id = call_record.id if call_record is not None else None
        return await CallAgentFactRepository.close_after_call_work(
            db,
            tenant_id=tenant_id,
            agent_id=agent_id,
            call_record_id=call_record_id,
            ended_at=ended_at or datetime.now(timezone.utc),
            end_reason=end_reason,
        )


def build_call_agent_facts(
    events: list[Any],
) -> tuple[list[AgentReceptionFact], list[AgentOperationFact]]:
    """Fold an ordered immutable event stream into employee facts."""
    ordered = sorted(
        events,
        key=lambda item: (
            item.occurred_at,
            getattr(item, "sequence_no", 0),
            getattr(item, "id", 0),
        ),
    )
    segments: list[AgentReceptionFact] = []
    operations: list[AgentOperationFact] = []
    intervals: list[_Interval] = []

    for event in ordered:
        event_type = event.event_type
        agent_id = _agent_id(event)
        if event_type == "reception_started":
            if _open_segment(segments, agent_id) is None:
                details = getattr(event, "details", None) or {}
                segments.append(
                    AgentReceptionFact(
                        started_event_id=event.event_id,
                        segment_ordinal=len(segments) + 1,
                        agent_id=agent_id,
                        agent_name_snapshot=_agent_name(event),
                        started_at=event.occurred_at,
                        entry_reason=_entry_reason(details.get("entry_reason") or event.reason_code),
                    )
                )
            continue
        if event_type in {"reception_ended", "human_service_ended"}:
            segment = _open_segment(segments, agent_id)
            if segment is not None:
                _close_segment(segment, event, _end_reason(event.reason_code), reliable=True)
            continue
        if event_type in {"hold_started", "consult_connected"}:
            kind = "hold" if event_type == "hold_started" else "consult"
            intervals.append(_Interval(kind=kind, agent_id=agent_id, started_at=event.occurred_at))
        elif event_type in {"hold_ended", "consult_ended", "consult_failed", "consult_canceled"}:
            kind = "hold" if event_type == "hold_ended" else "consult"
            interval = _open_interval(intervals, kind, agent_id)
            if interval is not None:
                interval.ended_at = max(interval.started_at, event.occurred_at)

        operation_type = _operation_type(event_type)
        if operation_type is not None:
            _fold_operation(operations, event, operation_type, agent_id)

        if event_type == "call_ended":
            for segment in segments:
                if segment.ended_at is None:
                    _close_segment(segment, event, "call_ended", reliable=True)
            for interval in intervals:
                if interval.ended_at is None:
                    interval.ended_at = max(interval.started_at, event.occurred_at)

    _apply_interval_durations(segments, intervals)
    return segments, operations


def _fold_operation(
    operations: list[AgentOperationFact], event: Any, operation_type: str, agent_id: int | None
) -> None:
    operation_key = str(getattr(event, "operation_id", None) or event.event_id)
    current = next(
        (
            item
            for item in reversed(operations)
            if item.operation_key == operation_key
            and item.operation_type == operation_type
            and (agent_id is None or item.actor_agent_id == agent_id)
        ),
        None,
    )
    starts = {"transfer_started", "consult_started"}
    if event.event_type in starts or (
        operation_type == "conference" and event.event_type == "conference_merged"
    ):
        if current is None:
            operations.append(
                AgentOperationFact(
                    operation_key=operation_key,
                    operation_type=operation_type,
                    actor_agent_id=agent_id,
                    actor_name_snapshot=_agent_name(event),
                    target_type=_text(getattr(event, "target_type", None)),
                    target_id=_text(getattr(event, "target_id", None)),
                    target_name_snapshot=_text(getattr(event, "target_name_snapshot", None)),
                    started_event_id=event.event_id,
                    started_at=event.occurred_at,
                    ended_event_id=event.event_id if operation_type == "conference" else None,
                    ended_at=event.occurred_at if operation_type == "conference" else None,
                    result="joined" if operation_type == "conference" else None,
                    result_reliable=operation_type == "conference",
                )
            )
            if operation_type == "conference" and getattr(event, "target_type", None) == "employee":
                target_agent_id = _positive_int(getattr(event, "target_id", None))
                if target_agent_id is not None and target_agent_id != agent_id:
                    operations.append(
                        AgentOperationFact(
                            operation_key=operation_key,
                            operation_type=operation_type,
                            actor_agent_id=target_agent_id,
                            actor_name_snapshot=_text(
                                getattr(event, "target_name_snapshot", None)
                            ),
                            target_type="employee",
                            target_id=_text(agent_id),
                            target_name_snapshot=_agent_name(event),
                            started_event_id=event.event_id,
                            started_at=event.occurred_at,
                            ended_event_id=event.event_id,
                            ended_at=event.occurred_at,
                            result="joined",
                            result_reliable=True,
                        )
                    )
        return
    if current is None:
        return
    result_map = {
        "transfer_completed": "completed",
        "transfer_failed": "failed",
        "consult_connected": "connected",
        "consult_failed": "failed",
        "consult_canceled": "canceled",
        "consult_ended": "connected",
        "conference_failed": "failed",
        "conference_ended": current.result or "joined",
    }
    result = result_map.get(event.event_type)
    if result is not None:
        current.ended_event_id = event.event_id
        current.ended_at = max(current.started_at, event.occurred_at)
        current.result = result
        current.result_reliable = True


def _apply_interval_durations(
    segments: list[AgentReceptionFact], intervals: list[_Interval]
) -> None:
    for segment in segments:
        if not segment.result_reliable or segment.ended_at is None:
            continue
        hold_ranges = _intersections(segment, intervals, "hold")
        consult_ranges = _intersections(segment, intervals, "consult")
        segment.hold_duration_ms = _total_ms(hold_ranges)
        segment.consult_duration_ms = _total_ms(consult_ranges)
        segment.held = bool(hold_ranges)
        excluded = _total_ms(_merge_ranges(hold_ranges + consult_ranges))
        segment.talk_duration_ms = max(0, (segment.duration_ms or 0) - excluded)


def _intersections(
    segment: AgentReceptionFact, intervals: list[_Interval], kind: str
) -> list[tuple[datetime, datetime]]:
    output = []
    for interval in intervals:
        if interval.kind != kind or interval.agent_id != segment.agent_id or interval.ended_at is None:
            continue
        start = max(segment.started_at, interval.started_at)
        end = min(segment.ended_at, interval.ended_at)  # type: ignore[arg-type]
        if end > start:
            output.append((start, end))
    return output


def _merge_ranges(ranges: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _total_ms(ranges: list[tuple[datetime, datetime]]) -> int:
    return sum(max(0, int((end - start).total_seconds() * 1000)) for start, end in ranges)


def _close_segment(
    segment: AgentReceptionFact, event: Any, reason: str, *, reliable: bool
) -> None:
    segment.ended_event_id = event.event_id
    segment.ended_at = max(segment.started_at, event.occurred_at)
    segment.end_reason = reason
    segment.duration_ms = max(0, int((segment.ended_at - segment.started_at).total_seconds() * 1000))
    segment.result_reliable = reliable


def _open_segment(
    segments: list[AgentReceptionFact], agent_id: int | None
) -> AgentReceptionFact | None:
    return next(
        (item for item in reversed(segments) if item.agent_id == agent_id and item.ended_at is None),
        None,
    )


def _open_interval(
    intervals: list[_Interval], kind: str, agent_id: int | None
) -> _Interval | None:
    return next(
        (
            item
            for item in reversed(intervals)
            if item.kind == kind and item.agent_id == agent_id and item.ended_at is None
        ),
        None,
    )


def _operation_type(event_type: str) -> str | None:
    if event_type.startswith("transfer_"):
        return "transfer"
    if event_type.startswith("consult_") and event_type != "consult_target_ringing":
        return "consult"
    if event_type in {"conference_merged", "conference_ended", "conference_failed"}:
        return "conference"
    return None


def _entry_reason(value: object) -> str:
    text = (_text(value) or "unknown").lower()
    if text in {"initial_answer", "first", "direct"}:
        return "initial"
    if "queue" in text:
        return "queue_transfer"
    if "transfer" in text:
        return "agent_transfer"
    if "outbound" in text:
        return "outbound"
    if "supervisor" in text or "takeover" in text:
        return "supervisor_takeover"
    return "other" if text != "unknown" else "unknown"


def _end_reason(value: object) -> str:
    text = (_text(value) or "unknown").lower()
    if "transfer" in text:
        return "transfer_completed"
    if "takeover" in text or "supervisor" in text:
        return "supervisor_takeover"
    if "exit" in text or "left" in text:
        return "agent_exit"
    if "end" in text or "hangup" in text or "satisfaction" in text:
        return "call_ended"
    if "error" in text or "fail" in text:
        return "system_error"
    return "other" if text != "unknown" else "unknown"


def _segment_row(call_record: CallRecord, item: AgentReceptionFact) -> dict:
    return {"tenant_id": call_record.tenant_id, "call_record_id": call_record.id, **item.__dict__}


def _operation_row(call_record: CallRecord, item: AgentOperationFact) -> dict:
    return {"tenant_id": call_record.tenant_id, "call_record_id": call_record.id, **item.__dict__}


async def _agent_snapshot(db: AsyncSession, call_record: CallRecord, agent_id: int) -> str | None:
    events = await CallEventRepository.list_for_call(db, call_record.id)
    for event in reversed(events):
        if _agent_id(event) == agent_id and _agent_name(event):
            return _agent_name(event)
    return None


def _agent_id(event: Any) -> int | None:
    if getattr(event, "actor_type", None) != "agent":
        return None
    value = getattr(event, "actor_id", None)
    return _positive_int(value)


def _agent_name(event: Any) -> str | None:
    if getattr(event, "actor_type", None) == "agent":
        return _text(getattr(event, "actor_name_snapshot", None))
    return None


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
