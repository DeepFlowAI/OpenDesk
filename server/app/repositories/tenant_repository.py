"""
Tenant repository
"""
import re

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant


TENANT_SLUG_MAX_LENGTH = 128
TENANT_SLUG_REGEX = re.compile(r"^[a-z0-9][a-z0-9._/-]{1,127}$")


def normalize_tenant_identifier(value: str) -> str:
    """Normalize user-facing tenant identifiers for lookup."""
    return value.strip().lower()


def normalize_tenant_slug(value: str | None) -> str | None:
    """Normalize tenant slug values before persistence."""
    if value is None:
        return None
    normalized = normalize_tenant_identifier(value)
    return normalized or None


def is_valid_tenant_slug(value: str) -> bool:
    """Return whether a normalized slug satisfies product rules."""
    return bool(TENANT_SLUG_REGEX.fullmatch(value))


class TenantRepository:

    @staticmethod
    async def get_by_tenant_id(db: AsyncSession, tenant_id: str) -> Tenant | None:
        """Find tenant by system-generated tenant_id string."""
        result = await db.execute(
            select(Tenant).where(Tenant.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Tenant | None:
        """Find tenant by normalized slug."""
        result = await db.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    @staticmethod
    async def resolve_by_identifier(db: AsyncSession, identifier: str) -> Tenant | None:
        """Resolve tenant input by tenant_id first, then slug."""
        normalized = normalize_tenant_identifier(identifier)
        tenant = await TenantRepository.get_by_tenant_id(db, normalized)
        if tenant:
            return tenant
        return await TenantRepository.get_by_slug(db, normalized)

    @staticmethod
    async def get_slug_conflict(
        db: AsyncSession,
        slug: str,
        current_tenant_pk: int | None = None,
    ) -> Tenant | None:
        """Find another tenant whose slug or tenant_id conflicts with slug."""
        query = select(Tenant).where(
            or_(Tenant.slug == slug, Tenant.tenant_id == slug)
        )
        if current_tenant_pk is not None:
            query = query.where(Tenant.id != current_tenant_pk)
        result = await db.execute(query.limit(1))
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
