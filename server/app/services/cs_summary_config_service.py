"""
CsSummaryConfig service — business logic for conversation minutes configuration
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.cs_summary_config_repository import CsSummaryConfigRepository
from app.schemas.cs_summary_config import (
    CsSummaryConfigFieldCreate,
    CsSummaryConfigFieldUpdate,
    CsSummaryInteractionRuleCreate,
    CsSummaryInteractionRuleUpdate,
    CsSummaryFieldSortRequest,
    CsSummaryRuleSortRequest,
)


class CsSummaryConfigService:

    @staticmethod
    async def get_or_create_config(db: AsyncSession, tenant_id: int):
        return await CsSummaryConfigRepository.get_or_create(db, tenant_id)

    @staticmethod
    async def _get_config_id(db: AsyncSession, tenant_id: int) -> int:
        """Get the config id for the tenant (create if absent)."""
        config = await CsSummaryConfigRepository.get_or_create(db, tenant_id)
        return config.id

    # ── Field management ──

    @staticmethod
    async def list_fields(db: AsyncSession, tenant_id: int):
        config = await CsSummaryConfigRepository.get_or_create(db, tenant_id)
        items = await CsSummaryConfigRepository.list_fields(db, config.id)
        return {"items": items, "total": len(items)}

    @staticmethod
    async def add_field(db: AsyncSession, tenant_id: int, data: CsSummaryConfigFieldCreate):
        if not data.field_definition_id and not data.field_key:
            raise ValidationError("Either field_definition_id or field_key is required")
        config = await CsSummaryConfigRepository.get_or_create(db, tenant_id)
        return await CsSummaryConfigRepository.add_field(
            db, config.id, data.model_dump(exclude_unset=True),
        )

    @staticmethod
    async def update_field(
        db: AsyncSession, tenant_id: int, field_id: int, data: CsSummaryConfigFieldUpdate,
    ):
        config_id = await CsSummaryConfigService._get_config_id(db, tenant_id)
        field = await CsSummaryConfigRepository.get_field_by_id(db, field_id)
        if not field or field.config_id != config_id:
            raise NotFoundError("Config field not found")
        return await CsSummaryConfigRepository.update_field(
            db, field, data.model_dump(exclude_unset=True),
        )

    @staticmethod
    async def delete_field(db: AsyncSession, tenant_id: int, field_id: int):
        config_id = await CsSummaryConfigService._get_config_id(db, tenant_id)
        field = await CsSummaryConfigRepository.get_field_by_id(db, field_id)
        if not field or field.config_id != config_id:
            raise NotFoundError("Config field not found")
        await CsSummaryConfigRepository.delete_field(db, field)

    @staticmethod
    async def sort_fields(db: AsyncSession, tenant_id: int, data: CsSummaryFieldSortRequest):
        config_id = await CsSummaryConfigService._get_config_id(db, tenant_id)
        await CsSummaryConfigRepository.bulk_update_field_sort(
            db, config_id, [item.model_dump() for item in data.items],
        )

    # ── Interaction Rule management ──

    @staticmethod
    async def list_rules(db: AsyncSession, tenant_id: int, page: int = 1, per_page: int = 100):
        config = await CsSummaryConfigRepository.get_or_create(db, tenant_id)
        items, total = await CsSummaryConfigRepository.list_rules(db, config.id, page, per_page)
        pages = (total + per_page - 1) // per_page
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": pages}

    @staticmethod
    async def get_rule(db: AsyncSession, tenant_id: int, rule_id: int):
        config_id = await CsSummaryConfigService._get_config_id(db, tenant_id)
        rule = await CsSummaryConfigRepository.get_rule_by_id(db, rule_id)
        if not rule or rule.config_id != config_id:
            raise NotFoundError("Interaction rule not found")
        return rule

    @staticmethod
    async def create_rule(db: AsyncSession, tenant_id: int, data: CsSummaryInteractionRuleCreate):
        config = await CsSummaryConfigRepository.get_or_create(db, tenant_id)
        return await CsSummaryConfigRepository.create_rule(
            db, config.id, data.model_dump(),
        )

    @staticmethod
    async def update_rule(
        db: AsyncSession, tenant_id: int, rule_id: int, data: CsSummaryInteractionRuleUpdate,
    ):
        config_id = await CsSummaryConfigService._get_config_id(db, tenant_id)
        rule = await CsSummaryConfigRepository.get_rule_by_id(db, rule_id)
        if not rule or rule.config_id != config_id:
            raise NotFoundError("Interaction rule not found")
        return await CsSummaryConfigRepository.update_rule(
            db, rule, data.model_dump(exclude_unset=True),
        )

    @staticmethod
    async def delete_rule(db: AsyncSession, tenant_id: int, rule_id: int):
        config_id = await CsSummaryConfigService._get_config_id(db, tenant_id)
        rule = await CsSummaryConfigRepository.get_rule_by_id(db, rule_id)
        if not rule or rule.config_id != config_id:
            raise NotFoundError("Interaction rule not found")
        await CsSummaryConfigRepository.delete_rule(db, rule)

    @staticmethod
    async def sort_rules(db: AsyncSession, tenant_id: int, data: CsSummaryRuleSortRequest):
        config_id = await CsSummaryConfigService._get_config_id(db, tenant_id)
        await CsSummaryConfigRepository.bulk_update_rule_sort(
            db, config_id, [item.model_dump() for item in data.items],
        )
