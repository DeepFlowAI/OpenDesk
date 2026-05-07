"""
FdInteractionRule repository — data access for interaction rules
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fd_interaction_rule import FdInteractionRule


class FdInteractionRuleRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, rule_id: int) -> FdInteractionRule | None:
        return await db.get(FdInteractionRule, rule_id)

    @staticmethod
    async def get_by_layout(
        db: AsyncSession, layout_id: int, page: int = 1, per_page: int = 100,
    ) -> tuple[list[FdInteractionRule], int]:
        total_result = await db.execute(
            select(func.count()).select_from(FdInteractionRule)
            .where(FdInteractionRule.layout_id == layout_id)
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(FdInteractionRule)
            .where(FdInteractionRule.layout_id == layout_id)
            .order_by(FdInteractionRule.sort_order)
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, layout_id: int, data: dict) -> FdInteractionRule:
        rule = FdInteractionRule(layout_id=layout_id, **data)
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def update(db: AsyncSession, rule: FdInteractionRule, data: dict) -> FdInteractionRule:
        for key, value in data.items():
            if hasattr(rule, key) and value is not None:
                setattr(rule, key, value)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def delete(db: AsyncSession, rule: FdInteractionRule) -> None:
        await db.delete(rule)
        await db.commit()

    @staticmethod
    async def bulk_update_sort(db: AsyncSession, items: list[dict]) -> None:
        for item in items:
            rule = await db.get(FdInteractionRule, item["id"])
            if rule:
                rule.sort_order = item["sort_order"]
        await db.commit()
