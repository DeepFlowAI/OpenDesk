"""
Conversation repository
"""
from datetime import datetime, timezone

from sqlalchemy import select, func, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.enums import ConversationStatus
from app.models.conversation import Conversation


class ConversationRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, conversation_id: int) -> Conversation | None:
        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_by_agent(
        db: AsyncSession, tenant_id: int, agent_id: int
    ) -> list[Conversation]:
        """Get all active (non-closed) conversations for an agent, sorted by last message."""
        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.agent_id == agent_id,
                Conversation.status.in_([ConversationStatus.ACTIVE.value, ConversationStatus.QUEUED.value]),
            )
            .order_by(Conversation.last_message_at.desc().nullslast())
        )
        return list(result.scalars().all())

    @staticmethod
    async def count_active_by_agent(db: AsyncSession, tenant_id: int, agent_id: int) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.agent_id == agent_id,
                Conversation.status == ConversationStatus.ACTIVE.value,
            )
        )
        return result.scalar_one()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Conversation:
        item = Conversation(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item, attribute_names=["visitor", "agent", "channel", "group"])
        return item

    @staticmethod
    async def end_conversation(
        db: AsyncSession, conversation: Conversation, ended_by: str
    ) -> Conversation:
        conversation.status = ConversationStatus.CLOSED.value
        conversation.ended_at = datetime.now(timezone.utc)
        conversation.ended_by = ended_by
        await db.commit()
        await db.refresh(conversation)
        return conversation

    @staticmethod
    async def assign_agent(
        db: AsyncSession, conversation: Conversation, agent_id: int, group_id: int | None
    ) -> Conversation:
        conversation.agent_id = agent_id
        conversation.group_id = group_id
        conversation.status = ConversationStatus.ACTIVE.value
        conversation.started_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(conversation, attribute_names=["visitor", "agent", "channel", "group"])
        return conversation

    @staticmethod
    async def update_last_message(
        db: AsyncSession,
        conversation_id: int,
        preview: str,
        timestamp: datetime,
        increment_unread: bool = False,
    ) -> None:
        values: dict = {
            "last_message_at": timestamp,
            "last_message_preview": preview[:200] if preview else None,
        }
        if increment_unread:
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(
                    **values,
                    unread_count=Conversation.unread_count + 1,
                )
            )
        else:
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(**values)
            )
        await db.commit()

    @staticmethod
    async def reset_unread(db: AsyncSession, conversation_id: int) -> None:
        await db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(unread_count=0)
        )
        await db.commit()

    @staticmethod
    async def get_queued_by_tenant(
        db: AsyncSession, tenant_id: int, limit: int = 50
    ) -> list[Conversation]:
        """Get unassigned queued conversations for a tenant, oldest first."""
        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.status == ConversationStatus.QUEUED.value,
                Conversation.agent_id.is_(None),
            )
            .order_by(Conversation.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_active_visitor_conversation(
        db: AsyncSession, tenant_id: int, visitor_id: int
    ) -> Conversation | None:
        """Check if visitor already has an active conversation."""
        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.visitor_id == visitor_id,
                Conversation.status.in_([ConversationStatus.ACTIVE.value, ConversationStatus.QUEUED.value]),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_visitor_history(
        db: AsyncSession,
        tenant_id: int,
        channel_id: int | None,
        visitor_id: int,
        *,
        current_conversation_id: int | None = None,
        before_id: int | None = None,
        agent_id: int | None = None,
        limit: int = 10,
    ) -> list[Conversation]:
        """Get visitor conversations, newest first."""
        sort_expr = func.coalesce(Conversation.started_at, Conversation.created_at)
        conditions = [
            Conversation.tenant_id == tenant_id,
            Conversation.visitor_id == visitor_id,
        ]
        if channel_id is not None:
            conditions.append(Conversation.channel_id == channel_id)
        if agent_id is not None:
            conditions.append(Conversation.agent_id == agent_id)

        if current_conversation_id is not None:
            conditions.append(Conversation.id != current_conversation_id)

        if before_id is not None:
            cursor = await db.get(Conversation, before_id)
            if cursor:
                cursor_sort = cursor.started_at or cursor.created_at
                conditions.append(
                    or_(
                        sort_expr < cursor_sort,
                        and_(sort_expr == cursor_sort, Conversation.id < cursor.id),
                    )
                )

        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
            )
            .where(*conditions)
            .order_by(sort_expr.desc(), Conversation.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
