"""Unit tests for call trajectory storage and query orchestration."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.schemas.call_trajectory import CallEventCreate
from app.services.call_trajectory_service import (
    CallTrajectoryService,
    _group_operations,
    _reconciliation_event_id,
)


def _payload(**overrides) -> CallEventCreate:
    data = {
        "event_id": "evt-1",
        "event_type": "dtmf_sent",
        "event_category": "control",
        "actor_type": "agent",
        "source": "opendesk",
        "occurred_at": datetime(2026, 8, 9, 2, 0, tzinfo=timezone.utc),
        "details": {"digit_count": 4, "digits": "1234", "nested": {"token": "secret"}},
    }
    data.update(overrides)
    return CallEventCreate(**data)


def _event(
    event_id: str,
    event_type: str,
    occurred_at: datetime,
    *,
    operation_id: str | None = None,
    result: str | None = None,
    duration_ms: int | None = None,
):
    return SimpleNamespace(
        id=1,
        event_id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        operation_id=operation_id,
        result=result,
        duration_ms=duration_ms,
        created_at=occurred_at,
    )


@pytest.mark.asyncio
async def test_append_event_resolves_call_and_removes_sensitive_details(monkeypatch):
    call_record = SimpleNamespace(id=9, tenant_id=3, call_id="call-9", root_call_id=None)
    stored = SimpleNamespace(id=21)
    get_record = AsyncMock(return_value=call_record)
    append = AsyncMock(return_value=(stored, True))
    monkeypatch.setattr(
        "app.services.call_trajectory_service.CallRecordRepository.get_by_id_unscoped",
        get_record,
    )
    monkeypatch.setattr(
        "app.services.call_trajectory_service.CallEventRepository.append",
        append,
    )

    result = await CallTrajectoryService.append_event(
        AsyncMock(), call_record_id=9, payload=_payload()
    )

    assert result == (stored, True)
    written = append.await_args.kwargs["data"]
    assert written["details"] == {"digit_count": 4, "nested": {}}
    assert append.await_args.kwargs["call_record"] is call_record


@pytest.mark.asyncio
async def test_append_event_rejects_unknown_taxonomy(monkeypatch):
    monkeypatch.setattr(
        "app.services.call_trajectory_service.CallRecordRepository.get_by_id_unscoped",
        AsyncMock(return_value=SimpleNamespace(id=1)),
    )

    with pytest.raises(ValidationError, match="category"):
        await CallTrajectoryService.append_event(
            AsyncMock(),
            call_record_id=1,
            payload=_payload(event_category="unsupported"),
        )


def test_group_operations_uses_explicit_final_duration_and_result():
    started = datetime(2026, 8, 9, 2, 0, tzinfo=timezone.utc)
    rows = [
        _event("one", "transfer_started", started, operation_id="op-1"),
        _event(
            "two",
            "transfer_completed",
            started + timedelta(seconds=12),
            operation_id="op-1",
            result="succeeded",
            duration_ms=12_345,
        ),
    ]

    assert _group_operations(rows) == [
        {
            "operation_id": "op-1",
            "event_ids": ["one", "two"],
            "started_at": started,
            "ended_at": started + timedelta(seconds=12),
            "duration_ms": 12_345,
            "result": "succeeded",
        }
    ]


@pytest.mark.asyncio
async def test_get_trajectory_checks_scope_before_reading_events(monkeypatch):
    public_id = uuid4()
    record = SimpleNamespace(
        id=7,
        public_id=public_id,
        call_id="call-7",
        lifecycle_status="ended",
        finalization_status="completed",
    )
    principal = SimpleNamespace(group_ids=[5])
    get_events = AsyncMock(return_value=[])
    scope_check = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_trajectory_service.CallRecordRepository.get_by_public_id",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.call_trajectory_service.DataScopeService.assert_call_record_in_scope",
        scope_check,
    )
    monkeypatch.setattr(
        "app.services.call_trajectory_service.CallEventRepository.list_for_call",
        get_events,
    )

    result = await CallTrajectoryService.get_trajectory(
        AsyncMock(), public_id=public_id, tenant_id=3, principal=principal
    )

    assert scope_check.await_args.args[2] is record
    get_events.assert_awaited_once()
    assert result["events"] == []
    assert result["is_live"] is False
    assert result["is_complete"] is True


@pytest.mark.asyncio
async def test_get_trajectory_returns_latest_settlement_and_gap_warning(monkeypatch):
    started = datetime(2026, 8, 9, 2, 0, tzinfo=timezone.utc)
    events = [
        _event("created", "call_created", started),
        _event("ended", "call_ended", started + timedelta(minutes=1)),
        _event("gap", "trajectory_gap_detected", started + timedelta(minutes=1, seconds=1)),
    ]
    public_id = uuid4()
    record = SimpleNamespace(
        id=8,
        public_id=public_id,
        call_id="call-8",
        lifecycle_status="ended",
        finalization_status="completed",
    )
    monkeypatch.setattr(
        "app.services.call_trajectory_service.CallRecordRepository.get_by_public_id",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.call_trajectory_service.DataScopeService.assert_call_record_in_scope",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.call_trajectory_service.CallEventRepository.list_for_call",
        AsyncMock(return_value=events),
    )
    monkeypatch.setattr(
        "app.services.call_trajectory_service._event_response_data",
        lambda event: {"event_id": event.event_id},
    )

    result = await CallTrajectoryService.get_trajectory(
        AsyncMock(),
        public_id=public_id,
        tenant_id=3,
        principal=SimpleNamespace(group_ids=[]),
    )

    assert result["settlement"]["event_id"] == "ended"
    assert result["is_complete"] is False
    assert result["warnings"] == [
        {"code": "trajectory_gap", "message": "Part of the call trajectory may be incomplete"}
    ]


def test_reconciliation_event_id_stays_within_limit_for_long_start_ids():
    start_event_id = (
        "opendesk:queue-entered:1:employee_group:138:"
        "de2d0cfa4b9845428c9dafe60c51e937"
    )
    event_id = _reconciliation_event_id("queue_exited", start_event_id)

    assert len(event_id) <= 96
    assert event_id.startswith("reconciliation:queue_exited:")
    assert event_id == _reconciliation_event_id("queue_exited", start_event_id)


@pytest.mark.asyncio
async def test_reconcile_open_intervals_accepts_long_queue_entered_ids(monkeypatch):
    started = datetime(2026, 8, 9, 13, 4, 44, tzinfo=timezone.utc)
    ended_at = started + timedelta(minutes=3)
    long_queue_event_id = (
        "opendesk:queue-entered:1:employee_group:138:"
        "de2d0cfa4b9845428c9dafe60c51e937"
    )
    open_queue = SimpleNamespace(
        event_id=long_queue_event_id,
        event_type="queue_entered",
        event_category="queue",
        occurred_at=started,
        operation_id=None,
        call_leg_id="call-1",
        parent_leg_id=None,
        participant_role="customer",
        actor_id=None,
        actor_name_snapshot=None,
        target_type="queue",
        target_id="138",
        target_name_snapshot="E2E 呼叫队列",
        queue_type="employee_group",
        queue_id=138,
        queue_name_snapshot="E2E 呼叫队列",
    )
    append = AsyncMock(return_value=(SimpleNamespace(id=1), True))
    monkeypatch.setattr(
        "app.services.call_trajectory_service.CallEventRepository.list_for_call",
        AsyncMock(return_value=[open_queue]),
    )
    monkeypatch.setattr(
        "app.services.call_trajectory_service.CallTrajectoryService.append_event",
        append,
    )

    created = await CallTrajectoryService.reconcile_open_intervals(
        AsyncMock(),
        call_record_id=1,
        ended_at=ended_at,
        commit=False,
    )

    assert created == 1
    queue_exit_payload = append.await_args_list[0].kwargs["payload"]
    assert queue_exit_payload.event_type == "queue_exited"
    assert len(queue_exit_payload.event_id) <= 96
    assert queue_exit_payload.details["synthesized_from_event_id"] == long_queue_event_id
    assert append.await_args_list[-1].kwargs["payload"].event_type == "trajectory_reconciled"
