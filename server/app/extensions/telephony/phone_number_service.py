"""
Phone number service — business logic for platform DID catalog.
"""
import uuid
from math import ceil
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.models.phone_number import PhoneNumber
from app.repositories.phone_number_repository import PhoneNumberRepository
from app.repositories.tenant_phone_number_repository import TenantPhoneNumberRepository
from app.repositories.tenant_repository import TenantRepository

from .schemas import (
    BatchUpdateFailure,
    BatchUpdateResponse,
    OutboundTimeSlot,
    PhoneNumberBatchPayload,
    PhoneNumberCreate,
    PhoneNumberListResponse,
    PhoneNumberResponse,
    PhoneNumberUpdate,
)
from .sip_trunk_service import SipTrunkService

CALL_TYPE_ORDER = ("inbound", "outbound")


def _normalize_call_types(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return list(CALL_TYPE_ORDER)
    normalized = [t for t in CALL_TYPE_ORDER if t in raw]
    return normalized or list(CALL_TYPE_ORDER)


def _normalize_status_with_tenant(status: str, tenant_id: str | None) -> str:
    """Keep disabled as-is; otherwise sync available/assigned with tenant binding."""
    if status == "disabled":
        return "disabled"
    if tenant_id and status == "available":
        return "assigned"
    if not tenant_id and status == "assigned":
        return "available"
    return status


def _assert_tenant_assignment_allowed(status: str, tenant_id: str | None) -> None:
    if tenant_id and status == "disabled":
        raise ValidationError("Cannot assign tenant to a disabled phone number")


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


def _serialize_outbound_time_slots(slots: list[OutboundTimeSlot]) -> list[dict[str, str]]:
    return [{"start": slot.start, "end": slot.end} for slot in slots]


def _to_response(row: PhoneNumber) -> PhoneNumberResponse:
    trunk = row.trunk
    tenant = row.tenant
    return PhoneNumberResponse(
        id=row.id,
        phone_number=row.phone_number,
        call_types=_normalize_call_types(row.call_types),
        trunk_id=row.trunk_id,
        trunk_name=trunk.trunk_name if trunk else None,
        supplier_name=trunk.supplier_name if trunk else None,
        tenant_id=row.tenant_id,
        tenant_name=tenant.name if tenant else None,
        tenant_status="enabled" if tenant and tenant.is_active else ("disabled" if tenant else None),
        status=row.status,
        remark=row.remark,
        concurrency=row.concurrency,
        called_number_prefix=row.called_number_prefix,
        outbound_time_slots=_normalize_outbound_time_slots(row.outbound_time_slots),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PhoneNumberService:

    @staticmethod
    async def _clear_tenant_meta_if_reassigned(
        db: AsyncSession,
        phone_number_id: str,
        old_tenant_id: str | None,
        new_tenant_id: str | None,
    ) -> bool:
        if old_tenant_id and old_tenant_id != new_tenant_id:
            await TenantPhoneNumberRepository.delete_meta_by_tenant_string_id(
                db, old_tenant_id, phone_number_id
            )
            return True
        return False

    @staticmethod
    def _build_patch(
        record: PhoneNumber,
        payload: PhoneNumberBatchPayload | PhoneNumberUpdate,
        update_fields: dict[str, Any],
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if "call_types" in update_fields and payload.call_types is not None:
            patch["call_types"] = list(payload.call_types)
        if "trunk_id" in update_fields:
            patch["trunk_id"] = payload.trunk_id or None
        if "tenant_id" in update_fields:
            patch["tenant_id"] = payload.tenant_id or None
        if "remark" in update_fields:
            patch["remark"] = (payload.remark or "").strip() or None
        if "status" in update_fields and payload.status is not None:
            patch["status"] = payload.status
        if "concurrency" in update_fields:
            patch["concurrency"] = payload.concurrency
        if "called_number_prefix" in update_fields:
            patch["called_number_prefix"] = payload.called_number_prefix
        if "outbound_time_slots" in update_fields and payload.outbound_time_slots is not None:
            patch["outbound_time_slots"] = _serialize_outbound_time_slots(
                payload.outbound_time_slots
            )
        return patch

    @staticmethod
    async def _validate_and_finalize_patch(
        db: AsyncSession,
        record: PhoneNumber,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        if not patch:
            return patch

        final_trunk_id = patch.get("trunk_id", record.trunk_id)
        final_call_types = patch.get("call_types", _normalize_call_types(record.call_types))
        await SipTrunkService.assert_trunk_assignable(
            db, final_trunk_id, call_types=final_call_types
        )
        if "tenant_id" in patch and patch["tenant_id"]:
            await PhoneNumberService._assert_tenant_assignable(db, patch["tenant_id"])

        next_status = patch.get("status", record.status)
        next_tenant_id = patch.get("tenant_id", record.tenant_id)
        _assert_tenant_assignment_allowed(next_status, next_tenant_id)

        if "status" in patch or "tenant_id" in patch:
            patch["status"] = _normalize_status_with_tenant(next_status, next_tenant_id)
        return patch

    @staticmethod
    async def _apply_phone_number_patch(
        db: AsyncSession,
        record: PhoneNumber,
        patch: dict[str, Any],
    ) -> PhoneNumber:
        old_tenant_id = record.tenant_id
        row = await PhoneNumberRepository.update(db, record, patch)
        if "tenant_id" in patch:
            cleared = await PhoneNumberService._clear_tenant_meta_if_reassigned(
                db, row.id, old_tenant_id, row.tenant_id
            )
            if cleared:
                await db.commit()
        return row

    @staticmethod
    async def _assert_tenant_assignable(db: AsyncSession, tenant_id: str) -> None:
        tenant = await TenantRepository.get_by_tenant_id(db, tenant_id)
        if not tenant:
            raise ValidationError("OpenDesk tenant not found")
        if not tenant.is_active:
            raise ValidationError("OpenDesk tenant is disabled")

    @staticmethod
    async def list_phone_numbers(
        db: AsyncSession,
        page: int,
        per_page: int,
        q: str | None,
        trunk_id: str | None,
        tenant_id: str | None,
        status: str | None,
    ) -> PhoneNumberListResponse:
        total = await PhoneNumberRepository.count_filtered(
            db, q=q, trunk_id=trunk_id, tenant_id=tenant_id, status=status
        )
        offset = (page - 1) * per_page
        items = await PhoneNumberRepository.list_filtered(
            db,
            q=q,
            trunk_id=trunk_id,
            tenant_id=tenant_id,
            status=status,
            offset=offset,
            limit=per_page,
        )
        pages = ceil(total / per_page) if total else 0
        return PhoneNumberListResponse(
            items=[_to_response(item) for item in items],
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
        )

    @staticmethod
    async def list_for_export(
        db: AsyncSession,
        q: str | None,
        trunk_id: str | None,
        tenant_id: str | None,
        status: str | None,
    ) -> list[PhoneNumberResponse]:
        items = await PhoneNumberRepository.list_filtered(
            db,
            q=q,
            trunk_id=trunk_id,
            tenant_id=tenant_id,
            status=status,
        )
        return [_to_response(item) for item in items]

    @staticmethod
    async def get_phone_number(db: AsyncSession, phone_id: str) -> PhoneNumberResponse:
        row = await PhoneNumberRepository.get_by_id(db, phone_id)
        if not row:
            raise NotFoundError("Phone number not found")
        return _to_response(row)

    @staticmethod
    async def create_phone_number(
        db: AsyncSession, payload: PhoneNumberCreate
    ) -> PhoneNumberResponse:
        existing = await PhoneNumberRepository.get_by_phone_number(db, payload.phone_number)
        if existing:
            raise BusinessError(
                "Phone number already exists",
                status_code=409,
                code="DUPLICATE_PHONE_NUMBER",
            )
        await SipTrunkService.assert_trunk_assignable(
            db, payload.trunk_id, call_types=list(payload.call_types)
        )
        if payload.tenant_id:
            await PhoneNumberService._assert_tenant_assignable(db, payload.tenant_id)
        _assert_tenant_assignment_allowed(payload.status, payload.tenant_id)
        final_status = _normalize_status_with_tenant(payload.status, payload.tenant_id)
        row = await PhoneNumberRepository.create(
            db,
            {
                "id": f"pn_{uuid.uuid4().hex[:12]}",
                "phone_number": payload.phone_number.strip(),
                "call_types": list(payload.call_types),
                "trunk_id": payload.trunk_id or None,
                "tenant_id": payload.tenant_id or None,
                "status": final_status,
                "remark": (payload.remark or "").strip() or None,
                "concurrency": payload.concurrency,
                "called_number_prefix": payload.called_number_prefix,
                "outbound_time_slots": _serialize_outbound_time_slots(
                    payload.outbound_time_slots
                ),
            },
        )
        return _to_response(row)

    @staticmethod
    async def update_phone_number(
        db: AsyncSession,
        phone_id: str,
        payload: PhoneNumberUpdate,
        update_fields: dict[str, Any],
    ) -> PhoneNumberResponse:
        row = await PhoneNumberRepository.get_by_id(db, phone_id)
        if not row:
            raise NotFoundError("Phone number not found")

        patch = PhoneNumberService._build_patch(row, payload, update_fields)

        if patch:
            patch = await PhoneNumberService._validate_and_finalize_patch(db, row, patch)
            row = await PhoneNumberService._apply_phone_number_patch(db, row, patch)

        return _to_response(row)

    @staticmethod
    async def delete_phone_number(db: AsyncSession, phone_id: str) -> None:
        row = await PhoneNumberRepository.get_by_id(db, phone_id)
        if not row:
            raise NotFoundError("Phone number not found")
        await PhoneNumberRepository.delete(db, row)

    @staticmethod
    async def _apply_batch_patch(
        db: AsyncSession,
        record: PhoneNumber,
        payload: PhoneNumberBatchPayload,
        update_fields: dict[str, Any],
    ) -> None:
        patch = PhoneNumberService._build_patch(record, payload, update_fields)
        if not patch:
            return
        patch = await PhoneNumberService._validate_and_finalize_patch(db, record, patch)
        await PhoneNumberService._apply_phone_number_patch(db, record, patch)

    @staticmethod
    async def batch_update(
        db: AsyncSession,
        payload: PhoneNumberBatchPayload,
        update_fields: dict[str, Any],
    ) -> BatchUpdateResponse:
        if not any(
            k in update_fields for k in ("call_types", "trunk_id", "tenant_id", "status")
        ):
            raise ValidationError("Select at least one field to update")

        rows = await PhoneNumberRepository.get_many_by_ids(db, payload.ids)
        by_id = {row.id: row for row in rows}

        success = 0
        failures: list[BatchUpdateFailure] = []

        for pid in payload.ids:
            record = by_id.get(pid)
            if not record:
                failures.append(BatchUpdateFailure(id=pid, reason="Phone number not found"))
                continue
            try:
                await PhoneNumberService._apply_batch_patch(
                    db, record, payload, update_fields
                )
                success += 1
            except (BusinessError, ValidationError) as exc:
                failures.append(
                    BatchUpdateFailure(
                        id=pid,
                        phone_number=record.phone_number,
                        reason=exc.message,
                    )
                )

        return BatchUpdateResponse(
            success_count=success,
            fail_count=len(failures),
            failures=failures,
        )
