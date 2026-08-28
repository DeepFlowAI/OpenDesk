"""Data access for immutable call satisfaction flow versions."""
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.satisfaction_flow import SatisfactionFlowVersion


class SatisfactionFlowVersionRepository:
    @staticmethod
    async def latest_version_no(
        db: AsyncSession, flow_id: int, tenant_id: int
    ) -> int:
        query = select(func.coalesce(func.max(SatisfactionFlowVersion.version_no), 0)).where(
            SatisfactionFlowVersion.satisfaction_flow_id == flow_id,
            SatisfactionFlowVersion.tenant_id == tenant_id,
        )
        return int((await db.execute(query)).scalar_one())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SatisfactionFlowVersion:
        row = SatisfactionFlowVersion(**data)
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row

    @staticmethod
    async def get_by_version_no(
        db: AsyncSession, flow_id: int, version_no: int, tenant_id: int
    ) -> SatisfactionFlowVersion | None:
        query = select(SatisfactionFlowVersion).where(
            SatisfactionFlowVersion.satisfaction_flow_id == flow_id,
            SatisfactionFlowVersion.version_no == version_no,
            SatisfactionFlowVersion.tenant_id == tenant_id,
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def list_for_flow(
        db: AsyncSession, flow_id: int, tenant_id: int, limit: int
    ) -> list[SatisfactionFlowVersion]:
        query = (
            select(SatisfactionFlowVersion)
            .where(
                SatisfactionFlowVersion.satisfaction_flow_id == flow_id,
                SatisfactionFlowVersion.tenant_id == tenant_id,
            )
            .order_by(desc(SatisfactionFlowVersion.version_no))
            .limit(limit)
        )
        return list((await db.execute(query)).scalars().all())
