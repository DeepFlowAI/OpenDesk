"""
Agent status service — manages agent online status via Redis.

Status is stored in Redis (not DB) for high-frequency reads/writes.

Disconnect grace window:
    A Socket.IO disconnect does not immediately flip the agent to offline.
    Instead, ``schedule_disconnect`` writes a ``pending_offline_until``
    timestamp and the caller schedules ``finalize_disconnect_if_stale`` to
    run after the grace window. A successful reconnect (``mark_connected``)
    clears the pending marker and restores the agent's desired status.
    ``get_status`` additionally treats an expired pending marker as offline
    so the state self-heals if the scheduled task is lost (e.g. worker restart).
    Once the grace window is finalized, the desired status is also reset to
    offline so a later login does not implicitly put the agent back online.
"""
import logging
import time

import redis.asyncio as aioredis

from app.configs.settings import settings
from app.enums import AgentOnlineStatus

logger = logging.getLogger(__name__)

_STATUS_KEY = "agent:status:{tenant_id}:{user_id}"
_ASSIGN_COUNTER_KEY = "agent:assign_counter:{tenant_id}:{group_id}"
_CONNECTION_SID_FIELD = "connection_sid"
_DESIRED_STATUS_FIELD = "desired_status"
_PENDING_OFFLINE_FIELD = "pending_offline_until"


