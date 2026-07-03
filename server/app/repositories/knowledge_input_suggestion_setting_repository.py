"""
Knowledge input suggestion setting data access.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_input_suggestion_setting import KnowledgeInputSuggestionSetting


class KnowledgeInputSuggestionSettingRepository:
    @staticmethod
    async def get_by_tenant(db: AsyncSession, tenant_id: int) -> KnowledgeInputSuggestionSetting | None:
        result = await db.execute(
            select(KnowledgeInputSuggestionSetting).where(KnowledgeInputSuggestionSetting.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def save(
        db: AsyncSession,
        tenant_id: int,
        data: dict,
        *,
        commit: bool = True,
    ) -> KnowledgeInputSuggestionSetting:
        row = await KnowledgeInputSuggestionSettingRepository.get_by_tenant(db, tenant_id)
        if row:
            for key, value in data.items():
                setattr(row, key, value)
        else:
            row = KnowledgeInputSuggestionSetting(tenant_id=tenant_id, **data)
            db.add(row)

        if commit:
            await db.commit()
            await db.refresh(row)
        else:
            await db.flush()
        return row
