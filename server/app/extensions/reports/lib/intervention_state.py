"""Shared supervisor-monitoring state.

Two concerns live here:

1. **Monitor lock** — enforces "only one supervisor may monitor a given call at
   a time" and "a supervisor may only monitor one call at a time" (本期边界).
   Backed by Redis when available so the constraint holds across worker
   processes; falls back to an in-process registry for single-worker/dev/test
   runs without Redis.

"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from uuid import uuid4

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Redis key prefixes. A monitor lock records who is monitoring a call; the
# supervisor reverse index records which call a supervisor is monitoring; the
# leg index maps a supervisor's own WebRTC leg id back to its target call so a
# kernel-side ICE candidate (addressed by that leg id) can be routed to the
# right supervisor's browser.
_CALL_LOCK_PREFIX = "cc:monitor:call"
_SUPERVISOR_PREFIX = "cc:monitor:supervisor"
_SUPERVISOR_LEG_PREFIX = "cc:monitor:leg"
# Locks auto-expire so a crashed supervisor session never wedges a call. The
# frontend refreshes state on a 10s cadence, so a few minutes is ample.
_LOCK_TTL_SECONDS = 300
# The leg → target index outlives the monitor lock so late-arriving kernel ICE
# candidates still resolve during a full monitoring session.
_LEG_INDEX_TTL_SECONDS = 3 * 60 * 60

# In-process fallback used only when Redis is not configured.
_local_call_locks: dict[str, dict] = {}
_local_supervisor_calls: dict[str, str] = {}
_local_supervisor_legs: dict[str, str] = {}


@dataclass(frozen=True)
class MonitorHolder:
    """Who currently monitors a call, and in which mode.

    ``supervisor_call_id`` is the supervisor's own WebRTC media leg (negotiated
    when the supervisor first needs to be audible — whisper / barge / takeover).
    ``room_id`` is the mixing room that joins customer + agent + supervisor legs
    once a speaking mode is entered. Both are ``None`` for a plain one-way
    listen session, which needs no media leg or room.
    """

    supervisor_id: int
    name: str
    mode: str
    supervisor_call_id: str | None = None
    room_id: str | None = None


def _call_key(tenant_id: int, call_id: str) -> str:
    return f"{_CALL_LOCK_PREFIX}:{tenant_id}:{call_id}"


def _supervisor_key(tenant_id: int, supervisor_id: int) -> str:
    return f"{_SUPERVISOR_PREFIX}:{tenant_id}:{supervisor_id}"


def _supervisor_leg_key(supervisor_call_id: str) -> str:
    # The supervisor leg id is kernel-global, so the index is keyed by it alone;
    # the mapped value carries the tenant so the holder can be re-loaded.
    return f"{_SUPERVISOR_LEG_PREFIX}:{supervisor_call_id}"


async def get_call_holder(
    redis: aioredis.Redis | None, tenant_id: int, call_id: str
) -> MonitorHolder | None:
    """Return the supervisor monitoring ``call_id``, if any."""

    if redis is None:
        data = _local_call_locks.get(_call_key(tenant_id, call_id))
    else:
        raw = await redis.get(_call_key(tenant_id, call_id))
        data = json.loads(raw) if raw else None
    if not data:
        return None
    return MonitorHolder(
        supervisor_id=int(data["supervisor_id"]),
        name=str(data.get("name", "")),
        mode=str(data.get("mode", "listen")),
        supervisor_call_id=data.get("supervisor_call_id") or None,
        room_id=data.get("room_id") or None,
    )


async def get_holders_bulk(
    redis: aioredis.Redis | None, tenant_id: int, call_ids: list[str]
) -> dict[str, MonitorHolder]:
    """Batch lookup of monitor holders for a set of calls."""

    holders: dict[str, MonitorHolder] = {}
    for call_id in call_ids:
        holder = await get_call_holder(redis, tenant_id, call_id)
        if holder is not None:
            holders[call_id] = holder
    return holders


async def supervisor_busy_on(
    redis: aioredis.Redis | None, tenant_id: int, supervisor_id: int
) -> str | None:
    """The call a supervisor is currently monitoring, or ``None``."""

    if redis is None:
        return _local_supervisor_calls.get(_supervisor_key(tenant_id, supervisor_id))
    raw = await redis.get(_supervisor_key(tenant_id, supervisor_id))
    return raw if raw else None


async def acquire(
    redis: aioredis.Redis | None,
    tenant_id: int,
    call_id: str,
    holder: MonitorHolder,
) -> bool:
    """Claim monitoring of a call. Returns False if another supervisor holds it.

    Re-acquiring a call the same supervisor already holds is allowed and simply
    updates the recorded mode (e.g. listen → whisper) plus any media-leg / room
    ids carried on the holder.
    """

    existing = await get_call_holder(redis, tenant_id, call_id)
    if existing is not None and existing.supervisor_id != holder.supervisor_id:
        return False

    payload = {
        "supervisor_id": holder.supervisor_id,
        "name": holder.name,
        "mode": holder.mode,
        "supervisor_call_id": holder.supervisor_call_id,
        "room_id": holder.room_id,
    }
    if redis is None:
        _local_call_locks[_call_key(tenant_id, call_id)] = payload
        _local_supervisor_calls[_supervisor_key(tenant_id, holder.supervisor_id)] = call_id
        return True
    await redis.set(_call_key(tenant_id, call_id), json.dumps(payload), ex=_LOCK_TTL_SECONDS)
    await redis.set(_supervisor_key(tenant_id, holder.supervisor_id), call_id, ex=_LOCK_TTL_SECONDS)
    return True


async def release(
    redis: aioredis.Redis | None,
    tenant_id: int,
    call_id: str,
    supervisor_id: int,
) -> None:
    """Release monitoring of a call held by ``supervisor_id`` (idempotent)."""

    existing = await get_call_holder(redis, tenant_id, call_id)
    if existing is not None and existing.supervisor_id != supervisor_id:
        return
    if redis is None:
        _local_call_locks.pop(_call_key(tenant_id, call_id), None)
        _local_supervisor_calls.pop(_supervisor_key(tenant_id, supervisor_id), None)
        return
    await redis.delete(_call_key(tenant_id, call_id))
    await redis.delete(_supervisor_key(tenant_id, supervisor_id))


async def set_supervisor_leg_index(
    redis: aioredis.Redis | None,
    tenant_id: int,
    call_id: str,
    supervisor_call_id: str,
) -> None:
    """Index the supervisor's WebRTC leg id → its ``{tenant_id}:{call_id}`` target.

    Lets a kernel-side ICE candidate (addressed by the leg id) be routed to the
    supervisor monitoring that call.
    """

    value = f"{tenant_id}:{call_id}"
    if redis is None:
        _local_supervisor_legs[_supervisor_leg_key(supervisor_call_id)] = value
        return
    await redis.set(
        _supervisor_leg_key(supervisor_call_id), value, ex=_LEG_INDEX_TTL_SECONDS
    )


async def get_supervisor_leg_target(
    redis: aioredis.Redis | None, supervisor_call_id: str
) -> tuple[int, str] | None:
    """Return ``(tenant_id, call_id)`` for a supervisor leg id, or ``None``."""

    if redis is None:
        raw = _local_supervisor_legs.get(_supervisor_leg_key(supervisor_call_id))
    else:
        raw = await redis.get(_supervisor_leg_key(supervisor_call_id))
    if not raw:
        return None
    tenant_str, _, call_id = raw.partition(":")
    if not tenant_str or not call_id:
        return None
    return int(tenant_str), call_id


async def clear_supervisor_leg_index(
    redis: aioredis.Redis | None, supervisor_call_id: str
) -> None:
    """Drop the leg → target index for a torn-down supervisor leg (idempotent)."""

    if redis is None:
        _local_supervisor_legs.pop(_supervisor_leg_key(supervisor_call_id), None)
        return
    await redis.delete(_supervisor_leg_key(supervisor_call_id))


async def append_trail_event(
    db: AsyncSession,
    tenant_id: int,
    call_id: str,
    event: dict,
) -> None:
    """Persist a supervisor intervention as a structured trajectory event."""

    raw_event = str(event.get("event", ""))
    mode = str(event.get("mode", "listen"))
    suffix_by_event = {
        "initiated": "started",
        "started": "started",
        "succeeded": "completed" if mode in {"takeover", "force_hangup"} else None,
        "ended": "ended",
        "failed": "failed",
        "unsupported": "failed",
    }
    suffix = suffix_by_event.get(raw_event)
    if suffix is None:
        return

    from app.services.call_trajectory_service import CallTrajectoryService

    supervisor_id = int(event["supervisor_id"])
    await CallTrajectoryService.append_for_call_id(
        db,
        tenant_id=tenant_id,
        call_id=call_id,
        event_id=f"opendesk:supervisor:{uuid4().hex}",
        event_type=f"supervisor_{mode}_{suffix}",
        event_category="supervisor",
        actor_type="supervisor",
        actor_id=str(supervisor_id),
        source="opendesk",
        operation_id=f"supervisor:{call_id}:{supervisor_id}",
        result="failed" if suffix == "failed" else "succeeded",
        reason_code=event.get("reason"),
        reason_detail=event.get("detail"),
        details={"note": event["note"]} if event.get("note") else {},
    )
