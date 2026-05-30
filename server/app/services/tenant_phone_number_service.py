"""
Tenant phone number service — read-only list + tag editing for admin UI.
"""
from math import ceil
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.phone_number import PhoneNumber
from app.repositories.tenant_phone_number_repository import TenantPhoneNumberRepository
from app.schemas.tenant_phone_number import (
    OutboundTimeSlot,
    TenantPhoneNumberListResponse,
    TenantPhoneNumberResponse,
    TenantPhoneNumberTagsUpdate,
)


def _normalize_outbound_time_slots(raw: Any) -> list[OutboundTimeSlot]:
    if not isinstance(raw, list):
        return []
    slots: list[OutboundTimeSlot] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        start = item.get("start")
        end = item.get("end")
        if not start or not end:
            continue
        slots.append(OutboundTimeSlot(start=str(start), end=str(end)))
    return slots


def _to_response(row: PhoneNumber, tags: list[str]) -> TenantPhoneNumberResponse:
    call_types = row.call_types if isinstance(row.call_types, list) else []
    return TenantPhoneNumberResponse(
        id=row.id,
        phone_number=row.phone_number,
        call_types=[t for t in ("inbound", "outbound") if t in call_types],
        tags=tags,
        outbound_time_slots=_normalize_outbound_time_slots(row.outbound_time_slots),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class TenantPhoneNumberService:

    @staticmethod
    async def _tenant_string_id(db: AsyncSession, tenant_pk: int) -> str:
        tenant = await TenantPhoneNumberRepository.get_tenant(db, tenant_pk)
        if tenant is None:
            raise NotFoundError("Tenant not found")
        return tenant.tenant_id

    @staticmethod
    async def list_for_tenant(
        db: AsyncSession,
        tenant_pk: int,
        page: int,
        per_page: int,
        q: str | None = None,
    ) -> TenantPhoneNumberListResponse:
        tenant_string_id = await TenantPhoneNumberService._tenant_string_id(db, tenant_pk)
        total = await TenantPhoneNumberRepository.count_assigned(db, tenant_string_id, q)
        offset = (page - 1) * per_page
        rows = await TenantPhoneNumberRepository.list_assigned(
            db,
            tenant_string_id,
            q=q,
            offset=offset,
            limit=per_page,
        )
        meta_map = await TenantPhoneNumberRepository.get_meta_map(
            db, tenant_pk, [row.id for row in rows]
        )
        items = [
            _to_response(
                row,
                list(meta_map.get(row.id).tags or []) if row.id in meta_map else [],
            )
            for row in rows
        ]
        pages = ceil(total / per_page) if total else 0
        return TenantPhoneNumberListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
        )

    @staticmethod
    async def get_for_tenant(
        db: AsyncSession,
        tenant_pk: int,
        phone_number_id: str,
    ) -> TenantPhoneNumberResponse:
        tenant_string_id = await TenantPhoneNumberService._tenant_string_id(db, tenant_pk)
        row = await TenantPhoneNumberRepository.get_assigned_by_id(
            db, tenant_string_id, phone_number_id
        )
        if row is None:
            raise NotFoundError("Phone number not found")
        meta = await TenantPhoneNumberRepository.get_meta(db, tenant_pk, phone_number_id)
        tags = list(meta.tags or []) if meta else []
        return _to_response(row, tags)

    @staticmethod
    async def update_tags(
        db: AsyncSession,
        tenant_pk: int,
        phone_number_id: str,
        body: TenantPhoneNumberTagsUpdate,
    ) -> TenantPhoneNumberResponse:
        tenant_string_id = await TenantPhoneNumberService._tenant_string_id(db, tenant_pk)
        row = await TenantPhoneNumberRepository.get_assigned_by_id(
            db, tenant_string_id, phone_number_id
        )
        if row is None:
            raise NotFoundError("Phone number not found")
        await TenantPhoneNumberRepository.upsert_tags(
            db, tenant_pk, phone_number_id, body.tags
        )
        await db.commit()
        return _to_response(row, body.tags)
