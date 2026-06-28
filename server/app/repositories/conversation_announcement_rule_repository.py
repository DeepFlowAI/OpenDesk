"""
ConversationAnnouncementRule repository.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_announcement_rule import ConversationAnnouncementRule


class ConversationAnnouncementRuleRepository:
    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[ConversationAnnouncementRule], int]:
        count_q = (
            select(func.count())
            .select_from(ConversationAnnouncementRule)
            .where(ConversationAnnouncementRule.tenant_id == tenant_id)
        )
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        q = (
            select(ConversationAnnouncementRule)
            .where(ConversationAnnouncementRule.tenant_id == tenant_id)
            .order_by(ConversationAnnouncementRule.priority.asc(), ConversationAnnouncementRule.id.asc())
            .offset(offset)
            .limit(per_page)
        )
        rows = list((await db.execute(q)).scalars().all())
        return rows, total

    @staticmethod
    async def list_enabled_ordered(db: AsyncSession, tenant_id: int) -> list[ConversationAnnouncementRule]:
        q = (
            select(ConversationAnnouncementRule)
            .where(
                ConversationAnnouncementRule.tenant_id == tenant_id,
                ConversationAnnouncementRule.enabled.is_(True),
            )
            .order_by(ConversationAnnouncementRule.priority.asc(), ConversationAnnouncementRule.id.asc())
        )
        return list((await db.execute(q)).scalars().all())

    @staticmethod
    async def list_all_ids_ordered(db: AsyncSession, tenant_id: int) -> list[int]:
        q = (
            select(ConversationAnnouncementRule.id)
            .where(ConversationAnnouncementRule.tenant_id == tenant_id)
            .order_by(ConversationAnnouncementRule.priority.asc(), ConversationAnnouncementRule.id.asc())
        )
        return list((await db.execute(q)).scalars().all())

    @staticmethod
    async def max_priority(db: AsyncSession, tenant_id: int) -> int:
        q = select(func.max(ConversationAnnouncementRule.priority)).where(
            ConversationAnnouncementRule.tenant_id == tenant_id
        )
        value = (await db.execute(q)).scalar_one()
        return int(value or 0)

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        rule_id: int,
        tenant_id: int,
    ) -> ConversationAnnouncementRule | None:
        q = select(ConversationAnnouncementRule).where(
            ConversationAnnouncementRule.id == rule_id,
            ConversationAnnouncementRule.tenant_id == tenant_id,
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> ConversationAnnouncementRule:
        row = ConversationAnnouncementRule(**data)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def update(
        db: AsyncSession,
        row: ConversationAnnouncementRule,
        data: dict,
    ) -> ConversationAnnouncementRule:
        for key, value in data.items():
            setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def delete(db: AsyncSession, row: ConversationAnnouncementRule) -> None:
        await db.delete(row)
        await db.commit()

    @staticmethod
    async def set_priorities(db: AsyncSession, tenant_id: int, id_to_priority: dict[int, int]) -> None:
        for rule_id, priority in id_to_priority.items():
            row = await ConversationAnnouncementRuleRepository.get_by_id(db, rule_id, tenant_id)
            if row:
                row.priority = priority
        await db.commit()
