"""
SessionRoutingRule repository
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.session_routing_rule import SessionRoutingRule
from app.models.employee_group import EmployeeGroup


class SessionRoutingRuleRepository:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[tuple[SessionRoutingRule, str | None]], int]:
        eg = aliased(EmployeeGroup)
        base = (
            select(SessionRoutingRule, eg.name)
            .outerjoin(eg, eg.id == SessionRoutingRule.target_group_id)
            .where(SessionRoutingRule.tenant_id == tenant_id)
        )
        count_q = (
            select(func.count())
            .select_from(SessionRoutingRule)
            .where(SessionRoutingRule.tenant_id == tenant_id)
        )
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        q = (
            base.order_by(SessionRoutingRule.priority.asc(), SessionRoutingRule.id.asc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(q)
        rows = list(result.all())
        return rows, total

    @staticmethod
    async def list_all_ids_ordered(db: AsyncSession, tenant_id: int) -> list[int]:
        q = (
            select(SessionRoutingRule.id)
            .where(SessionRoutingRule.tenant_id == tenant_id)
            .order_by(SessionRoutingRule.priority.asc(), SessionRoutingRule.id.asc())
        )
        return list((await db.execute(q)).scalars().all())

    @staticmethod
    async def max_priority(db: AsyncSession, tenant_id: int) -> int:
        q = select(func.max(SessionRoutingRule.priority)).where(
            SessionRoutingRule.tenant_id == tenant_id
        )
        v = (await db.execute(q)).scalar_one()
        return int(v or 0)

    @staticmethod
    async def get_by_id(
        db: AsyncSession, rule_id: int, tenant_id: int
    ) -> tuple[SessionRoutingRule, str | None] | None:
        eg = aliased(EmployeeGroup)
        q = (
            select(SessionRoutingRule, eg.name)
            .outerjoin(eg, eg.id == SessionRoutingRule.target_group_id)
            .where(SessionRoutingRule.id == rule_id, SessionRoutingRule.tenant_id == tenant_id)
        )
        row = (await db.execute(q)).one_or_none()
        return row

    @staticmethod
    async def get_raw_by_id(
        db: AsyncSession, rule_id: int, tenant_id: int
    ) -> SessionRoutingRule | None:
        q = select(SessionRoutingRule).where(
            SessionRoutingRule.id == rule_id, SessionRoutingRule.tenant_id == tenant_id
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SessionRoutingRule:
        row = SessionRoutingRule(**data)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def update(db: AsyncSession, row: SessionRoutingRule, data: dict) -> SessionRoutingRule:
        for k, v in data.items():
            setattr(row, k, v)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def delete(db: AsyncSession, row: SessionRoutingRule) -> None:
        await db.delete(row)
        await db.commit()

    @staticmethod
    async def set_priorities(
        db: AsyncSession, tenant_id: int, id_to_priority: dict[int, int]
    ) -> None:
        for rid, pr in id_to_priority.items():
            row = await SessionRoutingRuleRepository.get_raw_by_id(db, rid, tenant_id)
            if row:
                row.priority = pr
        await db.commit()
