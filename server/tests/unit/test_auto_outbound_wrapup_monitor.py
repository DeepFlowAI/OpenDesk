"""Unit tests for auto-outbound wrapup + monitor/stats aggregation."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ForbiddenError, ValidationError
from app.models.auto_outbound import AutoOutboundCallRecord, AutoOutboundTask
from app.schemas.auto_outbound import AutoOutboundWrapupRequest
from app.schemas.permission import EffectivePrincipal
from app.services.auto_outbound_task_service import AutoOutboundTaskService
from app.services.auto_outbound_event_service import AutoOutboundEventService


@pytest.fixture(autouse=True)
def _event_defaults(monkeypatch):
    monkeypatch.setattr(
        AutoOutboundEventService,
        "actor_snapshot",
        AsyncMock(return_value={"type": "employee", "name": "Agent"}),
    )
    monkeypatch.setattr(
        AutoOutboundEventService,
        "emit_business_record_event",
        AsyncMock(return_value=[]),
    )


def _principal(user_id: int = 77) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=user_id,
        tenant_id=1,
        permissions=["engagement.auto_outbound_task.manage"],
        is_super_admin=False,
    )


def _task(**overrides) -> AutoOutboundTask:
    data = dict(
        id=1,
        tenant_id=1,
        name="t",
        template_name="tpl",
        fields=[{"key": "note", "field_type": "single_line_text"}],
        status="active",
        execution_mode="agent",
        queue_id=30,
        pacing_mode="predictive",
        dial_intensity=Decimal("1.5"),
        abandon_rate_limit=Decimal("0.03"),
        abandon_prompt="hangup",
        wrapup_seconds=60,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        daily_time_windows=[],
        max_concurrency=10,
        retry_policy={},
        daily_per_number_limit=3,
    )
    data.update(overrides)
    return AutoOutboundTask(**data)


def _record(**overrides) -> AutoOutboundCallRecord:
    data = dict(
        id=100,
        tenant_id=1,
        task_id=1,
        target_id=10,
        phone_number="13800138000",
        attempt_no=1,
        started_at=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc),
        answered_at=datetime(2026, 8, 7, 10, 0, 5, tzinfo=timezone.utc),
        ended_at=datetime(2026, 8, 7, 10, 1, tzinfo=timezone.utc),
        duration_ms=55000,
        terminal_state="answered",
        reception_type="agent",
        agent_id=77,
        reception_result=None,
    )
    data.update(overrides)
    return AutoOutboundCallRecord(**data)


@pytest.mark.asyncio
async def test_wrapup_submit_writes_target_fields(monkeypatch):
    task = _task()
    record = _record(
        ended_at=None,
        reception_result={"assigned": True, "agent_id": 77},
    )
    target = SimpleNamespace(id=10, field_values={"old": "1"})

    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_task",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_record_for_task",
        AsyncMock(return_value=record),
    )

    async def update_record(db, item, data, **_kwargs):
        for k, v in data.items():
            setattr(item, k, v)
        return item

    update_target = AsyncMock(return_value=target)
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.update_record",
        update_record,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_target",
        AsyncMock(return_value=target),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.update_target",
        update_target,
    )

    db = AsyncMock()
    result = await AutoOutboundTaskService.submit_wrapup(
        db,
        _principal(77),
        1,
        100,
        AutoOutboundWrapupRequest(field_values={"note": "已回访"}),
    )
    assert result.reception_result["field_values"]["note"] == "已回访"
    assert result.reception_result["auto_submitted"] is False
    assert result.reception_result["assigned"] is True
    update_target.assert_awaited()
    assert update_target.await_args.args[2]["field_values"]["note"] == "已回访"
    assert update_target.await_args.kwargs["commit"] is False
    event = AutoOutboundEventService.emit_business_record_event
    event.assert_awaited_once()
    assert event.await_args.kwargs["event_type"] == (
        "auto_outbound.business_record.submitted"
    )
    assert event.await_args.kwargs["keys"] == ["note"]
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrapup_rejects_wrong_agent(monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_task",
        AsyncMock(return_value=_task()),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_record_for_task",
        AsyncMock(return_value=_record(agent_id=99)),
    )
    with pytest.raises(ForbiddenError):
        await AutoOutboundTaskService.submit_wrapup(
            MagicMock(),
            _principal(77),
            1,
            100,
            AutoOutboundWrapupRequest(field_values={"note": "x"}),
        )


@pytest.mark.asyncio
async def test_wrapup_allows_repeated_submit_and_emits_updated(monkeypatch):
    record = _record(
        reception_result={
            "assigned": True,
            "field_values": {"note": "done"},
            "auto_submitted": False,
            "submitted_by": 77,
        }
    )
    target = SimpleNamespace(id=10, field_values={"note": "done"})
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_task",
        AsyncMock(return_value=_task()),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_record_for_task",
        AsyncMock(return_value=record),
    )

    async def update_record(db, item, data, **_kwargs):
        for key, value in data.items():
            setattr(item, key, value)
        return item

    update_target = AsyncMock(return_value=target)
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.update_record",
        update_record,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_target",
        AsyncMock(return_value=target),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.update_target",
        update_target,
    )

    db = AsyncMock()
    result = await AutoOutboundTaskService.submit_wrapup(
        db,
        _principal(77),
        1,
        100,
        AutoOutboundWrapupRequest(field_values={"note": "again"}),
    )

    assert result.reception_result["field_values"] == {"note": "again"}
    assert result.reception_result["assigned"] is True
    assert update_target.await_args.args[2]["field_values"] == {"note": "again"}
    event = AutoOutboundEventService.emit_business_record_event
    event.assert_awaited_once()
    assert event.await_args.kwargs["event_type"] == (
        "auto_outbound.business_record.updated"
    )
    assert event.await_args.kwargs["keys_name"] == "changed_keys"
    assert event.await_args.kwargs["keys"] == ["note"]
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrapup_same_value_resubmit_succeeds_without_event(monkeypatch):
    record = _record(
        reception_result={
            "field_values": {"note": "same"},
            "auto_submitted": False,
            "submitted_by": 77,
        }
    )
    target = SimpleNamespace(id=10, field_values={"note": "same"})
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_task",
        AsyncMock(return_value=_task()),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_record_for_task",
        AsyncMock(return_value=record),
    )

    async def update_record(db, item, data, **_kwargs):
        for key, value in data.items():
            setattr(item, key, value)
        return item

    update_target = AsyncMock()
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.update_record",
        update_record,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_target",
        AsyncMock(return_value=target),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.update_target",
        update_target,
    )

    db = AsyncMock()
    result = await AutoOutboundTaskService.submit_wrapup(
        db,
        _principal(77),
        1,
        100,
        AutoOutboundWrapupRequest(field_values={"note": "same"}),
    )

    assert result.reception_result["field_values"] == {"note": "same"}
    update_target.assert_not_awaited()
    AutoOutboundEventService.emit_business_record_event.assert_not_awaited()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_stats_result_distribution_and_abandon_flag(monkeypatch):
    task = _task(execution_mode="bot", pacing_mode=None, abandon_rate_limit=None)
    records = [
        _record(
            reception_type="bot",
            agent_id=None,
            reception_result={"intent": "A", "handoff": True},
        ),
        _record(
            id=101,
            reception_type="bot",
            agent_id=None,
            reception_result={"intent": "A", "handoff": False},
        ),
        _record(
            id=102,
            reception_type="bot",
            agent_id=None,
            reception_result={"intent": "B", "handoff": False},
            answered_at=None,
        ),
    ]
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_task",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.daily_trend",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.terminal_state_distribution",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.list_records_for_stats",
        AsyncMock(return_value=records),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.abandon_counts",
        AsyncMock(return_value={"answered": 2, "abandoned": 0}),
    )
    stats = await AutoOutboundTaskService.get_stats(MagicMock(), _principal(), 1)
    assert stats.result_distribution["intents"] == {"A": 2, "B": 1}
    assert stats.result_distribution["handoff_count"] == 1


@pytest.mark.asyncio
async def test_monitor_abandon_over_limit(monkeypatch):
    task = _task()
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.get_task",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.count_in_progress_calls",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundRepository.abandon_counts",
        AsyncMock(return_value={"answered": 10, "abandoned": 2}),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.count_ready_agents_for_queue",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.count_in_call_agents_for_queue",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.frequency._default_redis",
        MagicMock(side_effect=RuntimeError("no redis")),
    )

    monitor = await AutoOutboundTaskService.get_monitor(MagicMock(), _principal(), 1)
    assert monitor.no_ready_agents is True
    assert monitor.abandon_rate == pytest.approx(0.2)
    assert monitor.abandon_over_limit is True
    assert monitor.in_call_agents == 1


@pytest.mark.asyncio
async def test_build_agent_result_distribution():
    task = _task()
    records = [
        _record(agent_id=1, duration_ms=1000),
        _record(id=2, agent_id=1, duration_ms=3000),
        _record(id=3, agent_id=2, duration_ms=2000),
    ]
    dist = AutoOutboundTaskService._build_result_distribution(task, records)
    by_id = {row["agent_id"]: row for row in dist["agents"]}
    assert by_id[1]["answered"] == 2
    assert by_id[1]["avg_duration_ms"] == 2000
    assert by_id[2]["answered"] == 1
