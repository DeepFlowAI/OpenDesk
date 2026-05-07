"""
TicketChange repository — data access for ticket update audit records.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket_change import TicketChange


class TicketChangeRepository:

    @staticmethod
    async def create_many(
        db: AsyncSession,
        rows: list[dict],
        commit: bool = True,
    ) -> list[TicketChange]:
        if not rows:
            return []
        changes = [TicketChange(**row) for row in rows]
        db.add_all(changes)
        if commit:
            await db.commit()
            for change in changes:
                await db.refresh(change)
        else:
            await db.flush()
        return changes

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        ticket_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[TicketChange], int]:
        count_q = (
            select(func.count())
            .select_from(TicketChange)
            .where(TicketChange.tenant_id == tenant_id, TicketChange.ticket_id == ticket_id)
        )
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        data_q = (
            select(TicketChange)
            .where(TicketChange.tenant_id == tenant_id, TicketChange.ticket_id == ticket_id)
            .order_by(TicketChange.created_at.desc(), TicketChange.id.desc())
            .offset(offset)
            .limit(per_page)
        )
        rows = (await db.execute(data_q)).scalars().all()
        return list(rows), total
