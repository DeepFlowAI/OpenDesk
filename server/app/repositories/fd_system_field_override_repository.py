"""
Repository for fd_system_field_overrides table.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fd_system_field_override import FdSystemFieldOverride


class FdSystemFieldOverrideRepository:

    @staticmethod
    async def get_all_for_tenant_domain(
        db: AsyncSession, tenant_id: int, domain: str,
    ) -> list[FdSystemFieldOverride]:
        result = await db.execute(
            select(FdSystemFieldOverride).where(
                FdSystemFieldOverride.tenant_id == tenant_id,
                FdSystemFieldOverride.domain == domain,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_one(
        db: AsyncSession, tenant_id: int, domain: str, field_key: str,
    ) -> FdSystemFieldOverride | None:
        result = await db.execute(
            select(FdSystemFieldOverride).where(
                FdSystemFieldOverride.tenant_id == tenant_id,
                FdSystemFieldOverride.domain == domain,
                FdSystemFieldOverride.field_key == field_key,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert(
        db: AsyncSession,
        tenant_id: int,
        domain: str,
        field_key: str,
        data: dict,
    ) -> FdSystemFieldOverride:
        """Insert or update an override row. Returns the resulting row."""
        existing = await FdSystemFieldOverrideRepository.get_one(db, tenant_id, domain, field_key)
        if existing:
            for k, v in data.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            await db.commit()
            await db.refresh(existing)
            return existing
        else:
            row = FdSystemFieldOverride(
                tenant_id=tenant_id,
                domain=domain,
                field_key=field_key,
                **data,
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return row

    @staticmethod
    async def batch_upsert_sort(
        db: AsyncSession,
        tenant_id: int,
        domain: str,
        items: list[dict],
    ) -> None:
        """Batch upsert sort_order for system field overrides."""
        for item in items:
            await FdSystemFieldOverrideRepository.upsert(
                db, tenant_id, domain, item["field_key"],
                {"sort_order": item["sort_order"]},
            )
