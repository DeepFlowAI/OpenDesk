"""
System settings service
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.system_settings_repository import SystemSettingsRepository
from app.schemas.system_settings import (
    SystemSettingsUpdate,
    OrganizationSettingsUpdate,
    SystemSettingsResponse,
)


DEFAULTS = SystemSettingsResponse(
    default_language="zh", default_timezone="Asia/Shanghai", organization_enabled=False,
)


class SystemSettingsService:

    @staticmethod
    async def get_settings(db: AsyncSession, tenant_id: int) -> SystemSettingsResponse:
        """Get system settings for a tenant, returning defaults if not configured."""
        item = await SystemSettingsRepository.get_by_tenant_id(db, tenant_id)
        if not item:
            return DEFAULTS
        return SystemSettingsResponse.model_validate(item)

    @staticmethod
    async def update_settings(
        db: AsyncSession, tenant_id: int, data: SystemSettingsUpdate
    ) -> SystemSettingsResponse:
        """Upsert system settings for a tenant."""
        item = await SystemSettingsRepository.get_by_tenant_id(db, tenant_id)
        if item:
            item = await SystemSettingsRepository.update(db, item, data.model_dump())
        else:
            item = await SystemSettingsRepository.create(db, tenant_id, data.model_dump())
        return SystemSettingsResponse.model_validate(item)

    @staticmethod
    async def update_organization_settings(
        db: AsyncSession, tenant_id: int, data: OrganizationSettingsUpdate
    ) -> SystemSettingsResponse:
        """Toggle organization feature for a tenant."""
        item = await SystemSettingsRepository.get_by_tenant_id(db, tenant_id)
        if item:
            item = await SystemSettingsRepository.update(db, item, data.model_dump())
        else:
            defaults = DEFAULTS.model_dump()
            defaults.update(data.model_dump())
            item = await SystemSettingsRepository.create(db, tenant_id, defaults)
        return SystemSettingsResponse.model_validate(item)
