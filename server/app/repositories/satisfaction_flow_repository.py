"""Data access for call satisfaction flow headers."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.satisfaction_flow import SatisfactionFlow


class SatisfactionFlowRepository:
    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int,
        per_page: int,
        keyword: str | None = None,
        enabled: bool | None = None,
    ) -> tuple[list[SatisfactionFlow], int]:
        filters = [
            SatisfactionFlow.tenant_id == tenant_id,
            SatisfactionFlow.deleted_at.is_(None),
        ]
        if keyword:
            filters.append(SatisfactionFlow.name.ilike(f"%{keyword}%"))
        if enabled is not None:
            filters.append(SatisfactionFlow.enabled == enabled)
        total = (
            await db.execute(select(func.count()).select_from(SatisfactionFlow).where(*filters))
        ).scalar_one()
        rows = (
            await db.execute(
                select(SatisfactionFlow)
                .options(joinedload(SatisfactionFlow.current_version))
                .where(*filters)
                .order_by(SatisfactionFlow.updated_at.desc(), SatisfactionFlow.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
        ).unique().scalars().all()
        return list(rows), int(total)

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        flow_id: int,
        tenant_id: int,
        *,
        for_update: bool = False,
    ) -> SatisfactionFlow | None:
        query = (
            select(SatisfactionFlow)
            .options(joinedload(SatisfactionFlow.current_version))
            .where(
                SatisfactionFlow.id == flow_id,
                SatisfactionFlow.tenant_id == tenant_id,
                SatisfactionFlow.deleted_at.is_(None),
            )
        )
        if for_update:
            query = query.with_for_update(of=SatisfactionFlow)
        return (await db.execute(query)).unique().scalar_one_or_none()

    @staticmethod
    async def get_active(
        db: AsyncSession,
        tenant_id: int,
        *,
        for_update: bool = False,
    ) -> SatisfactionFlow | None:
        query = (
            select(SatisfactionFlow)
            .options(joinedload(SatisfactionFlow.current_version))
            .where(
                SatisfactionFlow.tenant_id == tenant_id,
                SatisfactionFlow.enabled.is_(True),
                SatisfactionFlow.deleted_at.is_(None),
            )
        )
        if for_update:
            # Restrict the lock to the flow row: the eager-loaded version arrives
            # through a LEFT OUTER JOIN, and PostgreSQL refuses FOR UPDATE on the
            # nullable side of an outer join.
            query = query.with_for_update(of=SatisfactionFlow)
        return (await db.execute(query)).unique().scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SatisfactionFlow:
        row = SatisfactionFlow(**data)
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def update(db: AsyncSession, row: SatisfactionFlow, data: dict) -> None:
        for key, value in data.items():
            setattr(row, key, value)
        await db.flush()

    @staticmethod
    async def soft_delete(db: AsyncSession, row: SatisfactionFlow) -> None:
        row.deleted_at = datetime.now(timezone.utc)
        await db.flush()
