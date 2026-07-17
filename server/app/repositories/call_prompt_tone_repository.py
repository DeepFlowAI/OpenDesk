"""
CallPromptToneSettings repository — one row per (tenant, scene).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_prompt_tone_settings import CallPromptToneSettings


class CallPromptToneRepository:

    @staticmethod
    async def list_by_tenant(
        db: AsyncSession, tenant_id: int
    ) -> list[CallPromptToneSettings]:
        """Return all stored scene rows for a tenant."""
        result = await db.execute(
            select(CallPromptToneSettings).where(
                CallPromptToneSettings.tenant_id == tenant_id
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def upsert(
        db: AsyncSession, tenant_id: int, scene: str, data: dict
    ) -> CallPromptToneSettings:
        """Insert or update a single scene row for a tenant."""
        result = await db.execute(
            select(CallPromptToneSettings).where(
                CallPromptToneSettings.tenant_id == tenant_id,
                CallPromptToneSettings.scene == scene,
            )
        )
        item = result.scalar_one_or_none()
        if item:
            for key, value in data.items():
                setattr(item, key, value)
        else:
            item = CallPromptToneSettings(tenant_id=tenant_id, scene=scene, **data)
            db.add(item)
        return item
