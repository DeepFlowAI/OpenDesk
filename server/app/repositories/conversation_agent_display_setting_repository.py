"""
Conversation agent display-name setting data access.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_agent_display_setting import ConversationAgentDisplaySetting


class ConversationAgentDisplaySettingRepository:
    @staticmethod
    async def get_by_tenant(db: AsyncSession, tenant_id: int) -> ConversationAgentDisplaySetting | None:
        result = await db.execute(
            select(ConversationAgentDisplaySetting).where(ConversationAgentDisplaySetting.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def save(
        db: AsyncSession,
        tenant_id: int,
        data: dict,
        *,
        commit: bool = True,
    ) -> ConversationAgentDisplaySetting:
        row = await ConversationAgentDisplaySettingRepository.get_by_tenant(db, tenant_id)
        if row:
            for key, value in data.items():
                setattr(row, key, value)
        else:
            row = ConversationAgentDisplaySetting(tenant_id=tenant_id, **data)
            db.add(row)

        if commit:
            await db.commit()
            await db.refresh(row)
        else:
            await db.flush()
        return row
