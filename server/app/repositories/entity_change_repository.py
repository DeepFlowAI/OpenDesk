"""
EntityChange repository — data access for user and organization audit records.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity_change import EntityChange


class EntityChangeRepository:

    @staticmethod
    async def create_many(
        db: AsyncSession,
        rows: list[dict],
        commit: bool = True,
    ) -> list[EntityChange]:
        changes = [EntityChange(**row) for row in rows]
        db.add_all(changes)
        if commit:
            await db.commit()
            for change in changes:
                await db.refresh(change)
        return changes

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        entity_type: str,
        entity_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[EntityChange], int]:
        total_q = (
            select(func.count())
            .select_from(EntityChange)
            .where(
                EntityChange.tenant_id == tenant_id,
                EntityChange.entity_type == entity_type,
                EntityChange.entity_id == entity_id,
            )
        )
        total = (await db.execute(total_q)).scalar_one()
        q = (
            select(EntityChange)
            .where(
                EntityChange.tenant_id == tenant_id,
                EntityChange.entity_type == entity_type,
                EntityChange.entity_id == entity_id,
            )
            .order_by(EntityChange.created_at.desc(), EntityChange.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        items = (await db.execute(q)).scalars().all()
        return list(items), total
