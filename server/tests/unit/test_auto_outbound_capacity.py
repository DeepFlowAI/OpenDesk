"""Unit tests for composable auto-outbound dial capacity."""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from app.services.auto_outbound.capacity import (
    SOURCE_BATCH,
    SOURCE_FLOWKIT,
    SOURCE_RECEPTION,
    SOURCE_TASK,
    SOURCE_TENANT,
    SOURCE_TRUNK,
    BatchCapacitySource,
    CapacitySnapshot,
    DialCapacityPlanner,
    FlowKitCapacitySource,
    TaskCapacitySource,
    TenantCapacitySource,
    TrunkCapacitySource,
    _min_remaining,
)


@dataclass
class _FakeSource:
    name: str
    remaining: int | None
    limit: int | None = None

    async def snapshot(self, task_snap: dict, *, batch_size: int) -> CapacitySnapshot:
        return CapacitySnapshot(remaining=self.remaining, limit=self.limit)


def _task_snap(**overrides) -> dict:
    data = {
        "id": 1,
        "tenant_id": 9,
        "max_concurrency": 10,
        "execution_mode": "ivr",
        "caller_number_id": None,
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_min_of_configured_sources_only():
    planner = DialCapacityPlanner(
        sources=[
            _FakeSource(SOURCE_TASK, 8),
            _FakeSource(SOURCE_TENANT, None),
            _FakeSource(SOURCE_FLOWKIT, 3),
            _FakeSource(SOURCE_TRUNK, None),
            _FakeSource(SOURCE_BATCH, 20),
            _FakeSource(SOURCE_RECEPTION, None),
        ]
    )
    plan = await planner.resolve(_task_snap(), batch_size=20)
    assert plan.dialable == 3
    assert plan.sources[SOURCE_TENANT] is None
    assert plan.sources[SOURCE_TRUNK] is None
    assert plan.sources[SOURCE_RECEPTION] is None
    assert set(plan.sources) == {
        SOURCE_TASK,
        SOURCE_TENANT,
        SOURCE_FLOWKIT,
        SOURCE_TRUNK,
        SOURCE_BATCH,
        SOURCE_RECEPTION,
    }


@pytest.mark.asyncio
async def test_unconfigured_sources_do_not_invent_limits():
    planner = DialCapacityPlanner(
        sources=[
            _FakeSource(SOURCE_TASK, 5),
            _FakeSource(SOURCE_TENANT, None),
            _FakeSource(SOURCE_FLOWKIT, None),
            _FakeSource(SOURCE_TRUNK, None),
            _FakeSource(SOURCE_BATCH, 2),
            _FakeSource(SOURCE_RECEPTION, None),
        ]
    )
    plan = await planner.resolve(_task_snap(), batch_size=2)
    assert plan.dialable == 2
    assert all(plan.sources[name] is None for name in (SOURCE_TENANT, SOURCE_FLOWKIT, SOURCE_TRUNK, SOURCE_RECEPTION))


def test_min_remaining_empty_is_zero():
    assert _min_remaining([]) == 0
    assert _min_remaining([None, None]) == 0
    assert _min_remaining([None, 0, 4]) == 0


@pytest.mark.asyncio
async def test_tenant_source_unconfigured_when_limit_zero(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "app.services.auto_outbound.capacity.settings.AUTO_OUTBOUND_TENANT_MAX_CONCURRENCY",
        0,
    )
    snap = await TenantCapacitySource(redis=redis).snapshot(_task_snap(), batch_size=5)
    assert snap.remaining is None
    assert snap.limit is None


@pytest.mark.asyncio
async def test_task_source_subtracts_inflight():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    from app.services.auto_outbound import frequency as freq

    await freq.acquire_concurrency(1, 10, redis=redis)
    await freq.acquire_concurrency(1, 10, redis=redis)
    snap = await TaskCapacitySource(redis=redis).snapshot(_task_snap(max_concurrency=5), batch_size=10)
    assert snap.remaining == 3
    assert snap.limit == 5
    assert snap.in_flight == 2


@pytest.mark.asyncio
async def test_trunk_source_none_without_caller_number():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    snap = await TrunkCapacitySource(redis=redis).snapshot(_task_snap(), batch_size=5)
    assert snap.remaining is None


@pytest.mark.asyncio
async def test_trunk_source_uses_snapshot_concurrency():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    snap = await TrunkCapacitySource(redis=redis).snapshot(
        _task_snap(caller_number_id="pn_1", caller_number_concurrency=4),
        batch_size=5,
    )
    assert snap.remaining == 4
    assert snap.limit == 4


@pytest.mark.asyncio
async def test_flowkit_negative_remaining_means_unconstrained():
    telephony = AsyncMock()
    telephony.originate_capacity = AsyncMock(
        return_value={"originate_remaining": -1, "originate_max_concurrent": 0}
    )
    snap = await FlowKitCapacitySource(telephony_factory=lambda: telephony).snapshot(
        _task_snap(), batch_size=5
    )
    assert snap.remaining is None


@pytest.mark.asyncio
async def test_batch_source_is_batch_size():
    snap = await BatchCapacitySource().snapshot(_task_snap(), batch_size=7)
    assert snap.remaining == 7


@pytest.mark.asyncio
async def test_failed_source_does_not_constrain():
    class _Boom:
        name = SOURCE_FLOWKIT

        async def snapshot(self, task_snap: dict, *, batch_size: int) -> CapacitySnapshot:
            raise RuntimeError("probe down")

    planner = DialCapacityPlanner(
        sources=[
            _FakeSource(SOURCE_TASK, 4),
            _Boom(),
            _FakeSource(SOURCE_BATCH, 9),
        ]
    )
    plan = await planner.resolve(_task_snap(), batch_size=9)
    assert plan.sources[SOURCE_FLOWKIT] is None
    assert plan.dialable == 4
    assert await planner.resolve_claim_limit(_task_snap(), batch_size=9) == 4
