"""
SIP Trunk repository
"""
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.models.sip_trunk import SipTrunk


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = exc.orig
    if orig is not None:
        sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        if sqlstate == "23505":
            return True
    message = str(exc).lower()
    return "unique" in message or "duplicate" in message


def _raise_on_trunk_integrity(exc: IntegrityError) -> None:
    if _is_unique_violation(exc):
        raise BusinessError(
            "Trunk name already exists",
            status_code=409,
            code="DUPLICATE_TRUNK_NAME",
        ) from exc
    raise exc


class SipTrunkRepository:

    @staticmethod
    def _apply_filters(
        query,
        *,
        q: str | None = None,
        status: str | None = None,
    ):
        if q:
            q_lower = q.strip().lower()
            if q_lower:
                query = query.where(
                    or_(
                        func.lower(SipTrunk.supplier_name).contains(q_lower),
                        func.lower(SipTrunk.trunk_name).contains(q_lower),
                    )
                )
        if status:
            query = query.where(SipTrunk.status == status)
        return query

    @staticmethod
    async def get_by_id(db: AsyncSession, trunk_id: str) -> SipTrunk | None:
        return await db.get(SipTrunk, trunk_id)

    @staticmethod
    async def get_by_trunk_name(db: AsyncSession, trunk_name: str) -> SipTrunk | None:
        normalized = trunk_name.strip().lower()
        result = await db.execute(
            select(SipTrunk).where(func.lower(SipTrunk.trunk_name) == normalized)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def count_filtered(
        db: AsyncSession,
        *,
        q: str | None = None,
        status: str | None = None,
    ) -> int:
        query = SipTrunkRepository._apply_filters(select(SipTrunk), q=q, status=status)
        result = await db.execute(select(func.count()).select_from(query.subquery()))
        return int(result.scalar_one())

    @staticmethod
    async def list_filtered(
        db: AsyncSession,
        *,
        q: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[SipTrunk]:
        query = SipTrunkRepository._apply_filters(select(SipTrunk), q=q, status=status)
        query = query.order_by(SipTrunk.updated_at.desc()).offset(offset)
        if limit is not None:
            query = query.limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def list_options(db: AsyncSession, *, only_enabled: bool = True) -> list[SipTrunk]:
        query = select(SipTrunk)
        if only_enabled:
            query = query.where(SipTrunk.status == "enabled")
        query = query.order_by(SipTrunk.supplier_name.asc(), SipTrunk.trunk_name.asc())
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SipTrunk:
        row = SipTrunk(**data)
        db.add(row)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            _raise_on_trunk_integrity(exc)
        await db.refresh(row)
        return row

    @staticmethod
    async def update(db: AsyncSession, row: SipTrunk, data: dict) -> SipTrunk:
        for key, value in data.items():
            if hasattr(row, key):
                setattr(row, key, value)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            _raise_on_trunk_integrity(exc)
        await db.refresh(row)
        return row

    @staticmethod
    async def delete(db: AsyncSession, row: SipTrunk) -> None:
        await db.delete(row)
        await db.commit()
