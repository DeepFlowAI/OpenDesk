"""
Repository for workspace user statistic settings and count queries.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.call_record import CallRecord
from app.models.conversation import Conversation
from app.models.conversation_user_stat_setting import ConversationUserStatSetting
from app.models.ticket import Ticket


class ConversationUserStatRepository:
    @staticmethod
    async def get_settings_by_tenant(
        db: AsyncSession,
        tenant_id: int,
    ) -> ConversationUserStatSetting | None:
        q = select(ConversationUserStatSetting).where(ConversationUserStatSetting.tenant_id == tenant_id)
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def save_settings(
        db: AsyncSession,
        tenant_id: int,
        data: dict,
    ) -> ConversationUserStatSetting:
        row = await ConversationUserStatRepository.get_settings_by_tenant(db, tenant_id)
        if row:
            for key, value in data.items():
                setattr(row, key, value)
        else:
            row = ConversationUserStatSetting(tenant_id=tenant_id, **data)
            db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def count_sessions(
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        scope_predicate: ColumnElement | None = None,
    ) -> int:
        q = select(func.count()).select_from(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.visitor_id == user_id,
        )
        if scope_predicate is not None:
            q = q.where(scope_predicate)
        return int((await db.execute(q)).scalar_one())

    @staticmethod
    async def count_calls(
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        scope_predicate: ColumnElement | None = None,
    ) -> int:
        q = select(func.count()).select_from(CallRecord).where(
            CallRecord.tenant_id == tenant_id,
            CallRecord.user_id == user_id,
        )
        if scope_predicate is not None:
            q = q.where(scope_predicate)
        return int((await db.execute(q)).scalar_one())

    @staticmethod
    async def count_tickets(
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        *,
        unresolved_only: bool = False,
        scope_predicate: ColumnElement | None = None,
    ) -> int:
        q = select(func.count()).select_from(Ticket).where(
            Ticket.tenant_id == tenant_id,
            Ticket.user_id == user_id,
        )
        if unresolved_only:
            q = q.where(Ticket.status.notin_(("resolved", "closed")))
        if scope_predicate is not None:
            q = q.where(scope_predicate)
        return int((await db.execute(q)).scalar_one())
