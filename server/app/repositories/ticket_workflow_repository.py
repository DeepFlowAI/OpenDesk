"""
Ticket workflow repository.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from app.models.ticket_workflow import TicketWorkflow


class TicketWorkflowRepository:
    @staticmethod
    def _not_deleted_clause():
        return TicketWorkflow.deleted_at.is_(None)

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        keyword: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[list[TicketWorkflow], int]:
        q = select(TicketWorkflow).where(TicketWorkflow.tenant_id == tenant_id)
        if not include_deleted:
            q = q.where(TicketWorkflowRepository._not_deleted_clause())
        if keyword:
            q = q.where(TicketWorkflow.name.ilike(f"%{keyword}%"))

        count_q = select(func.count()).select_from(q.subquery())
        total = int((await db.execute(count_q)).scalar_one())
        offset = (page - 1) * per_page
        rows_q = q.order_by(TicketWorkflow.sort_order.asc(), TicketWorkflow.id.asc()).offset(offset).limit(per_page)
        rows = list((await db.execute(rows_q)).scalars().all())
        return rows, total

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        workflow_id: int,
        tenant_id: int,
        for_update: bool = False,
    ) -> TicketWorkflow | None:
        q = select(TicketWorkflow).where(
            TicketWorkflow.id == workflow_id,
            TicketWorkflow.tenant_id == tenant_id,
            TicketWorkflowRepository._not_deleted_clause(),
        )
        if for_update:
            q = q.options(lazyload(TicketWorkflow.current_version)).with_for_update(of=TicketWorkflow)
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def get_max_sort_order(db: AsyncSession, tenant_id: int) -> int:
        q = select(func.coalesce(func.max(TicketWorkflow.sort_order), 0)).where(
            TicketWorkflow.tenant_id == tenant_id,
            TicketWorkflowRepository._not_deleted_clause(),
        )
        return int((await db.execute(q)).scalar_one() or 0)

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> TicketWorkflow:
        row = TicketWorkflow(**data)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def update(db: AsyncSession, row: TicketWorkflow, data: dict) -> TicketWorkflow:
        for key, value in data.items():
            setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def soft_delete(db: AsyncSession, row: TicketWorkflow) -> None:
        row.deleted_at = datetime.now(timezone.utc)
        await db.commit()

    @staticmethod
    async def reorder(db: AsyncSession, tenant_id: int, ids: list[int]) -> None:
        rows = await db.execute(
            select(TicketWorkflow).where(
                TicketWorkflow.tenant_id == tenant_id,
                TicketWorkflow.id.in_(ids),
                TicketWorkflowRepository._not_deleted_clause(),
            )
        )
        by_id = {row.id: row for row in rows.scalars().all()}
        for index, workflow_id in enumerate(ids, start=1):
            row = by_id.get(workflow_id)
            if row:
                row.sort_order = index
        await db.commit()

    @staticmethod
    async def list_enabled_for_execution(db: AsyncSession, tenant_id: int) -> list[TicketWorkflow]:
        q = (
            select(TicketWorkflow)
            .where(
                TicketWorkflow.tenant_id == tenant_id,
                TicketWorkflow.enabled == True,  # noqa: E712
                TicketWorkflow.current_version_id.isnot(None),
                TicketWorkflowRepository._not_deleted_clause(),
            )
            .order_by(TicketWorkflow.sort_order.asc(), TicketWorkflow.id.asc())
        )
        return list((await db.execute(q)).scalars().all())
