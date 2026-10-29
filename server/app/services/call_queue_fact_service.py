"""Build durable queue visit and agent-offer facts from append-only call events."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.call_event_repository import CallEventRepository
from app.repositories.call_queue_fact_repository import CallQueueFactRepository
from app.repositories.call_record_repository import CallRecordRepository


QUEUE_FACT_EVENT_TYPES = frozenset(
    {
        "queue_entered",
        "queue_exited",
        "queue_timeout",
        "queue_limit_reached",
        "agent_offer_started",
        "agent_offer_accepted",
        "agent_offer_rejected",
        "agent_offer_timeout",
        "agent_offer_canceled",
        "agent_bridge_succeeded",
        "agent_bridge_failed",
        "reception_started",
        "call_ended",
    }
)


@dataclass
class QueueVisitFact:
    entered_event_id: str
    exited_event_id: str | None
    visit_ordinal: int
    queue_type: str
    queue_id: int
    queue_name_snapshot: str | None
    entry_kind: str
    entered_at: datetime
    exited_at: datetime | None = None
    result: str | None = None
    result_reliable: bool = False
    is_short_abandon: bool = False


@dataclass
class QueueOfferFact:
    visit: QueueVisitFact
    started_event_id: str
    operation_id: str | None
    agent_id: int | None
    agent_name_snapshot: str | None
    started_at: datetime
    ended_event_id: str | None = None
    ended_at: datetime | None = None
    result: str | None = None
    result_reliable: bool = False


class CallQueueFactService:
    """Rebuild query facts for one call without scanning events at report time."""

    @staticmethod
    async def project_for_call(db: AsyncSession, call_record_id: int) -> None:
        call_record = await CallRecordRepository.get_by_id_unscoped(db, call_record_id)
        if call_record is None:
            return
        events = await CallEventRepository.list_for_call(db, call_record_id)
        visits, offers = build_call_queue_facts(
            events,
            short_abandon_threshold_ms=getattr(
                call_record, "short_abandon_threshold_ms", None
            ),
            hangup_party=getattr(call_record, "hangup_party", None),
        )
        visit_rows = [
            _visit_row(call_record.tenant_id, call_record_id, visit)
            for visit in visits
        ]
        offer_rows = [
            _offer_row(call_record.tenant_id, call_record_id, offer)
            for offer in offers
        ]
        visit_ids = await CallQueueFactRepository.upsert_visits(db, visit_rows)
        await CallQueueFactRepository.upsert_offers(db, offer_rows, visit_ids)


def build_call_queue_facts(
    events: list[Any],
    *,
    short_abandon_threshold_ms: int | None,
    hangup_party: str | None = None,
) -> tuple[list[QueueVisitFact], list[QueueOfferFact]]:
    """Fold an ordered event stream into idempotent queue facts."""
    ordered = sorted(
        events,
        key=lambda event: (
            event.occurred_at,
            getattr(event, "sequence_no", 0),
            getattr(event, "id", 0),
        ),
    )
    visits: list[QueueVisitFact] = []
    offers: list[QueueOfferFact] = []

    for event in ordered:
        event_type = event.event_type
        if event_type == "queue_entered":
            queue_type = _text(getattr(event, "queue_type", None))
            queue_id = _positive_int(getattr(event, "queue_id", None))
            if queue_type not in {"employee_group", "employee"} or queue_id is None:
                continue
            open_visit = _last_open_visit(visits)
            if open_visit is not None:
                _close_visit(open_visit, event, "transfer_out", reliable=True)
            entry_kind = "first"
            if visits:
                previous = visits[-1]
                entry_kind = (
                    "reentry"
                    if (previous.queue_type, previous.queue_id) == (queue_type, queue_id)
                    else "transfer_in"
                )
            visits.append(
                QueueVisitFact(
                    entered_event_id=event.event_id,
                    exited_event_id=None,
                    visit_ordinal=len(visits) + 1,
                    queue_type=queue_type,
                    queue_id=queue_id,
                    queue_name_snapshot=_text(
                        getattr(event, "queue_name_snapshot", None)
                    ),
                    entry_kind=entry_kind,
                    entered_at=event.occurred_at,
                )
            )
            continue

        if event_type == "agent_offer_started":
            visit = _matching_open_visit(visits, event)
            if visit is None:
                continue
            offers.append(
                QueueOfferFact(
                    visit=visit,
                    started_event_id=event.event_id,
                    operation_id=_text(getattr(event, "operation_id", None)),
                    agent_id=_positive_int(
                        getattr(event, "target_id", None)
                        or getattr(event, "actor_id", None)
                    ),
                    agent_name_snapshot=_text(
                        getattr(event, "target_name_snapshot", None)
                        or getattr(event, "actor_name_snapshot", None)
                    ),
                    started_at=event.occurred_at,
                )
            )
            continue

        if event_type in {
            "agent_offer_accepted",
            "agent_offer_rejected",
            "agent_offer_timeout",
            "agent_offer_canceled",
        }:
            offer = _matching_offer(offers, event)
            if offer is None:
                continue
            offer.ended_event_id = event.event_id
            offer.ended_at = event.occurred_at
            offer.result = {
                "agent_offer_accepted": "accepted",
                "agent_offer_rejected": "rejected",
                "agent_offer_timeout": "timeout",
                "agent_offer_canceled": "canceled",
            }[event_type]
            offer.result_reliable = True
            continue

        if event_type in {"agent_bridge_succeeded", "reception_started"}:
            visit = _latest_accepted_visit(visits, offers, event.occurred_at)
            if visit is not None:
                _close_visit(visit, event, "answered", reliable=True)
            continue

        if event_type == "agent_bridge_failed":
            offer = _matching_offer(offers, event)
            if offer is not None:
                offer.ended_event_id = event.event_id
                offer.ended_at = event.occurred_at
                offer.result = "bridge_failed"
                offer.result_reliable = True
                _close_visit(offer.visit, event, "failed", reliable=True)
            continue

        if event_type in {"queue_exited", "queue_timeout", "queue_limit_reached"}:
            visit = _matching_open_visit(visits, event)
            if visit is None:
                continue
            result, reliable = _queue_exit_result(event)
            _close_visit(visit, event, result, reliable=reliable)
            continue

        if event_type == "call_ended":
            _settle_at_call_end(
                visits,
                offers,
                event,
                short_abandon_threshold_ms=short_abandon_threshold_ms,
                hangup_party=hangup_party,
            )

    return visits, offers


def _settle_at_call_end(
    visits: list[QueueVisitFact],
    offers: list[QueueOfferFact],
    event: Any,
    *,
    short_abandon_threshold_ms: int | None,
    hangup_party: str | None,
) -> None:
    details = getattr(event, "details", None) or {}
    party = (
        _text(details.get("hangup_party"))
        or _text(hangup_party)
        or _text(getattr(event, "actor_type", None))
    )
    reason = _text(getattr(event, "reason_code", None)) or ""
    for visit in visits:
        if visit.result_reliable:
            continue
        if party == "customer":
            _close_visit(visit, event, "abandoned", reliable=True)
            wait_ms = _duration_ms(visit.entered_at, event.occurred_at)
            visit.is_short_abandon = (
                short_abandon_threshold_ms is not None
                and wait_ms <= short_abandon_threshold_ms
            )
        elif "timeout" in reason:
            _close_visit(visit, event, "timeout", reliable=True)
        elif "cancel" in reason:
            _close_visit(visit, event, "canceled", reliable=True)
        else:
            _close_visit(visit, event, "failed", reliable=True)

    for offer in offers:
        if offer.result == "accepted" and offer.visit.result != "answered":
            offer.result = "bridge_failed"
            offer.ended_event_id = event.event_id
            offer.ended_at = event.occurred_at
            offer.result_reliable = True


def _queue_exit_result(event: Any) -> tuple[str | None, bool]:
    if event.event_type in {"queue_timeout", "queue_limit_reached"}:
        return "timeout", True
    reason = (_text(getattr(event, "reason_code", None)) or "").lower()
    result = (_text(getattr(event, "result", None)) or "").lower()
    if "agent_accepted" in reason:
        return None, False
    if "timeout" in reason:
        return "timeout", True
    if "transfer" in reason or "next_queue" in reason:
        return "transfer_out", True
    if "customer" in reason and ("hangup" in reason or "abandon" in reason):
        return "abandoned", True
    if "cancel" in reason:
        return "canceled", True
    if result in {"failed", "error"} or "fail" in reason:
        return "failed", True
    return None, False


def _matching_open_visit(visits: list[QueueVisitFact], event: Any) -> QueueVisitFact | None:
    queue_type = _text(getattr(event, "queue_type", None))
    queue_id = _positive_int(getattr(event, "queue_id", None))
    for visit in reversed(visits):
        if visit.result_reliable:
            continue
        if queue_type and queue_id is not None:
            if (visit.queue_type, visit.queue_id) != (queue_type, queue_id):
                continue
        return visit
    return None


def _last_open_visit(visits: list[QueueVisitFact]) -> QueueVisitFact | None:
    return next((visit for visit in reversed(visits) if not visit.result_reliable), None)


def _matching_offer(offers: list[QueueOfferFact], event: Any) -> QueueOfferFact | None:
    operation_id = _text(getattr(event, "operation_id", None))
    if operation_id:
        match = next(
            (offer for offer in reversed(offers) if offer.operation_id == operation_id),
            None,
        )
        if match is not None:
            return match
    return next((offer for offer in reversed(offers) if not offer.result_reliable), None)


def _latest_accepted_visit(
    visits: list[QueueVisitFact],
    offers: list[QueueOfferFact],
    occurred_at: datetime,
) -> QueueVisitFact | None:
    accepted = [
        offer
        for offer in offers
        if offer.result == "accepted" and offer.started_at <= occurred_at
    ]
    if accepted:
        return accepted[-1].visit
    return _last_open_visit(visits)


def _close_visit(
    visit: QueueVisitFact,
    event: Any,
    result: str | None,
    *,
    reliable: bool,
) -> None:
    visit.exited_event_id = event.event_id
    visit.exited_at = max(visit.entered_at, event.occurred_at)
    visit.result = result
    visit.result_reliable = reliable


def _visit_row(tenant_id: int, call_record_id: int, visit: QueueVisitFact) -> dict:
    return {
        "tenant_id": tenant_id,
        "call_record_id": call_record_id,
        "entered_event_id": visit.entered_event_id,
        "exited_event_id": visit.exited_event_id,
        "visit_ordinal": visit.visit_ordinal,
        "queue_type": visit.queue_type,
        "queue_id": visit.queue_id,
        "queue_name_snapshot": visit.queue_name_snapshot,
        "entry_kind": visit.entry_kind,
        "entered_at": visit.entered_at,
        "exited_at": visit.exited_at,
        "wait_duration_ms": (
            _duration_ms(visit.entered_at, visit.exited_at)
            if visit.exited_at is not None
            else None
        ),
        "result": visit.result,
        "result_reliable": visit.result_reliable,
        "is_short_abandon": visit.is_short_abandon,
    }


def _offer_row(tenant_id: int, call_record_id: int, offer: QueueOfferFact) -> dict:
    return {
        "tenant_id": tenant_id,
        "call_record_id": call_record_id,
        "visit_entered_event_id": offer.visit.entered_event_id,
        "started_event_id": offer.started_event_id,
        "ended_event_id": offer.ended_event_id,
        "operation_id": offer.operation_id,
        "agent_id": offer.agent_id,
        "agent_ref_id": offer.agent_id,
        "agent_name_snapshot": offer.agent_name_snapshot,
        "started_at": offer.started_at,
        "ended_at": offer.ended_at,
        "duration_ms": (
            _duration_ms(offer.started_at, offer.ended_at)
            if offer.ended_at is not None
            else None
        ),
        "result": offer.result,
        "result_reliable": offer.result_reliable,
    }


def _duration_ms(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() * 1000))


def _positive_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
