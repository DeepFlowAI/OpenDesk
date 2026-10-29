"""Unit tests for call queue visit and offer fact construction."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.call_queue_fact_service import build_call_queue_facts


BASE = datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc)


def _event(event_type: str, seconds: int, **overrides):
    values = {
        "id": seconds + 1,
        "event_id": f"event-{event_type}-{seconds}",
        "event_type": event_type,
        "occurred_at": BASE + timedelta(seconds=seconds),
        "sequence_no": seconds + 1,
        "queue_type": None,
        "queue_id": None,
        "queue_name_snapshot": None,
        "operation_id": None,
        "actor_type": "system",
        "actor_id": None,
        "actor_name_snapshot": None,
        "target_id": None,
        "target_name_snapshot": None,
        "result": None,
        "reason_code": None,
        "details": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_multiple_visits_keep_distinct_call_and_entry_counts():
    events = [
        _event(
            "queue_entered",
            0,
            queue_type="employee_group",
            queue_id=10,
            queue_name_snapshot="Support",
        ),
        _event(
            "queue_entered",
            30,
            queue_type="employee_group",
            queue_id=20,
            queue_name_snapshot="Escalation",
        ),
        _event(
            "queue_entered",
            60,
            queue_type="employee_group",
            queue_id=10,
            queue_name_snapshot="Support",
        ),
    ]

    visits, _ = build_call_queue_facts(events, short_abandon_threshold_ms=5_000)

    assert [visit.queue_id for visit in visits] == [10, 20, 10]
    assert [visit.entry_kind for visit in visits] == ["first", "transfer_in", "transfer_in"]
    assert [visit.result for visit in visits[:2]] == ["transfer_out", "transfer_out"]


def test_offer_acceptance_only_becomes_answered_after_bridge():
    events = [
        _event("queue_entered", 0, queue_type="employee", queue_id=7),
        _event(
            "agent_offer_started",
            3,
            queue_type="employee",
            queue_id=7,
            operation_id="offer-1",
            target_id="7",
        ),
        _event("agent_offer_accepted", 5, operation_id="offer-1"),
        _event(
            "queue_exited",
            5,
            queue_type="employee",
            queue_id=7,
            reason_code="agent_accepted",
        ),
    ]

    visits, offers = build_call_queue_facts(events, short_abandon_threshold_ms=5_000)
    assert offers[0].result == "accepted"
    assert visits[0].result is None
    assert visits[0].result_reliable is False

    events.append(_event("reception_started", 6, actor_type="agent", actor_id="7"))
    visits, offers = build_call_queue_facts(events, short_abandon_threshold_ms=5_000)
    assert offers[0].result == "accepted"
    assert visits[0].result == "answered"
    assert visits[0].result_reliable is True


def test_customer_hangup_closes_visit_and_freezes_short_abandon():
    events = [
        _event("queue_entered", 0, queue_type="employee_group", queue_id=10),
        _event(
            "call_ended",
            4,
            actor_type="customer",
            reason_code="customer_hangup",
            details={"hangup_party": "customer"},
        ),
    ]

    visits, _ = build_call_queue_facts(events, short_abandon_threshold_ms=5_000)

    assert visits[0].result == "abandoned"
    assert visits[0].is_short_abandon is True
    assert visits[0].exited_at == BASE + timedelta(seconds=4)


def test_final_projection_uses_persisted_hangup_party_as_fallback():
    events = [
        _event("queue_entered", 0, queue_type="employee_group", queue_id=10),
        _event("call_ended", 8, actor_type="system", reason_code="call_ended"),
    ]

    visits, _ = build_call_queue_facts(
        events,
        short_abandon_threshold_ms=5_000,
        hangup_party="customer",
    )

    assert visits[0].result == "abandoned"
    assert visits[0].is_short_abandon is False


def test_rebuild_with_duplicate_source_event_keeps_stable_fact_keys():
    entered = _event("queue_entered", 0, queue_type="employee_group", queue_id=10)
    events = [
        entered,
        _event(
            "agent_offer_started",
            1,
            queue_type="employee_group",
            queue_id=10,
            operation_id="offer-1",
        ),
        _event("agent_offer_timeout", 3, operation_id="offer-1"),
    ]

    first_visits, first_offers = build_call_queue_facts(
        events, short_abandon_threshold_ms=5_000
    )
    second_visits, second_offers = build_call_queue_facts(
        list(events), short_abandon_threshold_ms=5_000
    )

    assert [row.entered_event_id for row in first_visits] == [
        row.entered_event_id for row in second_visits
    ]
    assert [row.started_event_id for row in first_offers] == [
        row.started_event_id for row in second_offers
    ]
