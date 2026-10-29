"""Unit tests for core call trajectory lifecycle settlement."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.call_trajectory_service import CallTrajectoryService
from app.services.call_record_service import CallRecordService


STARTED = datetime(2026, 8, 9, 1, 0, tzinfo=timezone.utc)
MARK_RECEPTION_STARTED = CallRecordService.mark_reception_started


def _event(
    event_type: str,
    offset_ms: int,
    *,
    result: str | None = None,
    sequence_no: int = 1,
    source: str = "opendesk",
    reason_detail: str | None = None,
):
    return SimpleNamespace(
        event_type=event_type,
        occurred_at=STARTED + timedelta(milliseconds=offset_ms),
        result=result,
        sequence_no=sequence_no,
        source=source,
        reason_detail=reason_detail,
    )


async def _settle(
    monkeypatch,
    events,
    *,
    direction="inbound",
    reason="customer_hangup",
    hangup_party="customer",
    hangup_details=None,
    short_abandon_threshold_ms=None,
):
    record = SimpleNamespace(
        id=1,
        direction=direction,
        started_at=STARTED,
        short_abandon_threshold_ms=short_abandon_threshold_ms,
    )
    monkeypatch.setattr(
        "app.services.call_trajectory_service.CallRecordRepository.get_by_id_unscoped",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.call_trajectory_service.CallEventRepository.list_for_call",
        AsyncMock(return_value=events),
    )
    return await CallTrajectoryService.build_settlement_details(
        AsyncMock(),
        call_record_id=1,
        ended_at=STARTED + timedelta(seconds=10),
        hangup_reason=reason,
        hangup_party=hangup_party,
        hangup_details=hangup_details,
    )


@pytest.mark.asyncio
async def test_settlement_prioritizes_agent_answered_and_calculates_phases(monkeypatch):
    details = await _settle(
        monkeypatch,
        [
            _event("call_created", 0),
            _event("ivr_entered", 100),
            _event("ivr_exited", 1_100),
            _event("queue_entered", 1_200),
            _event("queue_exited", 3_200),
            _event("reception_started", 3_300),
            _event("hold_started", 5_000),
            _event("hold_ended", 6_000),
            _event("reception_ended", 9_500),
        ],
        reason="customer_hangup",
    )

    assert details["call_result"] == "agent_answered"
    assert details["hangup_party"] == "customer"
    assert details["hangup_stage"] == "in_call"
    assert details["phase_durations_ms"]["ivr"] == 1_000
    assert details["phase_durations_ms"]["agent_waiting"] == 2_000
    assert details["phase_durations_ms"]["talk"] == 6_200
    assert details["phase_durations_ms"]["hold"] == 1_000
    assert details["customer_agent_talk_duration_ms"] == 5_200
    assert details["result_rule_version"] == 4
    assert details["actual_reception_type"] == "agent"


@pytest.mark.asyncio
async def test_settlement_distinguishes_ivr_customer_hangup(monkeypatch):
    details = await _settle(
        monkeypatch,
        [
            _event("call_created", 0),
            _event("ivr_entered", 100),
            _event("ivr_exited", 3_000),
        ],
        reason="customer_hangup",
    )

    assert details["call_result"] == "ivr_customer_hangup"
    assert details["hangup_stage"] == "ivr"
    assert details["actual_reception_type"] == "ivr"


@pytest.mark.asyncio
async def test_settlement_uses_short_abandon_threshold_snapshot(monkeypatch):
    details = await _settle(
        monkeypatch,
        [
            _event("call_created", 0),
            _event("queue_entered", 1_000),
            _event("queue_exited", 4_500),
        ],
        reason="customer_hangup",
    )

    assert details["call_result"] == "customer_short_abandon"
    assert details["short_abandon_threshold_ms"] == 5_000


@pytest.mark.asyncio
async def test_settlement_uses_frozen_custom_threshold(monkeypatch):
    details = await _settle(
        monkeypatch,
        [
            _event("call_created", 0),
            _event("queue_entered", 1_000),
            _event("queue_exited", 4_500),
        ],
        reason="customer_hangup",
        short_abandon_threshold_ms=3_000,
    )

    assert details["call_result"] == "agent_no_answer"
    assert details["short_abandon_threshold_ms"] == 3_000


@pytest.mark.asyncio
async def test_settlement_short_abandon_boundary_is_inclusive(monkeypatch):
    at_boundary = await _settle(
        monkeypatch,
        [
            _event("call_created", 0),
            _event("queue_entered", 1_000),
            _event("queue_exited", 6_000),
        ],
        short_abandon_threshold_ms=5_000,
    )
    above_boundary = await _settle(
        monkeypatch,
        [
            _event("call_created", 0),
            _event("queue_entered", 1_000),
            _event("queue_exited", 6_001),
        ],
        short_abandon_threshold_ms=5_000,
    )

    assert at_boundary["call_result"] == "customer_short_abandon"
    assert above_boundary["call_result"] == "agent_no_answer"


@pytest.mark.asyncio
async def test_settlement_rebuilds_first_event_times(monkeypatch):
    details = await _settle(
        monkeypatch,
        [
            _event("call_created", 0),
            _event("agent_offer_started", 3_000),
            _event("queue_entered", 2_000),
            _event("bot_handoff_requested", 1_000),
            _event("bot_handoff_succeeded", 1_500),
            _event("queue_exited", 5_000),
        ],
    )

    assert details["human_service_requested_at"] == STARTED + timedelta(seconds=1)
    assert details["first_agent_wait_started_at"] == STARTED + timedelta(seconds=2)
    assert details["first_agent_offer_started_at"] == STARTED + timedelta(seconds=3)
    assert details["bot_handoff_requested_at"] == STARTED + timedelta(seconds=1)
    assert details["bot_handoff_succeeded_at"] == STARTED + timedelta(milliseconds=1_500)


@pytest.mark.asyncio
async def test_settlement_completes_after_late_fact_resolves_prior_gap(monkeypatch):
    details = await _settle(
        monkeypatch,
        [
            _event("call_created", 0, sequence_no=1),
            _event("queue_entered", 1_000, sequence_no=2),
            _event("queue_exited", 5_000, sequence_no=5),
            _event("trajectory_gap_detected", 9_000, sequence_no=3),
            _event("call_ended", 10_000, sequence_no=4),
        ],
    )

    assert details["agent_wait_duration_ms"] == 4_000
    assert details["projection_complete"] is True


@pytest.mark.asyncio
async def test_settlement_keeps_in_call_after_transfer_queue_and_offer(monkeypatch):
    details = await _settle(
        monkeypatch,
        [
            _event("call_created", 0),
            _event("reception_started", 1_000),
            _event("reception_ended", 3_000),
            _event("transfer_started", 3_100),
            _event("queue_entered", 3_200),
            _event("queue_exited", 4_000),
            _event("agent_offer_started", 4_100),
            _event("agent_offer_canceled", 5_000),
        ],
    )

    assert details["hangup_stage"] == "in_call"


@pytest.mark.asyncio
async def test_settlement_maps_outbound_busy_before_queue_rules(monkeypatch):
    details = await _settle(
        monkeypatch,
        [_event("call_created", 0), _event("customer_ringing_started", 100)],
        direction="outbound",
        reason="customer_busy",
        hangup_party="carrier",
    )

    assert details["call_result"] == "customer_busy"
    assert details["hangup_party"] == "carrier"
    assert details["hangup_reason_code"] == "customer_busy"


@pytest.mark.parametrize(
    ("sip_status", "expected"),
    [
        (180, "customer_no_answer"),
        (183, "provider_answer_unconfirmed"),
        (480, "provider_temporarily_unavailable"),
    ],
)
@pytest.mark.asyncio
async def test_settlement_splits_outbound_no_answer_by_last_sip_status(
    monkeypatch, sip_status, expected
):
    details = await _settle(
        monkeypatch,
        [_event("call_created", 0), _event("customer_ringing_started", 100)],
        direction="outbound",
        reason="no_answer",
        hangup_party=None,
        hangup_details={"sip_status": sip_status},
    )

    assert details["call_result"] == expected
    assert details["hangup_reason_code"] == expected
    assert details["hangup_party"] == "carrier"


# The telephony kernel reports a raw reason and never a business role, so the
# settlement has to classify the party itself. These cases pin the real
# production input shape: no explicit party.
@pytest.mark.parametrize(
    ("reason", "expected_party", "expected_code"),
    [
        ("agent_hangup", "agent", "agent_hangup"),
        ("remote_bye", "customer", "customer_hangup"),
        ("media_timeout", "customer", "customer_hangup"),
        ("supervisor_force_hangup", "supervisor", "supervisor_force_hangup"),
        ("no_route", "system", "no_route"),
        ("offer_expired", "system", "agent_no_answer"),
    ],
)
@pytest.mark.asyncio
async def test_settlement_derives_party_from_reason_when_absent(
    monkeypatch, reason, expected_party, expected_code
):
    details = await _settle(
        monkeypatch,
        [
            _event("call_created", 0),
            _event("queue_entered", 1_000),
            _event("queue_exited", 2_000),
            _event("reception_started", 2_100),
            _event("reception_ended", 9_000),
        ],
        reason=reason,
        hangup_party=None,
    )

    assert details["hangup_party"] == expected_party
    assert details["hangup_reason_code"] == expected_code
    assert details["raw_hangup_reason"] == reason


@pytest.mark.asyncio
async def test_settlement_short_abandon_needs_no_explicit_party(monkeypatch):
    details = await _settle(
        monkeypatch,
        [
            _event("call_created", 0),
            _event("queue_entered", 1_000),
            _event("queue_exited", 4_500),
        ],
        reason="remote_bye",
        hangup_party=None,
    )

    assert details["hangup_party"] == "customer"
    assert details["call_result"] == "customer_short_abandon"


@pytest.mark.asyncio
async def test_settlement_falls_back_to_unknown_without_any_signal(monkeypatch):
    details = await _settle(
        monkeypatch,
        [_event("call_created", 0), _event("reception_started", 100)],
        reason=None,
        hangup_party=None,
    )

    assert details["hangup_party"] == "unknown"
    assert details["hangup_reason_code"] == "normal_completed"


@pytest.mark.asyncio
async def test_settlement_classifies_and_preserves_supplier_detail(monkeypatch):
    details = await _settle(
        monkeypatch,
        [_event("call_created", 0)],
        direction="outbound",
        reason="rejected",
        hangup_party=None,
        hangup_details={
            "sip_status": 404,
            "sip_reason": "Not Found",
            "sip_warning": "route was not found",
            "sip_call_id": "provider-call-id",
        },
    )

    assert details["hangup_reason_code"] == "provider_not_found"
    assert details["hangup_party"] == "carrier"
    assert details["hangup_match_strategy"] == "sip_status"
    assert details["sip_reason"] == "Not Found"
    assert details["sip_call_id"] == "provider-call-id"
    assert details["result_rule_version"] == 4


@pytest.mark.asyncio
async def test_reception_transfer_closes_old_segment_and_starts_new_one(monkeypatch):
    written = []
    row = SimpleNamespace(
        id=7,
        tenant_id=3,
        call_id="call-7",
        last_serving_agent_id=11,
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_call_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.EmployeeRepository.get_by_ids",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=11,
                    tenant_id=3,
                    display_name="Alice",
                    nickname=None,
                    name="Alice",
                    username="alice",
                ),
                SimpleNamespace(
                    id=12,
                    tenant_id=3,
                    display_name="Bob",
                    nickname=None,
                    name="Bob",
                    username="bob",
                ),
            ]
        ),
    )

    async def _capture(_db, *, call_record_id, payload, commit):
        del commit
        written.append((call_record_id, payload))

    monkeypatch.setattr(
        "app.services.call_record_service.CallTrajectoryService.append_event",
        _capture,
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.update",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.call_record_service._add_agent_access_scopes",
        AsyncMock(),
    )

    await CallRecordService.mark_reception_transferred(
        AsyncMock(),
        3,
        "call-7",
        from_agent_id=11,
        to_agent_id=12,
        operation_id="transfer-1",
        target_leg_id="leg-12",
    )

    assert [payload.event_type for _, payload in written] == [
        "reception_ended",
        "reception_started",
    ]
    assert written[0][1].actor_name_snapshot == "Alice"
    assert written[1][1].actor_id == "12"
    assert written[1][1].actor_name_snapshot == "Bob"
    assert written[1][1].call_leg_id == "leg-12"


@pytest.mark.asyncio
async def test_reception_started_snapshots_agent_name(monkeypatch):
    written = []
    row = SimpleNamespace(
        id=7,
        tenant_id=3,
        call_id="call-7",
        first_agent_connected_at=None,
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_call_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.EmployeeRepository.get_by_ids",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=935,
                    tenant_id=3,
                    display_name="张三",
                    nickname=None,
                    name="张三",
                    username="zhangsan",
                )
            ]
        ),
    )

    async def _capture(_db, *, call_record_id, payload, commit):
        del commit
        written.append((call_record_id, payload))

    monkeypatch.setattr(
        "app.services.call_record_service.CallTrajectoryService.append_event",
        _capture,
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.update",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.call_record_service._add_agent_access_scopes",
        AsyncMock(),
    )

    await MARK_RECEPTION_STARTED(
        AsyncMock(),
        3,
        "call-7",
        agent_id=935,
        agent_leg_id="leg-935",
    )

    assert [payload.event_type for _, payload in written] == [
        "agent_bridge_succeeded",
        "reception_started",
    ]
    for _, payload in written:
        assert payload.actor_name_snapshot == "张三"
        assert payload.target_name_snapshot == "张三"


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["bot_hangup", "user_hangup"])
async def test_settlement_labels_bot_requested_hangup(monkeypatch, reason):
    details = await _settle(
        monkeypatch,
        [
            _event("call_created", 0),
            _event("bot_started", 100),
            _event("bot_ended", 9_000, result="succeeded", reason_detail="hangup"),
        ],
        reason=reason,
        hangup_party=None,
    )

    assert details["hangup_reason_code"] == "bot_hangup"
    assert details["hangup_party"] == "bot"
    assert details["call_result"] == "bot_completed"
