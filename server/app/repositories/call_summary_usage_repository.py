"""
CallSummaryUsage repository - data access for call summary values.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.call_record import CallRecord
from app.models.call_summary_config_field import CallSummaryConfigField
from app.models.call_summary_field_value import CallSummaryFieldValue
from app.models.call_summary_interaction_rule import CallSummaryInteractionRule


class CallSummaryUsageRepository:

    @staticmethod
    async def get_call_record(db: AsyncSession, call_record_id: int) -> CallRecord | None:
        return await db.get(CallRecord, call_record_id)

    @staticmethod
    async def get_active_fields(db: AsyncSession, config_id: int) -> list[CallSummaryConfigField]:
        result = await db.execute(
            select(CallSummaryConfigField)
            .where(
                CallSummaryConfigField.config_id == config_id,
                CallSummaryConfigField.is_active.is_(True),
            )
            .options(selectinload(CallSummaryConfigField.field_definition))
            .order_by(CallSummaryConfigField.sort_order, CallSummaryConfigField.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_enabled_rules(db: AsyncSession, config_id: int) -> list[CallSummaryInteractionRule]:
        result = await db.execute(
            select(CallSummaryInteractionRule)
            .where(
                CallSummaryInteractionRule.config_id == config_id,
                CallSummaryInteractionRule.is_enabled.is_(True),
            )
            .order_by(CallSummaryInteractionRule.sort_order, CallSummaryInteractionRule.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_values(
        db: AsyncSession,
        tenant_id: int,
        call_record_id: int,
    ) -> list[CallSummaryFieldValue]:
        result = await db.execute(
            select(CallSummaryFieldValue)
            .where(
                CallSummaryFieldValue.tenant_id == tenant_id,
                CallSummaryFieldValue.call_record_id == call_record_id,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_value(
        db: AsyncSession,
        tenant_id: int,
        call_record_id: int,
        *,
        field_definition_id: int | None = None,
        field_key: str | None = None,
    ) -> CallSummaryFieldValue | None:
        conditions = [
            CallSummaryFieldValue.tenant_id == tenant_id,
            CallSummaryFieldValue.call_record_id == call_record_id,
        ]
        if field_definition_id is not None:
            conditions.append(CallSummaryFieldValue.field_definition_id == field_definition_id)
        else:
            conditions.append(CallSummaryFieldValue.field_key == field_key)

        result = await db.execute(select(CallSummaryFieldValue).where(*conditions))
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_value(
        db: AsyncSession,
        *,
        tenant_id: int,
        call_record_id: int,
        field_definition_id: int | None,
        field_key: str | None,
        value: object,
    ) -> CallSummaryFieldValue:
        item = await CallSummaryUsageRepository.get_value(
            db,
            tenant_id,
            call_record_id,
            field_definition_id=field_definition_id,
            field_key=field_key,
        )
        if item:
            item.value = value
        else:
            item = CallSummaryFieldValue(
                tenant_id=tenant_id,
                call_record_id=call_record_id,
                field_definition_id=field_definition_id,
                field_key=field_key,
                value=value,
            )
            db.add(item)
        await db.commit()
        await db.refresh(item)
        return item
