"""
Tenant phone number repository — list assigned numbers and manage tags.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.phone_number import PhoneNumber
from app.models.phone_number_tenant_meta import PhoneNumberTenantMeta
from app.models.tenant import Tenant


class TenantPhoneNumberRepository:

    @staticmethod
    async def get_tenant(db: AsyncSession, tenant_pk: int) -> Tenant | None:
        return await db.get(Tenant, tenant_pk)

    @staticmethod
    def _assigned_query(tenant_string_id: str, q: str | None = None):
        query = (
            select(PhoneNumber)
            .where(
                PhoneNumber.tenant_id == tenant_string_id,
                PhoneNumber.status != "disabled",
            )
        )
        if q:
            q_str = q.strip()
            if q_str:
                query = query.where(PhoneNumber.phone_number.contains(q_str))
        return query

    @staticmethod
    async def count_assigned(
        db: AsyncSession,
        tenant_string_id: str,
        q: str | None = None,
    ) -> int:
        query = TenantPhoneNumberRepository._assigned_query(tenant_string_id, q)
        result = await db.execute(select(func.count()).select_from(query.subquery()))
        return int(result.scalar_one())

    @staticmethod
    async def list_assigned(
        db: AsyncSession,
        tenant_string_id: str,
        *,
        q: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[PhoneNumber]:
        query = (
            TenantPhoneNumberRepository._assigned_query(tenant_string_id, q)
            .order_by(PhoneNumber.phone_number.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_assigned_by_id(
        db: AsyncSession,
        tenant_string_id: str,
        phone_number_id: str,
    ) -> PhoneNumber | None:
        result = await db.execute(
            select(PhoneNumber).where(
                PhoneNumber.id == phone_number_id,
                PhoneNumber.tenant_id == tenant_string_id,
                PhoneNumber.status != "disabled",
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_meta_map(
        db: AsyncSession,
        tenant_pk: int,
        phone_number_ids: list[str],
    ) -> dict[str, PhoneNumberTenantMeta]:
        if not phone_number_ids:
            return {}
        result = await db.execute(
            select(PhoneNumberTenantMeta).where(
                PhoneNumberTenantMeta.tenant_id == tenant_pk,
                PhoneNumberTenantMeta.phone_number_id.in_(phone_number_ids),
            )
        )
        rows = list(result.scalars().all())
        return {row.phone_number_id: row for row in rows}

    @staticmethod
    async def get_meta(
        db: AsyncSession,
        tenant_pk: int,
        phone_number_id: str,
    ) -> PhoneNumberTenantMeta | None:
        result = await db.execute(
            select(PhoneNumberTenantMeta).where(
                PhoneNumberTenantMeta.tenant_id == tenant_pk,
                PhoneNumberTenantMeta.phone_number_id == phone_number_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_tags(
        db: AsyncSession,
        tenant_pk: int,
        phone_number_id: str,
        tags: list[str],
    ) -> PhoneNumberTenantMeta:
        row = await TenantPhoneNumberRepository.get_meta(db, tenant_pk, phone_number_id)
        if row is None:
            row = PhoneNumberTenantMeta(
                tenant_id=tenant_pk,
                phone_number_id=phone_number_id,
                tags=tags,
            )
            db.add(row)
        else:
            row.tags = tags
        return row

    @staticmethod
    async def delete_meta_for_tenant_phone(
        db: AsyncSession,
        tenant_pk: int,
        phone_number_id: str,
    ) -> None:
        row = await TenantPhoneNumberRepository.get_meta(db, tenant_pk, phone_number_id)
        if row is None:
            return
        await db.delete(row)

    @staticmethod
    async def delete_meta_by_tenant_string_id(
        db: AsyncSession,
        tenant_string_id: str,
        phone_number_id: str,
    ) -> None:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_string_id))
        ).scalar_one_or_none()
        if tenant is None:
            return
        await TenantPhoneNumberRepository.delete_meta_for_tenant_phone(
            db, tenant.id, phone_number_id
        )
