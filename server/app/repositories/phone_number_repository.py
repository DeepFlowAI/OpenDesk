"""
Phone number repository
"""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessError
from app.models.phone_number import PhoneNumber


UNASSIGNED = "unassigned"


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = exc.orig
    if orig is not None:
        sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        if sqlstate == "23505":
            return True
    message = str(exc).lower()
    return "unique" in message or "duplicate" in message


def _raise_on_phone_integrity(exc: IntegrityError) -> None:
    if _is_unique_violation(exc):
        raise BusinessError(
            "Phone number already exists",
            status_code=409,
            code="DUPLICATE_PHONE_NUMBER",
        ) from exc
    raise exc


class PhoneNumberRepository:

    @staticmethod
    def _apply_filters(
        query,
        *,
        q: str | None = None,
        trunk_id: str | None = None,
        tenant_id: str | None = None,
        status: str | None = None,
    ):
        if q:
            q_str = q.strip()
            if q_str:
                query = query.where(PhoneNumber.phone_number.contains(q_str))
        if trunk_id:
            if trunk_id == UNASSIGNED:
                query = query.where(PhoneNumber.trunk_id.is_(None))
            else:
                query = query.where(PhoneNumber.trunk_id == trunk_id)
        if tenant_id:
            if tenant_id == UNASSIGNED:
                query = query.where(PhoneNumber.tenant_id.is_(None))
            else:
                query = query.where(PhoneNumber.tenant_id == tenant_id)
        if status:
            query = query.where(PhoneNumber.status == status)
        return query

    @staticmethod
    async def get_by_id(db: AsyncSession, phone_id: str) -> PhoneNumber | None:
        result = await db.execute(
            select(PhoneNumber)
            .options(selectinload(PhoneNumber.trunk), selectinload(PhoneNumber.tenant))
            .where(PhoneNumber.id == phone_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_phone_number(db: AsyncSession, phone_number: str) -> PhoneNumber | None:
        result = await db.execute(
            select(PhoneNumber).where(PhoneNumber.phone_number == phone_number.strip())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def count_by_trunk_id(db: AsyncSession, trunk_id: str) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(PhoneNumber)
            .where(PhoneNumber.trunk_id == trunk_id)
        )
        return int(result.scalar_one())

    @staticmethod
    async def count_filtered(
        db: AsyncSession,
        *,
        q: str | None = None,
        trunk_id: str | None = None,
        tenant_id: str | None = None,
        status: str | None = None,
    ) -> int:
        query = PhoneNumberRepository._apply_filters(select(PhoneNumber), q=q, trunk_id=trunk_id, tenant_id=tenant_id, status=status)
        result = await db.execute(select(func.count()).select_from(query.subquery()))
        return int(result.scalar_one())

    @staticmethod
    async def list_filtered(
        db: AsyncSession,
        *,
        q: str | None = None,
        trunk_id: str | None = None,
        tenant_id: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[PhoneNumber]:
        query = (
            select(PhoneNumber)
            .options(selectinload(PhoneNumber.trunk), selectinload(PhoneNumber.tenant))
        )
        query = PhoneNumberRepository._apply_filters(
            query, q=q, trunk_id=trunk_id, tenant_id=tenant_id, status=status
        )
        query = query.order_by(PhoneNumber.updated_at.desc()).offset(offset)
        if limit is not None:
            query = query.limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_many_by_ids(db: AsyncSession, ids: list[str]) -> list[PhoneNumber]:
        if not ids:
            return []
        result = await db.execute(
            select(PhoneNumber)
            .options(selectinload(PhoneNumber.trunk), selectinload(PhoneNumber.tenant))
            .where(PhoneNumber.id.in_(ids))
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> PhoneNumber:
        row = PhoneNumber(**data)
        db.add(row)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            _raise_on_phone_integrity(exc)
        loaded = await PhoneNumberRepository.get_by_id(db, row.id)
        if loaded is None:
            raise RuntimeError(f"Phone number {row.id} missing after create")
        return loaded

    @staticmethod
    async def update(db: AsyncSession, row: PhoneNumber, data: dict) -> PhoneNumber:
        for key, value in data.items():
            if hasattr(row, key):
                setattr(row, key, value)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            _raise_on_phone_integrity(exc)
        loaded = await PhoneNumberRepository.get_by_id(db, row.id)
        if loaded is None:
            raise RuntimeError(f"Phone number {row.id} missing after update")
        return loaded

    @staticmethod
    async def delete(db: AsyncSession, row: PhoneNumber) -> None:
        await db.delete(row)
        await db.commit()
