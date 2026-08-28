"""
Dial pacing strategies for agent-mode auto-outbound tasks.

Progressive / ratio / predictive decide how many new originates a scan tick
may claim for a given task, based on queue agent capacity and in-flight calls.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from app.services.auto_outbound import frequency as freq

logger = logging.getLogger(__name__)

INTENSITY_KEY_PREFIX = "auto_outbound:intensity"
ABANDON_ANSWERED_KEY_PREFIX = "auto_outbound:window:answered"
ABANDON_ABANDONED_KEY_PREFIX = "auto_outbound:window:abandoned"
# Sliding window for abandon-rate feedback (predictive intensity adjust).
ABANDON_WINDOW_TTL_SECONDS = 30 * 60
INTENSITY_TTL_SECONDS = 24 * 60 * 60
INTENSITY_FLOOR = 1.0
INTENSITY_STEP = 0.1


@dataclass(frozen=True)
class PacingContext:
    ready_agents: int
    in_flight: int
    max_concurrency: int
    queue_in_flight: int | None = None
    dial_ratio: int | None = None
    dial_intensity: float | None = None
    abandon_rate_limit: float | None = None
    task_id: int | None = None


@dataclass(frozen=True)
class PacingResolution:
    claim_limit: int
    queue_capacity: int | None = None


class PacingStrategy(Protocol):
    async def compute_slots(self, task: Any, ctx: PacingContext) -> int: ...


def _remaining_cap(ctx: PacingContext) -> int:
    return max(0, int(ctx.max_concurrency) - int(ctx.in_flight))


def _pacing_in_flight(ctx: PacingContext) -> int:
    if ctx.queue_in_flight is not None:
        return int(ctx.queue_in_flight)
    return int(ctx.in_flight)


def _clamp_slots(raw: float | int, ctx: PacingContext) -> int:
    remaining = _remaining_cap(ctx)
    return max(0, min(int(raw), remaining))


class ProgressivePacing:
    """1:1 with queue agent capacity — no overdial."""

    async def compute_slots(self, task: Any, ctx: PacingContext) -> int:
        raw = int(ctx.ready_agents) - _pacing_in_flight(ctx)
        return _clamp_slots(raw, ctx)


class RatioPacing:
    """Fixed overdial: agent capacity * ratio - queue in-flight calls."""

    async def compute_slots(self, task: Any, ctx: PacingContext) -> int:
        ratio = ctx.dial_ratio if ctx.dial_ratio is not None else getattr(task, "dial_ratio", None)
        if ratio is None:
            ratio = 2
        ratio = int(ratio)
        raw = int(ctx.ready_agents) * ratio - _pacing_in_flight(ctx)
        return _clamp_slots(raw, ctx)


class PredictivePacing:
    """
    Overdial by intensity, with abandon-rate closed loop.

    When recent abandon_rate exceeds abandon_rate_limit, intensity steps down
    (floor 1.0). When rate is below half the limit, intensity slowly recovers
    toward the configured dial_intensity.
    """

    def __init__(self, *, redis: Any | None = None) -> None:
        self._redis = redis

    def _r(self) -> Any:
        if self._redis is not None:
            return self._redis
        return freq._default_redis()

    async def compute_slots(self, task: Any, ctx: PacingContext) -> int:
        if ctx.dial_intensity is not None:
            configured = float(ctx.dial_intensity)
        else:
            task_intensity = getattr(task, "dial_intensity", None)
            configured = float(task_intensity) if task_intensity is not None else 1.5
        if ctx.abandon_rate_limit is not None:
            limit = float(ctx.abandon_rate_limit)
        else:
            task_limit = getattr(task, "abandon_rate_limit", None)
            limit = float(task_limit) if task_limit is not None else 0.03
        task_id = int(ctx.task_id or getattr(task, "id", 0) or 0)
        intensity = await self._adjust_intensity(task_id, configured=configured, limit=limit)
        raw = math.floor(int(ctx.ready_agents) * intensity) - _pacing_in_flight(ctx)
        return _clamp_slots(raw, ctx)

    async def _adjust_intensity(
        self,
        task_id: int,
        *,
        configured: float,
        limit: float,
    ) -> float:
        if task_id <= 0:
            return max(INTENSITY_FLOOR, configured)
        r = self._r()
        key = intensity_key(task_id)
        current_raw = await r.get(key)
        if current_raw is None:
            current = configured
        else:
            try:
                current = float(current_raw)
            except (TypeError, ValueError):
                current = configured

        rate = await get_abandon_rate(task_id, redis=r)
        if rate is not None and limit > 0 and rate > limit:
            current = max(INTENSITY_FLOOR, round(current - INTENSITY_STEP, 2))
        elif rate is not None and limit > 0 and rate < (limit / 2.0):
            current = min(configured, round(current + INTENSITY_STEP, 2))

        current = max(INTENSITY_FLOOR, min(configured, current))
        await r.set(key, str(current), ex=INTENSITY_TTL_SECONDS)
        return current


def intensity_key(task_id: int) -> str:
    return f"{INTENSITY_KEY_PREFIX}:{task_id}"


def answered_window_key(task_id: int) -> str:
    return f"{ABANDON_ANSWERED_KEY_PREFIX}:{task_id}"


def abandoned_window_key(task_id: int) -> str:
    return f"{ABANDON_ABANDONED_KEY_PREFIX}:{task_id}"


async def record_answered_for_pacing(
    task_id: int,
    *,
    redis: Any | None = None,
) -> None:
    r = redis if redis is not None else freq._default_redis()
    key = answered_window_key(task_id)
    await r.incr(key)
    await r.expire(key, ABANDON_WINDOW_TTL_SECONDS)


async def record_abandon_for_pacing(
    task_id: int,
    *,
    redis: Any | None = None,
) -> None:
    r = redis if redis is not None else freq._default_redis()
    key = abandoned_window_key(task_id)
    await r.incr(key)
    await r.expire(key, ABANDON_WINDOW_TTL_SECONDS)


async def get_abandon_rate(
    task_id: int,
    *,
    redis: Any | None = None,
) -> float | None:
    """Recent abandon_rate = abandoned / answered in the Redis window."""
    r = redis if redis is not None else freq._default_redis()
    answered_raw = await r.get(answered_window_key(task_id))
    abandoned_raw = await r.get(abandoned_window_key(task_id))
    answered = int(answered_raw or 0)
    abandoned = int(abandoned_raw or 0)
    if answered <= 0:
        return None
    return abandoned / answered


async def get_current_intensity(
    task_id: int,
    *,
    redis: Any | None = None,
    default: float | None = None,
) -> float | None:
    r = redis if redis is not None else freq._default_redis()
    raw = await r.get(intensity_key(task_id))
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def resolve_pacing_strategy(
    pacing_mode: str | None,
    *,
    redis: Any | None = None,
) -> PacingStrategy | None:
    if pacing_mode == "progressive":
        return ProgressivePacing()
    if pacing_mode == "ratio":
        return RatioPacing()
    if pacing_mode == "predictive":
        return PredictivePacing(redis=redis)
    return None


def decimal_to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


class DefaultPacingResolver:
    """
    Engine-facing pacing resolver.

    Non-agent modes: remaining concurrency cap (same as Wave B1 effective limit).
    Agent modes: strategy slots, with agent capacity=0 → 0 (do not dial).
    """

    def __init__(self, *, redis: Any | None = None) -> None:
        self._redis = redis

    def _r(self) -> Any:
        if self._redis is not None:
            return self._redis
        return freq._default_redis()

    async def resolve(
        self, task_snap: dict, *, batch_size: int
    ) -> PacingResolution:
        max_concurrency = int(task_snap.get("max_concurrency") or 1)
        in_flight = await freq.get_concurrency(int(task_snap["id"]), redis=self._r())
        remaining = max(0, max_concurrency - in_flight)
        if remaining <= 0:
            return PacingResolution(claim_limit=0)

        mode = task_snap.get("execution_mode")
        if mode != "agent":
            return PacingResolution(claim_limit=min(batch_size, remaining))

        queue_id = task_snap.get("queue_id")
        if not queue_id:
            return PacingResolution(claim_limit=0)

        from app.services.auto_outbound.reception import count_pacing_agents_for_queue

        ready = await count_pacing_agents_for_queue(
            int(task_snap["tenant_id"]),
            int(queue_id),
            redis=self._r(),
        )
        if ready <= 0:
            return PacingResolution(claim_limit=0, queue_capacity=0)

        strategy = resolve_pacing_strategy(task_snap.get("pacing_mode"), redis=self._r())
        if strategy is None:
            strategy = ProgressivePacing()

        queue_in_flight = await freq.get_queue_inflight(
            int(task_snap["tenant_id"]),
            int(queue_id),
            redis=self._r(),
        )

        ctx = PacingContext(
            ready_agents=ready,
            in_flight=in_flight,
            max_concurrency=max_concurrency,
            queue_in_flight=queue_in_flight,
            dial_ratio=int(task_snap["dial_ratio"]) if task_snap.get("dial_ratio") is not None else None,
            dial_intensity=task_snap.get("dial_intensity"),
            abandon_rate_limit=task_snap.get("abandon_rate_limit"),
            task_id=int(task_snap["id"]),
        )
        # Pass a lightweight namespace so strategies can still read attributes.
        task_ns = type("TaskSnap", (), task_snap)()
        slots = await strategy.compute_slots(task_ns, ctx)
        slots = max(0, slots)
        return PacingResolution(
            claim_limit=min(batch_size, slots),
            queue_capacity=queue_in_flight + slots,
        )

    async def resolve_claim_limit(self, task_snap: dict, *, batch_size: int) -> int:
        """Backward-compatible integer-only pacing API."""
        resolution = await self.resolve(task_snap, batch_size=batch_size)
        return resolution.claim_limit
