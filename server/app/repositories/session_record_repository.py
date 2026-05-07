"""
Session record repository — read-only queries for historical conversation data
"""
from datetime import datetime

from sqlalchemy import select, func, or_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation
from app.models.user import User
from app.models.message import Message


class SessionRecordRepository:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        agent_id: int | None = None,
        visitor_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        keyword: str | None = None,
    ) -> tuple[list[Conversation], int]:
        """Paginated list of conversations with optional filters."""
        base_filter = [Conversation.tenant_id == tenant_id]

        if agent_id is not None:
            base_filter.append(Conversation.agent_id == agent_id)

        if visitor_id is not None:
            base_filter.append(Conversation.visitor_id == visitor_id)

        if start_date is not None:
            base_filter.append(Conversation.started_at >= start_date)

        if end_date is not None:
            base_filter.append(Conversation.started_at <= end_date)

        if keyword:
            kw = f"%{keyword}%"
            base_filter.append(
                or_(
                    Conversation.visitor.has(User.name.ilike(kw)),
                    cast(Conversation.id, String).ilike(kw),
                )
            )

        count_q = select(func.count()).select_from(Conversation).where(*base_filter)
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        data_q = (
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
            )
            .where(*base_filter)
            .order_by(func.coalesce(Conversation.started_at, Conversation.created_at).desc().nullslast())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(data_q)
        return list(result.scalars().all()), total

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
    async def get_messages(
        db: AsyncSession,
        conversation_id: int,
        after_id: int | None = None,
        limit: int = 20,
    ) -> list[Message]:
        """Fetch messages in chronological order with forward cursor pagination."""
        query = select(Message).where(Message.conversation_id == conversation_id)
        if after_id is not None:
            query = query.where(Message.id > after_id)
        query = query.order_by(Message.id.asc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())
