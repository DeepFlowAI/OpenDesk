"""
Reception segment repository — data access for ``conversation_reception_segments``.
"""
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_reception_segment import ConversationReceptionSegment


class ReceptionSegmentRepository:

    @staticmethod
    async def replace_for_conversation(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        rows: list[dict],
    ) -> None:
        """Rebuild all segment rows for a conversation (delete + insert). No commit."""
        await db.execute(
            delete(ConversationReceptionSegment).where(
                ConversationReceptionSegment.tenant_id == tenant_id,
                ConversationReceptionSegment.conversation_id == conversation_id,
            )
        )
        for row in rows:
            db.add(ConversationReceptionSegment(**row))
        await db.flush()

    @staticmethod
    async def list_for_conversation(
        db: AsyncSession, conversation_id: int
    ) -> list[ConversationReceptionSegment]:
        """All reception segments of a conversation ordered by sequence."""
        result = await db.execute(
            select(ConversationReceptionSegment)
            .where(ConversationReceptionSegment.conversation_id == conversation_id)
            .order_by(ConversationReceptionSegment.seq_no.asc())
        )
        return list(result.scalars().all())
