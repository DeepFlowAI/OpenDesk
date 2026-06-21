"""
API Key repository.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey


class ApiKeyRepository:
    @staticmethod
    async def get_by_tenant(db: AsyncSession, tenant_id: int) -> list[ApiKey]:
        result = await db.execute(
            select(ApiKey)
            .where(ApiKey.tenant_id == tenant_id)
            .order_by(ApiKey.created_at.desc(), ApiKey.id.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, api_key_id: int) -> ApiKey | None:
        return await db.get(ApiKey, api_key_id)

    @staticmethod
    async def get_by_hash(db: AsyncSession, key_hash: str) -> ApiKey | None:
        result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> ApiKey:
        item = ApiKey(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: ApiKey, data: dict) -> ApiKey:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update_last_used(db: AsyncSession, item: ApiKey, used_at: datetime) -> ApiKey:
        item.last_used_at = used_at
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: ApiKey) -> None:
        await db.delete(item)
        await db.commit()
