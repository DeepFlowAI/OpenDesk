"""
VoiceFlow repository
"""
from datetime import datetime, timezone

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.voice_flow import VoiceFlow


class VoiceFlowRepository:

    @staticmethod
    def _not_deleted_clause():
        return VoiceFlow.deleted_at.is_(None)

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 10,
        keyword: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[list[VoiceFlow], int]:
        q = select(VoiceFlow).where(VoiceFlow.tenant_id == tenant_id)
        if not include_deleted:
            q = q.where(VoiceFlowRepository._not_deleted_clause())
        if keyword:
            q = q.where(VoiceFlow.name.ilike(f"%{keyword}%"))

        count_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        q = q.order_by(VoiceFlow.id.asc()).offset(offset).limit(per_page)
        rows = list((await db.execute(q)).scalars().all())
        return rows, total

    @staticmethod
    async def list_for_select(db: AsyncSession, tenant_id: int) -> list[VoiceFlow]:
        q = (
            select(VoiceFlow)
            .where(
                VoiceFlow.tenant_id == tenant_id,
                VoiceFlow.enabled == True,  # noqa: E712
                VoiceFlowRepository._not_deleted_clause(),
            )
            .order_by(VoiceFlow.name.asc())
        )
        return list((await db.execute(q)).scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, flow_id: int, tenant_id: int) -> VoiceFlow | None:
        q = select(VoiceFlow).where(
            VoiceFlow.id == flow_id,
            VoiceFlow.tenant_id == tenant_id,
            VoiceFlowRepository._not_deleted_clause(),
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def get_by_id_include_deleted(
        db: AsyncSession, flow_id: int, tenant_id: int
    ) -> VoiceFlow | None:
        q = select(VoiceFlow).where(VoiceFlow.id == flow_id, VoiceFlow.tenant_id == tenant_id)
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> VoiceFlow:
        row = VoiceFlow(**data)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def update(db: AsyncSession, row: VoiceFlow, data: dict) -> VoiceFlow:
        for k, v in data.items():
            setattr(row, k, v)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def soft_delete(db: AsyncSession, row: VoiceFlow) -> None:
        row.deleted_at = datetime.now(timezone.utc)
        await db.commit()

    @staticmethod
    async def is_usable_target(db: AsyncSession, flow_id: int, tenant_id: int) -> bool:
        q = (
            select(func.count())
            .select_from(VoiceFlow)
            .where(
                and_(
                    VoiceFlow.id == flow_id,
                    VoiceFlow.tenant_id == tenant_id,
                    VoiceFlow.enabled == True,  # noqa: E712
                    VoiceFlowRepository._not_deleted_clause(),
                )
            )
        )
        n = (await db.execute(q)).scalar_one()
        return n > 0
