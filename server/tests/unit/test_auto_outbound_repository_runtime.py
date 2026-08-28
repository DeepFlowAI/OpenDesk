"""Unit tests for auto-outbound repository API-facing helpers."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.auto_outbound import AutoOutboundTarget, AutoOutboundTask
from app.repositories.auto_outbound_repository import (
    AutoOutboundRepository,
    _max_policy_retries,
    _used_retry_total,
)


def test_remaining_retries_helpers():
    assert _max_policy_retries(
        {"no_answer": {"max_retries": 2}, "busy": {"max_retries": 1}}
    ) == 2
    assert _used_retry_total({"no_answer": 1, "busy": 1}) == 2
    assert max(0, 2 - 2) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [("active", True), ("paused", False), (None, False)],
)
async def test_is_task_active_checks_current_status(status, expected):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = status
    db.execute = AsyncMock(return_value=result)

    assert await AutoOutboundRepository.is_task_active(db, task_id=7) is expected
    stmt = db.execute.await_args.args[0]
    assert 7 in stmt.compile().params.values()


@pytest.mark.asyncio
async def test_list_tasks_excludes_archived_by_default():
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    db.execute = AsyncMock(side_effect=[count_result, result])

    await AutoOutboundRepository.list_tasks(db, tenant_id=1, page=1, per_page=20)
    # First execute is count; default filter is status != archived (bound param).
    count_stmt = db.execute.await_args_list[0].args[0]
    compiled = str(count_stmt).lower()
    assert "status !=" in compiled or "status!=" in compiled
    # Confirm the bound value is archived.
    bound = count_stmt.compile().params
    assert "archived" in bound.values()


@pytest.mark.asyncio
async def test_list_targets_attaches_user_name_and_remaining_retries():
    task = AutoOutboundTask(
        id=1,
        tenant_id=1,
        name="t",
        template_name="tpl",
        fields=[],
        status="active",
        execution_mode="ivr",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        daily_time_windows=[],
        max_concurrency=1,
        retry_policy={"no_answer": {"max_retries": 3}, "busy": {"max_retries": 1}},
        daily_per_number_limit=1,
    )
    target = AutoOutboundTarget(
        id=10,
        tenant_id=1,
        task_id=1,
        phone_number="13800138000",
        user_id=5,
        status="pending",
        field_values={},
        call_count=1,
        answered_count=0,
        retry_counts={"no_answer": 1},
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=task)

    count_result = MagicMock()
    count_result.scalar_one.return_value = 1
    rows_result = MagicMock()
    rows_result.all.return_value = [(target, "Alice")]
    db.execute = AsyncMock(side_effect=[count_result, rows_result])

    items, total = await AutoOutboundRepository.list_targets(
        db, tenant_id=1, task_id=1, page=1, per_page=20
    )
    assert total == 1
    assert len(items) == 1
    assert items[0].user_name == "Alice"
    # max_policy=3, used_total=1 → remaining 2
    assert items[0].remaining_retries == 2


@pytest.mark.asyncio
async def test_task_stats_includes_rates():
    db = AsyncMock()
    target_row = SimpleNamespace(
        task_id=1,
        total_targets=10,
        finished_targets=4,
        call_count=8,
        answered_count=2,
    )
    target_result = MagicMock()
    target_result.__iter__ = lambda self: iter([target_row])

    transfer_row = SimpleNamespace(task_id=1, transfer_count=3, abandon_count=1)
    transfer_result = MagicMock()
    transfer_result.__iter__ = lambda self: iter([transfer_row])

    db.execute = AsyncMock(side_effect=[target_result, transfer_result])

    stats = await AutoOutboundRepository.task_stats(db, tenant_id=1, task_ids=[1])
    assert stats[1]["answer_rate"] == pytest.approx(0.25)
    assert stats[1]["transfer_count"] == 3
    assert stats[1]["abandon_count"] == 1


@pytest.mark.asyncio
async def test_list_stale_calling_targets_query_shape():
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)

    await AutoOutboundRepository.list_stale_calling_targets(
        db, updated_before=datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc)
    )
    stmt = db.execute.await_args.args[0]
    compiled = str(stmt).lower()
    assert "updated_at" in compiled
    assert "calling" in stmt.compile().params.values()


@pytest.mark.asyncio
async def test_mark_answered_once_uses_conditional_record_update_and_atomic_increment():
    db = AsyncMock()
    record_result = MagicMock(rowcount=1)
    target_result = MagicMock(rowcount=1)
    db.execute = AsyncMock(side_effect=[record_result, target_result])

    claimed = await AutoOutboundRepository.mark_answered_once(
        db,
        record_id=100,
        target_id=10,
        answered_at=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc),
    )

    assert claimed is True
    record_stmt, target_stmt = [call.args[0] for call in db.execute.await_args_list]
    record_sql = str(record_stmt).lower()
    target_sql = str(target_stmt).lower()
    assert "answered_at is null" in record_sql
    assert "ended_at is null" in record_sql
    assert "answered_count" in target_sql and "+" in target_sql
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_record_once_claims_only_open_record_and_returns_db_terminal():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "answered"
    db.execute = AsyncMock(return_value=result)

    terminal = await AutoOutboundRepository.finalize_record_once(
        db,
        record_id=100,
        ended_at=datetime(2026, 8, 7, 10, 1, tzinfo=timezone.utc),
        duration_ms=60_000,
        terminal_state="no_answer",
        fail_reason=None,
    )

    assert terminal == "answered"
    stmt = db.execute.await_args.args[0]
    compiled = str(stmt).lower()
    assert "ended_at is null" in compiled
    assert "case" in compiled
    assert "returning" in compiled
    db.commit.assert_awaited_once()
