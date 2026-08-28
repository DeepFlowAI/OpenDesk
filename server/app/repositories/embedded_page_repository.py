"""
EmbeddedPage repository.
"""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedded_page import EmbeddedPage


class EmbeddedPageRepository:
    @staticmethod
    async def list_by_location(
        db: AsyncSession,
        tenant_id: int,
        location: str,
    ) -> list[EmbeddedPage]:
        q = (
            select(EmbeddedPage)
            .where(
                EmbeddedPage.tenant_id == tenant_id,
                EmbeddedPage.location == location,
            )
            .order_by(EmbeddedPage.sort_order.asc(), EmbeddedPage.updated_at.desc(), EmbeddedPage.id.asc())
        )
        return list((await db.execute(q)).scalars().all())

    @staticmethod
    async def list_enabled_by_location(
        db: AsyncSession,
        tenant_id: int,
        location: str,
    ) -> list[EmbeddedPage]:
        q = (
            select(EmbeddedPage)
            .where(
                EmbeddedPage.tenant_id == tenant_id,
                EmbeddedPage.location == location,
                EmbeddedPage.enabled.is_(True),
            )
            .order_by(EmbeddedPage.sort_order.asc(), EmbeddedPage.updated_at.desc(), EmbeddedPage.id.asc())
        )
        return list((await db.execute(q)).scalars().all())

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        page_id: int,
        tenant_id: int,
    ) -> EmbeddedPage | None:
        q = select(EmbeddedPage).where(
            EmbeddedPage.id == page_id,
            EmbeddedPage.tenant_id == tenant_id,
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> EmbeddedPage:
        row = EmbeddedPage(**data)
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def update(
        db: AsyncSession,
        row: EmbeddedPage,
        data: dict,
    ) -> EmbeddedPage:
        for key, value in data.items():
            setattr(row, key, value)
        await db.flush()
        return row

    @staticmethod
    async def delete(db: AsyncSession, row: EmbeddedPage) -> None:
        await db.delete(row)
        await db.commit()

    @staticmethod
    async def clear_default_focus_others(
        db: AsyncSession,
        tenant_id: int,
        location: str,
        keep_id: int | None,
    ) -> int:
        """Unset default_focus on sibling pages; returns how many were changed."""
        q = (
            update(EmbeddedPage)
            .where(
                EmbeddedPage.tenant_id == tenant_id,
                EmbeddedPage.location == location,
                EmbeddedPage.default_focus.is_(True),
                EmbeddedPage.id != (keep_id or 0),
            )
            .values(default_focus=False)
        )
        result = await db.execute(q)
        return int(result.rowcount or 0)
