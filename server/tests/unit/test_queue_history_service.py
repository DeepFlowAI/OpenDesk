from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.repositories.queue_history_repository import QueueHistoryRepository
from app.services.queue_history_service import QueueHistoryService


def _task(
    task_id: int,
    ref_id: str,
    *,
    queue_type: str = "employee_group",
    queue_id: int = 1,
    enqueued_at: datetime,
    assigned_at: datetime | None = None,
    canceled_at: datetime | None = None,
    timeout_at: datetime | None = None,
):
    return SimpleNamespace(
        id=task_id,
        task_ref_id=ref_id,
        queue_type=queue_type,
        queue_id=queue_id,
        enqueued_at=enqueued_at,
        assigned_at=assigned_at,
        canceled_at=canceled_at,
        timeout_at=timeout_at,
    )


def _event(
    event_id: int,
    task_id: int,
    *,
    queue_type: str = "employee_group",
    queue_id: int = 1,
    snapshot: str | None = None,
    created_at: datetime,
):
    return SimpleNamespace(
        id=event_id,
        task_id=task_id,
        queue_type=queue_type,
        queue_id=queue_id,
        queue_name_snapshot=snapshot,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_summaries_use_assignment_snapshot_and_wait_duration(monkeypatch):
    now = datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)
    task = _task(1, "42", enqueued_at=now, assigned_at=now + timedelta(seconds=86))
    event = _event(1, 1, snapshot="售后组", created_at=now + timedelta(seconds=86))

    async def fake_tasks(*_args, **_kwargs):
        return [task]

    async def fake_events(*_args, **_kwargs):
        return [event]

    async def fake_names(*_args, **_kwargs):
        return {("employee_group", 1): "当前售后组"}

    monkeypatch.setattr(QueueHistoryRepository, "list_tasks_for_refs", fake_tasks)
    monkeypatch.setattr(QueueHistoryRepository, "list_success_events", fake_events)
    monkeypatch.setattr(QueueHistoryRepository, "current_queue_names", fake_names)

    summaries = await QueueHistoryService.summaries_for_refs(
        object(),
        7,
        channel="online_chat",
        task_types=["conversation"],
        ref_ids=["42"],
    )

    assert summaries["42"]["last_assigned_queue"] == {
        "queue_type": "employee_group",
        "queue_id": 1,
        "name": "售后组",
    }
    assert summaries["42"]["queue_duration_seconds"] == 86


@pytest.mark.asyncio
async def test_summaries_fallback_to_current_name_when_snapshot_missing(monkeypatch):
    now = datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)
    task = _task(
        1,
        "call-1",
        queue_type="employee",
        queue_id=9,
        enqueued_at=now,
        assigned_at=now + timedelta(seconds=12),
    )
    event = _event(
        1,
        1,
        queue_type="employee",
        queue_id=9,
        snapshot=None,
        created_at=now + timedelta(seconds=12),
    )

    async def fake_tasks(*_args, **_kwargs):
        return [task]

    async def fake_events(*_args, **_kwargs):
        return [event]

    async def fake_names(*_args, **_kwargs):
        return {("employee", 9): "张三"}

    monkeypatch.setattr(QueueHistoryRepository, "list_tasks_for_refs", fake_tasks)
    monkeypatch.setattr(QueueHistoryRepository, "list_success_events", fake_events)
    monkeypatch.setattr(QueueHistoryRepository, "current_queue_names", fake_names)

    summaries = await QueueHistoryService.summaries_for_refs(
        object(),
        7,
        channel="call_center",
        task_types=["call"],
        ref_ids=["call-1"],
    )

    assert summaries["call-1"]["last_assigned_queue"] == {
        "queue_type": "employee",
        "queue_id": 9,
        "name": "张三",
    }
    assert summaries["call-1"]["queue_duration_seconds"] == 12


@pytest.mark.asyncio
async def test_summaries_keep_deleted_queue_empty_without_snapshot(monkeypatch):
    now = datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)
    task = _task(1, "42", enqueued_at=now, assigned_at=now + timedelta(seconds=1))
    event = _event(1, 1, snapshot=None, created_at=now + timedelta(seconds=1))

    async def fake_tasks(*_args, **_kwargs):
        return [task]

    async def fake_events(*_args, **_kwargs):
        return [event]

    async def fake_names(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(QueueHistoryRepository, "list_tasks_for_refs", fake_tasks)
    monkeypatch.setattr(QueueHistoryRepository, "list_success_events", fake_events)
    monkeypatch.setattr(QueueHistoryRepository, "current_queue_names", fake_names)

    summaries = await QueueHistoryService.summaries_for_refs(
        object(),
        7,
        channel="online_chat",
        task_types=["conversation"],
        ref_ids=["42"],
    )

    assert summaries["42"]["last_assigned_queue"] is None
    assert summaries["42"]["queue_duration_seconds"] == 1


@pytest.mark.asyncio
async def test_summaries_omit_zero_second_wait(monkeypatch):
    now = datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)
    task = _task(1, "42", enqueued_at=now, assigned_at=now)

    async def fake_tasks(*_args, **_kwargs):
        return [task]

    async def fake_events(*_args, **_kwargs):
        return []

    async def fake_names(*_args, **_kwargs):
        return {("employee_group", 1): "售前组"}

    monkeypatch.setattr(QueueHistoryRepository, "list_tasks_for_refs", fake_tasks)
    monkeypatch.setattr(QueueHistoryRepository, "list_success_events", fake_events)
    monkeypatch.setattr(QueueHistoryRepository, "current_queue_names", fake_names)

    summaries = await QueueHistoryService.summaries_for_refs(
        object(),
        7,
        channel="online_chat",
        task_types=["conversation"],
        ref_ids=["42"],
    )

    assert summaries["42"]["last_assigned_queue"]["name"] == "售前组"
    assert summaries["42"]["queue_duration_seconds"] is None
