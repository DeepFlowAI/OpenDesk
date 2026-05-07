"""
Channel repository — data access layer
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel


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
    async def get_by_id(db: AsyncSession, channel_id: int) -> Channel | None:
        return await db.get(Channel, channel_id)

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
    async def delete(db: AsyncSession, item: Channel) -> None:
        await db.delete(item)
        await db.commit()
