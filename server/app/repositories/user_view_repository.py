"""
UserView repository — data access for user view configurations
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_view import UserView


class UserViewRepository:

    @staticmethod
    async def get_by_id(
        db: AsyncSession, view_id: int, tenant_id: int
    ) -> UserView | None:
        q = select(UserView).where(
            UserView.id == view_id, UserView.tenant_id == tenant_id
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession, tenant_id: int, page: int = 1, per_page: int = 50
    ) -> tuple[list[UserView], int]:
        count_q = (
            select(func.count())
            .select_from(UserView)
            .where(UserView.tenant_id == tenant_id)
        )
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        q = (
            select(UserView)
            .where(UserView.tenant_id == tenant_id)
            .order_by(UserView.sort_order.asc(), UserView.id.asc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(q)
        return list(result.scalars().all()), total

    @staticmethod
    async def max_sort_order(db: AsyncSession, tenant_id: int) -> int:
        q = select(func.max(UserView.sort_order)).where(
            UserView.tenant_id == tenant_id
        )
        v = (await db.execute(q)).scalar_one()
        return int(v or 0)

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> UserView:
        row = UserView(**data)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def update(db: AsyncSession, row: UserView, data: dict) -> UserView:
        for k, v in data.items():
            setattr(row, k, v)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def delete(db: AsyncSession, row: UserView) -> None:
        await db.delete(row)
        await db.commit()

    @staticmethod
    async def bulk_update_sort(
        db: AsyncSession, tenant_id: int, items: list[dict]
    ) -> None:
        for item in items:
            row = await UserViewRepository.get_by_id(db, item["id"], tenant_id)
            if row:
                row.sort_order = item["sort_order"]
        await db.commit()
