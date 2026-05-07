"""
SystemSettings repository
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_settings import SystemSettings


class SystemSettingsRepository:

    @staticmethod
    async def get_by_tenant_id(db: AsyncSession, tenant_id: int) -> SystemSettings | None:
        """Get system settings for a tenant."""
        result = await db.execute(
            select(SystemSettings).where(SystemSettings.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: dict) -> SystemSettings:
        """Create system settings for a tenant."""
        item = SystemSettings(tenant_id=tenant_id, **data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: SystemSettings, data: dict) -> SystemSettings:
        """Update existing system settings."""
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item
