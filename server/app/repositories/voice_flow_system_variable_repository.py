"""
VoiceFlowSystemVariable repository — global seed table; read-only at runtime.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.voice_flow_system_variable import VoiceFlowSystemVariable


class VoiceFlowSystemVariableRepository:

    @staticmethod
    async def list_all(db: AsyncSession) -> list[VoiceFlowSystemVariable]:
        q = select(VoiceFlowSystemVariable).order_by(
            VoiceFlowSystemVariable.sort_order.asc(),
            VoiceFlowSystemVariable.name.asc(),
        )
        return list((await db.execute(q)).scalars().all())

    @staticmethod
    async def names(db: AsyncSession) -> set[str]:
        q = select(VoiceFlowSystemVariable.name)
        return set((await db.execute(q)).scalars().all())
