"""
TicketComment repository — data access for ticket comment thread.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket_comment import TicketComment


class TicketCommentRepository:

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> TicketComment:
        item = TicketComment(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        ticket_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[TicketComment], int]:
        count_q = (
            select(func.count())
            .select_from(TicketComment)
            .where(
                TicketComment.tenant_id == tenant_id,
                TicketComment.ticket_id == ticket_id,
            )
        )
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        data_q = (
            select(TicketComment)
            .where(
                TicketComment.tenant_id == tenant_id,
                TicketComment.ticket_id == ticket_id,
            )
            .order_by(TicketComment.created_at.desc(), TicketComment.id.desc())
            .offset(offset)
            .limit(per_page)
        )
        rows = (await db.execute(data_q)).scalars().all()
        return list(rows), total
