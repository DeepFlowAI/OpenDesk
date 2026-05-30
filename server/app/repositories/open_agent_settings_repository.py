"""
OpenAgentSettings repository.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.open_agent_settings import OpenAgentSettings


class OpenAgentSettingsRepository:

    @staticmethod
    async def get_by_tenant_id(db: AsyncSession, tenant_id: int) -> OpenAgentSettings | None:
        """Get OpenAgent settings for a tenant."""
        result = await db.execute(
            select(OpenAgentSettings).where(OpenAgentSettings.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> OpenAgentSettings:
        """Create OpenAgent settings."""
        item = OpenAgentSettings(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(
        db: AsyncSession,
        item: OpenAgentSettings,
        data: dict,
    ) -> OpenAgentSettings:
        """Update existing OpenAgent settings."""
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item
