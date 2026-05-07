"""
Tenant repository
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant


class TenantRepository:

    @staticmethod
    async def get_by_tenant_id(db: AsyncSession, tenant_id: str) -> Tenant | None:
        """Find tenant by slug (tenant_id string)."""
        result = await db.execute(
            select(Tenant).where(Tenant.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_pk(db: AsyncSession, pk: int) -> Tenant | None:
        return await db.get(Tenant, pk)

    @staticmethod
    async def get_by_name(db: AsyncSession, name: str) -> Tenant | None:
        result = await db.execute(select(Tenant).where(Tenant.name == name))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession, page: int = 1, per_page: int = 10
    ) -> tuple[list[Tenant], int]:
        count_q = select(func.count()).select_from(Tenant)
        total_result = await db.execute(count_q)
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        data_q = (
            select(Tenant)
            .order_by(Tenant.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(data_q)
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Tenant:
        tenant = Tenant(**data)
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
        return tenant

    @staticmethod
    async def update(db: AsyncSession, tenant: Tenant, data: dict) -> Tenant:
        for key, value in data.items():
            if hasattr(tenant, key):
                setattr(tenant, key, value)
        await db.commit()
        await db.refresh(tenant)
        return tenant
