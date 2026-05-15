"""Realtime helpers for agent-facing Socket.IO events."""
import logging

import redis.asyncio as aioredis

from app.db.session import AsyncSessionLocal
from app.libs.realtime import get_realtime_transport
from app.repositories.employee_repository import EmployeeRepository

logger = logging.getLogger(__name__)

CHAT_NAMESPACE = "/chat"


class AgentRealtimeService:
    """Broadcast agent-specific realtime state updates."""

    @staticmethod
    async def emit_stats_updated(
        r: aioredis.Redis,
        tenant_id: int,
        user_id: int,
    ) -> None:
        """Push the latest reception stats to an agent's personal room.

        Called automatically by AgentStatusService after every count mutation.
        Uses lazy import to avoid circular dependency.
        """
        try:
            from app.services.agent_status_service import AgentStatusService

            async with AsyncSessionLocal() as db:
                user = await EmployeeRepository.get_by_id(db, user_id)
                max_concurrent = user.max_concurrent if user else 10

            stats = await AgentStatusService.get_status(
                r, tenant_id, user_id, max_concurrent
            )
            payload = {
                "current_count": stats["current_count"],
                "max_concurrent": stats["max_concurrent"],
            }
            rt = get_realtime_transport()
            agent_room = f"agent:{tenant_id}:{user_id}"
            await rt.emit(
                "agent_stats_updated",
                payload,
                room=agent_room,
                namespace=CHAT_NAMESPACE,
            )
        except Exception:
            logger.exception("Failed to emit stats update for agent %s", user_id)
