"""
ServiceHours service — business logic layer
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.service_hours_repository import ServiceHoursRepository
from app.schemas.service_hours import ServiceHoursCreate, ServiceHoursUpdate


class ServiceHoursService:

    @staticmethod
    async def list_by_tenant(db: AsyncSession, tenant_id: int):
        return await ServiceHoursRepository.get_by_tenant(db, tenant_id)

    @staticmethod
    async def get_by_id(db: AsyncSession, service_hours_id: int, tenant_id: int):
        item = await ServiceHoursRepository.get_by_id(db, service_hours_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Service hours not found")
        return item

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: ServiceHoursCreate):
        payload = data.model_dump()
        payload["tenant_id"] = tenant_id
        # Convert nested Pydantic models to plain dicts for JSONB
        payload["weekly_schedules"] = [s.model_dump() for s in data.weekly_schedules]
        payload["holidays"] = [h.model_dump() for h in data.holidays]
        payload["makeup_days"] = [m.model_dump() for m in data.makeup_days]
        return await ServiceHoursRepository.create(db, payload)

    @staticmethod
    async def update(db: AsyncSession, service_hours_id: int, tenant_id: int, data: ServiceHoursUpdate):
        item = await ServiceHoursRepository.get_by_id(db, service_hours_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Service hours not found")
        payload = data.model_dump()
        payload["weekly_schedules"] = [s.model_dump() for s in data.weekly_schedules]
        payload["holidays"] = [h.model_dump() for h in data.holidays]
        payload["makeup_days"] = [m.model_dump() for m in data.makeup_days]
        return await ServiceHoursRepository.update(db, item, payload)

    @staticmethod
    async def delete(db: AsyncSession, service_hours_id: int, tenant_id: int) -> None:
        item = await ServiceHoursRepository.get_by_id(db, service_hours_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Service hours not found")
        await ServiceHoursRepository.delete(db, item)
