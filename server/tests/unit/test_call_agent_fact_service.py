"""Unit tests for employee call fact construction."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.call_agent_fact_service import build_call_agent_facts


BASE = datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc)


def _event(event_type: str, seconds: int, **overrides):
    values = {
        "id": seconds + 1,
        "event_id": f"event-{event_type}-{seconds}",
        "event_type": event_type,
        "occurred_at": BASE + timedelta(seconds=seconds),
        "sequence_no": seconds + 1,
        "operation_id": None,
        "actor_type": "agent",
        "actor_id": "7",
        "actor_name_snapshot": "Ada",
        "target_type": None,
        "target_id": None,
        "target_name_snapshot": None,
        "reason_code": None,
        "details": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_transfer_creates_distinct_employee_segments():
    events = [
        _event("reception_started", 0, details={"entry_reason": "initial_answer"}),
        _event("transfer_started", 30, operation_id="transfer-1"),
        _event("transfer_completed", 40, operation_id="transfer-1"),
        _event("reception_ended", 40, operation_id="transfer-1", reason_code="transfer_completed"),
        _event(
            "reception_started",
            40,
            operation_id="transfer-1",
            actor_id="8",
            actor_name_snapshot="Lin",
            details={"entry_reason": "transfer_completed"},
        ),
        _event("call_ended", 100, actor_type="system", actor_id=None),
    ]

    segments, operations = build_call_agent_facts(events)

    assert [item.agent_id for item in segments] == [7, 8]
    assert [item.duration_ms for item in segments] == [40_000, 60_000]
    assert operations[0].result == "completed"


def test_same_employee_reentry_counts_two_segments():
    events = [
        _event("reception_started", 0),
        _event("reception_ended", 20, reason_code="agent_exit"),
        _event("reception_started", 30, event_id="reentry", details={"entry_reason": "direct"}),
        _event("call_ended", 50, actor_type="system", actor_id=None),
    ]

    segments, _ = build_call_agent_facts(events)

    assert len(segments) == 2
    assert [item.segment_ordinal for item in segments] == [1, 2]


def test_hold_and_consult_are_excluded_once_from_talk_duration():
    events = [
        _event("reception_started", 0),
        _event("hold_started", 10),
        _event("consult_connected", 20, operation_id="consult-1"),
        _event("hold_ended", 30),
        _event("consult_ended", 40, operation_id="consult-1"),
        _event("call_ended", 60, actor_type="system", actor_id=None),
    ]

    segments, _ = build_call_agent_facts(events)

    assert segments[0].hold_duration_ms == 20_000
    assert segments[0].consult_duration_ms == 20_000
    assert segments[0].talk_duration_ms == 30_000


def test_open_segment_has_no_final_duration():
    segments, _ = build_call_agent_facts([_event("reception_started", 0)])

    assert segments[0].result_reliable is False
    assert segments[0].duration_ms is None
    assert segments[0].talk_duration_ms is None


def test_rebuild_keeps_stable_fact_identities():
    events = [
        _event("reception_started", 0),
        _event("transfer_started", 10, operation_id="transfer-1"),
        _event("transfer_failed", 20, operation_id="transfer-1"),
    ]

    first_segments, first_operations = build_call_agent_facts(events)
    second_segments, second_operations = build_call_agent_facts(list(events))

    assert first_segments[0].started_event_id == second_segments[0].started_event_id
    assert first_operations[0].operation_key == second_operations[0].operation_key


def test_system_transfer_result_keeps_original_actor_not_queue_target():
    events = [
        _event(
            "transfer_started",
            0,
            target_type="queue",
            target_id="42",
            operation_id="route-1",
        ),
        _event(
            "transfer_failed",
            1,
            actor_type="system",
            actor_id=None,
            target_type="queue",
            target_id="42",
            operation_id="route-1",
        ),
    ]

    _, operations = build_call_agent_facts(events)

    assert operations[0].actor_agent_id == 7
    assert operations[0].result == "failed"


def test_conference_counts_host_and_employee_target_as_participants():
    _, operations = build_call_agent_facts([
        _event(
            "conference_merged",
            0,
            operation_id="conference-1",
            target_type="employee",
            target_id="8",
            target_name_snapshot="Lin",
        )
    ])

    assert [(item.actor_agent_id, item.result) for item in operations] == [
        (7, "joined"),
        (8, "joined"),
    ]
