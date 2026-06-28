"""
Conversation read-status setting repository.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_read_status_setting import ConversationReadStatusSetting


class ConversationReadStatusRepository:
    @staticmethod
    async def get_by_tenant(db: AsyncSession, tenant_id: int) -> ConversationReadStatusSetting | None:
        result = await db.execute(
            select(ConversationReadStatusSetting).where(
                ConversationReadStatusSetting.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def save(db: AsyncSession, tenant_id: int, data: dict) -> ConversationReadStatusSetting:
        row = await ConversationReadStatusRepository.get_by_tenant(db, tenant_id)
        if row:
            for key, value in data.items():
                setattr(row, key, value)
        else:
            row = ConversationReadStatusSetting(tenant_id=tenant_id, **data)
            db.add(row)

        await db.commit()
        await db.refresh(row)
        return row
