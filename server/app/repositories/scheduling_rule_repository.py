"""
Scheduling rule set repository.
"""
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduling_rule import ScheduleRuleSet


class ScheduleRuleSetRepository:

    @staticmethod
    async def list_by_tenant(db: AsyncSession, tenant_id: int) -> list[ScheduleRuleSet]:
        result = await db.execute(
            select(ScheduleRuleSet)
            .where(ScheduleRuleSet.tenant_id == tenant_id)
            .order_by(ScheduleRuleSet.updated_at.desc(), ScheduleRuleSet.id.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, rule_set_id: int) -> ScheduleRuleSet | None:
        result = await db.execute(
            select(ScheduleRuleSet).where(
                ScheduleRuleSet.id == rule_set_id,
                ScheduleRuleSet.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_name(
        db: AsyncSession, tenant_id: int, name: str, exclude_id: int | None = None
    ) -> ScheduleRuleSet | None:
        stmt = select(ScheduleRuleSet).where(
            ScheduleRuleSet.tenant_id == tenant_id,
            ScheduleRuleSet.name == name,
        )
        if exclude_id is not None:
            stmt = stmt.where(ScheduleRuleSet.id != exclude_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_default(db: AsyncSession, tenant_id: int) -> ScheduleRuleSet | None:
        result = await db.execute(
            select(ScheduleRuleSet).where(
                ScheduleRuleSet.tenant_id == tenant_id,
                ScheduleRuleSet.is_default.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def count_by_tenant(db: AsyncSession, tenant_id: int) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(ScheduleRuleSet)
            .where(ScheduleRuleSet.tenant_id == tenant_id)
        )
        return result.scalar_one()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> ScheduleRuleSet:
        rule_set = ScheduleRuleSet(**data)
        db.add(rule_set)
        await db.commit()
        await db.refresh(rule_set)
        return rule_set

    @staticmethod
    async def update(db: AsyncSession, rule_set: ScheduleRuleSet, data: dict) -> ScheduleRuleSet:
        for key, value in data.items():
            setattr(rule_set, key, value)
        await db.commit()
        await db.refresh(rule_set)
        return rule_set

    @staticmethod
    async def delete(db: AsyncSession, rule_set: ScheduleRuleSet) -> None:
        await db.delete(rule_set)
        await db.commit()

    @staticmethod
    async def clear_default(db: AsyncSession, tenant_id: int, exclude_id: int | None = None) -> None:
        """Unset is_default on all other rule sets of the tenant (tenant-unique default)."""
        stmt = (
            update(ScheduleRuleSet)
            .where(
                ScheduleRuleSet.tenant_id == tenant_id,
                ScheduleRuleSet.is_default.is_(True),
            )
            .values(is_default=False)
        )
        if exclude_id is not None:
            stmt = stmt.where(ScheduleRuleSet.id != exclude_id)
        await db.execute(stmt)
        await db.flush()
