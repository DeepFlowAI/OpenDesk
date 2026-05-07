"""
CsSummaryUsage repository — data access for conversation minutes usage
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation
from app.models.cs_summary_config_field import CsSummaryConfigField
from app.models.cs_summary_field_value import CsSummaryFieldValue
from app.models.cs_summary_interaction_rule import CsSummaryInteractionRule


class CsSummaryUsageRepository:

    @staticmethod
    async def get_conversation(db: AsyncSession, conversation_id: int) -> Conversation | None:
        return await db.get(Conversation, conversation_id)

    @staticmethod
    async def get_active_fields(db: AsyncSession, config_id: int) -> list[CsSummaryConfigField]:
        result = await db.execute(
            select(CsSummaryConfigField)
            .where(
                CsSummaryConfigField.config_id == config_id,
                CsSummaryConfigField.is_active.is_(True),
            )
            .options(selectinload(CsSummaryConfigField.field_definition))
            .order_by(CsSummaryConfigField.sort_order)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_enabled_rules(db: AsyncSession, config_id: int) -> list[CsSummaryInteractionRule]:
        result = await db.execute(
            select(CsSummaryInteractionRule)
            .where(
                CsSummaryInteractionRule.config_id == config_id,
                CsSummaryInteractionRule.is_enabled.is_(True),
            )
            .order_by(CsSummaryInteractionRule.sort_order)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_values(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
    ) -> list[CsSummaryFieldValue]:
        result = await db.execute(
            select(CsSummaryFieldValue)
            .where(
                CsSummaryFieldValue.tenant_id == tenant_id,
                CsSummaryFieldValue.conversation_id == conversation_id,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_value(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        *,
        field_definition_id: int | None = None,
        field_key: str | None = None,
    ) -> CsSummaryFieldValue | None:
        conditions = [
            CsSummaryFieldValue.tenant_id == tenant_id,
            CsSummaryFieldValue.conversation_id == conversation_id,
        ]
        if field_definition_id is not None:
            conditions.append(CsSummaryFieldValue.field_definition_id == field_definition_id)
        else:
            conditions.append(CsSummaryFieldValue.field_key == field_key)

        result = await db.execute(select(CsSummaryFieldValue).where(*conditions))
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_value(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        field_definition_id: int | None,
        field_key: str | None,
        value: object,
    ) -> CsSummaryFieldValue:
        item = await CsSummaryUsageRepository.get_value(
            db,
            tenant_id,
            conversation_id,
            field_definition_id=field_definition_id,
            field_key=field_key,
        )
        if item:
            item.value = value
        else:
            item = CsSummaryFieldValue(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                field_definition_id=field_definition_id,
                field_key=field_key,
                value=value,
            )
            db.add(item)
        await db.commit()
        await db.refresh(item)
        return item
