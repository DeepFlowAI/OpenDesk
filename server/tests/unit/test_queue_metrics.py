"""
Unit tests for the shared queue waiting-time caliber.
"""
from datetime import datetime, timedelta, timezone

from app.libs.queue_metrics import (
    compute_conversation_queue_summary,
    terminal_time,
    wait_seconds,
)
from types import SimpleNamespace

NOW = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)


def _task(
    task_id,
    *,
    queue_type="employee_group",
    queue_id=1,
    enqueued_at=NOW,
    assigned_at=None,
    canceled_at=None,
    timeout_at=None,
):
    return SimpleNamespace(
        id=task_id,
        queue_type=queue_type,
        queue_id=queue_id,
        enqueued_at=enqueued_at,
        assigned_at=assigned_at,
        canceled_at=canceled_at,
        timeout_at=timeout_at,
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


def test_wait_seconds_uses_earliest_terminal():
    task = _task(1, assigned_at=NOW + timedelta(seconds=30), canceled_at=NOW + timedelta(seconds=90))
    assert terminal_time(task) == NOW + timedelta(seconds=30)
    assert wait_seconds(task) == 30


def test_wait_seconds_zero_when_still_waiting():
    assert wait_seconds(_task(1)) == 0


def test_empty_tasks_returns_empty_result():
    result = compute_conversation_queue_summary(tasks=[], events=[], current_names={})
    assert result.total_queue_duration_seconds is None
    assert result.last_assigned_queue_type is None
    assert result.rows == []


def test_single_queue_assigned():
    task = _task(1, assigned_at=NOW + timedelta(seconds=86))
    event = _event(1, event_type="auto_assigned", snapshot="售后组", created_at=NOW + timedelta(seconds=86))
    result = compute_conversation_queue_summary(tasks=[task], events=[event], current_names={})

    assert result.total_queue_duration_seconds == 86
    assert result.last_assigned_queue_type == "employee_group"
    assert result.last_assigned_queue_id == 1
    assert result.last_assigned_queue_name == "售后组"
    assert len(result.rows) == 1
    assert result.rows[0].is_last_assigned is True
    assert result.rows[0].wait_duration_seconds == 86
    assert result.rows[0].queue_result == "assigned"


def test_multi_queue_last_assigned_is_latest_success_event():
    # Queue 1: queued then canceled (waited 40s). Queue 2: assigned (waited 20s).
    t1 = _task(1, queue_type="employee_group", queue_id=1, canceled_at=NOW + timedelta(seconds=40))
    t2 = _task(
        2,
        queue_type="employee",
        queue_id=9,
        enqueued_at=NOW + timedelta(seconds=40),
        assigned_at=NOW + timedelta(seconds=60),
    )
    e_cancel = _event(1, event_type="canceled", queue_type="employee_group", queue_id=1, snapshot="A组", created_at=NOW + timedelta(seconds=40))
    e_assign = _event(2, event_type="pull_assigned", queue_type="employee", queue_id=9, snapshot="张三", created_at=NOW + timedelta(seconds=60))

    result = compute_conversation_queue_summary(
        tasks=[t1, t2], events=[e_cancel, e_assign], current_names={}
    )

    assert result.total_queue_duration_seconds == 60
    assert result.last_assigned_queue_type == "employee"
    assert result.last_assigned_queue_id == 9
    assert result.last_assigned_queue_name == "张三"

    rows = {(r.queue_type, r.queue_id): r for r in result.rows}
    assert rows[("employee_group", 1)].wait_duration_seconds == 40
    assert rows[("employee_group", 1)].is_last_assigned is False
    assert rows[("employee_group", 1)].queue_name_snapshot == "A组"
    assert rows[("employee_group", 1)].queue_result == "canceled"
    assert rows[("employee", 9)].wait_duration_seconds == 20
    assert rows[("employee", 9)].is_last_assigned is True
    assert rows[("employee", 9)].queue_result == "assigned"


def test_name_falls_back_to_current_names_without_snapshot():
    task = _task(1, assigned_at=NOW + timedelta(seconds=10))
    event = _event(1, event_type="auto_assigned", snapshot=None, created_at=NOW + timedelta(seconds=10))
    result = compute_conversation_queue_summary(
        tasks=[task], events=[event], current_names={("employee_group", 1): "当前组"}
    )
    assert result.last_assigned_queue_name == "当前组"
    assert result.rows[0].queue_name_snapshot == "当前组"


def test_zero_wait_total_is_none_but_row_kept():
    task = _task(1, assigned_at=NOW)
    event = _event(1, event_type="auto_assigned", snapshot="即时分配", created_at=NOW)
    result = compute_conversation_queue_summary(tasks=[task], events=[event], current_names={})
    assert result.total_queue_duration_seconds is None
    assert len(result.rows) == 1
    assert result.rows[0].wait_duration_seconds == 0
    assert result.rows[0].is_last_assigned is True
    # No substantial task -> no per-queue result either.
    assert result.rows[0].queue_result is None
    # No substantial task -> no lifecycle.
    assert result.queue_entered_at is None
    assert result.queue_assigned_at is None
    assert result.queue_result is None


def test_lifecycle_assigned_uses_substantial_tasks():
    task = _task(1, assigned_at=NOW + timedelta(seconds=86))
    event = _event(1, event_type="auto_assigned", created_at=NOW + timedelta(seconds=86))
    result = compute_conversation_queue_summary(tasks=[task], events=[event], current_names={})

    assert result.queue_entered_at == NOW
    assert result.queue_assigned_at == NOW + timedelta(seconds=86)
    assert result.queue_result == "assigned"


def test_lifecycle_latest_substantial_task_canceled():
    # Earlier queue assigned, later re-queue canceled: latest substantial task wins.
    t1 = _task(1, queue_type="employee_group", queue_id=1, assigned_at=NOW + timedelta(seconds=30))
    t2 = _task(
        2,
        queue_type="employee",
        queue_id=9,
        enqueued_at=NOW + timedelta(seconds=40),
        canceled_at=NOW + timedelta(seconds=70),
    )
    result = compute_conversation_queue_summary(tasks=[t1, t2], events=[], current_names={})

    assert result.queue_entered_at == NOW
    assert result.queue_assigned_at == NOW + timedelta(seconds=30)
    assert result.queue_result == "canceled"

    rows = {(r.queue_type, r.queue_id): r for r in result.rows}
    assert rows[("employee_group", 1)].queue_result == "assigned"
    assert rows[("employee", 9)].queue_result == "canceled"
