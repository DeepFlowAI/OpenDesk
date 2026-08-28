"""Data access for Web SDK form-message configuration versions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel_form_config_version import ChannelFormConfigVersion


class ChannelFormConfigVersionRepository:
    @staticmethod
    async def get_by_channel_version(
        db: AsyncSession,
        tenant_id: int,
        channel_id: int,
        version: int,
    ) -> ChannelFormConfigVersion | None:
        result = await db.execute(
            select(ChannelFormConfigVersion).where(
                ChannelFormConfigVersion.tenant_id == tenant_id,
                ChannelFormConfigVersion.channel_id == channel_id,
                ChannelFormConfigVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        tenant_id: int,
        channel_id: int,
        version: int,
        config: dict,
    ) -> ChannelFormConfigVersion:
        item = ChannelFormConfigVersion(
            tenant_id=tenant_id,
            channel_id=channel_id,
            version=version,
            config=config,
        )
        db.add(item)
        await db.flush()
        return item
