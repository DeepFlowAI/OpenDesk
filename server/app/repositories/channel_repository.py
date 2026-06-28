"""
Channel repository — data access layer
"""
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel

CHANNEL_KEY_PREFIX = "ch_"
CHANNEL_KEY_RANDOM_BYTES = 24
MAX_KEY_GENERATION_ATTEMPTS = 10


class ChannelRepository:

    @staticmethod
    async def get_by_tenant(db: AsyncSession, tenant_id: int) -> list[Channel]:
        result = await db.execute(
            select(Channel)
            .where(Channel.tenant_id == tenant_id)
            .order_by(Channel.updated_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_names_by_tenant(db: AsyncSession, tenant_id: int) -> list[str]:
        result = await db.execute(
            select(Channel.name).where(Channel.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, channel_id: int) -> Channel | None:
        return await db.get(Channel, channel_id)

    @staticmethod
    async def get_by_key(db: AsyncSession, channel_key: str) -> Channel | None:
        result = await db.execute(
            select(Channel).where(Channel.channel_key == channel_key)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def generate_channel_key() -> str:
        return f"{CHANNEL_KEY_PREFIX}{secrets.token_urlsafe(CHANNEL_KEY_RANDOM_BYTES)}"

    @staticmethod
    async def generate_unique_channel_key(db: AsyncSession) -> str:
        for _ in range(MAX_KEY_GENERATION_ATTEMPTS):
            channel_key = ChannelRepository.generate_channel_key()
            if not await ChannelRepository.get_by_key(db, channel_key):
                return channel_key
        raise RuntimeError("Failed to generate a unique channel key")

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Channel:
        item = Channel(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: Channel, data: dict) -> Channel:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def rotate_channel_key(db: AsyncSession, item: Channel, channel_key: str) -> Channel:
        item.channel_key = channel_key
        item.channel_key_version += 1
        item.key_rotated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: Channel) -> None:
        await db.delete(item)
        await db.commit()
