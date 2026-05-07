"""
CsSummaryConfig repository — data access for conversation minutes configuration
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cs_summary_config import CsSummaryConfig
from app.models.cs_summary_config_field import CsSummaryConfigField
from app.models.cs_summary_interaction_rule import CsSummaryInteractionRule


class CsSummaryConfigRepository:

    @staticmethod
    async def get_or_create(db: AsyncSession, tenant_id: int) -> CsSummaryConfig:
        """Get the config for a tenant, creating one if it doesn't exist."""
        result = await db.execute(
            select(CsSummaryConfig)
            .where(CsSummaryConfig.tenant_id == tenant_id)
            .options(
                selectinload(CsSummaryConfig.fields),
                selectinload(CsSummaryConfig.interaction_rules),
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            config = CsSummaryConfig(tenant_id=tenant_id)
            db.add(config)
            await db.commit()
            await db.refresh(config, attribute_names=["fields", "interaction_rules"])
        return config

    # ── Field operations ──

    @staticmethod
    async def list_fields(db: AsyncSession, config_id: int) -> list[CsSummaryConfigField]:
        result = await db.execute(
            select(CsSummaryConfigField)
            .where(CsSummaryConfigField.config_id == config_id)
            .order_by(CsSummaryConfigField.sort_order)
        )
        return list(result.scalars().all())

    @staticmethod
    async def add_field(db: AsyncSession, config_id: int, data: dict) -> CsSummaryConfigField:
        max_result = await db.execute(
            select(func.coalesce(func.max(CsSummaryConfigField.sort_order), -1))
            .where(CsSummaryConfigField.config_id == config_id)
        )
        max_sort = max_result.scalar_one()
        field = CsSummaryConfigField(config_id=config_id, sort_order=max_sort + 1, **data)
        db.add(field)
        await db.commit()
        await db.refresh(field)
        return field

    @staticmethod
    async def get_field_by_id(db: AsyncSession, field_id: int) -> CsSummaryConfigField | None:
        return await db.get(CsSummaryConfigField, field_id)

    @staticmethod
    async def update_field(db: AsyncSession, field: CsSummaryConfigField, data: dict) -> CsSummaryConfigField:
        for key, value in data.items():
            if hasattr(field, key) and value is not None:
                setattr(field, key, value)
        await db.commit()
        await db.refresh(field)
        return field

    @staticmethod
    async def delete_field(db: AsyncSession, field: CsSummaryConfigField) -> None:
        await db.delete(field)
        await db.commit()

    @staticmethod
    async def bulk_update_field_sort(db: AsyncSession, config_id: int, items: list[dict]) -> None:
        for item in items:
            field = await db.get(CsSummaryConfigField, item["id"])
            if field and field.config_id == config_id:
                field.sort_order = item["sort_order"]
        await db.commit()

    # ── Interaction Rule operations ──

    @staticmethod
    async def list_rules(
        db: AsyncSession, config_id: int, page: int = 1, per_page: int = 100,
    ) -> tuple[list[CsSummaryInteractionRule], int]:
        total_result = await db.execute(
            select(func.count()).select_from(CsSummaryInteractionRule)
            .where(CsSummaryInteractionRule.config_id == config_id)
        )
        total = total_result.scalar_one()
        offset = (page - 1) * per_page
        result = await db.execute(
            select(CsSummaryInteractionRule)
            .where(CsSummaryInteractionRule.config_id == config_id)
            .order_by(CsSummaryInteractionRule.sort_order)
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_rule_by_id(db: AsyncSession, rule_id: int) -> CsSummaryInteractionRule | None:
        return await db.get(CsSummaryInteractionRule, rule_id)

    @staticmethod
    async def create_rule(db: AsyncSession, config_id: int, data: dict) -> CsSummaryInteractionRule:
        rule = CsSummaryInteractionRule(config_id=config_id, **data)
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def update_rule(db: AsyncSession, rule: CsSummaryInteractionRule, data: dict) -> CsSummaryInteractionRule:
        for key, value in data.items():
            if hasattr(rule, key) and value is not None:
                setattr(rule, key, value)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def delete_rule(db: AsyncSession, rule: CsSummaryInteractionRule) -> None:
        await db.delete(rule)
        await db.commit()

    @staticmethod
    async def bulk_update_rule_sort(db: AsyncSession, config_id: int, items: list[dict]) -> None:
        for item in items:
            rule = await db.get(CsSummaryInteractionRule, item["id"])
            if rule and rule.config_id == config_id:
                rule.sort_order = item["sort_order"]
        await db.commit()
