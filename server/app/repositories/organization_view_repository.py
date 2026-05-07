"""
OrganizationView repository — data access for organization view configurations
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization_view import OrganizationView


class OrganizationViewRepository:

    @staticmethod
    async def get_by_id(
        db: AsyncSession, view_id: int, tenant_id: int
    ) -> OrganizationView | None:
        q = select(OrganizationView).where(
            OrganizationView.id == view_id, OrganizationView.tenant_id == tenant_id
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession, tenant_id: int, page: int = 1, per_page: int = 50
    ) -> tuple[list[OrganizationView], int]:
        count_q = (
            select(func.count())
            .select_from(OrganizationView)
            .where(OrganizationView.tenant_id == tenant_id)
        )
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        q = (
            select(OrganizationView)
            .where(OrganizationView.tenant_id == tenant_id)
            .order_by(OrganizationView.sort_order.asc(), OrganizationView.id.asc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(q)
        return list(result.scalars().all()), total

    @staticmethod
    async def max_sort_order(db: AsyncSession, tenant_id: int) -> int:
        q = select(func.max(OrganizationView.sort_order)).where(
            OrganizationView.tenant_id == tenant_id
        )
        v = (await db.execute(q)).scalar_one()
        return int(v or 0)

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> OrganizationView:
        row = OrganizationView(**data)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def update(db: AsyncSession, row: OrganizationView, data: dict) -> OrganizationView:
        for k, v in data.items():
            setattr(row, k, v)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def delete(db: AsyncSession, row: OrganizationView) -> None:
        await db.delete(row)
        await db.commit()

    @staticmethod
    async def bulk_update_sort(
        db: AsyncSession, tenant_id: int, items: list[dict]
    ) -> None:
        for item in items:
            row = await OrganizationViewRepository.get_by_id(db, item["id"], tenant_id)
            if row:
                row.sort_order = item["sort_order"]
        await db.commit()
