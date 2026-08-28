"""Unit tests for auto-outbound Redis frequency / concurrency helpers."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import fakeredis.aioredis
import pytest

from app.services.auto_outbound import frequency as freq


@pytest.fixture
async def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_acquire_and_release_concurrency(redis):
    assert await freq.acquire_concurrency(1, 2, redis=redis) is True
    assert await freq.acquire_concurrency(1, 2, redis=redis) is True
    assert await freq.acquire_concurrency(1, 2, redis=redis) is False
    assert int(await redis.get(freq.inflight_key(1))) == 2

    await freq.release_concurrency(1, redis=redis)
    assert int(await redis.get(freq.inflight_key(1))) == 1
    assert await freq.acquire_concurrency(1, 2, redis=redis) is True


@pytest.mark.asyncio
async def test_release_concurrency_floor_at_zero(redis):
    await freq.release_concurrency(9, redis=redis)
    # decr on missing key → -1, then floored to 0
    assert int(await redis.get(freq.inflight_key(9))) == 0


@pytest.mark.asyncio
async def test_pacing_slot_is_atomic_across_tasks_sharing_queue(redis):
    attempts = [
        freq.acquire_pacing_slot(
            1 if target_id % 2 else 2,
            10,
            tenant_id=9,
            queue_id=7,
            queue_capacity=2,
            target_id=target_id,
            redis=redis,
        )
        for target_id in range(1, 21)
    ]

    results = await asyncio.gather(*attempts)

    assert sum(results) == 2
    assert int(await redis.get(freq.queue_inflight_key(9, 7))) == 2
    task_total = int(await redis.get(freq.inflight_key(1)) or 0) + int(
        await redis.get(freq.inflight_key(2)) or 0
    )
    assert task_total == 2


@pytest.mark.asyncio
async def test_release_pacing_slot_is_idempotent(redis):
    assert await freq.acquire_pacing_slot(
        3,
        10,
        tenant_id=9,
        queue_id=7,
        queue_capacity=2,
        target_id=101,
        redis=redis,
    )

    await freq.release_pacing_slot(
        3, tenant_id=9, queue_id=7, target_id=101, redis=redis
    )
    await freq.release_pacing_slot(
        3, tenant_id=9, queue_id=7, target_id=101, redis=redis
    )

    assert int(await redis.get(freq.inflight_key(3))) == 0
    assert int(await redis.get(freq.queue_inflight_key(9, 7))) == 0


@pytest.mark.asyncio
async def test_daily_frequency_limit_and_key_shape(redis):
    now = datetime(2026, 8, 7, 10, 0, 0).astimezone()
    day = now.strftime("%Y%m%d")
    key = freq.freq_key(3, "13800138000", day)

    assert await freq.check_and_incr(3, "13800138000", 2, redis=redis, now=now) is True
    assert await freq.check_and_incr(3, "13800138000", 2, redis=redis, now=now) is True
    assert await freq.check_and_incr(3, "13800138000", 2, redis=redis, now=now) is False
    assert int(await redis.get(key)) == 2
    ttl = await redis.ttl(key)
    assert ttl > 0


@pytest.mark.asyncio
async def test_daily_frequency_uses_tenant_timezone_bucket(redis):
    # 2026-08-08 02:00 UTC → still 2026-08-07 in America/Los_Angeles.
    now = datetime(2026, 8, 8, 2, 0, 0, tzinfo=timezone.utc)
    tz = ZoneInfo("America/Los_Angeles")
    day = "20260807"
    key = freq.freq_key(3, "13800138000", day)
    assert await freq.check_and_incr(
        3, "13800138000", 1, redis=redis, now=now, tz=tz
    ) is True
    assert int(await redis.get(key)) == 1
    assert await redis.get(freq.freq_key(3, "13800138000", "20260808")) is None


@pytest.mark.asyncio
async def test_rollback_daily_count(redis):
    now = datetime(2026, 8, 7, 10, 0, 0, tzinfo=timezone.utc)
    tz = ZoneInfo("Asia/Shanghai")
    assert await freq.check_and_incr(
        1, "13900001111", 3, redis=redis, now=now, tz=tz
    ) is True
    await freq.rollback_daily_count(1, "13900001111", redis=redis, now=now, tz=tz)
    day = now.astimezone(tz).strftime("%Y%m%d")
    assert await redis.get(freq.freq_key(1, "13900001111", day)) is None


@pytest.mark.asyncio
async def test_consecutive_failures_redis(redis):
    assert await freq.incr_consecutive_failures(7, redis=redis) == 1
    assert await freq.incr_consecutive_failures(7, redis=redis) == 2
    await freq.clear_consecutive_failures(7, redis=redis)
    assert await redis.get(freq.consec_fail_key(7)) is None


@pytest.mark.asyncio
async def test_reset_concurrency(redis):
    await freq.acquire_concurrency(5, 10, redis=redis)
    await freq.acquire_concurrency(5, 10, redis=redis)
    await freq.reset_concurrency(5, redis=redis)
    assert await redis.get(freq.inflight_key(5)) is None


@pytest.mark.asyncio
async def test_session_mapping_roundtrip(redis):
    await freq.set_session_mapping(
        "call-1",
        {"task_id": 1, "target_id": 2, "record_id": 3, "tenant_id": 9},
        redis=redis,
        ttl_seconds=60,
    )
    data = await freq.get_session_mapping("call-1", redis=redis)
    assert data == {"task_id": 1, "target_id": 2, "record_id": 3, "tenant_id": 9}
    assert await freq.has_session_for_target(2, redis=redis) is True
    await freq.delete_session_mapping("call-1", redis=redis)
    assert await freq.get_session_mapping("call-1", redis=redis) is None
    assert await freq.has_session_for_target(2, redis=redis) is False
