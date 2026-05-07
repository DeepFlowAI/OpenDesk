"""
ServiceHours repository — data access layer
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service_hours import ServiceHours


class ServiceHoursRepository:

    @staticmethod
    async def get_by_tenant(db: AsyncSession, tenant_id: int) -> list[ServiceHours]:
        result = await db.execute(
            select(ServiceHours)
            .where(ServiceHours.tenant_id == tenant_id)
            .order_by(ServiceHours.updated_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, service_hours_id: int) -> ServiceHours | None:
        return await db.get(ServiceHours, service_hours_id)

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> ServiceHours:
        item = ServiceHours(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: ServiceHours, data: dict) -> ServiceHours:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: ServiceHours) -> None:
        await db.delete(item)
        await db.commit()
