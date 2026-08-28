"""Unit tests for auto-outbound dial pacing strategies."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from app.services.auto_outbound.pacing import (
    DefaultPacingResolver,
    PacingContext,
    PredictivePacing,
    ProgressivePacing,
    RatioPacing,
    get_abandon_rate,
    record_abandon_for_pacing,
    record_answered_for_pacing,
)


def _task(**overrides):
    data = dict(
        id=1,
        dial_ratio=2,
        dial_intensity=1.5,
        abandon_rate_limit=0.03,
        pacing_mode="progressive",
    )
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.fixture
async def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ready,in_flight,max_c,expected",
    [
        (3, 0, 10, 3),
        (3, 2, 10, 1),
        (1, 1, 10, 0),
        (0, 0, 10, 0),
        (5, 0, 2, 2),  # capped by remaining concurrency
    ],
)
async def test_progressive_slots(ready, in_flight, max_c, expected):
    ctx = PacingContext(ready_agents=ready, in_flight=in_flight, max_concurrency=max_c)
    assert await ProgressivePacing().compute_slots(_task(), ctx) == expected


@pytest.mark.asyncio
async def test_progressive_subtracts_shared_queue_calls_not_task_calls():
    ctx = PacingContext(
        ready_agents=2,
        in_flight=3,
        queue_in_flight=1,
        max_concurrency=10,
    )
    assert await ProgressivePacing().compute_slots(_task(), ctx) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ready,ratio,in_flight,max_c,expected",
    [
        (2, 2, 0, 10, 4),
        (2, 3, 1, 10, 5),
        (2, 2, 0, 3, 3),
        (0, 5, 0, 10, 0),
    ],
)
async def test_ratio_slots(ready, ratio, in_flight, max_c, expected):
    ctx = PacingContext(
        ready_agents=ready,
        in_flight=in_flight,
        max_concurrency=max_c,
        dial_ratio=ratio,
    )
    assert await RatioPacing().compute_slots(_task(dial_ratio=ratio), ctx) == expected


@pytest.mark.asyncio
async def test_ratio_subtracts_shared_queue_calls_not_task_calls():
    ctx = PacingContext(
        ready_agents=2,
        in_flight=3,
        queue_in_flight=4,
        max_concurrency=10,
        dial_ratio=3,
    )
    assert await RatioPacing().compute_slots(_task(dial_ratio=3), ctx) == 2


@pytest.mark.asyncio
async def test_predictive_slots_basic(redis):
    pacing = PredictivePacing(redis=redis)
    ctx = PacingContext(
        ready_agents=4,
        in_flight=1,
        max_concurrency=20,
        dial_intensity=1.5,
        abandon_rate_limit=0.03,
        task_id=9,
    )
    # floor(4 * 1.5) - 1 = 6 - 1 = 5
    assert await pacing.compute_slots(_task(), ctx) == 5


@pytest.mark.asyncio
async def test_predictive_subtracts_shared_queue_calls_not_task_calls(redis):
    pacing = PredictivePacing(redis=redis)
    ctx = PacingContext(
        ready_agents=4,
        in_flight=3,
        queue_in_flight=1,
        max_concurrency=20,
        dial_intensity=1.5,
        abandon_rate_limit=0.03,
        task_id=9,
    )
    assert await pacing.compute_slots(_task(), ctx) == 5


@pytest.mark.asyncio
async def test_predictive_intensity_drops_on_high_abandon(redis):
    pacing = PredictivePacing(redis=redis)
    task_id = 42
    # 10 answered, 2 abandoned → 20% > 3%
    for _ in range(10):
        await record_answered_for_pacing(task_id, redis=redis)
    for _ in range(2):
        await record_abandon_for_pacing(task_id, redis=redis)
    assert await get_abandon_rate(task_id, redis=redis) == pytest.approx(0.2)

    ctx = PacingContext(
        ready_agents=10,
        in_flight=0,
        max_concurrency=50,
        dial_intensity=2.0,
        abandon_rate_limit=0.03,
        task_id=task_id,
    )
    await pacing.compute_slots(_task(dial_intensity=2.0), ctx)
    # intensity should have stepped down from 2.0 toward floor
    raw = await redis.get(f"auto_outbound:intensity:{task_id}")
    assert float(raw) == pytest.approx(1.9)


@pytest.mark.asyncio
async def test_predictive_intensity_recovers_when_low_abandon(redis):
    pacing = PredictivePacing(redis=redis)
    task_id = 43
    await redis.set(f"auto_outbound:intensity:{task_id}", "1.2")
    # 20 answered, 0 abandoned → rate 0 < half of 0.03
    for _ in range(20):
        await record_answered_for_pacing(task_id, redis=redis)

    ctx = PacingContext(
        ready_agents=4,
        in_flight=0,
        max_concurrency=50,
        dial_intensity=2.0,
        abandon_rate_limit=0.03,
        task_id=task_id,
    )
    await pacing.compute_slots(_task(dial_intensity=2.0), ctx)
    raw = await redis.get(f"auto_outbound:intensity:{task_id}")
    assert float(raw) == pytest.approx(1.3)


@pytest.mark.asyncio
async def test_default_resolver_non_agent_uses_remaining(redis, monkeypatch):
    from app.services.auto_outbound import frequency as freq

    await freq.acquire_concurrency(1, 10, redis=redis)
    await freq.acquire_concurrency(1, 10, redis=redis)
    resolver = DefaultPacingResolver(redis=redis)
    snap = {
        "id": 1,
        "tenant_id": 1,
        "execution_mode": "ivr",
        "max_concurrency": 10,
    }
    limit = await resolver.resolve_claim_limit(snap, batch_size=50)
    assert limit == 8  # 10 - 2


@pytest.mark.asyncio
async def test_default_resolver_agent_zero_ready(redis, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.count_pacing_agents_for_queue",
        AsyncMock(return_value=0),
    )
    resolver = DefaultPacingResolver(redis=redis)
    snap = {
        "id": 1,
        "tenant_id": 1,
        "execution_mode": "agent",
        "max_concurrency": 10,
        "queue_id": 5,
        "pacing_mode": "progressive",
    }
    assert await resolver.resolve_claim_limit(snap, batch_size=50) == 0


@pytest.mark.asyncio
async def test_default_resolver_agent_progressive(redis, monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.count_pacing_agents_for_queue",
        AsyncMock(return_value=3),
    )
    resolver = DefaultPacingResolver(redis=redis)
    snap = {
        "id": 1,
        "tenant_id": 1,
        "execution_mode": "agent",
        "max_concurrency": 10,
        "queue_id": 5,
        "pacing_mode": "progressive",
        "dial_ratio": None,
        "dial_intensity": None,
        "abandon_rate_limit": None,
    }
    assert await resolver.resolve_claim_limit(snap, batch_size=50) == 3


@pytest.mark.asyncio
async def test_default_resolver_returns_queue_capacity_before_batch_cap(
    redis, monkeypatch
):
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.count_pacing_agents_for_queue",
        AsyncMock(return_value=3),
    )
    resolver = DefaultPacingResolver(redis=redis)
    snap = {
        "id": 1,
        "tenant_id": 1,
        "execution_mode": "agent",
        "max_concurrency": 10,
        "queue_id": 5,
        "pacing_mode": "progressive",
        "dial_ratio": None,
        "dial_intensity": None,
        "abandon_rate_limit": None,
    }

    resolution = await resolver.resolve(snap, batch_size=1)

    assert resolution.claim_limit == 1
    assert resolution.queue_capacity == 3


@pytest.mark.asyncio
async def test_default_resolver_uses_shared_queue_inflight(redis, monkeypatch):
    from app.services.auto_outbound import frequency as freq

    monkeypatch.setattr(
        "app.services.auto_outbound.reception.count_pacing_agents_for_queue",
        AsyncMock(return_value=2),
    )
    await redis.set(freq.inflight_key(1), 3)
    await redis.set(freq.queue_inflight_key(1, 5), 1)
    resolver = DefaultPacingResolver(redis=redis)
    snap = {
        "id": 1,
        "tenant_id": 1,
        "execution_mode": "agent",
        "max_concurrency": 10,
        "queue_id": 5,
        "pacing_mode": "progressive",
        "dial_ratio": None,
        "dial_intensity": None,
        "abandon_rate_limit": None,
    }

    resolution = await resolver.resolve(snap, batch_size=50)

    assert resolution.claim_limit == 1
    assert resolution.queue_capacity == 2


@pytest.mark.asyncio
async def test_ratio_explicit_zero_not_replaced_by_default():
    """dial_ratio=0 must not fall through falsy `or 2` default."""
    ctx = PacingContext(
        ready_agents=5,
        in_flight=0,
        max_concurrency=50,
        dial_ratio=0,
    )
    assert await RatioPacing().compute_slots(_task(dial_ratio=0), ctx) == 0


@pytest.mark.asyncio
async def test_predictive_task_zero_intensity_not_replaced_by_default(redis):
    """task.dial_intensity=0 must not fall through falsy `or 1.5`."""
    pacing = PredictivePacing(redis=redis)
    ctx = PacingContext(
        ready_agents=10,
        in_flight=0,
        max_concurrency=50,
        dial_intensity=None,
        abandon_rate_limit=None,
        task_id=99,
    )
    await pacing.compute_slots(_task(dial_intensity=0.0, abandon_rate_limit=0.0), ctx)
    # configured=0 → intensity clamped via floor/min ends at INTENSITY_FLOOR (1.0), not 1.5
    raw = await redis.get("auto_outbound:intensity:99")
    assert float(raw) == pytest.approx(1.0)
