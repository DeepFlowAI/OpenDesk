"""Unit tests for AutoOutboundDialEngine claim / dial / terminal flows."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import fakeredis.aioredis
import pytest

from app.models.auto_outbound import AutoOutboundCallRecord, AutoOutboundTarget, AutoOutboundTask
from app.services.auto_outbound.engine import (
    AUTO_PAUSE_REASON_DIAL_UNAVAILABLE,
    AUTO_PAUSE_REASON_QUEUE_FINISHED,
    AutoOutboundDialEngine,
    next_daily_window_start,
)
from app.services.auto_outbound.simulator import CallSimulator, SimulationProfile
from app.services.auto_outbound.tenant_time import clear_tenant_timezone_cache
from app.services.auto_outbound_event_service import AutoOutboundEventService


@pytest.fixture(autouse=True)
def _engine_scan_defaults(monkeypatch):
    """Avoid MagicMock DB side-effects for timezone resolve / stale sweep."""
    clear_tenant_timezone_cache()
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.resolve_tenant_timezone",
        AsyncMock(return_value=ZoneInfo("Asia/Shanghai")),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_stale_calling_targets",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_paused_tasks",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.is_task_active",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_task",
        AsyncMock(return_value=_task()),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.mark_answered_once",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundEventService.emit_task_event",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundEventService.emit_call_event",
        AsyncMock(return_value=[]),
    )

    async def _finalize_record_once(_db, **kwargs):
        return kwargs["terminal_state"]

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.finalize_record_once",
        _finalize_record_once,
    )
    yield
    clear_tenant_timezone_cache()


def _task(**overrides) -> AutoOutboundTask:
    data = dict(
        id=1,
        tenant_id=1,
        name="t",
        template_name="tpl",
        fields=[],
        status="active",
        execution_mode="ivr",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        daily_time_windows=[{"start": "00:00", "end": "23:59"}],
        caller_number_id="pn_1",
        max_concurrency=2,
        retry_policy={
            "no_answer": {"max_retries": 2, "interval_minutes": 30},
            "busy": {"max_retries": 1, "interval_minutes": 10},
            "power_off": {"max_retries": 1, "interval_minutes": 10},
        },
        daily_per_number_limit=3,
        wrapup_seconds=60,
    )
    data.update(overrides)
    return AutoOutboundTask(**data)


def _target(**overrides) -> AutoOutboundTarget:
    data = dict(
        id=10,
        tenant_id=1,
        task_id=1,
        phone_number="13800138000",
        status="pending",
        field_values={},
        call_count=0,
        answered_count=0,
        retry_counts={},
        next_call_at=None,
    )
    data.update(overrides)
    return AutoOutboundTarget(**data)


def _record(**overrides) -> AutoOutboundCallRecord:
    data = dict(
        id=100,
        tenant_id=1,
        task_id=1,
        target_id=10,
        phone_number="13800138000",
        attempt_no=1,
        started_at=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc),
        duration_ms=0,
    )
    data.update(overrides)
    return AutoOutboundCallRecord(**data)


class _SessionCM:
    """Minimal async session context manager for injecting into the engine."""

    def __init__(self, db=None):
        self.db = db or MagicMock()
        if db is None:
            self.db.commit = AsyncMock()
            self.db.refresh = AsyncMock()

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *args):
        return False


@pytest.fixture
async def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_claim_due_targets_skip_locked_shape():
    """Repository claim uses FOR UPDATE SKIP LOCKED and flips status."""
    from app.repositories.auto_outbound_repository import AutoOutboundRepository

    target = _target(status="pending")
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [target]
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    claimed = await AutoOutboundRepository.claim_due_targets(
        db, task_id=1, now=datetime.now(timezone.utc), limit=10
    )
    assert len(claimed) == 1
    assert claimed[0][0].status == "calling"
    assert claimed[0][1] == "pending"
    db.commit.assert_awaited()
    # Ensure the compiled statement asked for skip_locked
    stmt = db.execute.await_args.args[0]
    assert "FOR UPDATE" in str(stmt).upper() or True  # dialect may render later
    # with_for_update was applied on the selectable
    assert stmt._for_update_arg is not None
    assert stmt._for_update_arg.skip_locked is True


@pytest.mark.asyncio
async def test_restore_claimed_targets_groups_previous_statuses():
    from app.repositories.auto_outbound_repository import AutoOutboundRepository

    db = AsyncMock()
    pending_result = MagicMock(rowcount=2)
    redial_result = MagicMock(rowcount=1)
    db.execute = AsyncMock(side_effect=[pending_result, redial_result])
    db.commit = AsyncMock()

    restored = await AutoOutboundRepository.restore_claimed_targets(
        db,
        [(10, "pending"), (11, "pending"), (12, "redial_pending")],
    )

    assert restored == 3
    assert db.execute.await_count == 2
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_waits_for_active_scan_without_cancelling(monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_DIAL_SCAN_INTERVAL_SECONDS",
        60,
    )
    scan_started = asyncio.Event()
    allow_scan_to_finish = asyncio.Event()
    scan_completed = False
    engine = AutoOutboundDialEngine(session_factory=lambda: _SessionCM())

    async def _scan_once():
        nonlocal scan_completed
        scan_started.set()
        await allow_scan_to_finish.wait()
        scan_completed = True

    engine.scan_once = _scan_once  # type: ignore[method-assign]
    await engine.start()
    await asyncio.wait_for(scan_started.wait(), timeout=1)

    stop_task = asyncio.create_task(engine.stop())
    await asyncio.sleep(0)
    assert not stop_task.done()

    allow_scan_to_finish.set()
    await asyncio.wait_for(stop_task, timeout=1)
    assert scan_completed is True


@pytest.mark.asyncio
async def test_stop_during_claim_batch_restores_unprocessed_tail(redis, monkeypatch):
    task = _task()
    claimed = [
        (_target(id=10, status="calling"), "pending"),
        (_target(id=11, status="calling"), "redial_pending"),
        (_target(id=12, status="calling"), "pending"),
    ]
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[task]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        AsyncMock(return_value=claimed),
    )
    restore_claims = AsyncMock(return_value=2)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.restore_claimed_targets",
        restore_claims,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=1),
    )

    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    processed: list[int] = []

    async def _process(_snap, *, target_id: int, **_kwargs):
        processed.append(target_id)
        engine._stopping = True
        return True

    engine._process_claimed_target = _process  # type: ignore[method-assign]
    stats = await engine.scan_once(
        now=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc)
    )

    assert processed == [10]
    assert stats["dialed"] == 1
    restore_claims.assert_awaited_once()
    assert restore_claims.await_args.args[1] == [
        (11, "redial_pending"),
        (12, "pending"),
    ]


@pytest.mark.asyncio
async def test_pause_during_claim_batch_stops_dialing_and_restores_tail(redis, monkeypatch):
    task = _task()
    claimed = [
        (_target(id=10, status="calling"), "pending"),
        (_target(id=11, status="calling"), "redial_pending"),
        (_target(id=12, status="calling"), "pending"),
    ]
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[task]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        AsyncMock(return_value=claimed),
    )
    task_active = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.is_task_active",
        task_active,
    )
    restore_claims = AsyncMock(return_value=2)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.restore_claimed_targets",
        restore_claims,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=1),
    )

    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    processed: list[int] = []

    async def _process(_snap, *, target_id: int, **_kwargs):
        processed.append(target_id)
        return True

    engine._process_claimed_target = _process  # type: ignore[method-assign]
    stats = await engine.scan_once(
        now=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc)
    )

    assert processed == [10]
    assert stats["dialed"] == 1
    assert task_active.await_count == 2
    restore_claims.assert_awaited_once()
    assert restore_claims.await_args.args[1] == [
        (11, "redial_pending"),
        (12, "pending"),
    ]


@pytest.mark.asyncio
async def test_scan_skips_out_of_window(redis, monkeypatch):
    task = _task(daily_time_windows=[{"start": "09:00", "end": "12:00"}])
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[task]),
    )
    claim = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        claim,
    )
    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    # 08:00 local — outside window
    now = datetime(2026, 8, 7, 8, 0, 0).astimezone()
    stats = await engine.scan_once(now=now)
    assert stats["skipped"] >= 1
    claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrency_full_restores_status_without_freq(redis, monkeypatch):
    task = _task(max_concurrency=1)
    target = _target(status="calling")
    # Pre-fill concurrency
    from app.services.auto_outbound import frequency as freq

    assert await freq.acquire_concurrency(1, 1, redis=redis)

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[task]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        AsyncMock(return_value=[(target, "pending")]),
    )
    restore_target = _target(id=10, status="calling")
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(return_value=restore_target),
    )
    update_target = AsyncMock(return_value=restore_target)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=1),
    )

    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    now = datetime(2026, 8, 7, 10, 0, 0).astimezone()
    stats = await engine.scan_once(now=now)
    assert stats["dialed"] == 0
    # Frequency key must not exist — concurrency short-circuit before incr
    day = now.strftime("%Y%m%d")
    assert await redis.get(freq.freq_key(1, "13800138000", day)) is None
    update_target.assert_awaited()
    assert update_target.await_args.args[2]["status"] == "pending"


@pytest.mark.asyncio
async def test_frequency_defer_releases_concurrency(redis, monkeypatch):
    task = _task(daily_per_number_limit=1, max_concurrency=5)
    target = _target(status="calling")
    from app.services.auto_outbound import frequency as freq
    now = datetime(2026, 8, 7, 10, 0, 0).astimezone()

    # Burn the daily slot first
    assert await freq.check_and_incr(
        1, "13800138000", 1, redis=redis, now=now
    ) is True

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[task]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        AsyncMock(return_value=[(target, "pending")]),
    )
    defer_target = _target(id=10, status="calling")
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(return_value=defer_target),
    )
    update_target = AsyncMock(return_value=defer_target)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=1),
    )

    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    await engine.scan_once(now=now)

    # Concurrency released after frequency deny
    inflight = await redis.get(freq.inflight_key(1))
    assert inflight is None or int(inflight) == 0
    patch = update_target.await_args.args[2]
    assert patch["status"] == "pending"
    assert patch["next_call_at"] is not None


@pytest.mark.asyncio
async def test_terminal_answered_completes_target(redis, monkeypatch):
    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    record = _record()
    target = _target(status="calling", call_count=1)
    task = _task()

    from app.services.auto_outbound import frequency as freq

    await freq.set_session_mapping(
        "c1",
        {
            "tenant_id": 1,
            "task_id": 1,
            "target_id": 10,
            "record_id": 100,
            "phone_number": "13800138000",
            "answered": True,
        },
        redis=redis,
    )
    await freq.acquire_concurrency(1, 10, redis=redis)

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_task",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(return_value=target),
    )
    update_target = AsyncMock(return_value=target)
    update_task = AsyncMock(return_value=task)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_task",
        update_task,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=0),
    )

    await engine.handle_call_ended("c1", "normal", 200)

    assert update_target.await_args.args[2]["status"] == "completed"
    # Queue finished → task auto-pauses with queue_finished reason (not completed).
    assert update_task.await_args.args[2]["status"] == "paused"
    assert update_task.await_args.args[2]["auto_pause_reason"] == AUTO_PAUSE_REASON_QUEUE_FINISHED
    assert await freq.get_session_mapping("c1", redis=redis) is None


@pytest.mark.asyncio
async def test_terminal_no_answer_redial_pending(redis, monkeypatch):
    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    record = _record()
    target = _target(status="calling", call_count=1, retry_counts={})
    task = _task()

    from app.services.auto_outbound import frequency as freq

    await freq.set_session_mapping(
        "c2",
        {
            "tenant_id": 1,
            "task_id": 1,
            "target_id": 10,
            "record_id": 100,
            "phone_number": "13800138000",
            "answered": False,
        },
        redis=redis,
    )
    await freq.acquire_concurrency(1, 10, redis=redis)

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_task",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(return_value=target),
    )
    update_target = AsyncMock(return_value=target)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=1),
    )

    before = datetime.now(timezone.utc)
    await engine.handle_call_ended("c2", "no_answer", 408)
    patch = update_target.await_args.args[2]
    assert patch["status"] == "redial_pending"
    assert patch["retry_counts"]["no_answer"] == 1
    assert patch["next_call_at"] >= before + timedelta(minutes=29)


@pytest.mark.asyncio
async def test_terminal_no_answer_retry_exhausted(redis, monkeypatch):
    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    record = _record()
    target = _target(status="calling", call_count=3, retry_counts={"no_answer": 2})
    task = _task()

    from app.services.auto_outbound import frequency as freq

    await freq.set_session_mapping(
        "c3",
        {
            "tenant_id": 1,
            "task_id": 1,
            "target_id": 10,
            "record_id": 100,
            "phone_number": "13800138000",
            "answered": False,
        },
        redis=redis,
    )
    await freq.acquire_concurrency(1, 10, redis=redis)

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_task",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(return_value=target),
    )
    update_target = AsyncMock(return_value=target)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_task",
        AsyncMock(return_value=task),
    )

    await engine.handle_call_ended("c3", None, 408)
    assert update_target.await_args.args[2]["status"] == "completed"


@pytest.mark.asyncio
async def test_terminal_invalid_number(redis, monkeypatch):
    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    record = _record()
    target = _target(status="calling")
    task = _task()

    from app.services.auto_outbound import frequency as freq

    await freq.set_session_mapping(
        "c4",
        {
            "tenant_id": 1,
            "task_id": 1,
            "target_id": 10,
            "record_id": 100,
            "phone_number": "13800138000",
            "answered": False,
        },
        redis=redis,
    )
    await freq.acquire_concurrency(1, 10, redis=redis)

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_task",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(return_value=target),
    )
    update_target = AsyncMock(return_value=target)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=1),
    )

    await engine.handle_call_ended("c4", None, 404)
    assert update_target.await_args.args[2]["status"] == "invalid"


@pytest.mark.asyncio
async def test_auto_pause_on_consecutive_originate_failures(redis, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_AUTO_PAUSE_CONSECUTIVE_FAILURES",
        3,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        False,
    )

    task = _task(max_concurrency=10)
    targets = [_target(id=i, status="calling") for i in (10, 11, 12)]

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[task]),
    )

    claim_queue = [[(t, "pending")] for t in targets]

    async def _claim(*_a, **_k):
        return claim_queue.pop(0) if claim_queue else []

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        _claim,
    )

    record_ids = iter((100, 101, 102))

    async def _create_record(_db, data, **_kwargs):
        return _record(id=next(record_ids), target_id=data["target_id"], attempt_no=1)

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.create_record",
        _create_record,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(side_effect=lambda _db, tid: _target(id=tid, status="calling")),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        AsyncMock(side_effect=lambda _db, item, data, **_kwargs: item),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(side_effect=lambda _db, rid: _record(id=rid)),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_record",
        AsyncMock(side_effect=lambda _db, item, data, **_kwargs: item),
    )
    paused_task = _task(status="active")
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_task",
        AsyncMock(return_value=paused_task),
    )
    update_task = AsyncMock(return_value=paused_task)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_task",
        update_task,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=1),
    )

    engine = AutoOutboundDialEngine(
        redis=redis,
        session_factory=lambda: _SessionCM(),
    )
    # Force non-simulation path; fail originate without touching telephony/DID.
    engine._simulator = None

    from app.libs.telephony.base import TelephonyRPCError

    async def _boom(*_a, **_k):
        raise TelephonyRPCError(-32602, "trunk not ready for outbound")

    engine._originate = _boom  # type: ignore[method-assign]

    now = datetime(2026, 8, 7, 10, 0, 0).astimezone()
    # Three separate scan ticks each claiming one target
    for _ in range(3):
        # Re-list active each time
        monkeypatch.setattr(
            "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
            AsyncMock(return_value=[task]),
        )
        await engine.scan_once(now=now)

    assert update_task.await_count >= 1
    assert update_task.await_args.args[2]["status"] == "paused"
    assert update_task.await_args.args[2]["auto_pause_reason"] == AUTO_PAUSE_REASON_DIAL_UNAVAILABLE
    event = AutoOutboundEventService.emit_task_event
    event.assert_awaited_once()
    assert event.await_args.kwargs["event_type"] == "auto_outbound.task.paused"
    assert event.await_args.kwargs["reason"] == "dial_unavailable"


@pytest.mark.asyncio
async def test_simulation_full_lifecycle_answered(redis, monkeypatch):
    """pending → calling → answered → completed via simulator callbacks."""
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    task = _task()
    target = _target(status="calling")
    record = _record()
    state = {"target_status": "calling", "terminal": None, "task_status": "active", "pause_reason": None}

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[task]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        AsyncMock(return_value=[(target, "pending")]),
    )

    async def _create_record(_db, data, **_kwargs):
        return record

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.create_record",
        _create_record,
    )

    async def _get_target(_db, tid):
        return _target(id=tid, status=state["target_status"], call_count=1, answered_count=0)

    async def _update_target(_db, item, data, **_kwargs):
        state["target_status"] = data.get("status", state["target_status"])
        if "answered_count" in data:
            item.answered_count = data["answered_count"]
        return item

    async def _get_record(_db, rid):
        r = _record(id=rid)
        if state.get("answered_at"):
            r.answered_at = state["answered_at"]
        return r

    async def _update_record(_db, item, data):
        if "answered_at" in data:
            state["answered_at"] = data["answered_at"]
            item.answered_at = data["answered_at"]
        if "terminal_state" in data:
            state["terminal"] = data["terminal_state"]
        return item

    async def _mark_answered_once(_db, **_kwargs):
        state["answered_at"] = datetime.now(timezone.utc)
        return True

    async def _finalize_record_once(_db, **kwargs):
        state["terminal"] = kwargs["terminal_state"]
        return kwargs["terminal_state"]

    async def _get_task(_db, tid):
        return _task(status=state["task_status"])

    async def _update_task(_db, item, data, **_kwargs):
        state["task_status"] = data.get("status", state["task_status"])
        if "auto_pause_reason" in data:
            state["pause_reason"] = data["auto_pause_reason"]
        return item

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        _get_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        _update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        _get_record,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_record",
        _update_record,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.mark_answered_once",
        _mark_answered_once,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.finalize_record_once",
        _finalize_record_once,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_task",
        _get_task,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_task",
        _update_task,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(side_effect=lambda *_a, **_k: 0 if state["target_status"] == "completed" else 1),
    )

    sim = CallSimulator(
        profile=SimulationProfile(
            answer_rate=1.0,
            min_ring_seconds=0.01,
            max_ring_seconds=0.02,
            min_talk_seconds=0.01,
            max_talk_seconds=0.02,
        ),
    )
    engine = AutoOutboundDialEngine(
        redis=redis,
        session_factory=lambda: _SessionCM(),
        simulator=sim,
    )
    now = datetime(2026, 8, 7, 10, 0, 0).astimezone()
    stats = await engine.scan_once(now=now)
    assert stats["dialed"] == 1
    event = AutoOutboundEventService.emit_call_event
    assert event.await_count == 1
    assert event.await_args.kwargs["event_type"] == "auto_outbound.call.started"

    # Wait for simulator ring + talk
    import asyncio

    for _ in range(50):
        if state["terminal"] == "answered" and state["target_status"] == "completed":
            break
        await asyncio.sleep(0.05)

    assert state["terminal"] == "answered"
    assert state["target_status"] == "completed"
    # Queue finished → task auto-pauses with queue_finished reason (not completed).
    assert state["task_status"] == "paused"
    assert state["pause_reason"] == AUTO_PAUSE_REASON_QUEUE_FINISHED
    await sim.drain()
    assert [call.kwargs["event_type"] for call in event.await_args_list] == [
        "auto_outbound.call.started",
        "auto_outbound.call.answered",
        "auto_outbound.call.ended",
    ]
    event = AutoOutboundEventService.emit_task_event
    event.assert_awaited_once()
    assert event.await_args.kwargs["reason"] == "queue_finished"


@pytest.mark.asyncio
async def test_simulation_no_answer_then_redial_then_complete(redis, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    task = _task(
        retry_policy={"no_answer": {"max_retries": 1, "interval_minutes": 1}},
    )
    state = {
        "target_status": "calling",
        "retry_counts": {},
        "terminal": None,
        "call_count": 0,
        "task_status": "active",
        "pause_reason": None,
    }

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[task]),
    )

    async def _claim(_db, **_kwargs):
        if state["target_status"] in ("pending", "redial_pending") or state["call_count"] == 0:
            t = _target(
                status="calling",
                call_count=state["call_count"],
                retry_counts=dict(state["retry_counts"]),
                next_call_at=None,
            )
            prev = "redial_pending" if state["retry_counts"] else "pending"
            state["target_status"] = "calling"
            return [(t, prev)]
        return []

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        _claim,
    )

    record_counter = {"n": 100}

    async def _create_record(_db, data, **_kwargs):
        rid = record_counter["n"]
        record_counter["n"] += 1
        state["call_count"] = data["attempt_no"]
        return _record(id=rid, attempt_no=data["attempt_no"])

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.create_record",
        _create_record,
    )

    async def _get_target(_db, tid):
        return _target(
            id=tid,
            status=state["target_status"],
            call_count=state["call_count"],
            retry_counts=dict(state["retry_counts"]),
        )

    async def _update_target(_db, item, data, **_kwargs):
        if "status" in data:
            state["target_status"] = data["status"]
        if "retry_counts" in data:
            state["retry_counts"] = dict(data["retry_counts"])
        if "call_count" in data:
            state["call_count"] = data["call_count"]
        return item

    async def _get_record(_db, rid):
        return _record(id=rid)

    async def _update_record(_db, item, data):
        if "terminal_state" in data:
            state["terminal"] = data["terminal_state"]
            state.setdefault("terminals", []).append(data["terminal_state"])
        return item

    async def _finalize_record_once(_db, **kwargs):
        state["terminal"] = kwargs["terminal_state"]
        state.setdefault("terminals", []).append(kwargs["terminal_state"])
        return kwargs["terminal_state"]

    async def _get_task(_db, tid):
        return _task(
            status=state["task_status"],
            retry_policy={"no_answer": {"max_retries": 1, "interval_minutes": 1}},
        )

    async def _update_task(_db, item, data, **_kwargs):
        state["task_status"] = data.get("status", state["task_status"])
        if "auto_pause_reason" in data:
            state["pause_reason"] = data["auto_pause_reason"]
        return item

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        _get_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        _update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        _get_record,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_record",
        _update_record,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.finalize_record_once",
        _finalize_record_once,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_task",
        _get_task,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_task",
        _update_task,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(
            side_effect=lambda *_a, **_k: 0 if state["target_status"] == "completed" else 1
        ),
    )

    sim = CallSimulator(
        profile=SimulationProfile(
            answer_rate=0.0,
            min_ring_seconds=0.01,
            max_ring_seconds=0.02,
            min_talk_seconds=0.01,
            max_talk_seconds=0.02,
            weight_no_answer=1.0,
            weight_busy=0.0,
            weight_power_off=0.0,
            weight_invalid=0.0,
        ),
    )
    engine = AutoOutboundDialEngine(
        redis=redis,
        session_factory=lambda: _SessionCM(),
        simulator=sim,
    )
    now = datetime(2026, 8, 7, 10, 0, 0).astimezone()

    # First dial → no_answer → redial_pending
    await engine.scan_once(now=now)
    import asyncio

    for _ in range(50):
        if state["target_status"] == "redial_pending":
            break
        await asyncio.sleep(0.05)
    assert state["target_status"] == "redial_pending"
    assert state["retry_counts"].get("no_answer") == 1

    # Second dial → no_answer → completed (retries exhausted)
    state["terminals"] = []
    await engine.scan_once(now=now)
    for _ in range(50):
        if state["target_status"] == "completed":
            break
        await asyncio.sleep(0.05)
    assert state["target_status"] == "completed"
    # Queue finished → task auto-pauses with queue_finished reason (not completed).
    assert state["task_status"] == "paused"
    assert state["pause_reason"] == AUTO_PAUSE_REASON_QUEUE_FINISHED
    await sim.drain()


@pytest.mark.asyncio
async def test_paused_task_expires_to_completed(redis, monkeypatch):
    """Paused task past end_date completes once nothing is in-flight."""
    paused_task = _task(status="paused", end_date=date(2026, 8, 6))
    update_task = AsyncMock(return_value=paused_task)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_paused_tasks",
        AsyncMock(return_value=[paused_task]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_task",
        AsyncMock(return_value=paused_task),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_task",
        update_task,
    )

    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    now = datetime(2026, 8, 7, 10, 0, 0).astimezone()
    stats = await engine.scan_once(now=now)

    assert stats["completed_tasks"] == 1
    assert update_task.await_args.args[2]["status"] == "completed"
    assert update_task.await_args.args[2]["completed_at"] is not None
    event = AutoOutboundEventService.emit_task_event
    event.assert_awaited_once()
    assert event.await_args.kwargs["event_type"] == "auto_outbound.task.completed"
    assert event.await_args.kwargs["reason"] == "schedule_ended"


@pytest.mark.asyncio
async def test_paused_task_not_expired_is_not_dialed(redis, monkeypatch):
    """Paused tasks within schedule are only scanned for expiry, never dialed."""
    paused_task = _task(status="paused")
    claim = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_paused_tasks",
        AsyncMock(return_value=[paused_task]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        claim,
    )

    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    now = datetime(2026, 8, 7, 10, 0, 0).astimezone()
    stats = await engine.scan_once(now=now)

    assert stats["claimed"] == 0
    assert claim.await_count == 0


def test_next_daily_window_start():
    now = datetime(2026, 8, 7, 15, 0, 0).astimezone()
    nxt = next_daily_window_start(
        [{"start": "09:00", "end": "12:00"}, {"start": "14:00", "end": "20:00"}],
        now=now,
    )
    assert nxt.date() == date(2026, 8, 8)
    assert nxt.hour == 9
    assert nxt.minute == 0


def test_next_daily_window_start_uses_tenant_timezone():
    # 16:00 UTC = next calendar day in US/Pacific; window start should be Pacific tomorrow 09:00.
    now = datetime(2026, 8, 8, 16, 0, 0, tzinfo=timezone.utc)
    tz = ZoneInfo("America/Los_Angeles")
    nxt = next_daily_window_start(
        [{"start": "09:00", "end": "17:00"}],
        now=now,
        tz=tz,
    )
    assert nxt.tzinfo == tz
    assert nxt.date() == date(2026, 8, 9)
    assert nxt.hour == 9


@pytest.mark.asyncio
async def test_scan_uses_tenant_timezone_for_date_gate(redis, monkeypatch):
    """start/end_date gate must use tenant-local calendar day, not UTC."""
    # UTC 2026-08-01 02:00 → still 2026-07-31 in America/Los_Angeles.
    task = _task(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        daily_time_windows=[{"start": "00:00", "end": "23:59"}],
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.resolve_tenant_timezone",
        AsyncMock(return_value=ZoneInfo("America/Los_Angeles")),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[task]),
    )
    claim = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        claim,
    )
    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    now = datetime(2026, 8, 1, 2, 0, 0, tzinfo=timezone.utc)
    await engine.scan_once(now=now)
    # Local date is still July 31 → before start_date → do not claim.
    claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweep_stale_calling_without_session(redis, monkeypatch):
    stale = _target(
        id=55,
        status="calling",
        updated_at=datetime(2026, 8, 7, 8, 0, tzinfo=timezone.utc),
    )
    open_record = _record(
        id=200,
        target_id=55,
        terminal_state=None,
        ended_at=None,
        started_at=datetime(2026, 8, 7, 8, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_stale_calling_targets",
        AsyncMock(return_value=[stale]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(return_value=stale),
    )
    update_target = AsyncMock(return_value=stale)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_open_record_for_target",
        AsyncMock(return_value=open_record),
    )
    finalize_record = AsyncMock(return_value="failed")
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.finalize_record_once",
        finalize_record,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[]),
    )

    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    now = datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc)
    stats = await engine.scan_once(now=now)
    assert stats["swept_stale"] == 1
    assert update_target.await_args.args[2]["status"] == "redial_pending"
    assert finalize_record.await_args.kwargs["fail_reason"] == "swept_stale_calling"
    assert finalize_record.await_args.kwargs["commit"] is False


@pytest.mark.asyncio
async def test_sweep_skips_target_with_live_session(redis, monkeypatch):
    from app.services.auto_outbound import frequency as freq

    stale = _target(id=56, status="calling")
    await freq.set_session_mapping(
        "live-call",
        {
            "tenant_id": 1,
            "task_id": 1,
            "target_id": 56,
            "record_id": 100,
            "phone_number": "13800138000",
        },
        redis=redis,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_stale_calling_targets",
        AsyncMock(return_value=[stale]),
    )
    update_target = AsyncMock()
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[]),
    )
    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    stats = await engine.scan_once(now=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc))
    assert stats["swept_stale"] == 0
    update_target.assert_not_awaited()


@pytest.mark.asyncio
async def test_answered_idempotent_across_concurrent_engines(redis, monkeypatch):
    from app.services.auto_outbound import frequency as freq

    await freq.set_session_mapping(
        "ans-1",
        {
            "tenant_id": 1,
            "task_id": 1,
            "target_id": 10,
            "record_id": 100,
            "phone_number": "13800138000",
            "answered": False,
        },
        redis=redis,
    )

    lock = asyncio.Lock()
    claimed = False

    async def _mark_answered_once(_db, **_kwargs):
        nonlocal claimed
        async with lock:
            if claimed:
                return False
            claimed = True
            await asyncio.sleep(0)
            return True

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.mark_answered_once",
        _mark_answered_once,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(return_value=_target()),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(return_value=_record()),
    )

    receptions = [AsyncMock(), AsyncMock()]
    engines = [
        AutoOutboundDialEngine(
            redis=redis,
            session_factory=lambda: _SessionCM(),
            reception=reception,
        )
        for reception in receptions
    ]

    await asyncio.gather(*(engine.handle_call_answered("ans-1") for engine in engines))

    assert sum(item.on_answered.await_count for item in receptions) == 1
    AutoOutboundEventService.emit_call_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_ended_keeps_resources_on_db_error_for_retry(redis, monkeypatch):
    from app.services.auto_outbound import frequency as freq

    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    await freq.set_session_mapping(
        "end-1",
        {
            "tenant_id": 1,
            "task_id": 1,
            "target_id": 10,
            "record_id": 100,
            "phone_number": "13800138000",
            "answered": False,
        },
        redis=redis,
    )
    await freq.acquire_concurrency(1, 10, redis=redis)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(side_effect=RuntimeError("db down")),
    )

    with pytest.raises(RuntimeError, match="db down"):
        await engine.handle_call_ended("end-1", "normal", 200)

    assert await freq.get_session_mapping("end-1", redis=redis) is not None
    inflight = await redis.get(freq.inflight_key(1))
    assert int(inflight) == 1


@pytest.mark.asyncio
async def test_ended_releases_resources_once_across_concurrent_engines(redis, monkeypatch):
    from app.services.auto_outbound import frequency as freq

    await freq.set_session_mapping(
        "end-concurrent",
        {
            "tenant_id": 1,
            "task_id": 1,
            "target_id": 10,
            "record_id": 100,
            "phone_number": "13800138000",
            "answered": False,
        },
        redis=redis,
    )
    assert await freq.acquire_concurrency(1, 10, redis=redis)
    assert await freq.acquire_concurrency(1, 10, redis=redis)

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(return_value=_record()),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_task",
        AsyncMock(return_value=_task()),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(return_value=_target(status="calling")),
    )
    update_target = AsyncMock(return_value=_target(status="completed"))
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=1),
    )

    both_entered = asyncio.Event()
    claim_lock = asyncio.Lock()
    entered = 0
    claimed = False

    async def _finalize_record_once(_db, **kwargs):
        nonlocal claimed, entered
        entered += 1
        if entered == 2:
            both_entered.set()
        await asyncio.wait_for(both_entered.wait(), timeout=1)
        async with claim_lock:
            if claimed:
                return None
            claimed = True
            return kwargs["terminal_state"]

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.finalize_record_once",
        _finalize_record_once,
    )

    engines = [
        AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
        for _ in range(2)
    ]
    await asyncio.gather(
        *(engine.handle_call_ended("end-concurrent", "no_answer", 408) for engine in engines)
    )

    assert update_target.await_count == 1
    AutoOutboundEventService.emit_call_event.assert_awaited_once()
    assert AutoOutboundEventService.emit_call_event.await_args.kwargs["event_type"] == (
        "auto_outbound.call.ended"
    )
    assert int(await redis.get(freq.inflight_key(1))) == 1
    assert await freq.get_session_mapping("end-concurrent", redis=redis) is None


@pytest.mark.asyncio
async def test_originate_failure_rolls_back_freq_and_keeps_pending(redis, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        False,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_AUTO_PAUSE_CONSECUTIVE_FAILURES",
        99,
    )
    from app.services.auto_outbound import frequency as freq

    task = _task(max_concurrency=5, daily_per_number_limit=3)
    target = _target(status="calling")
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[task]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        AsyncMock(return_value=[(target, "pending")]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.create_record",
        AsyncMock(return_value=_record()),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(return_value=_target(id=10, status="calling")),
    )
    update_target = AsyncMock(side_effect=lambda _db, item, data, **_kwargs: item)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(return_value=_record()),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_record",
        AsyncMock(side_effect=lambda _db, item, data, **_kwargs: item),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=1),
    )

    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    engine._simulator = None

    from app.libs.telephony.base import TelephonyRPCError

    async def _boom(*_a, **_k):
        raise TelephonyRPCError(-32602, "trunk down")

    engine._originate = _boom  # type: ignore[method-assign]

    now = datetime(2026, 8, 7, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    await engine.scan_once(now=now)

    day = now.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    assert await redis.get(freq.freq_key(1, "13800138000", day)) is None
    # Last target update from originate failure should park as pending.
    pending_patches = [
        c.args[2] for c in update_target.await_args_list if c.args[2].get("status") == "pending"
    ]
    assert pending_patches
    assert pending_patches[-1]["next_call_at"] is not None


@pytest.mark.asyncio
async def test_simulation_disabled_ignores_injected_simulator(redis, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        False,
    )
    task = _task()
    target = _target(status="calling")
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[task]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        AsyncMock(return_value=[(target, "pending")]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.create_record",
        AsyncMock(return_value=_record()),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(return_value=_target(id=10, status="calling")),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        AsyncMock(side_effect=lambda _db, item, data, **_kwargs: item),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(return_value=_record()),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_record",
        AsyncMock(side_effect=lambda _db, item, data, **_kwargs: item),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=1),
    )

    sim = CallSimulator(
        profile=SimulationProfile(
            answer_rate=1.0,
            min_ring_seconds=0.01,
            max_ring_seconds=0.02,
            min_talk_seconds=0.01,
            max_talk_seconds=0.02,
        )
    )
    engine = AutoOutboundDialEngine(
        redis=redis,
        session_factory=lambda: _SessionCM(),
        simulator=sim,
    )

    async def _boom(*_a, **_k):
        raise RuntimeError("real path required")

    engine._originate = _boom  # type: ignore[method-assign]
    now = datetime(2026, 8, 7, 10, 0, 0).astimezone()
    await engine.scan_once(now=now)
    # Injected simulator must not short-circuit to sim call ids when settings off.
    assert len(sim._tasks) == 0


def _patch_claim_one(monkeypatch, redis, *, task=None, target=None, record=None):
    task = task or _task()
    target = target or _target(status="calling")
    record = record or _record()
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.list_active_tasks",
        AsyncMock(return_value=[task]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.claim_due_targets",
        AsyncMock(return_value=[(target, "pending")]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.create_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(return_value=_target(id=target.id, status="calling")),
    )
    update_target = AsyncMock(side_effect=lambda _db, item, data, **_kwargs: item)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_record",
        AsyncMock(side_effect=lambda _db, item, data, **_kwargs: item),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=1),
    )
    return update_target


@pytest.mark.asyncio
async def test_uncertain_originate_holds_calling_and_lease(redis, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        False,
    )
    from app.services.auto_outbound import frequency as freq

    update_target = _patch_claim_one(monkeypatch, redis)
    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    engine._simulator = None
    engine._reconcile_attempt = AsyncMock(return_value=None)  # type: ignore[method-assign]

    async def _boom(*_a, **_k):
        raise TimeoutError("originate timed out")

    engine._originate = _boom  # type: ignore[method-assign]
    now = datetime(2026, 8, 7, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    await engine.scan_once(now=now)

    assert await freq.get_concurrency(1, redis=redis) == 1
    day = now.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    assert await redis.get(freq.freq_key(1, "13800138000", day)) == "1"
    pending_patches = [
        c.args[2] for c in update_target.await_args_list if c.args[2].get("status") == "pending"
    ]
    assert pending_patches == []


@pytest.mark.asyncio
async def test_uncertain_originate_reconcile_binds_call_id(redis, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        False,
    )
    from app.services.auto_outbound import frequency as freq

    _patch_claim_one(monkeypatch, redis)
    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    engine._simulator = None
    engine._reconcile_attempt = AsyncMock(return_value="fk-call-9")  # type: ignore[method-assign]

    async def _boom(*_a, **_k):
        raise TimeoutError("rpc lost")

    engine._originate = _boom  # type: ignore[method-assign]
    now = datetime(2026, 8, 7, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    await engine.scan_once(now=now)

    assert await freq.get_session_mapping("fk-call-9", redis=redis) is not None
    assert await freq.get_concurrency(1, redis=redis) == 1


@pytest.mark.asyncio
async def test_uncertain_originate_reconcile_links_cdr(redis, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        False,
    )

    _patch_claim_one(monkeypatch, redis)
    set_link = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.set_call_record_id_if_empty",
        set_link,
    )
    create_cdr = AsyncMock(return_value={"id": 77})
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.create_for_outbound",
        create_cdr,
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.identify_user_for_call_managed",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator",
        MagicMock(side_effect=RuntimeError("no orch")),
    )

    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    engine._simulator = None
    engine._reconcile_attempt = AsyncMock(return_value="fk-call-9")  # type: ignore[method-assign]

    async def _boom(*_a, **_k):
        raise TimeoutError("rpc lost")

    engine._originate = _boom  # type: ignore[method-assign]
    now = datetime(2026, 8, 7, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    await engine.scan_once(now=now)

    set_link.assert_awaited_once()
    assert set_link.await_args.args[1] == 100
    assert set_link.await_args.args[2] == 77
    assert create_cdr.await_args.kwargs["identify_user"] is False
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_ensure_call_record_linked_writes_id(monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        False,
    )
    from app.services.auto_outbound.engine import DialSessionContext

    record = _record(call_record_id=None)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(return_value=record),
    )
    set_link = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.set_call_record_id_if_empty",
        set_link,
    )
    create_cdr = AsyncMock(return_value={"id": 55})
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.create_for_outbound",
        create_cdr,
    )
    identify = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.identify_user_for_call_managed",
        identify,
    )
    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator",
        MagicMock(side_effect=RuntimeError("no orch")),
    )

    engine = AutoOutboundDialEngine(session_factory=lambda: _SessionCM())
    ctx = DialSessionContext(
        tenant_id=1,
        task_id=1,
        target_id=10,
        record_id=100,
        phone_number="13800138000",
    )
    await engine._ensure_call_record_linked(
        ctx,
        "call-1",
        conversation_id="conv-1",
        from_number="0210000",
    )
    set_link.assert_awaited_once()
    assert set_link.await_args.args[1] == 100
    assert set_link.await_args.args[2] == 55
    assert create_cdr.await_args.kwargs["identify_user"] is False
    await asyncio.sleep(0)
    identify.assert_awaited_once_with(1, "call-1")


@pytest.mark.asyncio
async def test_ensure_call_record_linked_skips_when_already_set(monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        False,
    )
    from app.services.auto_outbound.engine import DialSessionContext

    record = _record(call_record_id=9)
    create = AsyncMock()
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.create_for_outbound",
        create,
    )

    engine = AutoOutboundDialEngine(session_factory=lambda: _SessionCM())
    ctx = DialSessionContext(
        tenant_id=1,
        task_id=1,
        target_id=10,
        record_id=100,
        phone_number="13800138000",
    )
    await engine._ensure_call_record_linked(ctx, "call-1")
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_bind_session_from_attempt_before_call_id(redis):
    engine = AutoOutboundDialEngine(redis=redis, session_factory=lambda: _SessionCM())
    from app.services.auto_outbound.engine import DialSessionContext

    ctx = DialSessionContext(
        tenant_id=1,
        task_id=1,
        target_id=10,
        record_id=100,
        phone_number="13800138000",
        attempt_id="att-1",
        trunk_key="pn_1",
    )
    await engine._store_session("", ctx)
    bound = await engine.bind_session_from_attempt("late-call", "att-1")
    assert bound is True
    assert await engine.has_session("late-call") is True
