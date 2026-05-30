"""
Redis-backed real-time call-center agent resource state.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import WatchError

from app.core.exceptions import ConflictError, ValidationError


VISIBLE_STATUSES = {"ready", "busy", "break", "after_call_work", "offline"}
RESOURCE_STATES = {
    "idle",
    "reserved",
    "ringing",
    "in_call",
    "after_call_work",
    "unavailable",
}
ACTIVE_RESOURCE_STATES = {"reserved", "ringing", "in_call"}


class CcAgentResourceService:
    DEFAULT_OFFER_TTL_SEC = 30
    DEFAULT_OUTBOUND_TTL_SEC = 120

    @staticmethod
    def key(tenant_id: int, employee_id: int) -> str:
        return f"cc:agent:resource:{tenant_id}:{employee_id}"

    @staticmethod
    def queue_rr_key(tenant_id: int, group_id: int, channel: str = "call_center") -> str:
        return f"cc:queue:rr:{tenant_id}:group:{group_id}:{channel}"

    @staticmethod
    def offer_accept_lock_key(tenant_id: int, offer_id: str) -> str:
        return f"cc:offer:accept-lock:{tenant_id}:{offer_id}"

    @staticmethod
    def resource_for_visible(status: str) -> str:
        if status == "ready":
            return "idle"
        if status == "after_call_work":
            return "after_call_work"
        return "unavailable"

    @classmethod
    async def get_snapshot(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
    ) -> dict | None:
        raw = await r.hgetall(cls.key(tenant_id, employee_id))
        if not raw:
            return None
        snapshot = cls._snapshot_from_raw(employee_id, raw)
        if cls._is_expired(snapshot):
            reason = (
                "offer_expired"
                if snapshot.get("resource_state") == "ringing"
                else "reservation_expired"
            )
            snapshot = await cls.release(
                r,
                tenant_id,
                employee_id,
                reason=reason,
                expected_offer_id=snapshot.get("offer_id"),
                allow_in_call=False,
            )
        return snapshot

    @classmethod
    async def ensure_from_visible(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        visible_status: str,
    ) -> dict:
        key = cls.key(tenant_id, employee_id)
        for _ in range(3):
            async with r.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.hgetall(key)
                    if raw:
                        return cls._snapshot_from_raw(employee_id, raw)
                    mapping = cls._base_mapping(
                        visible_status=visible_status,
                        resource_state=cls.resource_for_visible(visible_status),
                    )
                    pipe.multi()
                    pipe.hset(key, mapping=mapping)
                    await pipe.execute()
                    return cls._snapshot_from_raw(employee_id, mapping)
                except WatchError:
                    continue
        raise ConflictError("Call-center resource state changed, please retry")

    @classmethod
    async def set_visible_status(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        status: str,
    ) -> dict:
        if status not in VISIBLE_STATUSES:
            raise ValidationError(f"Invalid status: {status}")

        key = cls.key(tenant_id, employee_id)
        for _ in range(3):
            async with r.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.hgetall(key)
                    current = cls._snapshot_from_raw(employee_id, raw) if raw else None
                    if current and current["resource_state"] in ACTIVE_RESOURCE_STATES:
                        if current["resource_state"] == "in_call" and status == "busy":
                            resource_state = "in_call"
                            mapping = cls._base_mapping(
                                visible_status="busy",
                                resource_state=resource_state,
                                current_call_id=current.get("current_call_id"),
                                direction=current.get("direction"),
                            )
                        else:
                            raise ConflictError("Current call resource is occupied")
                    else:
                        mapping = cls._base_mapping(
                            visible_status=status,
                            resource_state=cls.resource_for_visible(status),
                        )
                    pipe.multi()
                    pipe.hset(key, mapping=mapping)
                    await pipe.execute()
                    return cls._snapshot_from_raw(employee_id, mapping)
                except WatchError:
                    continue
        raise ConflictError("Call-center resource state changed, please retry")

    @classmethod
    async def reserve_inbound(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        *,
        call_id: str,
        offer_id: str,
        queue_id: int | None,
        ttl_seconds: float | None = None,
    ) -> dict | None:
        ttl = float(ttl_seconds or cls.DEFAULT_OFFER_TTL_SEC)
        return await cls._reserve(
            r,
            tenant_id,
            employee_id,
            call_id=call_id,
            offer_id=offer_id,
            queue_id=queue_id,
            direction="inbound",
            ttl_seconds=ttl,
            previous_visible_status=None,
            allow_non_ready=False,
        )

    @classmethod
    async def reserve_outbound(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        *,
        reservation_id: str,
        ttl_seconds: float | None = None,
    ) -> dict:
        ttl = float(ttl_seconds or cls.DEFAULT_OUTBOUND_TTL_SEC)
        reserved = await cls._reserve(
            r,
            tenant_id,
            employee_id,
            call_id=reservation_id,
            offer_id="",
            queue_id=None,
            direction="outbound",
            ttl_seconds=ttl,
            previous_visible_status=None,
            allow_non_ready=True,
        )
        if reserved is None:
            raise ConflictError("Current call resource is occupied")
        return reserved

    @classmethod
    async def bind_outbound_call(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        *,
        reservation_id: str,
        call_id: str,
        ttl_seconds: float | None = None,
    ) -> dict:
        ttl = float(ttl_seconds or cls.DEFAULT_OUTBOUND_TTL_SEC)
        key = cls.key(tenant_id, employee_id)
        for _ in range(3):
            async with r.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.hgetall(key)
                    current = cls._snapshot_from_raw(employee_id, raw) if raw else None
                    if not current or current.get("current_call_id") != reservation_id:
                        raise ConflictError("Outbound reservation expired")
                    mapping = cls._base_mapping(
                        visible_status="busy",
                        resource_state="ringing",
                        current_call_id=call_id,
                        direction="outbound",
                        reserved_until=cls._now_epoch() + ttl,
                        previous_visible_status=current.get("previous_visible_status"),
                    )
                    pipe.multi()
                    pipe.hset(key, mapping=mapping)
                    await pipe.execute()
                    return cls._snapshot_from_raw(employee_id, mapping)
                except WatchError:
                    continue
        raise ConflictError("Call-center resource state changed, please retry")

    @classmethod
    async def mark_ringing(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        *,
        offer_id: str,
        call_id: str,
        ttl_seconds: float | None = None,
    ) -> dict:
        ttl = float(ttl_seconds or cls.DEFAULT_OFFER_TTL_SEC)
        key = cls.key(tenant_id, employee_id)
        for _ in range(3):
            async with r.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.hgetall(key)
                    current = cls._snapshot_from_raw(employee_id, raw) if raw else None
                    if (
                        not current
                        or current.get("resource_state") != "reserved"
                        or current.get("offer_id") != offer_id
                        or current.get("current_call_id") != call_id
                        or cls._is_expired(current)
                    ):
                        raise ConflictError("Offer reservation expired")
                    mapping = cls._base_mapping(
                        visible_status="ready",
                        resource_state="ringing",
                        current_call_id=call_id,
                        offer_id=offer_id,
                        queue_id=current.get("queue_id"),
                        direction="inbound",
                        reserved_until=cls._now_epoch() + ttl,
                        last_assigned_at=current.get("last_assigned_at"),
                    )
                    pipe.multi()
                    pipe.hset(key, mapping=mapping)
                    await pipe.execute()
                    return cls._snapshot_from_raw(employee_id, mapping)
                except WatchError:
                    continue
        raise ConflictError("Call-center resource state changed, please retry")

    @classmethod
    async def validate_offer(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        *,
        offer_id: str,
    ) -> dict | None:
        snapshot = await cls.get_snapshot(r, tenant_id, employee_id)
        if not snapshot:
            return None
        if snapshot.get("offer_id") != offer_id:
            return None
        if snapshot.get("resource_state") not in {"reserved", "ringing"}:
            return None
        if cls._is_expired(snapshot):
            return None
        return snapshot

    @classmethod
    async def acquire_offer_accept_lock(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        offer_id: str,
        *,
        ttl_seconds: float | None = None,
    ) -> str | None:
        ttl = int(max(1, ttl_seconds or cls.DEFAULT_OFFER_TTL_SEC))
        token = uuid.uuid4().hex
        acquired = await r.set(
            cls.offer_accept_lock_key(tenant_id, offer_id),
            token,
            ex=ttl,
            nx=True,
        )
        return token if acquired else None

    @classmethod
    async def release_offer_accept_lock(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        offer_id: str,
        token: str,
    ) -> None:
        key = cls.offer_accept_lock_key(tenant_id, offer_id)
        for _ in range(3):
            async with r.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    current = await pipe.get(key)
                    if isinstance(current, bytes):
                        current = current.decode()
                    if current != token:
                        return
                    pipe.multi()
                    pipe.delete(key)
                    await pipe.execute()
                    return
                except WatchError:
                    continue

    @classmethod
    def accept_lock_ttl_seconds(cls, snapshot: dict) -> int:
        deadline = snapshot.get("reserved_until_epoch")
        if deadline is None:
            return cls.DEFAULT_OFFER_TTL_SEC
        remaining = float(deadline) - cls._now_epoch()
        return int(max(1, remaining + 5))

    @classmethod
    async def mark_in_call(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        *,
        call_id: str,
        direction: str,
        offer_id: str | None = None,
    ) -> dict:
        key = cls.key(tenant_id, employee_id)
        for _ in range(3):
            async with r.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.hgetall(key)
                    current = cls._snapshot_from_raw(employee_id, raw) if raw else None
                    if current is None:
                        raise ConflictError("Call resource not reserved")
                    if offer_id and current.get("offer_id") != offer_id:
                        raise ConflictError("Offer expired")
                    if current.get("resource_state") not in {"reserved", "ringing", "in_call"}:
                        raise ConflictError("Call resource not reserved")
                    mapping = cls._base_mapping(
                        visible_status="busy",
                        resource_state="in_call",
                        current_call_id=call_id,
                        direction=direction,
                        previous_visible_status=current.get("previous_visible_status"),
                    )
                    pipe.multi()
                    pipe.hset(key, mapping=mapping)
                    await pipe.execute()
                    return cls._snapshot_from_raw(employee_id, mapping)
                except WatchError:
                    continue
        raise ConflictError("Call-center resource state changed, please retry")

    @classmethod
    async def mark_after_call_work(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        *,
        call_id: str | None = None,
        reason: str = "call_hangup",
    ) -> dict:
        key = cls.key(tenant_id, employee_id)
        mapping = cls._base_mapping(
            visible_status="after_call_work",
            resource_state="after_call_work",
            last_released_at=cls._now_iso(),
            last_release_reason=reason,
        )
        if call_id:
            for _ in range(3):
                async with r.pipeline(transaction=True) as pipe:
                    try:
                        await pipe.watch(key)
                        raw = await pipe.hgetall(key)
                        current = cls._snapshot_from_raw(employee_id, raw) if raw else None
                        if current and current.get("current_call_id") not in {None, "", call_id}:
                            raise ConflictError("Call resource belongs to another call")
                        pipe.multi()
                        pipe.hset(key, mapping=mapping)
                        await pipe.execute()
                        return cls._snapshot_from_raw(employee_id, mapping)
                    except WatchError:
                        continue
            raise ConflictError("Call-center resource state changed, please retry")
        await r.hset(key, mapping=mapping)
        return cls._snapshot_from_raw(employee_id, mapping)

    @classmethod
    async def release(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        *,
        reason: str,
        expected_offer_id: str | None = None,
        expected_call_id: str | None = None,
        allow_in_call: bool = False,
    ) -> dict:
        key = cls.key(tenant_id, employee_id)
        for _ in range(3):
            async with r.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.hgetall(key)
                    current = cls._snapshot_from_raw(employee_id, raw) if raw else None
                    if current is None:
                        visible_status = "offline"
                    else:
                        if expected_offer_id and current.get("offer_id") != expected_offer_id:
                            return current
                        if expected_call_id and current.get("current_call_id") != expected_call_id:
                            return current
                        if current.get("resource_state") == "in_call" and not allow_in_call:
                            return current
                        visible_status = cls._release_visible_status(current)
                    mapping = cls._base_mapping(
                        visible_status=visible_status,
                        resource_state=cls.resource_for_visible(visible_status),
                        last_released_at=cls._now_iso(),
                        last_release_reason=reason,
                    )
                    pipe.multi()
                    pipe.hset(key, mapping=mapping)
                    await pipe.execute()
                    return cls._snapshot_from_raw(employee_id, mapping)
                except WatchError:
                    continue
        raise ConflictError("Call-center resource state changed, please retry")

    @classmethod
    async def recover_from_sources(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        *,
        visible_status: str,
        active_call_id: str | None = None,
        active_call_direction: str | None = None,
        active_call_state: str | None = None,
        webrtc_state: str | None = None,
    ) -> dict:
        if active_call_id and active_call_state in {"in_progress", "answered"}:
            mapping = cls._base_mapping(
                visible_status="busy",
                resource_state="in_call",
                current_call_id=active_call_id,
                direction=active_call_direction,
            )
        elif active_call_id and active_call_state in {"ringing", "queued"}:
            mapping = cls._base_mapping(
                visible_status="busy",
                resource_state="ringing",
                current_call_id=active_call_id,
                direction=active_call_direction,
                reserved_until=cls._now_epoch() + cls.DEFAULT_OUTBOUND_TTL_SEC,
            )
        elif visible_status == "after_call_work":
            mapping = cls._base_mapping(
                visible_status="after_call_work",
                resource_state="after_call_work",
            )
        elif webrtc_state == "busy":
            mapping = cls._base_mapping(
                visible_status="busy",
                resource_state="unavailable",
            )
        else:
            mapping = cls._base_mapping(
                visible_status=visible_status,
                resource_state=cls.resource_for_visible(visible_status),
            )
        await r.hset(cls.key(tenant_id, employee_id), mapping=mapping)
        return cls._snapshot_from_raw(employee_id, mapping)

    @classmethod
    async def next_queue_index(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        group_id: int,
    ) -> int:
        value = await r.incr(cls.queue_rr_key(tenant_id, group_id))
        return int(value) - 1

    @classmethod
    async def _reserve(
        cls,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        *,
        call_id: str,
        offer_id: str,
        queue_id: int | None,
        direction: str,
        ttl_seconds: float,
        previous_visible_status: str | None,
        allow_non_ready: bool,
    ) -> dict | None:
        key = cls.key(tenant_id, employee_id)
        for _ in range(3):
            async with r.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.hgetall(key)
                    current = cls._snapshot_from_raw(employee_id, raw) if raw else None
                    visible = (current or {}).get("visible_status") or "ready"
                    resource = (current or {}).get("resource_state") or "idle"
                    if current and cls._is_expired(current):
                        resource = cls.resource_for_visible(visible)
                    if visible == "offline":
                        return None
                    if not allow_non_ready and visible != "ready":
                        return None
                    if resource in ACTIVE_RESOURCE_STATES and not (
                        current and cls._is_expired(current)
                    ):
                        return None
                    if resource not in {"idle", "after_call_work", "unavailable"}:
                        return None
                    if not allow_non_ready and resource != "idle":
                        return None
                    restore_visible = previous_visible_status or visible
                    mapping = cls._base_mapping(
                        visible_status="busy" if direction == "outbound" else visible,
                        resource_state="reserved",
                        current_call_id=call_id,
                        offer_id=offer_id,
                        queue_id=queue_id,
                        direction=direction,
                        reserved_until=cls._now_epoch() + ttl_seconds,
                        last_assigned_at=cls._now_iso(),
                        previous_visible_status=(
                            restore_visible if direction == "outbound" else None
                        ),
                    )
                    pipe.multi()
                    pipe.hset(key, mapping=mapping)
                    await pipe.execute()
                    return cls._snapshot_from_raw(employee_id, mapping)
                except WatchError:
                    continue
        raise ConflictError("Call-center resource state changed, please retry")

    @staticmethod
    def _release_visible_status(current: dict) -> str:
        if current.get("direction") == "outbound" and current.get("previous_visible_status"):
            return str(current["previous_visible_status"])
        visible = str(current.get("visible_status") or "offline")
        if visible == "busy":
            return "ready"
        return visible

    @staticmethod
    def _base_mapping(
        *,
        visible_status: str,
        resource_state: str,
        current_call_id: str | None = None,
        offer_id: str | None = None,
        queue_id: int | str | None = None,
        direction: str | None = None,
        reserved_until: float | str | None = None,
        last_assigned_at: str | None = None,
        last_released_at: str | None = None,
        last_release_reason: str | None = None,
        previous_visible_status: str | None = None,
    ) -> dict[str, str]:
        now = CcAgentResourceService._now_iso()
        return {
            "visible_status": visible_status,
            "resource_state": resource_state,
            "current_call_id": current_call_id or "",
            "offer_id": offer_id or "",
            "queue_id": str(queue_id) if queue_id is not None else "",
            "direction": direction or "",
            "reserved_until": str(reserved_until) if reserved_until is not None else "",
            "last_assigned_at": CcAgentResourceService._format_datetime(last_assigned_at),
            "last_released_at": CcAgentResourceService._format_datetime(last_released_at),
            "last_release_reason": last_release_reason or "",
            "previous_visible_status": previous_visible_status or "",
            "updated_at": now,
        }

    @staticmethod
    def _snapshot_from_raw(employee_id: int, raw: dict[str, Any]) -> dict:
        def val(name: str) -> str:
            value = raw.get(name, "")
            if isinstance(value, bytes):
                value = value.decode()
            return str(value or "")

        reserved_until_raw = val("reserved_until")
        reserved_until_epoch: float | None = None
        if reserved_until_raw:
            try:
                reserved_until_epoch = float(reserved_until_raw)
            except ValueError:
                reserved_until_epoch = None
        return {
            "employee_id": employee_id,
            "visible_status": val("visible_status") or "offline",
            "resource_state": val("resource_state") or "unavailable",
            "current_call_id": val("current_call_id") or None,
            "offer_id": val("offer_id") or None,
            "queue_id": int(val("queue_id")) if val("queue_id").isdigit() else None,
            "direction": val("direction") or None,
            "reserved_until_epoch": reserved_until_epoch,
            "reserved_until": (
                datetime.fromtimestamp(reserved_until_epoch, timezone.utc)
                if reserved_until_epoch is not None
                else None
            ),
            "last_assigned_at": CcAgentResourceService._parse_datetime(val("last_assigned_at")),
            "last_released_at": CcAgentResourceService._parse_datetime(val("last_released_at")),
            "last_release_reason": val("last_release_reason") or None,
            "previous_visible_status": val("previous_visible_status") or None,
            "resource_updated_at": CcAgentResourceService._parse_datetime(val("updated_at")),
        }

    @staticmethod
    def _is_expired(snapshot: dict) -> bool:
        state = snapshot.get("resource_state")
        deadline = snapshot.get("reserved_until_epoch")
        return (
            state in {"reserved", "ringing"}
            and deadline is not None
            and deadline <= CcAgentResourceService._now_epoch()
        )

    @staticmethod
    def _now_epoch() -> float:
        return datetime.now(timezone.utc).timestamp()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _format_datetime(value: str | datetime | None) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat()
        return value
