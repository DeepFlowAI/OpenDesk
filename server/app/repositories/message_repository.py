"""
Message repository
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.message import Message


class MessageRepository:

    @staticmethod
    async def get_by_conversation(
        db: AsyncSession,
        conversation_id: int,
        before_id: int | None = None,
        limit: int = 20,
    ) -> list[Message]:
        """Fetch messages for a conversation, paginated by cursor (before_id)."""
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
        )
        if before_id:
            query = query.where(Message.id < before_id)
        query = query.order_by(Message.id.desc()).limit(limit)
        result = await db.execute(query)
        items = list(result.scalars().all())
        items.reverse()  # return in chronological order
        return items

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Message:
        item = Message(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def count_by_conversation(db: AsyncSession, conversation_id: int) -> int:
        result = await db.execute(
            select(func.count()).select_from(Message).where(
                Message.conversation_id == conversation_id
            )
        )
        return result.scalar_one()

    @staticmethod
    async def get_recent_by_conversations(
        db: AsyncSession,
        tenant_id: int,
        conversation_ids: list[int],
        per_conversation_limit: int = 200,
    ) -> dict[int, list[Message]]:
        """Fetch recent messages for multiple conversations with a per-conversation cap."""
        if not conversation_ids:
            return {}

        row_number = func.row_number().over(
            partition_by=Message.conversation_id,
            order_by=Message.id.desc(),
        ).label("row_number")
        ranked = (
            select(Message, row_number)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id.in_(conversation_ids),
            )
            .subquery()
        )
        message_alias = aliased(Message, ranked)
        result = await db.execute(
            select(message_alias)
            .where(ranked.c.row_number <= per_conversation_limit)
            .order_by(message_alias.conversation_id.asc(), message_alias.id.asc())
        )

        grouped: dict[int, list[Message]] = {conversation_id: [] for conversation_id in conversation_ids}
        for message in result.scalars().all():
            grouped.setdefault(message.conversation_id, []).append(message)
        return grouped
