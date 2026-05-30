"""
CallSummaryConfig repository - data access for call summary configuration
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.call_summary_config import CallSummaryConfig
from app.models.call_summary_config_field import CallSummaryConfigField
from app.models.call_summary_interaction_rule import CallSummaryInteractionRule


class CallSummaryConfigRepository:

    @staticmethod
    async def get_or_create(db: AsyncSession, tenant_id: int) -> CallSummaryConfig:
        """Get the config for a tenant, creating one if it does not exist."""
        result = await db.execute(
            select(CallSummaryConfig)
            .where(CallSummaryConfig.tenant_id == tenant_id)
            .options(
                selectinload(CallSummaryConfig.fields),
                selectinload(CallSummaryConfig.interaction_rules),
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            config = CallSummaryConfig(tenant_id=tenant_id)
            db.add(config)
            await db.commit()
            await db.refresh(config, attribute_names=["fields", "interaction_rules"])
        return config

    # -- Field operations --

    @staticmethod
    async def list_fields(db: AsyncSession, config_id: int) -> list[CallSummaryConfigField]:
        result = await db.execute(
            select(CallSummaryConfigField)
            .where(CallSummaryConfigField.config_id == config_id)
            .order_by(CallSummaryConfigField.sort_order, CallSummaryConfigField.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def find_field(
        db: AsyncSession,
        config_id: int,
        field_definition_id: int | None,
        field_key: str | None,
    ) -> CallSummaryConfigField | None:
        if field_definition_id is not None:
            result = await db.execute(
                select(CallSummaryConfigField).where(
                    CallSummaryConfigField.config_id == config_id,
                    CallSummaryConfigField.field_definition_id == field_definition_id,
                )
            )
            return result.scalar_one_or_none()
        if field_key:
            result = await db.execute(
                select(CallSummaryConfigField).where(
                    CallSummaryConfigField.config_id == config_id,
                    CallSummaryConfigField.field_key == field_key,
                )
            )
            return result.scalar_one_or_none()
        return None

    @staticmethod
    async def add_field(db: AsyncSession, config_id: int, data: dict) -> CallSummaryConfigField:
        max_result = await db.execute(
            select(func.coalesce(func.max(CallSummaryConfigField.sort_order), -1))
            .where(CallSummaryConfigField.config_id == config_id)
        )
        max_sort = max_result.scalar_one()
        field = CallSummaryConfigField(config_id=config_id, sort_order=max_sort + 1, **data)
        db.add(field)
        await db.commit()
        await db.refresh(field)
        return field

    @staticmethod
    async def get_field_by_id(db: AsyncSession, field_id: int) -> CallSummaryConfigField | None:
        return await db.get(CallSummaryConfigField, field_id)

    @staticmethod
    async def update_field(
        db: AsyncSession, field: CallSummaryConfigField, data: dict,
    ) -> CallSummaryConfigField:
        for key, value in data.items():
            if hasattr(field, key) and value is not None:
                setattr(field, key, value)
        await db.commit()
        await db.refresh(field)
        return field

    @staticmethod
    async def delete_field(db: AsyncSession, field: CallSummaryConfigField) -> None:
        await db.delete(field)
        await db.commit()

    @staticmethod
    async def bulk_update_field_sort(db: AsyncSession, config_id: int, items: list[dict]) -> None:
        for item in items:
            field = await db.get(CallSummaryConfigField, item["id"])
            if field and field.config_id == config_id:
                field.sort_order = item["sort_order"]
        await db.commit()

    # -- Interaction Rule operations --

    @staticmethod
    async def list_rules(
        db: AsyncSession, config_id: int, page: int = 1, per_page: int = 100,
    ) -> tuple[list[CallSummaryInteractionRule], int]:
        total_result = await db.execute(
            select(func.count()).select_from(CallSummaryInteractionRule)
            .where(CallSummaryInteractionRule.config_id == config_id)
        )
        total = total_result.scalar_one()
        offset = (page - 1) * per_page
        result = await db.execute(
            select(CallSummaryInteractionRule)
            .where(CallSummaryInteractionRule.config_id == config_id)
            .order_by(CallSummaryInteractionRule.sort_order, CallSummaryInteractionRule.id)
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_rule_by_id(db: AsyncSession, rule_id: int) -> CallSummaryInteractionRule | None:
        return await db.get(CallSummaryInteractionRule, rule_id)

    @staticmethod
    async def create_rule(db: AsyncSession, config_id: int, data: dict) -> CallSummaryInteractionRule:
        if data.get("sort_order") is None:
            max_result = await db.execute(
                select(func.coalesce(func.max(CallSummaryInteractionRule.sort_order), -1))
                .where(CallSummaryInteractionRule.config_id == config_id)
            )
            data["sort_order"] = max_result.scalar_one() + 1
        rule = CallSummaryInteractionRule(config_id=config_id, **data)
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def update_rule(
        db: AsyncSession, rule: CallSummaryInteractionRule, data: dict,
    ) -> CallSummaryInteractionRule:
        for key, value in data.items():
            if hasattr(rule, key) and value is not None:
                setattr(rule, key, value)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def delete_rule(db: AsyncSession, rule: CallSummaryInteractionRule) -> None:
        await db.delete(rule)
        await db.commit()

    @staticmethod
    async def bulk_update_rule_sort(db: AsyncSession, config_id: int, items: list[dict]) -> None:
        for item in items:
            rule = await db.get(CallSummaryInteractionRule, item["id"])
            if rule and rule.config_id == config_id:
                rule.sort_order = item["sort_order"]
        await db.commit()
