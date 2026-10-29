"""
Wave C2: full-chain auto-outbound verification under the built-in simulator.

Hermetic (fakeredis + in-memory repository). No FlowKit / real Postgres.
Runs under ``pytest tests/unit/``.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from app.models.auto_outbound import AutoOutboundCallRecord, AutoOutboundTarget, AutoOutboundTask
from app.models.outbound_task import OutboundTaskTemplate
from app.schemas.auto_outbound import AutoOutboundTaskCreate
from app.schemas.permission import EffectivePrincipal
from app.services.auto_outbound import frequency as freq
from app.services.auto_outbound.engine import (
    AUTO_PAUSE_REASON_DIAL_UNAVAILABLE,
    AUTO_PAUSE_REASON_QUEUE_FINISHED,
    AutoOutboundDialEngine,
)
from app.services.auto_outbound.pacing import (
    DefaultPacingResolver,
    PredictivePacing,
    PacingContext,
    get_current_intensity,
    record_abandon_for_pacing,
    record_answered_for_pacing,
)
from app.services.auto_outbound.reception import (
    AgentReception,
    BotReception,
    IvrReception,
    ReceptionDispatcher,
    TaskReceptionSnap,
)
from app.services.auto_outbound.simulator import CallSimulator, SimulationProfile
from app.services.auto_outbound_task_service import AutoOutboundTaskService


# ── in-memory store ──────────────────────────────────────────────────────────


class InMemoryAutoOutboundStore:
    """Minimal repository stand-in for engine + task-service paths."""

    def __init__(self) -> None:
        self.tasks: dict[int, AutoOutboundTask] = {}
        self.targets: dict[int, AutoOutboundTarget] = {}
        self.records: dict[int, AutoOutboundCallRecord] = {}
        self._task_seq = 1
        self._target_seq = 1
        self._record_seq = 1

    def add_task(self, **kwargs) -> AutoOutboundTask:
        data = dict(
            id=self._task_seq,
            tenant_id=1,
            name="sim-e2e",
            template_id=2,
            template_name="tpl",
            fields=[
                {
                    "key": "note",
                    "name": "备注",
                    "field_type": "single_line_text",
                    "required": False,
                    "enabled": True,
                }
            ],
            status="draft",
            execution_mode="ivr",
            voice_flow_id=10,
            voice_flow_name="flow",
            owner_id=10,
            created_by_id=10,
            updated_by_id=10,
            start_date=date(2026, 8, 1),
            end_date=date(2099, 12, 31),
            daily_time_windows=[{"start": "00:00", "end": "23:59"}],
            caller_number_id="pn_1",
            max_concurrency=10,
            retry_policy={
                "no_answer": {"max_retries": 1, "interval_minutes": 1},
                "busy": {"max_retries": 0, "interval_minutes": 1},
                "power_off": {"max_retries": 0, "interval_minutes": 1},
            },
            daily_per_number_limit=3,
            auto_resume_on_target_append=False,
            wrapup_seconds=60,
        )
        data.update(kwargs)
        if "id" not in kwargs:
            data["id"] = self._task_seq
            self._task_seq += 1
        else:
            self._task_seq = max(self._task_seq, int(data["id"]) + 1)
        task = AutoOutboundTask(**data)
        self.tasks[task.id] = task
        return task

    async def create_task(self, _db, data: dict) -> AutoOutboundTask:
        return self.add_task(**data)

    async def get_task(self, _db, task_id: int) -> AutoOutboundTask | None:
        return self.tasks.get(task_id)

    async def get_task_for_update(
        self, _db, task_id: int
    ) -> AutoOutboundTask | None:
        return self.tasks.get(task_id)

    async def update_task(
        self, _db, item: AutoOutboundTask, data: dict, **_kwargs
    ) -> AutoOutboundTask:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        self.tasks[item.id] = item
        return item

    async def list_active_tasks(self, _db) -> list[AutoOutboundTask]:
        return [t for t in self.tasks.values() if t.status == "active"]

    async def list_paused_tasks(self, _db) -> list[AutoOutboundTask]:
        return [t for t in self.tasks.values() if t.status == "paused"]

    async def is_task_active(self, _db, task_id: int) -> bool:
        task = self.tasks.get(task_id)
        return task is not None and task.status == "active"

    async def count_targets(self, _db, tenant_id: int, task_id: int) -> int:
        return sum(
            1
            for t in self.targets.values()
            if t.tenant_id == tenant_id and t.task_id == task_id
        )

    async def task_stats(self, _db, tenant_id: int, task_ids: list[int]) -> dict:
        out: dict[int, dict] = {}
        for tid in task_ids:
            targets = [
                t
                for t in self.targets.values()
                if t.tenant_id == tenant_id and t.task_id == tid
            ]
            call_count = sum(int(t.call_count or 0) for t in targets)
            answered_count = sum(int(t.answered_count or 0) for t in targets)
            out[tid] = {
                "total_targets": len(targets),
                "finished_targets": sum(
                    1 for t in targets if t.status in {"completed", "invalid"}
                ),
                "call_count": call_count,
                "answered_count": answered_count,
                "answer_rate": (answered_count / call_count) if call_count else None,
                "transfer_count": 0,
                "abandon_count": 0,
            }
        return out

    async def create_target(
        self, _db, data: dict, *, commit: bool = True
    ) -> AutoOutboundTarget:
        tid = self._target_seq
        self._target_seq += 1
        target = AutoOutboundTarget(
            id=tid,
            tenant_id=data["tenant_id"],
            task_id=data["task_id"],
            phone_number=data["phone_number"],
            user_id=data.get("user_id"),
            status=data.get("status") or "pending",
            field_values=dict(data.get("field_values") or {}),
            call_count=int(data.get("call_count") or 0),
            answered_count=int(data.get("answered_count") or 0),
            retry_counts=dict(data.get("retry_counts") or {}),
            next_call_at=data.get("next_call_at"),
            last_called_at=data.get("last_called_at"),
            last_call_result=data.get("last_call_result"),
        )
        self.targets[tid] = target
        return target

    async def create_targets_bulk(
        self, _db, rows: list[dict], *, commit: bool = True
    ) -> list[AutoOutboundTarget]:
        return [await self.create_target(_db, row, commit=commit) for row in rows]

    async def get_target(self, _db, target_id: int) -> AutoOutboundTarget | None:
        return self.targets.get(target_id)

    async def update_target(
        self, _db, item: AutoOutboundTarget, data: dict, **_kwargs
    ) -> AutoOutboundTarget:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        self.targets[item.id] = item
        return item

    async def claim_due_targets(
        self, _db, *, task_id: int, now: datetime, limit: int
    ) -> list[tuple[AutoOutboundTarget, str]]:
        if limit <= 0:
            return []
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        candidates = [
            t
            for t in self.targets.values()
            if t.task_id == task_id
            and t.status in {"pending", "redial_pending"}
            and (t.next_call_at is None or t.next_call_at <= now)
        ]
        candidates.sort(
            key=lambda t: (
                t.next_call_at is not None,
                t.next_call_at or datetime.min.replace(tzinfo=timezone.utc),
                t.id,
            )
        )
        claimed: list[tuple[AutoOutboundTarget, str]] = []
        for target in candidates[:limit]:
            previous = target.status
            target.status = "calling"
            claimed.append((target, previous))
        return claimed

    async def create_record(
        self, _db, data: dict, **_kwargs
    ) -> AutoOutboundCallRecord:
        rid = self._record_seq
        self._record_seq += 1
        record = AutoOutboundCallRecord(
            id=rid,
            tenant_id=data["tenant_id"],
            task_id=data["task_id"],
            target_id=data["target_id"],
            phone_number=data["phone_number"],
            attempt_id=data.get("attempt_id"),
            attempt_no=int(data.get("attempt_no") or 1),
            started_at=data.get("started_at") or datetime.now(timezone.utc),
            duration_ms=int(data.get("duration_ms") or 0),
            reception_type=data.get("reception_type"),
        )
        self.records[rid] = record
        return record

    async def get_record(self, _db, record_id: int) -> AutoOutboundCallRecord | None:
        return self.records.get(record_id)

    async def update_record(
        self, _db, item: AutoOutboundCallRecord, data: dict, **_kwargs
    ) -> AutoOutboundCallRecord:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        self.records[item.id] = item
        return item

    async def mark_answered_once(
        self,
        _db,
        *,
        record_id: int,
        target_id: int,
        answered_at: datetime,
        **_kwargs,
    ) -> bool:
        record = self.records.get(record_id)
        target = self.targets.get(target_id)
        if (
            record is None
            or target is None
            or record.answered_at is not None
            or record.ended_at is not None
        ):
            return False
        record.answered_at = answered_at
        target.answered_count = int(target.answered_count or 0) + 1
        return True

    async def finalize_record_once(
        self,
        _db,
        *,
        record_id: int,
        ended_at: datetime,
        duration_ms: int,
        terminal_state: str,
        fail_reason: str | None,
        **_kwargs,
    ) -> str | None:
        record = self.records.get(record_id)
        if record is None or record.ended_at is not None:
            return None
        persisted_terminal = "answered" if record.answered_at is not None else terminal_state
        record.ended_at = ended_at
        record.duration_ms = duration_ms
        record.terminal_state = persisted_terminal
        record.fail_reason = None if persisted_terminal == "answered" else fail_reason
        return persisted_terminal

    async def count_targets_by_status(
        self, _db, task_id: int, *, statuses: list[str]
    ) -> int:
        return sum(
            1 for t in self.targets.values() if t.task_id == task_id and t.status in statuses
        )

    async def list_stale_calling_targets(self, _db, *, updated_before: datetime):
        return []

    async def count_records_for_numbers_on_day(
        self, _db, tenant_id: int, task_id: int, phone_numbers: list[str], day: date
    ) -> dict[str, int]:
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        day_end = datetime.combine(day, datetime.max.time(), tzinfo=timezone.utc)
        counts: dict[str, int] = {}
        for phone in phone_numbers:
            counts[phone] = sum(
                1
                for r in self.records.values()
                if r.tenant_id == tenant_id
                and r.task_id == task_id
                and r.phone_number == phone
                and day_start <= r.started_at <= day_end
            )
        return counts

    def terminal_distribution(self, task_id: int) -> dict[str, int]:
        dist: dict[str, int] = {}
        for r in self.records.values():
            if r.task_id != task_id or not r.terminal_state:
                continue
            dist[r.terminal_state] = dist.get(r.terminal_state, 0) + 1
        return dist

    def target_statuses(self, task_id: int) -> dict[str, int]:
        dist: dict[str, int] = {}
        for t in self.targets.values():
            if t.task_id != task_id:
                continue
            dist[t.status] = dist.get(t.status, 0) + 1
        return dist


class _SessionCM:
    def __init__(self, db=None):
        self.db = db if db is not None else MagicMock()
        self.db.commit = AsyncMock()
        self.db.refresh = AsyncMock()

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *args):
        return False


def _principal() -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=10,
        tenant_id=1,
        permissions=[
            "engagement.auto_outbound_task.create",
            "engagement.auto_outbound_task.manage",
        ],
        is_super_admin=False,
    )


def _fast_profile(**overrides) -> SimulationProfile:
    data = dict(
        answer_rate=1.0,
        min_ring_seconds=0.0,
        max_ring_seconds=0.0,
        min_talk_seconds=0.0,
        max_talk_seconds=0.0,
        weight_no_answer=1.0,
        weight_busy=0.0,
        weight_power_off=0.0,
        weight_invalid=0.0,
    )
    data.update(overrides)
    return SimulationProfile(**data)


def _service_db() -> MagicMock:
    """AsyncSession stand-in for service calls that also run pending-phone IN queries."""
    db = MagicMock()
    pending_result = MagicMock()
    pending_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=pending_result)
    db.get = AsyncMock(return_value=None)
    db.commit = AsyncMock()
    return db


def _wire_store(monkeypatch, store: InMemoryAutoOutboundStore) -> None:
    """Bind store methods onto repository symbols used by engine / service / reception."""
    methods = [
        "create_task",
        "get_task",
        "get_task_for_update",
        "update_task",
        "list_active_tasks",
        "list_paused_tasks",
        "is_task_active",
        "count_targets",
        "task_stats",
        "create_target",
        "create_targets_bulk",
        "get_target",
        "update_target",
        "claim_due_targets",
        "create_record",
        "get_record",
        "update_record",
        "mark_answered_once",
        "finalize_record_once",
        "count_targets_by_status",
        "count_records_for_numbers_on_day",
        "list_stale_calling_targets",
    ]
    modules = (
        "app.services.auto_outbound.engine.AutoOutboundRepository",
        "app.services.auto_outbound_task_service.AutoOutboundRepository",
        "app.repositories.auto_outbound_repository.AutoOutboundRepository",
    )
    for mod in modules:
        for name in methods:
            monkeypatch.setattr(f"{mod}.{name}", getattr(store, name), raising=False)

    async def _load_snap(task_id: int) -> TaskReceptionSnap | None:
        task = store.tasks.get(task_id)
        if task is None:
            return None
        return TaskReceptionSnap(
            id=task.id,
            tenant_id=task.tenant_id,
            execution_mode=task.execution_mode,
            voice_flow_id=task.voice_flow_id,
            transfer_queue_id=task.transfer_queue_id,
            voicespeed_agent_id=task.voicespeed_agent_id,
            voicespeed_agent_name=task.voicespeed_agent_name,
            intent_result_field_key=task.intent_result_field_key,
            queue_id=task.queue_id,
            abandon_prompt=task.abandon_prompt,
            fields=list(task.fields or []),
            wrapup_seconds=int(task.wrapup_seconds or 60),
        )

    async def _update_record(record_id: int, data: dict) -> None:
        record = store.records.get(record_id)
        if record is None:
            return
        for key, value in data.items():
            if hasattr(record, key):
                setattr(record, key, value)

    monkeypatch.setattr(
        "app.services.auto_outbound.reception._load_task_snap", _load_snap
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._update_record", _update_record
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.AsyncSessionLocal",
        lambda: _SessionCM(),
    )


async def _wait_until(predicate, *, timeout: float = 2.0, interval: float = 0.02) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()


def _scan_now() -> datetime:
    return datetime(2026, 8, 7, 10, 0, 0).astimezone()


@pytest.fixture
async def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture(autouse=True)
def _event_defaults(monkeypatch):
    for path in (
        "app.services.auto_outbound.engine.AutoOutboundEventService.emit_call_event",
        "app.services.auto_outbound.engine.AutoOutboundEventService.emit_task_event",
        "app.services.auto_outbound_task_service.AutoOutboundEventService.emit_task_event",
    ):
        monkeypatch.setattr(path, AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundEventService.actor_snapshot",
        AsyncMock(return_value={"type": "employee", "name": "Agent"}),
    )


@pytest.fixture
def store():
    return InMemoryAutoOutboundStore()


# ── Scenario A: IVR create → import → start → dial → terminals ───────────────


@pytest.mark.asyncio
async def test_scenario_a_ivr_all_answered(redis, store, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    _wire_store(monkeypatch, store)

    task = store.add_task(execution_mode="ivr", max_concurrency=10, status="draft")
    csv_content = (
        "phone_number,备注\n"
        "13800000001,a\n"
        "13800000002,b\n"
        "13800000003,c\n"
    ).encode("utf-8")

    monkeypatch.setattr(
        AutoOutboundTaskService,
        "_assert_caller_number_available",
        AsyncMock(),
    )
    monkeypatch.setattr(
        AutoOutboundTaskService,
        "_assert_reception_refs",
        AsyncMock(),
    )
    with patch(
        "app.services.auto_outbound_task_service.UserRepository.list_with_phone",
        AsyncMock(return_value=[]),
    ), patch(
        "app.services.auto_outbound_task_service.UserRepository.list_by_ids",
        AsyncMock(return_value=[]),
    ), patch(
        "app.services.auto_outbound_task_service.EmployeeRepository.get_by_ids",
        AsyncMock(return_value=[]),
    ):
        imported = await AutoOutboundTaskService.import_targets(
            _service_db(), _principal(), task.id, "targets.csv", csv_content
        )
        assert imported.created == 3
        started = await AutoOutboundTaskService.start_task(
            _service_db(), _principal(), task.id
        )
        assert started.status == "active"

    sim = CallSimulator(profile=_fast_profile(answer_rate=1.0))
    engine = AutoOutboundDialEngine(
        redis=redis,
        session_factory=lambda: _SessionCM(),
        simulator=sim,
        pacing_resolver=DefaultPacingResolver(redis=redis),
    )
    stats = await engine.scan_once(now=_scan_now())
    assert stats["dialed"] == 3

    # Queue finished → task auto-pauses with queue_finished reason (not completed).
    ok = await _wait_until(
        lambda: store.tasks[task.id].status == "paused"
        and all(t.status == "completed" for t in store.targets.values() if t.task_id == task.id)
    )
    assert ok, (
        f"task={store.tasks[task.id].status} "
        f"targets={store.target_statuses(task.id)} "
        f"terminals={store.terminal_distribution(task.id)}"
    )
    assert store.tasks[task.id].auto_pause_reason == AUTO_PAUSE_REASON_QUEUE_FINISHED
    dist = store.terminal_distribution(task.id)
    assert dist.get("answered") == 3
    assert len(store.records) == 3
    await sim.drain()


@pytest.mark.asyncio
async def test_scenario_a_ivr_no_answer_retry_then_complete(redis, store, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    _wire_store(monkeypatch, store)

    task = store.add_task(
        status="active",
        max_concurrency=5,
        retry_policy={"no_answer": {"max_retries": 1, "interval_minutes": 1}},
    )
    await store.create_target(
        None,
        {
            "tenant_id": 1,
            "task_id": task.id,
            "phone_number": "13800000099",
            "status": "pending",
            "field_values": {},
            "retry_counts": {},
        },
    )

    sim = CallSimulator(
        profile=_fast_profile(
            answer_rate=0.0,
            weight_no_answer=1.0,
            weight_busy=0.0,
            weight_power_off=0.0,
            weight_invalid=0.0,
        )
    )
    engine = AutoOutboundDialEngine(
        redis=redis,
        session_factory=lambda: _SessionCM(),
        simulator=sim,
        pacing_resolver=DefaultPacingResolver(redis=redis),
    )

    now = _scan_now()
    await engine.scan_once(now=now)
    ok = await _wait_until(
        lambda: next(iter(store.targets.values())).status == "redial_pending"
    )
    assert ok
    target = next(iter(store.targets.values()))
    assert target.retry_counts.get("no_answer") == 1
    assert target.next_call_at is not None
    assert target.next_call_at >= datetime.now(timezone.utc) - timedelta(seconds=5)
    assert store.terminal_distribution(task.id).get("no_answer") == 1

    # Second attempt after retry interval — retries exhausted → target completed,
    # queue finished → task auto-pauses (not completed).
    later = target.next_call_at + timedelta(seconds=1)
    await engine.scan_once(now=later)
    ok = await _wait_until(
        lambda: next(iter(store.targets.values())).status == "completed"
        and store.tasks[task.id].status == "paused"
    )
    assert ok
    assert store.tasks[task.id].auto_pause_reason == AUTO_PAUSE_REASON_QUEUE_FINISHED
    assert store.terminal_distribution(task.id).get("no_answer") == 2
    assert len(store.records) == 2
    await sim.drain()


# ── Scenario B: daily frequency ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_b_daily_frequency_defers_to_next_day(redis, store, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    _wire_store(monkeypatch, store)

    task = store.add_task(
        status="active",
        daily_per_number_limit=1,
        max_concurrency=5,
        daily_time_windows=[{"start": "09:00", "end": "20:00"}],
    )
    phone = "13800000111"
    t1 = await store.create_target(
        None,
        {
            "tenant_id": 1,
            "task_id": task.id,
            "phone_number": phone,
            "status": "pending",
            "field_values": {},
            "retry_counts": {},
        },
    )
    # Second target same number (duplicate list row) to force a same-day second dial attempt.
    t2 = await store.create_target(
        None,
        {
            "tenant_id": 1,
            "task_id": task.id,
            "phone_number": phone,
            "status": "pending",
            "field_values": {},
            "retry_counts": {},
        },
    )

    sim = CallSimulator(profile=_fast_profile(answer_rate=1.0))
    engine = AutoOutboundDialEngine(
        redis=redis,
        session_factory=lambda: _SessionCM(),
        simulator=sim,
        pacing_resolver=DefaultPacingResolver(redis=redis),
    )
    now = datetime(2026, 8, 7, 10, 0, 0).astimezone()
    stats = await engine.scan_once(now=now)
    # First dial burns the daily slot; second is deferred (not dialed).
    assert stats["dialed"] == 1

    ok = await _wait_until(lambda: store.records and all(r.terminal_state for r in store.records.values()))
    assert ok

    deferred = [t for t in (t1, t2) if t.status == "pending" and t.next_call_at is not None]
    assert len(deferred) == 1
    assert deferred[0].next_call_at.date() == date(2026, 8, 8)
    assert deferred[0].next_call_at.hour == 9
    day = now.strftime("%Y%m%d")
    assert int(await redis.get(freq.freq_key(task.id, phone, day)) or 0) == 1
    await sim.drain()


# ── Scenario C: concurrency cap ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_c_max_concurrency_caps_same_tick(redis, store, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    _wire_store(monkeypatch, store)

    task = store.add_task(status="active", max_concurrency=2)
    for i in range(10):
        await store.create_target(
            None,
            {
                "tenant_id": 1,
                "task_id": task.id,
                "phone_number": f"13800001{i:03d}",
                "status": "pending",
                "field_values": {},
                "retry_counts": {},
            },
        )

    # Keep calls in-flight during the scan so concurrency slots are not recycled.
    sim = CallSimulator(
        profile=_fast_profile(
            answer_rate=1.0,
            min_ring_seconds=0.3,
            max_ring_seconds=0.3,
            min_talk_seconds=0.3,
            max_talk_seconds=0.3,
        )
    )
    engine = AutoOutboundDialEngine(
        redis=redis,
        session_factory=lambda: _SessionCM(),
        simulator=sim,
        pacing_resolver=DefaultPacingResolver(redis=redis),
    )
    stats = await engine.scan_once(now=_scan_now())
    assert stats["dialed"] == 2
    assert stats["claimed"] == 2
    inflight = int(await redis.get(freq.inflight_key(task.id)) or 0)
    assert inflight == 2
    calling = sum(1 for t in store.targets.values() if t.status == "calling")
    assert calling == 2
    await sim.drain()


# ── Scenario D: agent progressive pacing + abandon ───────────────────────────


@pytest.mark.asyncio
async def test_scenario_d_agent_progressive_and_abandon(redis, store, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    _wire_store(monkeypatch, store)

    task = store.add_task(
        status="active",
        execution_mode="agent",
        queue_id=30,
        pacing_mode="progressive",
        abandon_prompt="hangup",
        max_concurrency=10,
        voice_flow_id=None,
    )
    for i in range(3):
        await store.create_target(
            None,
            {
                "tenant_id": 1,
                "task_id": task.id,
                "phone_number": f"13900000{i:03d}",
                "status": "pending",
                "field_values": {},
                "retry_counts": {},
            },
        )

    ready = {"n": 0}
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.count_pacing_agents_for_queue",
        AsyncMock(side_effect=lambda *_a, **_k: ready["n"]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.pacing.count_pacing_agents_for_queue",
        AsyncMock(side_effect=lambda *_a, **_k: ready["n"]),
        raising=False,
    )
    # DefaultPacingResolver imports from reception module at call time.
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.count_pacing_agents_for_queue",
        AsyncMock(side_effect=lambda *_a, **_k: ready["n"]),
    )

    picker = MagicMock()
    picker.pick_ready_agent_for_queue = AsyncMock(return_value=None)
    hangup = AsyncMock()
    monkeypatch.setattr("app.services.auto_outbound.reception._safe_hangup", hangup)

    reception = ReceptionDispatcher(
        redis=redis,
        strategies={
            "agent": AgentReception(redis=redis, picker=picker),
            "ivr": IvrReception(),
            "bot": BotReception(),
        },
    )
    sim = CallSimulator(profile=_fast_profile(answer_rate=1.0))
    engine = AutoOutboundDialEngine(
        redis=redis,
        session_factory=lambda: _SessionCM(),
        simulator=sim,
        reception=reception,
        pacing_resolver=DefaultPacingResolver(redis=redis),
    )

    # No ready agents → do not dial.
    ready["n"] = 0
    stats = await engine.scan_once(now=_scan_now())
    assert stats["dialed"] == 0
    assert all(t.status == "pending" for t in store.targets.values())

    # One ready agent → progressive 1:1 → dial exactly one.
    ready["n"] = 1
    stats = await engine.scan_once(now=_scan_now())
    assert stats["dialed"] == 1

    ok = await _wait_until(
        lambda: any(
            isinstance(r.reception_result, dict) and r.reception_result.get("abandoned")
            for r in store.records.values()
        )
    )
    assert ok, f"records={[r.reception_result for r in store.records.values()]}"
    abandoned = [
        r
        for r in store.records.values()
        if isinstance(r.reception_result, dict) and r.reception_result.get("abandoned")
    ]
    assert abandoned[0].reception_result.get("abandon_prompt") == "hangup"
    hangup.assert_awaited()
    await sim.drain()


# ── Scenario E: auto-pause on consecutive originate failures ─────────────────


@pytest.mark.asyncio
async def test_scenario_e_auto_pause_on_originate_failures(redis, store, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_AUTO_PAUSE_CONSECUTIVE_FAILURES",
        3,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        False,
    )
    _wire_store(monkeypatch, store)

    task = store.add_task(status="active", max_concurrency=10)
    for i in range(3):
        await store.create_target(
            None,
            {
                "tenant_id": 1,
                "task_id": task.id,
                "phone_number": f"13700000{i:03d}",
                "status": "pending",
                "field_values": {},
                "retry_counts": {},
            },
        )

    engine = AutoOutboundDialEngine(
        redis=redis,
        session_factory=lambda: _SessionCM(),
        pacing_resolver=DefaultPacingResolver(redis=redis),
    )
    engine._simulator = None

    from app.libs.telephony.base import TelephonyRPCError

    async def _boom(*_a, **_k):
        raise TelephonyRPCError(-32602, "connection refused")

    engine._originate = _boom  # type: ignore[method-assign]

    now = _scan_now()
    # Claim/dial one per tick so consecutive-failure counter accumulates.
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_DIAL_BATCH_SIZE",
        1,
    )
    for _ in range(3):
        if store.tasks[task.id].status != "active":
            break
        await engine.scan_once(now=now)

    assert store.tasks[task.id].status == "paused"
    assert store.tasks[task.id].auto_pause_reason == AUTO_PAUSE_REASON_DIAL_UNAVAILABLE
    failed = [r for r in store.records.values() if r.terminal_state == "failed"]
    assert len(failed) >= 3


# ── Scenario F: predictive abandon → dial_intensity down ─────────────────────


@pytest.mark.asyncio
async def test_scenario_f_predictive_abandon_lowers_intensity(redis, store, monkeypatch):
    _wire_store(monkeypatch, store)
    task = store.add_task(
        status="active",
        execution_mode="agent",
        queue_id=30,
        pacing_mode="predictive",
        dial_intensity=2.0,
        abandon_rate_limit=0.03,
        max_concurrency=50,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.count_pacing_agents_for_queue",
        AsyncMock(return_value=10),
    )

    # Seed high abandon rate: 10 answered, 2 abandoned → 20% > 3%.
    for _ in range(10):
        await record_answered_for_pacing(task.id, redis=redis)
    for _ in range(2):
        await record_abandon_for_pacing(task.id, redis=redis)

    resolver = DefaultPacingResolver(redis=redis)
    snap = {
        "id": task.id,
        "tenant_id": task.tenant_id,
        "execution_mode": "agent",
        "max_concurrency": 50,
        "queue_id": 30,
        "pacing_mode": "predictive",
        "dial_ratio": None,
        "dial_intensity": 2.0,
        "abandon_rate_limit": 0.03,
    }
    await resolver.resolve_claim_limit(snap, batch_size=50)
    intensity = await get_current_intensity(task.id, redis=redis)
    assert intensity == pytest.approx(1.9)

    # Direct strategy path (same closed loop) for clarity.
    pacing = PredictivePacing(redis=redis)
    ctx = PacingContext(
        ready_agents=10,
        in_flight=0,
        max_concurrency=50,
        dial_intensity=1.9,
        abandon_rate_limit=0.03,
        task_id=task.id,
    )
    await pacing.compute_slots(SimpleNamespace(id=task.id, dial_intensity=2.0), ctx)
    intensity2 = await get_current_intensity(task.id, redis=redis)
    assert intensity2 == pytest.approx(1.8)


@pytest.mark.asyncio
async def test_scenario_a_create_via_service_schema(monkeypatch, store):
    """Create path uses AutoOutboundTaskCreate validation + repository create."""
    _wire_store(monkeypatch, store)
    template = OutboundTaskTemplate(
        id=2,
        tenant_id=1,
        name="回访模板",
        description=None,
        fields=[
            {
                "key": "note",
                "name": "备注",
                "field_type": "single_line_text",
                "required": False,
                "enabled": True,
            }
        ],
    )
    payload = AutoOutboundTaskCreate(
        name="sim-create",
        template_id=2,
        execution_mode="ivr",
        voice_flow_id=10,
        voice_flow_name="flow",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        daily_time_windows=[{"start": "00:00", "end": "23:59"}],
        caller_number_id="pn_1",
    )
    with patch(
        "app.services.auto_outbound_task_service.OutboundTaskRepository.get_template",
        AsyncMock(return_value=template),
    ), patch(
        "app.services.auto_outbound_task_service.EmployeeRepository.get_by_ids",
        AsyncMock(return_value=[]),
    ), patch.object(
        AutoOutboundTaskService,
        "_assert_reception_refs",
        new=AsyncMock(),
    ):
        resp = await AutoOutboundTaskService.create_task(
            _service_db(), _principal(), payload
        )
    assert resp.status == "draft"
    assert resp.execution_mode == "ivr"
    assert store.tasks[resp.id].name == "sim-create"
