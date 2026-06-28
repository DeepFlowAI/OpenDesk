"""
Reception event service.

Records structured reception events at runtime ownership changes so the post-end
reception-segment generation has an agent-id-accurate fact source. Runtime code
only logs events here; segments are generated after the conversation ends.
"""
import logging

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ReceptionEventType
from app.models.conversation_reception_event import ConversationReceptionEvent
from app.repositories.reception_event_repository import ReceptionEventRepository

logger = logging.getLogger(__name__)

# Event types that hand ownership to ``to_agent_id`` and therefore open a new
# reception segment; used for the no-op dedupe below.
_OWNERSHIP_GRANT_TYPES = {
    ReceptionEventType.ASSIGNED.value,
    ReceptionEventType.TRANSFERRED.value,
}


class ReceptionEventService:

    @staticmethod
    async def record(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        event_type: str,
        occurred_at: datetime,
        agent_id: int | None = None,
        group_id: int | None = None,
        from_agent_id: int | None = None,
        to_agent_id: int | None = None,
        reason: str | None = None,
    ) -> ConversationReceptionEvent | None:
        """Record one reception event in the caller's transaction (flush, no commit).

        Ownership-grant events (``assigned`` / ``transferred``) are de-duplicated:
        when the conversation's latest event already grants ownership to the same
        ``to_agent_id``, no new event is written (mirrors the agent-assigned system
        message dedupe so retries don't spawn duplicate segments).
        """
        if event_type in _OWNERSHIP_GRANT_TYPES and to_agent_id is not None:
            latest = await ReceptionEventRepository.get_latest(db, conversation_id)
            if (
                latest is not None
                and latest.event_type in _OWNERSHIP_GRANT_TYPES
                and latest.to_agent_id == to_agent_id
            ):
                return None

        return await ReceptionEventRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "event_type": event_type,
                "reason": reason,
                "occurred_at": occurred_at,
                "agent_id": agent_id,
                "group_id": group_id,
                "from_agent_id": from_agent_id,
                "to_agent_id": to_agent_id,
            },
        )
