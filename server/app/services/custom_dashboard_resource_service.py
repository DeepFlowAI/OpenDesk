"""Redis-backed resource governance for custom dashboard component runs."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass

import redis.asyncio as aioredis

from app.configs.settings import settings
from app.core.exceptions import RateLimitedError, ValidationError


_ACQUIRE_LUA = """
local tenant = tonumber(redis.call('get', KEYS[1]) or '0')
local dashboard = tonumber(redis.call('get', KEYS[2]) or '0')
if tenant >= tonumber(ARGV[1]) or dashboard >= tonumber(ARGV[2]) then
  return 0
end
redis.call('incr', KEYS[1])
redis.call('expire', KEYS[1], tonumber(ARGV[3]))
redis.call('incr', KEYS[2])
redis.call('expire', KEYS[2], tonumber(ARGV[3]))
return 1
"""

_RELEASE_LUA = """
for i = 1, #KEYS do
  local value = tonumber(redis.call('get', KEYS[i]) or '0')
  if value <= 1 then
    redis.call('del', KEYS[i])
  else
    redis.call('decr', KEYS[i])
  end
end
return 1
"""

_INCREMENT_LIMITED_LUA = """
local value = redis.call('incr', KEYS[1])
if value == 1 then redis.call('expire', KEYS[1], tonumber(ARGV[2])) end
if value > tonumber(ARGV[1]) then return 0 end
return value
"""


@dataclass
class DashboardExecutionLease:
    """Acquired tenant and dashboard concurrency slots."""

    redis: aioredis.Redis
    tenant_key: str
    dashboard_key: str
    released: bool = False

    async def release(self) -> None:
        if self.released:
            return
        await self.redis.eval(
            _RELEASE_LUA,
            2,
            self.tenant_key,
            self.dashboard_key,
        )
        self.released = True


class CustomDashboardResourceService:
    """Coordinate limits, cancellation, caches, and cooldowns across nodes."""

    @staticmethod
    async def acquire_execution(
        redis: aioredis.Redis,
        *,
        tenant_id: int,
        dashboard_id: int,
        cancel_checker,
    ) -> DashboardExecutionLease:
        tenant_key = f"dashboard:inflight:tenant:{tenant_id}"
        dashboard_key = f"dashboard:inflight:dashboard:{tenant_id}:{dashboard_id}"
        queue_key = f"dashboard:queue:{tenant_id}"
        lease_ttl = max(30, int(settings.DASHBOARD_RUN_WALL_SECONDS) + 10)

        if await CustomDashboardResourceService._try_acquire(
            redis,
            tenant_key,
            dashboard_key,
            lease_ttl,
        ):
            return DashboardExecutionLease(redis, tenant_key, dashboard_key)

        queued = await redis.eval(
            _INCREMENT_LIMITED_LUA,
            1,
            queue_key,
            settings.DASHBOARD_TENANT_MAX_QUEUED,
            max(15, int(settings.DASHBOARD_QUEUE_WAIT_SECONDS) + 5),
        )
        if not queued:
            await redis.decr(queue_key)
            raise RateLimitedError("Tenant dashboard queue is full")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + settings.DASHBOARD_QUEUE_WAIT_SECONDS
        try:
            while loop.time() < deadline:
                if await cancel_checker():
                    raise ValidationError("Dashboard run was cancelled")
                if await CustomDashboardResourceService._try_acquire(
                    redis,
                    tenant_key,
                    dashboard_key,
                    lease_ttl,
                ):
                    return DashboardExecutionLease(redis, tenant_key, dashboard_key)
                await asyncio.sleep(0.2)
            raise RateLimitedError("Tenant dashboard queue wait timed out")
        finally:
            await _decrement_floor_zero(redis, queue_key)

    @staticmethod
    async def _try_acquire(
        redis: aioredis.Redis,
        tenant_key: str,
        dashboard_key: str,
        lease_ttl: int,
    ) -> bool:
        result = await redis.eval(
            _ACQUIRE_LUA,
            2,
            tenant_key,
            dashboard_key,
            settings.DASHBOARD_TENANT_MAX_CONCURRENCY,
            settings.DASHBOARD_MAX_CONCURRENCY,
            lease_ttl,
        )
        return bool(result)

    @staticmethod
    async def enforce_miss_rate(
        redis: aioredis.Redis,
        *,
        tenant_id: int,
        employee_id: int,
    ) -> None:
        checks = (
            (
                f"dashboard:rate:tenant-minute:{tenant_id}",
                settings.DASHBOARD_TENANT_RATE_PER_MINUTE,
                60,
            ),
            (
                f"dashboard:rate:tenant-second:{tenant_id}",
                settings.DASHBOARD_TENANT_BURST_PER_SECOND,
                1,
            ),
            (
                f"dashboard:rate:employee-minute:{tenant_id}:{employee_id}",
                settings.DASHBOARD_EMPLOYEE_RATE_PER_MINUTE,
                60,
            ),
        )
        for key, limit, ttl in checks:
            allowed = await redis.eval(_INCREMENT_LIMITED_LUA, 1, key, limit, ttl)
            if not allowed:
                raise RateLimitedError("Dashboard run rate limit exceeded")

    @staticmethod
    async def enforce_refresh_cooldown(
        redis: aioredis.Redis,
        *,
        tenant_id: int,
        employee_id: int,
        dashboard_id: int,
    ) -> None:
        key = f"dashboard:rate:refresh:{tenant_id}:{employee_id}:{dashboard_id}"
        allowed = await redis.set(
            key,
            "1",
            nx=True,
            ex=settings.DASHBOARD_REFRESH_COOLDOWN_SECONDS,
        )
        if not allowed:
            raise RateLimitedError("Dashboard refresh is cooling down")

    @staticmethod
    async def consume_page_query(
        redis: aioredis.Redis,
        *,
        tenant_id: int,
        employee_id: int,
        page_run_id: str,
    ) -> None:
        key = f"dashboard:page:queries:{tenant_id}:{employee_id}:{page_run_id}"
        allowed = await redis.eval(
            _INCREMENT_LIMITED_LUA,
            1,
            key,
            settings.DASHBOARD_PAGE_MAX_QUERIES,
            60,
        )
        if not allowed:
            raise ValidationError("Dashboard page query quota exceeded")

    @staticmethod
    async def get_cache(redis: aioredis.Redis, cache_key: str) -> dict | None:
        raw = await redis.get(f"dashboard:cache:{cache_key}")
        if raw is None:
            return None
        try:
            return json.loads(_decode(raw))
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    async def set_cache(redis: aioredis.Redis, cache_key: str, value: dict) -> None:
        await redis.setex(
            f"dashboard:cache:{cache_key}",
            settings.DASHBOARD_RESULT_CACHE_SECONDS,
            json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        )

    @staticmethod
    def build_cache_key(payload: dict) -> str:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    async def cancel_run(
        redis: aioredis.Redis,
        *,
        tenant_id: int,
        employee_id: int,
        request_id: str,
    ) -> None:
        await redis.setex(
            _run_cancel_key(tenant_id, employee_id, request_id),
            30,
            "1",
        )

    @staticmethod
    async def cancel_page(
        redis: aioredis.Redis,
        *,
        tenant_id: int,
        employee_id: int,
        page_run_id: str,
    ) -> None:
        await redis.setex(
            _page_cancel_key(tenant_id, employee_id, page_run_id),
            60,
            "1",
        )

    @staticmethod
    async def is_cancelled(
        redis: aioredis.Redis,
        *,
        tenant_id: int,
        employee_id: int,
        request_id: str,
        page_run_id: str,
    ) -> bool:
        values = await redis.mget(
            _run_cancel_key(tenant_id, employee_id, request_id),
            _page_cancel_key(tenant_id, employee_id, page_run_id),
        )
        return any(value is not None for value in values)

    @staticmethod
    async def is_cooling_down(redis: aioredis.Redis, component_key: str) -> bool:
        return bool(await redis.exists(f"dashboard:resource:cooldown:{component_key}"))

    @staticmethod
    async def record_resource_failure(redis: aioredis.Redis, component_key: str) -> None:
        failure_key = f"dashboard:resource:failures:{component_key}"
        failures = await redis.incr(failure_key)
        await redis.expire(failure_key, settings.DASHBOARD_RESOURCE_COOLDOWN_SECONDS)
        if failures >= settings.DASHBOARD_RESOURCE_COOLDOWN_FAILURES:
            await redis.setex(
                f"dashboard:resource:cooldown:{component_key}",
                settings.DASHBOARD_RESOURCE_COOLDOWN_SECONDS,
                "1",
            )
            await redis.delete(failure_key)

    @staticmethod
    async def record_success(redis: aioredis.Redis, component_key: str) -> None:
        await redis.delete(f"dashboard:resource:failures:{component_key}")


async def _decrement_floor_zero(redis: aioredis.Redis, key: str) -> None:
    await redis.eval(_RELEASE_LUA, 1, key)


def _run_cancel_key(tenant_id: int, employee_id: int, request_id: str) -> str:
    return f"dashboard:run:cancel:{tenant_id}:{employee_id}:{request_id}"


def _page_cancel_key(tenant_id: int, employee_id: int, page_run_id: str) -> str:
    return f"dashboard:page:cancel:{tenant_id}:{employee_id}:{page_run_id}"


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
