"""
Composable dial-capacity planner for auto-outbound.

Actual dialable count is the minimum of every configured remaining quota.
A source that is not configured returns None and does not constrain the min.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.configs.settings import settings
from app.db.session import AsyncSessionLocal
from app.models.phone_number import PhoneNumber
from app.services.auto_outbound import frequency as freq
from app.services.auto_outbound.pacing import DefaultPacingResolver

logger = logging.getLogger(__name__)

SOURCE_TASK = "task"
SOURCE_TENANT = "tenant"
SOURCE_FLOWKIT = "flowkit"
SOURCE_TRUNK = "trunk"
SOURCE_BATCH = "batch"
SOURCE_RECEPTION = "reception"


@dataclass(frozen=True)
class CapacitySnapshot:
    remaining: int | None
    limit: int | None = None
    in_flight: int = 0


@dataclass(frozen=True)
class ConcurrencyLimits:
    task_id: int
    task_limit: int
    tenant_id: int
    tenant_limit: int | None
    trunk_key: str | None
    trunk_limit: int | None


@dataclass(frozen=True)
class DialCapacityPlan:
    dialable: int
    sources: dict[str, int | None] = field(default_factory=dict)
    limits: ConcurrencyLimits | None = None
    queue_capacity: int | None = None

    @property
    def claim_limit(self) -> int:
        return self.dialable

    def as_dict(self) -> dict[str, Any]:
        return {
            "dialable": self.dialable,
            "sources": dict(self.sources),
        }


class CapacitySource(Protocol):
    name: str

    async def snapshot(self, task_snap: dict, *, batch_size: int) -> CapacitySnapshot: ...


def _min_remaining(values: list[int | None]) -> int:
    constrained = [int(v) for v in values if v is not None]
    if not constrained:
        return 0
    return max(0, min(constrained))


class TaskCapacitySource:
    name = SOURCE_TASK

    def __init__(self, *, redis: Any | None = None) -> None:
        self._redis = redis

    async def snapshot(self, task_snap: dict, *, batch_size: int) -> CapacitySnapshot:
        limit = max(0, int(task_snap.get("max_concurrency") or 1))
        in_flight = await freq.get_concurrency(int(task_snap["id"]), redis=self._redis)
        return CapacitySnapshot(remaining=max(0, limit - in_flight), limit=limit, in_flight=in_flight)


class TenantCapacitySource:
    name = SOURCE_TENANT

    def __init__(self, *, redis: Any | None = None) -> None:
        self._redis = redis

    async def snapshot(self, task_snap: dict, *, batch_size: int) -> CapacitySnapshot:
        raw = getattr(settings, "AUTO_OUTBOUND_TENANT_MAX_CONCURRENCY", 0) or 0
        limit = int(raw)
        tenant_id = int(task_snap["tenant_id"])
        in_flight = await freq.get_tenant_concurrency(tenant_id, redis=self._redis)
        if limit <= 0:
            return CapacitySnapshot(remaining=None, limit=None, in_flight=in_flight)
        return CapacitySnapshot(remaining=max(0, limit - in_flight), limit=limit, in_flight=in_flight)


class FlowKitCapacitySource:
    name = SOURCE_FLOWKIT

    def __init__(self, *, telephony_factory=None) -> None:
        self._telephony_factory = telephony_factory

    async def snapshot(self, task_snap: dict, *, batch_size: int) -> CapacitySnapshot:
        if bool(settings.AUTO_OUTBOUND_SIMULATION_ENABLED):
            return CapacitySnapshot(remaining=None)
        try:
            if self._telephony_factory is not None:
                telephony = self._telephony_factory()
            else:
                from app.libs.telephony.factory import get_telephony_client

                telephony = get_telephony_client()
            probe = getattr(telephony, "originate_capacity", None)
            if probe is None:
                return CapacitySnapshot(remaining=None)
            data = await probe()
        except Exception:  # noqa: BLE001
            logger.warning("auto_outbound flowkit capacity probe failed", exc_info=True)
            return CapacitySnapshot(remaining=None)
        if not isinstance(data, dict):
            return CapacitySnapshot(remaining=None)
        remaining = data.get("originate_remaining")
        limit = data.get("originate_max_concurrent")
        in_flight = data.get("originate_in_flight")
        if remaining is None:
            return CapacitySnapshot(remaining=None)
        try:
            remaining_int = int(remaining)
        except (TypeError, ValueError):
            return CapacitySnapshot(remaining=None)
        if remaining_int < 0:
            return CapacitySnapshot(remaining=None)
        return CapacitySnapshot(
            remaining=remaining_int,
            limit=int(limit) if limit is not None else None,
            in_flight=int(in_flight or 0),
        )


class TrunkCapacitySource:
    name = SOURCE_TRUNK

    def __init__(self, *, redis: Any | None = None, session_factory=AsyncSessionLocal) -> None:
        self._redis = redis
        self._session_factory = session_factory

    async def snapshot(self, task_snap: dict, *, batch_size: int) -> CapacitySnapshot:
        caller_number_id = task_snap.get("caller_number_id")
        if not caller_number_id:
            return CapacitySnapshot(remaining=None)
        key = str(caller_number_id)
        in_flight = await freq.get_trunk_concurrency(key, redis=self._redis)
        limit = task_snap.get("caller_number_concurrency")
        if limit is None:
            async with self._session_factory() as db:
                number = await db.get(PhoneNumber, caller_number_id)
                limit = getattr(number, "concurrency", None) if number is not None else None
        if limit is None:
            return CapacitySnapshot(remaining=None, limit=None, in_flight=in_flight)
        try:
            limit_int = int(limit)
        except (TypeError, ValueError):
            return CapacitySnapshot(remaining=None, limit=None, in_flight=in_flight)
        if limit_int <= 0:
            return CapacitySnapshot(remaining=None, limit=None, in_flight=in_flight)
        return CapacitySnapshot(
            remaining=max(0, limit_int - in_flight),
            limit=limit_int,
            in_flight=in_flight,
        )


class BatchCapacitySource:
    name = SOURCE_BATCH

    async def snapshot(self, task_snap: dict, *, batch_size: int) -> CapacitySnapshot:
        limit = max(0, int(batch_size))
        return CapacitySnapshot(remaining=limit, limit=limit, in_flight=0)


class ReceptionCapacitySource:
    """Agent pacing or VoiceSpeed/IVR capacity. Unconfigured modes do not constrain."""

    name = SOURCE_RECEPTION

    def __init__(self, *, redis: Any | None = None) -> None:
        self._redis = redis
        self._pacing = DefaultPacingResolver(redis=redis)

    async def snapshot(self, task_snap: dict, *, batch_size: int) -> CapacitySnapshot:
        mode = task_snap.get("execution_mode")
        if mode != "agent":
            return CapacitySnapshot(remaining=None)
        slots = await self._pacing.resolve_claim_limit(task_snap, batch_size=batch_size)
        return CapacitySnapshot(remaining=max(0, int(slots)))


class DialCapacityPlanner:
    """
    Engine-facing resolver: min of every configured remaining quota.

    Implements the same ``resolve_claim_limit`` contract as DefaultPacingResolver.
    """

    def __init__(
        self,
        *,
        redis: Any | None = None,
        telephony_factory=None,
        sources: list[CapacitySource] | None = None,
    ) -> None:
        self._redis = redis
        self._sources = sources or [
            TaskCapacitySource(redis=redis),
            TenantCapacitySource(redis=redis),
            FlowKitCapacitySource(telephony_factory=telephony_factory),
            TrunkCapacitySource(redis=redis),
            BatchCapacitySource(),
            ReceptionCapacitySource(redis=redis),
        ]

    async def resolve(self, task_snap: dict, *, batch_size: int) -> DialCapacityPlan:
        remainings: dict[str, int | None] = {}
        task_limit = max(0, int(task_snap.get("max_concurrency") or 1))
        tenant_limit: int | None = None
        trunk_limit: int | None = None
        for source in self._sources:
            try:
                snap = await source.snapshot(task_snap, batch_size=batch_size)
            except Exception:  # noqa: BLE001
                logger.exception("auto_outbound capacity source failed name=%s", source.name)
                remainings[source.name] = None
                continue
            remainings[source.name] = snap.remaining
            if source.name == SOURCE_TASK and snap.limit is not None:
                task_limit = snap.limit
            elif source.name == SOURCE_TENANT:
                tenant_limit = snap.limit
            elif source.name == SOURCE_TRUNK:
                trunk_limit = snap.limit
        dialable = _min_remaining(list(remainings.values()))
        caller_number_id = task_snap.get("caller_number_id")
        queue_capacity: int | None = None
        if task_snap.get("execution_mode") == "agent":
            try:
                pacing = DefaultPacingResolver(redis=self._redis)
                resolution = await pacing.resolve(task_snap, batch_size=batch_size)
                queue_capacity = resolution.queue_capacity
            except Exception:  # noqa: BLE001
                logger.warning("auto_outbound pacing queue_capacity probe failed", exc_info=True)
        return DialCapacityPlan(
            dialable=dialable,
            sources=remainings,
            limits=ConcurrencyLimits(
                task_id=int(task_snap["id"]),
                task_limit=task_limit,
                tenant_id=int(task_snap["tenant_id"]),
                tenant_limit=tenant_limit,
                trunk_key=str(caller_number_id) if caller_number_id else None,
                trunk_limit=trunk_limit,
            ),
            queue_capacity=queue_capacity,
        )

    async def resolve_claim_limit(self, task_snap: dict, *, batch_size: int) -> int:
        plan = await self.resolve(task_snap, batch_size=batch_size)
        return plan.dialable
