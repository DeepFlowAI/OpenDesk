"""
InboundRoutingRule repository
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.inbound_routing_rule import InboundRoutingRule
from app.models.voice_flow import VoiceFlow


class InboundRoutingRuleRepository:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[tuple[InboundRoutingRule, str | None]], int]:
        vf = aliased(VoiceFlow)
        base = (
            select(InboundRoutingRule, vf.name)
            .outerjoin(vf, vf.id == InboundRoutingRule.target_voice_flow_id)
            .where(InboundRoutingRule.tenant_id == tenant_id)
        )
        count_q = (
            select(func.count())
            .select_from(InboundRoutingRule)
            .where(InboundRoutingRule.tenant_id == tenant_id)
        )
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        q = (
            base.order_by(InboundRoutingRule.priority.asc(), InboundRoutingRule.id.asc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(q)
        rows = list(result.all())
        return rows, total

    @staticmethod
    async def list_all_ids_ordered(db: AsyncSession, tenant_id: int) -> list[int]:
        q = (
            select(InboundRoutingRule.id)
            .where(InboundRoutingRule.tenant_id == tenant_id)
            .order_by(InboundRoutingRule.priority.asc(), InboundRoutingRule.id.asc())
        )
        return list((await db.execute(q)).scalars().all())

    @staticmethod
    async def max_priority(db: AsyncSession, tenant_id: int) -> int:
        q = select(func.max(InboundRoutingRule.priority)).where(
            InboundRoutingRule.tenant_id == tenant_id
        )
        v = (await db.execute(q)).scalar_one()
        return int(v or 0)

    @staticmethod
    async def get_by_id(
        db: AsyncSession, rule_id: int, tenant_id: int
    ) -> tuple[InboundRoutingRule, str | None] | None:
        vf = aliased(VoiceFlow)
        q = (
            select(InboundRoutingRule, vf.name)
            .outerjoin(vf, vf.id == InboundRoutingRule.target_voice_flow_id)
            .where(InboundRoutingRule.id == rule_id, InboundRoutingRule.tenant_id == tenant_id)
        )
        row = (await db.execute(q)).one_or_none()
        return row

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> InboundRoutingRule:
        row = InboundRoutingRule(**data)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def update(db: AsyncSession, row: InboundRoutingRule, data: dict) -> InboundRoutingRule:
        for k, v in data.items():
            setattr(row, k, v)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def delete(db: AsyncSession, row: InboundRoutingRule) -> None:
        await db.delete(row)
        await db.commit()

    @staticmethod
    async def set_priorities(
        db: AsyncSession, tenant_id: int, id_to_priority: dict[int, int]
    ) -> None:
        for rid, pr in id_to_priority.items():
            row = await InboundRoutingRuleRepository.get_raw_by_id(db, rid, tenant_id)
            if row:
                row.priority = pr
        await db.commit()

    @staticmethod
    async def get_raw_by_id(
        db: AsyncSession, rule_id: int, tenant_id: int
    ) -> InboundRoutingRule | None:
        q = select(InboundRoutingRule).where(
            InboundRoutingRule.id == rule_id, InboundRoutingRule.tenant_id == tenant_id
        )
        return (await db.execute(q)).scalar_one_or_none()
