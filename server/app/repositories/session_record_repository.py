"""
Session record repository — read-only queries for historical conversation data
"""
from datetime import datetime

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.conversation import Conversation
from app.models.user import User
from app.models.message import Message
from app.models.satisfaction_survey_record import SatisfactionSurveyRecord
from app.repositories.satisfaction_survey_record_repository import SatisfactionSurveyRecordRepository


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
        satisfaction_statuses: list[str] | None = None,
        current_satisfaction_version: int | None = None,
        satisfaction_resolved: list[str] | None = None,
        service_rating_options: list[str] | None = None,
        service_labels: list[str] | None = None,
        product_rating_options: list[str] | None = None,
        product_labels: list[str] | None = None,
        scope_predicate: ColumnElement | None = None,
    ) -> tuple[list[Conversation], int]:
        """Paginated list of conversations with optional filters."""
        base_filter = [Conversation.tenant_id == tenant_id]
        if scope_predicate is not None:
            base_filter.append(scope_predicate)

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
                    Conversation.visitor.has(User.public_id.ilike(kw)),
                    Conversation.visitor.has(User.name.ilike(kw)),
                    Conversation.share_code.ilike(kw),
                    Conversation.public_id.ilike(kw),
                )
            )

        filters = SatisfactionSurveyRecordRepository.apply_filters(
            base_filter,
            statuses=satisfaction_statuses,
            current_version=current_satisfaction_version,
            resolved=satisfaction_resolved,
            service_options=service_rating_options,
            service_labels=service_labels,
            product_options=product_rating_options,
            product_labels=product_labels,
        )

        count_q = (
            select(func.count())
            .select_from(Conversation)
            .outerjoin(SatisfactionSurveyRecord, SatisfactionSurveyRecord.conversation_id == Conversation.id)
            .where(*filters)
        )
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        data_q = (
            select(Conversation)
            .outerjoin(SatisfactionSurveyRecord, SatisfactionSurveyRecord.conversation_id == Conversation.id)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(*filters)
            .order_by(func.coalesce(Conversation.started_at, Conversation.created_at).desc().nullslast())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(data_q)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int | None = None,
    ) -> Conversation | None:
        filters = [Conversation.id == conversation_id]
        if tenant_id is not None:
            filters.append(Conversation.tenant_id == tenant_id)

        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(*filters)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_messages(
        db: AsyncSession,
        conversation_id: int,
        after_id: int | None = None,
        limit: int = 20,
    ) -> list[Message]:
        """Fetch messages in chronological order with forward ID pagination."""
        query = select(Message).where(Message.conversation_id == conversation_id)
        if after_id is not None:
            query = query.where(Message.id > after_id)
        query = query.order_by(Message.id.asc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())
