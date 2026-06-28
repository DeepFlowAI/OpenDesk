"""
Reception event repository — data access for ``conversation_reception_events``.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_reception_event import ConversationReceptionEvent


class ReceptionEventRepository:

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> ConversationReceptionEvent:
        """Insert one reception event. Flushes but does not commit."""
        item = ConversationReceptionEvent(**data)
        db.add(item)
        await db.flush()
        return item

    @staticmethod
    async def get_latest(
        db: AsyncSession, conversation_id: int
    ) -> ConversationReceptionEvent | None:
        """Latest reception event of a conversation by event time (then id)."""
        result = await db.execute(
            select(ConversationReceptionEvent)
            .where(ConversationReceptionEvent.conversation_id == conversation_id)
            .order_by(
                ConversationReceptionEvent.occurred_at.desc(),
                ConversationReceptionEvent.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def has_events(db: AsyncSession, conversation_id: int) -> bool:
        """Whether a conversation has any reception event yet."""
        result = await db.execute(
            select(ConversationReceptionEvent.id)
            .where(ConversationReceptionEvent.conversation_id == conversation_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def list_for_conversation(
        db: AsyncSession, conversation_id: int
    ) -> list[ConversationReceptionEvent]:
        """All reception events of a conversation in chronological order."""
        result = await db.execute(
            select(ConversationReceptionEvent)
            .where(ConversationReceptionEvent.conversation_id == conversation_id)
            .order_by(
                ConversationReceptionEvent.occurred_at.asc(),
                ConversationReceptionEvent.id.asc(),
            )
        )
        return list(result.scalars().all())
