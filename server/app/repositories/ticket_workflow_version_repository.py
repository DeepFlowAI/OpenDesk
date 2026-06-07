"""
Ticket workflow version repository.
"""
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket_workflow_version import TicketWorkflowVersion


class TicketWorkflowVersionRepository:
    @staticmethod
    async def get_latest_version_no(db: AsyncSession, workflow_id: int, tenant_id: int) -> int:
        q = select(func.coalesce(func.max(TicketWorkflowVersion.version_no), 0)).where(
            TicketWorkflowVersion.workflow_id == workflow_id,
            TicketWorkflowVersion.tenant_id == tenant_id,
        )
        return int((await db.execute(q)).scalar_one() or 0)

    @staticmethod
    async def get_by_version_no(
        db: AsyncSession,
        workflow_id: int,
        version_no: int,
        tenant_id: int,
    ) -> TicketWorkflowVersion | None:
        q = select(TicketWorkflowVersion).where(
            TicketWorkflowVersion.workflow_id == workflow_id,
            TicketWorkflowVersion.version_no == version_no,
            TicketWorkflowVersion.tenant_id == tenant_id,
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def list_for_workflow(
        db: AsyncSession,
        workflow_id: int,
        tenant_id: int,
        limit: int = 50,
    ) -> list[TicketWorkflowVersion]:
        q = (
            select(TicketWorkflowVersion)
            .where(
                TicketWorkflowVersion.workflow_id == workflow_id,
                TicketWorkflowVersion.tenant_id == tenant_id,
            )
            .order_by(desc(TicketWorkflowVersion.version_no))
            .limit(limit)
        )
        return list((await db.execute(q)).scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> TicketWorkflowVersion:
        row = TicketWorkflowVersion(**data)
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row
