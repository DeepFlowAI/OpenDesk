"""Redis frequency control and in-flight reservations for auto outbound."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from redis.exceptions import WatchError

logger = logging.getLogger(__name__)

FREQ_KEY_PREFIX = "auto_outbound:freq"
INFLIGHT_KEY_PREFIX = "auto_outbound:inflight"
QUEUE_INFLIGHT_KEY_PREFIX = "auto_outbound:queue_inflight"
PACING_RESERVATION_KEY_PREFIX = "auto_outbound:pacing_reservation"
TENANT_INFLIGHT_KEY_PREFIX = "auto_outbound:inflight:tenant"
TRUNK_INFLIGHT_KEY_PREFIX = "auto_outbound:inflight:trunk"
SESSION_KEY_PREFIX = "auto_outbound:session"
TARGET_SESSION_KEY_PREFIX = "auto_outbound:target_session"
ATTEMPT_SESSION_KEY_PREFIX = "auto_outbound:attempt"
CONSEC_FAIL_KEY_PREFIX = "auto_outbound:consec_fail"

# Safety TTLs so leaked counters / sessions eventually expire.
INFLIGHT_TTL_SECONDS = 2 * 60 * 60
SESSION_TTL_SECONDS = 4 * 60 * 60
# Consecutive originate failures across replicas; cleared on success.
CONSEC_FAIL_TTL_SECONDS = 10 * 60


class RedisLike(Protocol):
    async def get(self, name: str) -> Any: ...
    async def incr(self, name: str) -> int: ...
    async def decr(self, name: str) -> int: ...
    async def expire(self, name: str, time: int) -> bool: ...
    async def delete(self, *names: str) -> int: ...
    async def set(self, name: str, value: Any, ex: int | None = None) -> Any: ...
    def pipeline(self, transaction: bool = True) -> Any: ...


def _default_redis() -> Any:
    from app.db.redis import redis_client

    return redis_client.client


def freq_key(task_id: int, phone: str, day: str) -> str:
    return f"{FREQ_KEY_PREFIX}:{task_id}:{phone}:{day}"


def inflight_key(task_id: int) -> str:
    return f"{INFLIGHT_KEY_PREFIX}:{task_id}"


def queue_inflight_key(tenant_id: int, queue_id: int) -> str:
    return f"{QUEUE_INFLIGHT_KEY_PREFIX}:{tenant_id}:{queue_id}"


def pacing_reservation_key(target_id: int) -> str:
    return f"{PACING_RESERVATION_KEY_PREFIX}:{target_id}"


def tenant_inflight_key(tenant_id: int) -> str:
    return f"{TENANT_INFLIGHT_KEY_PREFIX}:{tenant_id}"


def trunk_inflight_key(trunk_key: str) -> str:
    return f"{TRUNK_INFLIGHT_KEY_PREFIX}:{trunk_key}"


def session_key(call_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}:{call_id}"


def attempt_session_key(attempt_id: str) -> str:
    return f"{ATTEMPT_SESSION_KEY_PREFIX}:{attempt_id}"


def target_session_key(target_id: int) -> str:
    return f"{TARGET_SESSION_KEY_PREFIX}:{target_id}"


def consec_fail_key(task_id: int) -> str:
    return f"{CONSEC_FAIL_KEY_PREFIX}:{task_id}"


def _yyyymmdd(now: datetime | None = None, *, tz: ZoneInfo | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    # Frequency buckets follow the tenant calendar day (or server local when tz omitted).
    local = current.astimezone(tz) if tz is not None else current.astimezone()
    return local.strftime("%Y%m%d")


def _seconds_until_local_day_end(
    now: datetime | None = None, *, tz: ZoneInfo | None = None
) -> int:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = current.astimezone(tz) if tz is not None else current.astimezone()
    tomorrow = (local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1, int((tomorrow - local).total_seconds()))


async def check_and_incr(
    task_id: int,
    phone: str,
    daily_limit: int,
    *,
    redis: RedisLike | None = None,
    now: datetime | None = None,
    tz: ZoneInfo | None = None,
) -> bool:
    """
    Atomically consume one daily dial slot for (task, phone).

    Returns True when the call is allowed. When the limit is already reached
    (or a race pushes the counter past the limit), returns False and does
    not roll the counter back — simple and correct: the number stays blocked
    for the rest of the local (tenant) day.
    """
    if daily_limit <= 0:
        return False
    r = redis if redis is not None else _default_redis()
    day = _yyyymmdd(now, tz=tz)
    key = freq_key(task_id, phone, day)

    existing = await r.get(key)
    if existing is not None and int(existing) >= daily_limit:
        return False

    count = int(await r.incr(key))
    if count == 1:
        await r.expire(key, _seconds_until_local_day_end(now, tz=tz))
    if count > daily_limit:
        # Race past the limit; leave the count (no DECR) so the day stays blocked.
        return False
    return True


async def rollback_daily_count(
    task_id: int,
    phone: str,
    *,
    redis: RedisLike | None = None,
    now: datetime | None = None,
    tz: ZoneInfo | None = None,
) -> None:
    """
    Roll back one daily frequency slot (e.g. after originate failure).

    Never lets the counter go negative.
    """
    r = redis if redis is not None else _default_redis()
    day = _yyyymmdd(now, tz=tz)
    key = freq_key(task_id, phone, day)
    try:
        existing = await r.get(key)
        if existing is None:
            return
        value = int(await r.decr(key))
        if value <= 0:
            await r.delete(key)
    except Exception:  # noqa: BLE001
        logger.exception(
            "auto_outbound rollback_daily_count failed task_id=%s phone=%s",
            task_id,
            phone,
        )


async def acquire_concurrency(
    task_id: int,
    max_concurrency: int,
    *,
    redis: RedisLike | None = None,
) -> bool:
    """
    Try to take one in-flight slot. Returns False when already at capacity.
    On failure the counter is decremented back so the slot is not leaked.
    """
    if max_concurrency <= 0:
        return False
    r = redis if redis is not None else _default_redis()
    key = inflight_key(task_id)
    count = int(await r.incr(key))
    if count == 1:
        await r.expire(key, INFLIGHT_TTL_SECONDS)
    else:
        # Refresh floor TTL on every acquire to cover long-running campaigns.
        await r.expire(key, INFLIGHT_TTL_SECONDS)
    if count > max_concurrency:
        await r.decr(key)
        return False
    return True


async def release_concurrency(
    task_id: int,
    *,
    redis: RedisLike | None = None,
) -> None:
    """Release one in-flight slot; never lets the counter go negative."""
    r = redis if redis is not None else _default_redis()
    key = inflight_key(task_id)
    try:
        value = int(await r.decr(key))
    except Exception:  # noqa: BLE001
        logger.exception("auto_outbound release_concurrency failed task_id=%s", task_id)
        return
    if value < 0:
        await r.set(key, 0, ex=INFLIGHT_TTL_SECONDS)
    elif value == 0:
        await r.expire(key, INFLIGHT_TTL_SECONDS)


async def acquire_pacing_slot(
    task_id: int,
    max_concurrency: int,
    *,
    tenant_id: int,
    queue_id: int,
    queue_capacity: int,
    target_id: int,
    redis: RedisLike | None = None,
) -> bool:
    """Atomically reserve task and shared reception-queue dial capacity."""
    if max_concurrency <= 0 or queue_capacity <= 0:
        return False

    r = redis if redis is not None else _default_redis()
    task_key = inflight_key(task_id)
    queue_key = queue_inflight_key(tenant_id, queue_id)
    reservation_key = pacing_reservation_key(target_id)

    for _ in range(5):
        async with r.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(task_key, queue_key, reservation_key)
                task_count = int(await pipe.get(task_key) or 0)
                queue_count = int(await pipe.get(queue_key) or 0)
                if await pipe.get(reservation_key) is not None:
                    await pipe.reset()
                    return False
                if task_count >= max_concurrency or queue_count >= queue_capacity:
                    await pipe.reset()
                    return False

                pipe.multi()
                pipe.set(task_key, task_count + 1, ex=INFLIGHT_TTL_SECONDS)
                pipe.set(queue_key, queue_count + 1, ex=INFLIGHT_TTL_SECONDS)
                pipe.set(reservation_key, "1", ex=INFLIGHT_TTL_SECONDS)
                await pipe.execute()
                return True
            except WatchError:
                continue

    logger.warning(
        "auto_outbound pacing slot conflict task_id=%s queue_id=%s target_id=%s",
        task_id,
        queue_id,
        target_id,
    )
    return False


async def release_pacing_slot(
    task_id: int,
    *,
    tenant_id: int,
    queue_id: int,
    target_id: int,
    redis: RedisLike | None = None,
) -> None:
    """Idempotently release a task and shared reception-queue reservation."""
    r = redis if redis is not None else _default_redis()
    task_key = inflight_key(task_id)
    queue_key = queue_inflight_key(tenant_id, queue_id)
    reservation_key = pacing_reservation_key(target_id)

    for _ in range(5):
        async with r.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(task_key, queue_key, reservation_key)
                if await pipe.get(reservation_key) is None:
                    await pipe.reset()
                    return
                task_count = max(0, int(await pipe.get(task_key) or 0) - 1)
                queue_count = max(0, int(await pipe.get(queue_key) or 0) - 1)

                pipe.multi()
                pipe.set(task_key, task_count, ex=INFLIGHT_TTL_SECONDS)
                pipe.set(queue_key, queue_count, ex=INFLIGHT_TTL_SECONDS)
                pipe.delete(reservation_key)
                await pipe.execute()
                return
            except WatchError:
                continue

    logger.warning(
        "auto_outbound pacing release conflict task_id=%s queue_id=%s target_id=%s",
        task_id,
        queue_id,
        target_id,
    )


async def reset_concurrency(
    task_id: int,
    *,
    redis: RedisLike | None = None,
) -> None:
    """Drop the in-flight counter (used when a task is auto-paused)."""
    r = redis if redis is not None else _default_redis()
    await r.delete(inflight_key(task_id))


async def get_concurrency(
    task_id: int,
    *,
    redis: RedisLike | None = None,
) -> int:
    """Current in-flight call count for a task (0 when missing)."""
    r = redis if redis is not None else _default_redis()
    raw = await r.get(inflight_key(task_id))
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


async def get_queue_inflight(
    tenant_id: int,
    queue_id: int,
    *,
    redis: RedisLike | None = None,
) -> int:
    """Return calls currently reserving shared reception-queue capacity."""
    r = redis if redis is not None else _default_redis()
    raw = await r.get(queue_inflight_key(tenant_id, queue_id))
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


async def get_tenant_concurrency(
    tenant_id: int,
    *,
    redis: RedisLike | None = None,
) -> int:
    r = redis if redis is not None else _default_redis()
    raw = await r.get(tenant_inflight_key(tenant_id))
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


async def get_trunk_concurrency(
    trunk_key: str,
    *,
    redis: RedisLike | None = None,
) -> int:
    r = redis if redis is not None else _default_redis()
    raw = await r.get(trunk_inflight_key(trunk_key))
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


async def _acquire_counter(key: str, limit: int | None, *, redis: RedisLike) -> bool:
    """Increment a counter. ``limit is None`` means track-only (never reject)."""
    count = int(await redis.incr(key))
    await redis.expire(key, INFLIGHT_TTL_SECONDS)
    if limit is not None and count > int(limit):
        await redis.decr(key)
        return False
    return True


async def _release_counter(key: str, *, redis: RedisLike) -> None:
    try:
        value = int(await redis.decr(key))
    except Exception:  # noqa: BLE001
        logger.exception("auto_outbound release counter failed key=%s", key)
        return
    if value < 0:
        await redis.set(key, 0, ex=INFLIGHT_TTL_SECONDS)
    else:
        await redis.expire(key, INFLIGHT_TTL_SECONDS)


class ConcurrencyLease:
    """Holds task + tenant + DID slots acquired for one originate."""

    def __init__(
        self,
        *,
        task_id: int,
        tenant_id: int,
        trunk_key: str | None,
        redis: RedisLike,
    ) -> None:
        self.task_id = task_id
        self.tenant_id = tenant_id
        self.trunk_key = trunk_key
        self._redis = redis
        self._released = False

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await release_concurrency(self.task_id, redis=self._redis)
        await _release_counter(tenant_inflight_key(self.tenant_id), redis=self._redis)
        if self.trunk_key:
            await _release_counter(trunk_inflight_key(self.trunk_key), redis=self._redis)


async def acquire_tenant_trunk(
    *,
    tenant_id: int,
    tenant_limit: int | None,
    trunk_key: str | None,
    trunk_limit: int | None,
    redis: RedisLike | None = None,
) -> bool:
    """Take tenant + DID slots without touching the task counter."""
    r = redis if redis is not None else _default_redis()
    if not await _acquire_counter(tenant_inflight_key(tenant_id), tenant_limit, redis=r):
        return False
    if trunk_key:
        if not await _acquire_counter(trunk_inflight_key(trunk_key), trunk_limit, redis=r):
            await _release_counter(tenant_inflight_key(tenant_id), redis=r)
            return False
    return True


async def release_tenant_trunk(
    *,
    tenant_id: int,
    trunk_key: str | None,
    redis: RedisLike | None = None,
) -> None:
    r = redis if redis is not None else _default_redis()
    await _release_counter(tenant_inflight_key(tenant_id), redis=r)
    if trunk_key:
        await _release_counter(trunk_inflight_key(trunk_key), redis=r)


async def acquire_lease(
    *,
    task_id: int,
    task_limit: int,
    tenant_id: int,
    tenant_limit: int | None,
    trunk_key: str | None,
    trunk_limit: int | None,
    redis: RedisLike | None = None,
) -> ConcurrencyLease | None:
    """
    Take one slot on each configured layer. Any rejection rolls back
    already-taken counters so a failed claim does not leak quota.
    """
    r = redis if redis is not None else _default_redis()
    if not await acquire_concurrency(task_id, task_limit, redis=r):
        return None
    if not await _acquire_counter(tenant_inflight_key(tenant_id), tenant_limit, redis=r):
        await release_concurrency(task_id, redis=r)
        return None
    if trunk_key:
        if not await _acquire_counter(trunk_inflight_key(trunk_key), trunk_limit, redis=r):
            await _release_counter(tenant_inflight_key(tenant_id), redis=r)
            await release_concurrency(task_id, redis=r)
            return None
    return ConcurrencyLease(
        task_id=task_id,
        tenant_id=tenant_id,
        trunk_key=trunk_key,
        redis=r,
    )


async def incr_consecutive_failures(
    task_id: int,
    *,
    redis: RedisLike | None = None,
) -> int:
    """Increment per-task consecutive originate failures; returns new count."""
    r = redis if redis is not None else _default_redis()
    key = consec_fail_key(task_id)
    count = int(await r.incr(key))
    await r.expire(key, CONSEC_FAIL_TTL_SECONDS)
    return count


async def clear_consecutive_failures(
    task_id: int,
    *,
    redis: RedisLike | None = None,
) -> None:
    r = redis if redis is not None else _default_redis()
    await r.delete(consec_fail_key(task_id))


async def set_session_mapping(
    call_id: str,
    payload: dict,
    *,
    redis: RedisLike | None = None,
    ttl_seconds: int = SESSION_TTL_SECONDS,
) -> None:
    import json

    r = redis if redis is not None else _default_redis()
    if call_id:
        await r.set(session_key(call_id), json.dumps(payload), ex=ttl_seconds)
    # Reverse index so stale-calling sweep can check session existence by target.
    # Pending originates (empty call_id) index the target to attempt_id.
    target_id = payload.get("target_id")
    attempt_id = payload.get("attempt_id")
    if target_id is not None:
        token = call_id or (str(attempt_id) if attempt_id else "")
        if token:
            await r.set(target_session_key(int(target_id)), token, ex=ttl_seconds)
    if attempt_id:
        await r.set(attempt_session_key(str(attempt_id)), json.dumps(payload), ex=ttl_seconds)


async def get_session_by_attempt(
    attempt_id: str,
    *,
    redis: RedisLike | None = None,
) -> dict | None:
    import json

    r = redis if redis is not None else _default_redis()
    raw = await r.get(attempt_session_key(attempt_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


async def get_session_mapping(
    call_id: str,
    *,
    redis: RedisLike | None = None,
) -> dict | None:
    import json

    r = redis if redis is not None else _default_redis()
    raw = await r.get(session_key(call_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


async def has_session_for_target(
    target_id: int,
    *,
    redis: RedisLike | None = None,
) -> bool:
    """True when a live session mapping exists for this target."""
    r = redis if redis is not None else _default_redis()
    token = await r.get(target_session_key(target_id))
    if not token:
        return False
    token_s = str(token)
    if await get_session_mapping(token_s, redis=r) is not None:
        return True
    return await get_session_by_attempt(token_s, redis=r) is not None


async def delete_session_mapping(
    call_id: str,
    *,
    redis: RedisLike | None = None,
) -> None:
    r = redis if redis is not None else _default_redis()
    data = await get_session_mapping(call_id, redis=r)
    await r.delete(session_key(call_id))
    if data and data.get("target_id") is not None:
        await r.delete(target_session_key(int(data["target_id"])))
    if data and data.get("attempt_id"):
        await r.delete(attempt_session_key(str(data["attempt_id"])))
