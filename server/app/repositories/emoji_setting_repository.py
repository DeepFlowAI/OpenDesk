"""
Emoji setting repository.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emoji_setting import EmojiSetting


class EmojiSettingRepository:
    @staticmethod
    async def get_by_tenant(db: AsyncSession, tenant_id: int) -> EmojiSetting | None:
        q = select(EmojiSetting).where(EmojiSetting.tenant_id == tenant_id)
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def save(db: AsyncSession, tenant_id: int, data: dict) -> EmojiSetting:
        row = await EmojiSettingRepository.get_by_tenant(db, tenant_id)
        if row:
            for key, value in data.items():
                setattr(row, key, value)
        else:
            row = EmojiSetting(tenant_id=tenant_id, **data)
            db.add(row)

        await db.commit()
        await db.refresh(row)
        return row