class AgentStatusService:

    @staticmethod
    def _key(tenant_id: int, user_id: int) -> str:
        return _STATUS_KEY.format(tenant_id=tenant_id, user_id=user_id)

    @staticmethod
    async def get_status(
        r: aioredis.Redis, tenant_id: int, user_id: int, max_concurrent: int = 10
    ) -> dict:
        key = AgentStatusService._key(tenant_id, user_id)
        data = await r.hgetall(key)
        if not data:
            return {
                "user_id": user_id,
                "status": AgentOnlineStatus.OFFLINE.value,
                "current_count": 0,
                "max_concurrent": max_concurrent,
            }
        status = data.get("status", AgentOnlineStatus.OFFLINE.value)
        # Self-heal: if a pending offline marker is past due, surface offline
        # immediately even if the finalize task never ran (e.g. worker crash).
        pending = data.get(_PENDING_OFFLINE_FIELD)
        if pending:
            try:
                if time.time() >= float(pending):
                    status = AgentOnlineStatus.OFFLINE.value
            except ValueError:
                pass
        return {
            "user_id": user_id,
            "status": status,
            "current_count": int(data.get("current_count", 0)),
            "max_concurrent": max_concurrent,
        }

    @staticmethod
    async def get_statuses_bulk(
        r: aioredis.Redis,
        tenant_id: int,
        users: list[tuple[int, int]],
    ) -> dict[int, dict]:
        """Fetch statuses for many agents in a single Redis round-trip.

        Each ``users`` entry is ``(user_id, max_concurrent)``. Returns a dict
        keyed by ``user_id`` with the same payload shape as ``get_status``.

        Same self-heal semantics as ``get_status``: an expired
        ``pending_offline_until`` marker surfaces as ``offline``. Per-user
        Redis errors do not abort the batch — affected users get ``offline``.
        """
        if not users:
            return {}

        # Pipeline (non-transactional) is enough: we only read, no atomicity
        # required across keys.
        async with r.pipeline(transaction=False) as pipe:
            for uid, _max in users:
                pipe.hgetall(AgentStatusService._key(tenant_id, uid))
            try:
                raw = await pipe.execute()
            except Exception:
                # If the entire pipeline fails (e.g. Redis down), surface every
                # caller as "offline" rather than raising — keeps the monitor
                # page usable during transient Redis outages.
                return {
                    uid: {
                        "user_id": uid,
                        "status": AgentOnlineStatus.OFFLINE.value,
                        "current_count": 0,
                        "max_concurrent": max_c,
                    }
                    for uid, max_c in users
                }

        now = time.time()
        result: dict[int, dict] = {}
        for (uid, max_c), data in zip(users, raw):
            if not data:
                result[uid] = {
                    "user_id": uid,
                    "status": AgentOnlineStatus.OFFLINE.value,
                    "current_count": 0,
                    "max_concurrent": max_c,
                }
                continue
            status = data.get("status", AgentOnlineStatus.OFFLINE.value)
            pending = data.get(_PENDING_OFFLINE_FIELD)
            if pending:
                try:
                    if now >= float(pending):
                        status = AgentOnlineStatus.OFFLINE.value
                except ValueError:
                    pass
            result[uid] = {
                "user_id": uid,
                "status": status,
                "current_count": int(data.get("current_count", 0)),
                "max_concurrent": max_c,
            }
        return result

    @staticmethod
    async def set_status(
        r: aioredis.Redis,
        tenant_id: int,
        user_id: int,
        status: str,
        current_count: int | None = None,
    ) -> None:
        key = AgentStatusService._key(tenant_id, user_id)
        mapping = {
            "status": status,
            _DESIRED_STATUS_FIELD: status,
        }
        if current_count is not None:
            mapping["current_count"] = max(0, current_count)
        await r.hset(
            key,
            mapping=mapping,
        )
        await r.hdel(key, _PENDING_OFFLINE_FIELD)
        if current_count is not None:
            await AgentStatusService._notify_stats_changed(r, tenant_id, user_id)
        logger.info("Agent %d status -> %s", user_id, status)

    @staticmethod
    async def mark_connected(
        r: aioredis.Redis, tenant_id: int, user_id: int, sid: str
    ) -> None:
        key = AgentStatusService._key(tenant_id, user_id)
        data = await r.hgetall(key)
        pending = data.get(_PENDING_OFFLINE_FIELD)
        pending_expired = False
        if pending:
            try:
                pending_expired = time.time() >= float(pending)
            except ValueError:
                pending_expired = False

        if pending_expired:
            desired_status = AgentOnlineStatus.OFFLINE.value
        else:
            desired_status = (
                data.get(_DESIRED_STATUS_FIELD)
                or data.get("status")
                or AgentOnlineStatus.OFFLINE.value
            )
        if desired_status not in [s.value for s in AgentOnlineStatus]:
            desired_status = AgentOnlineStatus.OFFLINE.value
        await r.hset(
            key,
            mapping={
                "status": desired_status,
                _CONNECTION_SID_FIELD: sid,
            },
        )
        # Cancel any pending offline transition from a prior disconnect.
        await r.hdel(key, _PENDING_OFFLINE_FIELD)
        logger.info(
            "Agent %d connected sid -> %s status -> %s",
            user_id,
            sid,
            desired_status,
        )

    @staticmethod
    async def schedule_disconnect(
        r: aioredis.Redis,
        tenant_id: int,
        user_id: int,
        sid: str,
        grace_seconds: int | None = None,
    ) -> bool:
        """Mark the agent as pending-offline without flipping status yet.

        Returns True when the marker was written (meaning ``sid`` is still the
        active connection and the caller should schedule a finalize task).
        Returns False when the disconnect is stale (a newer connection exists)
        and should be ignored.
        """
        key = AgentStatusService._key(tenant_id, user_id)
        grace = grace_seconds if grace_seconds is not None else settings.AGENT_OFFLINE_GRACE_SECONDS
        expires_at = time.time() + max(0, grace)
        script = """
        if redis.call('HGET', KEYS[1], ARGV[1]) == ARGV[2] then
            if redis.call('HEXISTS', KEYS[1], ARGV[3]) == 0 then
                local current_status = redis.call('HGET', KEYS[1], 'status') or ARGV[6]
                redis.call('HSET', KEYS[1], ARGV[3], current_status)
            end
            redis.call('HSET', KEYS[1], ARGV[4], ARGV[5])
            return 1
        end
        return 0
        """
        scheduled = await r.eval(
            script,
            1,
            key,
            _CONNECTION_SID_FIELD,
            sid,
            _DESIRED_STATUS_FIELD,
            _PENDING_OFFLINE_FIELD,
            str(expires_at),
            AgentOnlineStatus.OFFLINE.value,
        )
        if scheduled:
            logger.info(
                "Agent %d disconnect scheduled (grace=%ss) sid=%s",
                user_id,
                grace,
                sid,
            )
        else:
            logger.info("Ignored stale disconnect for agent %d sid=%s", user_id, sid)
        return bool(scheduled)

    @staticmethod
    async def finalize_disconnect_if_stale(
        r: aioredis.Redis, tenant_id: int, user_id: int, sid: str
    ) -> bool:
        """Flip the agent to offline iff it is still the same disconnected sid.

        A successful reconnect clears ``pending_offline_until`` and overwrites
        ``connection_sid``, so this Lua script will simply no-op in that case.
        """
        key = AgentStatusService._key(tenant_id, user_id)
        script = """
        if redis.call('HGET', KEYS[1], ARGV[1]) == ARGV[2]
           and redis.call('HEXISTS', KEYS[1], ARGV[3]) == 1 then
            redis.call('HDEL', KEYS[1], ARGV[1], ARGV[3])
            redis.call('HSET', KEYS[1], 'status', ARGV[4])
            redis.call('HSET', KEYS[1], ARGV[5], ARGV[4])
            return 1
        end
        return 0
        """
        changed = await r.eval(
            script,
            1,
            key,
            _CONNECTION_SID_FIELD,
            sid,
            _PENDING_OFFLINE_FIELD,
            AgentOnlineStatus.OFFLINE.value,
            _DESIRED_STATUS_FIELD,
        )
        if changed:
            logger.info("Agent %d finalized offline sid=%s", user_id, sid)
        else:
            logger.info(
                "Skipped offline finalize for agent %d sid=%s (reconnected or already cleared)",
                user_id,
                sid,
            )
        return bool(changed)

    @staticmethod
    async def _notify_stats_changed(
        r: aioredis.Redis, tenant_id: int, user_id: int
    ) -> None:
        """Best-effort push of updated stats via WebSocket after count change."""
        from app.services.agent_realtime_service import AgentRealtimeService

        await AgentRealtimeService.emit_stats_updated(r, tenant_id, user_id)

    @staticmethod
    async def set_count(r: aioredis.Redis, tenant_id: int, user_id: int, count: int) -> None:
        key = AgentStatusService._key(tenant_id, user_id)
        await r.hset(key, "current_count", max(0, count))
        await AgentStatusService._notify_stats_changed(r, tenant_id, user_id)

    @staticmethod
    async def increment_count(r: aioredis.Redis, tenant_id: int, user_id: int) -> int:
        key = AgentStatusService._key(tenant_id, user_id)
        val = await r.hincrby(key, "current_count", 1)
        await AgentStatusService._notify_stats_changed(r, tenant_id, user_id)
        return val

    @staticmethod
    async def decrement_count(r: aioredis.Redis, tenant_id: int, user_id: int) -> int:
        key = AgentStatusService._key(tenant_id, user_id)
        val = await r.hincrby(key, "current_count", -1)
        if val < 0:
            await r.hset(key, "current_count", 0)
            val = 0
        await AgentStatusService._notify_stats_changed(r, tenant_id, user_id)
        return val

    @staticmethod
    async def trigger_queue_backfill(
        r: aioredis.Redis, tenant_id: int, user_id: int
    ) -> None:
        """Pull queued conversations to an agent that just gained capacity.

        Safe to call on any capacity-gain event (agent goes online, a
        conversation ends, a conversation is transferred away, max-concurrent
        raised). The pull routine itself skips offline or already-full agents,
        so callers do not need to pre-check status.
        """
        try:
            from app.libs.realtime import get_realtime_transport
            from app.socketio import chat_handlers

            rt = get_realtime_transport()
            await chat_handlers._assign_queued_conversations(rt, r, tenant_id, user_id)
        except Exception:
            logger.exception(
                "Failed to backfill queued conversations for agent %s", user_id
            )

    @staticmethod
    async def find_available_agent(
        r: aioredis.Redis,
        tenant_id: int,
        group_member_ids: list[int],
        max_concurrent_map: dict[int, int],
    ) -> int | None:
        """Round-robin find an online agent with capacity in the group.

        Returns agent user_id or None if no one is available.
        """
        count = len(group_member_ids)
        if count == 0:
            return None

        # Try each member starting from a rotating offset
        counter_key = _ASSIGN_COUNTER_KEY.format(tenant_id=tenant_id, group_id="all")
        idx = await r.incr(counter_key)

        for i in range(count):
            uid = group_member_ids[(idx + i) % count]
            status_data = await AgentStatusService.get_status(
                r, tenant_id, uid, max_concurrent_map.get(uid, 10)
            )
            if (
                status_data["status"] == AgentOnlineStatus.ONLINE.value
                and status_data["current_count"] < status_data["max_concurrent"]
            ):
                return uid
        return None

    @staticmethod
    async def update_own_max_concurrent(
        db,
        r: aioredis.Redis,
        tenant_id: int,
        user_id: int,
        max_concurrent: int,
    ) -> dict:
        """Update the current agent's max_concurrent and refresh reception stats."""
        from app.core.exceptions import NotFoundError
        from app.repositories.employee_repository import EmployeeRepository
        from app.services.agent_realtime_service import AgentRealtimeService

        employee = await EmployeeRepository.get_by_id(db, user_id)
        if not employee or employee.tenant_id != tenant_id:
            raise NotFoundError("Employee not found")

        await EmployeeRepository.update(db, employee, {"max_concurrent": max_concurrent})
        status = await AgentStatusService.get_status(r, tenant_id, user_id, max_concurrent)
        stats = {
            "current_count": status["current_count"],
            "max_concurrent": max_concurrent,
        }
        await AgentRealtimeService.emit_stats_updated(r, tenant_id, user_id)

        if (
            status["status"] == AgentOnlineStatus.ONLINE.value
            and status["current_count"] < max_concurrent
        ):
            await AgentStatusService.trigger_queue_backfill(r, tenant_id, user_id)

        return stats
