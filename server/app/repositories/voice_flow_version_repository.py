"""
VoiceFlowVersion repository
"""
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.voice_flow_version import VoiceFlowVersion


class VoiceFlowVersionRepository:

    @staticmethod
    async def get_by_id(
        db: AsyncSession, version_id: int, tenant_id: int
    ) -> VoiceFlowVersion | None:
        q = select(VoiceFlowVersion).where(
            VoiceFlowVersion.id == version_id,
            VoiceFlowVersion.tenant_id == tenant_id,
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def get_latest_version_no(
        db: AsyncSession, voice_flow_id: int, tenant_id: int
    ) -> int:
        q = select(func.coalesce(func.max(VoiceFlowVersion.version_no), 0)).where(
            VoiceFlowVersion.voice_flow_id == voice_flow_id,
            VoiceFlowVersion.tenant_id == tenant_id,
        )
        return int((await db.execute(q)).scalar_one() or 0)

    @staticmethod
    async def get_by_version_no(
        db: AsyncSession, voice_flow_id: int, version_no: int, tenant_id: int
    ) -> VoiceFlowVersion | None:
        q = select(VoiceFlowVersion).where(
            VoiceFlowVersion.voice_flow_id == voice_flow_id,
            VoiceFlowVersion.version_no == version_no,
            VoiceFlowVersion.tenant_id == tenant_id,
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def list_for_flow(
        db: AsyncSession, voice_flow_id: int, tenant_id: int, limit: int = 50
    ) -> list[VoiceFlowVersion]:
        q = (
            select(VoiceFlowVersion)
            .where(
                VoiceFlowVersion.voice_flow_id == voice_flow_id,
                VoiceFlowVersion.tenant_id == tenant_id,
            )
            .order_by(desc(VoiceFlowVersion.version_no))
            .limit(limit)
        )
        return list((await db.execute(q)).scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> VoiceFlowVersion:
        row = VoiceFlowVersion(**data)
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row
