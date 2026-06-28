"""
Unit tests for QueueMaterializationService.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.queue_materialization_service import QueueMaterializationService

NOW = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)


def _task(task_id, *, queue_type="employee_group", queue_id=1, enqueued_at=NOW, assigned_at=None):
    return SimpleNamespace(
        id=task_id,
        queue_type=queue_type,
        queue_id=queue_id,
        enqueued_at=enqueued_at,
        assigned_at=assigned_at,
        canceled_at=None,
        timeout_at=None,
    )


def _event(event_id, *, event_type, queue_type="employee_group", queue_id=1, snapshot=None, created_at=NOW):
    return SimpleNamespace(
        id=event_id,
        event_type=event_type,
        queue_type=queue_type,
        queue_id=queue_id,
        queue_name_snapshot=snapshot,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_materialize_writes_conversation_fields_and_rows(monkeypatch):
    conversation = SimpleNamespace(
        id=7,
        tenant_id=1,
        started_at=NOW,
        last_assigned_queue_type=None,
        last_assigned_queue_id=None,
        last_assigned_queue_name=None,
        total_queue_duration_seconds=None,
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=conversation)

    task = _task(1, assigned_at=NOW + timedelta(seconds=50))
    event = _event(1, event_type="auto_assigned", snapshot="售后组", created_at=NOW + timedelta(seconds=50))

    monkeypatch.setattr(
        "app.services.queue_materialization_service.QueueHistoryRepository.list_tasks_for_refs",
        AsyncMock(return_value=[task]),
    )
    monkeypatch.setattr(
        "app.services.queue_materialization_service.QueueHistoryRepository.list_events_for_tasks",
        AsyncMock(return_value=[event]),
    )
    monkeypatch.setattr(
        "app.services.queue_materialization_service.QueueHistoryRepository.current_queue_names",
        AsyncMock(return_value={}),
    )
    replace = AsyncMock()
    monkeypatch.setattr(
        "app.services.queue_materialization_service.ConversationQueueSummaryRepository.replace_for_conversation",
        replace,
    )

    await QueueMaterializationService.materialize_conversation(db, 1, 7)

    assert conversation.last_assigned_queue_type == "employee_group"
    assert conversation.last_assigned_queue_id == 1
    assert conversation.last_assigned_queue_name == "售后组"
    assert conversation.total_queue_duration_seconds == 50
    assert conversation.queue_entered_at == NOW
    assert conversation.queue_assigned_at == NOW + timedelta(seconds=50)
    assert conversation.queue_result == "assigned"

    replace.assert_awaited_once()
    _, _, conv_id, rows = replace.await_args.args
    assert conv_id == 7
    assert len(rows) == 1
    assert rows[0]["queue_type"] == "employee_group"
    assert rows[0]["wait_duration_seconds"] == 50
    assert rows[0]["is_last_assigned"] is True
    assert rows[0]["conversation_started_at"] == NOW


@pytest.mark.asyncio
async def test_materialize_skips_missing_conversation(monkeypatch):
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    replace = AsyncMock()
    monkeypatch.setattr(
        "app.services.queue_materialization_service.ConversationQueueSummaryRepository.replace_for_conversation",
        replace,
    )

    await QueueMaterializationService.materialize_conversation(db, 1, 999)

    replace.assert_not_awaited()
