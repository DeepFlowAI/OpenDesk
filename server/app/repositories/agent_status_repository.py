"""
AgentStatus repository.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_status import AgentStatus


class AgentStatusRepository:

    @staticmethod
    async def get_for_employee(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> AgentStatus | None:
        q = select(AgentStatus).where(
            AgentStatus.tenant_id == tenant_id,
            AgentStatus.employee_id == employee_id,
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def upsert(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        status: str,
        reason: str | None,
    ) -> AgentStatus:
        existing = await AgentStatusRepository.get_for_employee(db, tenant_id, employee_id)
        if existing:
            if existing.status != status:
                existing.status_changed_at = datetime.now(timezone.utc)
            existing.status = status
            existing.reason = reason
            await db.commit()
            await db.refresh(existing)
            return existing
        row = AgentStatus(
            tenant_id=tenant_id, employee_id=employee_id, status=status, reason=reason
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def list_by_status(
        db: AsyncSession, tenant_id: int, status: str
    ) -> list[AgentStatus]:
        q = select(AgentStatus).where(
            AgentStatus.tenant_id == tenant_id,
            AgentStatus.status == status,
        )
        return list((await db.execute(q)).scalars().all())
