"""
FdInteractionRule service — business logic for interaction rules
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.fd_form_layout_repository import FdFormLayoutRepository
from app.repositories.fd_interaction_rule_repository import FdInteractionRuleRepository
from app.schemas.fd_interaction_rule import (
    FdInteractionRuleCreate,
    FdInteractionRuleUpdate,
    InteractionRuleSortRequest,
)


class FdInteractionRuleService:

    @staticmethod
    async def _verify_layout_tenant(db: AsyncSession, layout_id: int, tenant_id: int) -> None:
        layout = await FdFormLayoutRepository.get_by_id(db, layout_id)
        if not layout or layout.tenant_id != tenant_id:
            raise NotFoundError("Form layout not found")

    @staticmethod
    async def get_paginated(
        db: AsyncSession, layout_id: int, tenant_id: int,
        page: int = 1, per_page: int = 100,
    ) -> dict:
        await FdInteractionRuleService._verify_layout_tenant(db, layout_id, tenant_id)
        items, total = await FdInteractionRuleRepository.get_by_layout(db, layout_id, page, per_page)
        pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, rule_id: int, tenant_id: int):
        item = await FdInteractionRuleRepository.get_by_id(db, rule_id)
        if not item:
            raise NotFoundError("Interaction rule not found")
        await FdInteractionRuleService._verify_layout_tenant(db, item.layout_id, tenant_id)
        return item

    @staticmethod
    async def create(db: AsyncSession, layout_id: int, tenant_id: int, data: FdInteractionRuleCreate):
        await FdInteractionRuleService._verify_layout_tenant(db, layout_id, tenant_id)
        return await FdInteractionRuleRepository.create(db, layout_id, data.model_dump())

    @staticmethod
    async def update(db: AsyncSession, rule_id: int, tenant_id: int, data: FdInteractionRuleUpdate):
        item = await FdInteractionRuleRepository.get_by_id(db, rule_id)
        if not item:
            raise NotFoundError("Interaction rule not found")
        await FdInteractionRuleService._verify_layout_tenant(db, item.layout_id, tenant_id)
        return await FdInteractionRuleRepository.update(db, item, data.model_dump(exclude_unset=True))

    @staticmethod
    async def delete(db: AsyncSession, rule_id: int, tenant_id: int) -> None:
        item = await FdInteractionRuleRepository.get_by_id(db, rule_id)
        if not item:
            raise NotFoundError("Interaction rule not found")
        await FdInteractionRuleService._verify_layout_tenant(db, item.layout_id, tenant_id)
        await FdInteractionRuleRepository.delete(db, item)

    @staticmethod
    async def sort(db: AsyncSession, layout_id: int, tenant_id: int, data: InteractionRuleSortRequest) -> None:
        await FdInteractionRuleService._verify_layout_tenant(db, layout_id, tenant_id)
        await FdInteractionRuleRepository.bulk_update_sort(
            db, [item.model_dump() for item in data.items]
        )
