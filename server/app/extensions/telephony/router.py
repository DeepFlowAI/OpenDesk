"""
Telephony catalog routers — SIP Trunk and phone number APIs for Tenant Platform.

Authenticated via X-API-Key (same key as /api/v1/tenants).
"""
import csv
import hmac
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import UnauthorizedError
from app.db.deps import get_db

from .phone_number_service import PhoneNumberService
from .schemas import (
    BatchUpdateResponse,
    PhoneNumberBatchPayload,
    PhoneNumberCreate,
    PhoneNumberListResponse,
    PhoneNumberResponse,
    PhoneNumberUpdate,
    SipTrunkCreate,
    SipTrunkListResponse,
    SipTrunkOption,
    SipTrunkResponse,
    SipTrunkUpdate,
)
from .sip_trunk_service import SipTrunkService


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    expected = settings.TENANT_API_KEY or ""
    if not hmac.compare_digest(x_api_key.strip(), expected):
        raise UnauthorizedError("Invalid or missing API Key")
    return x_api_key


sip_trunks_router = APIRouter(
    prefix="/sip-trunks",
    tags=["SIP Trunks"],
    dependencies=[Depends(verify_api_key)],
)

phone_numbers_router = APIRouter(
    prefix="/phone-numbers",
    tags=["Phone Numbers"],
    dependencies=[Depends(verify_api_key)],
)


@sip_trunks_router.get("", response_model=SipTrunkListResponse)
async def list_sip_trunks(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> SipTrunkListResponse:
    return await SipTrunkService.list_trunks(db, page=page, per_page=per_page, q=q, status=status)


@sip_trunks_router.get("/options", response_model=list[SipTrunkOption])
async def list_sip_trunk_options(
    db: AsyncSession = Depends(get_db),
) -> list[SipTrunkOption]:
    return await SipTrunkService.list_options(db, only_enabled=True)


@sip_trunks_router.get("/export")
async def export_sip_trunks(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    items = await SipTrunkService.list_all_for_export(db, q=q, status=status)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "supplier_name",
            "trunk_name",
            "trunk_types",
            "remark",
            "status",
            "peer_endpoints",
            "updated_at",
        ]
    )
    for it in items:
        endpoints = ";".join(f"{ep.ip}:{ep.port}" for ep in it.peer_endpoints)
        writer.writerow(
            [
                it.supplier_name,
                it.trunk_name,
                ";".join(it.trunk_types),
                it.remark or "",
                it.status,
                endpoints,
                it.updated_at.isoformat() if it.updated_at else "",
            ]
        )
    csv_bytes = buffer.getvalue().encode("utf-8-sig")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    filename = f"sip-trunks-{timestamp}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@sip_trunks_router.post("", response_model=SipTrunkResponse, status_code=status.HTTP_201_CREATED)
async def create_sip_trunk(
    payload: SipTrunkCreate,
    db: AsyncSession = Depends(get_db),
) -> SipTrunkResponse:
    return await SipTrunkService.create_trunk(db, payload)


@sip_trunks_router.get("/{trunk_id}", response_model=SipTrunkResponse)
async def get_sip_trunk(
    trunk_id: str,
    db: AsyncSession = Depends(get_db),
) -> SipTrunkResponse:
    return await SipTrunkService.get_trunk(db, trunk_id)


@sip_trunks_router.put("/{trunk_id}", response_model=SipTrunkResponse)
async def update_sip_trunk(
    trunk_id: str,
    payload: SipTrunkUpdate,
    db: AsyncSession = Depends(get_db),
) -> SipTrunkResponse:
    return await SipTrunkService.update_trunk(db, trunk_id, payload)


@sip_trunks_router.delete("/{trunk_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sip_trunk(
    trunk_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await SipTrunkService.delete_trunk(db, trunk_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@phone_numbers_router.get("", response_model=PhoneNumberListResponse)
async def list_phone_numbers(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    trunk_id: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> PhoneNumberListResponse:
    return await PhoneNumberService.list_phone_numbers(
        db,
        page=page,
        per_page=per_page,
        q=q,
        trunk_id=trunk_id,
        tenant_id=tenant_id,
        status=status,
    )


@phone_numbers_router.get("/export")
async def export_phone_numbers(
    q: str | None = Query(default=None),
    trunk_id: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    items = await PhoneNumberService.list_for_export(
        db,
        q=q,
        trunk_id=trunk_id,
        tenant_id=tenant_id,
        status=status,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "phone_number",
            "call_types",
            "trunk_name",
            "tenant_id",
            "tenant_name",
            "status",
            "remark",
            "concurrency",
            "called_number_prefix",
            "outbound_time_slots",
            "updated_at",
        ]
    )
    for it in items:
        slots = ";".join(f"{slot.start}-{slot.end}" for slot in it.outbound_time_slots)
        writer.writerow(
            [
                it.phone_number,
                ";".join(it.call_types),
                it.trunk_name or "",
                it.tenant_id or "",
                it.tenant_name or "",
                it.status,
                it.remark or "",
                it.concurrency if it.concurrency is not None else "",
                it.called_number_prefix or "",
                slots,
                it.updated_at.isoformat() if it.updated_at else "",
            ]
        )
    csv_bytes = buffer.getvalue().encode("utf-8-sig")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    filename = f"phone-numbers-{timestamp}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@phone_numbers_router.post("/batch-update", response_model=BatchUpdateResponse)
async def batch_update_phone_numbers(
    payload: PhoneNumberBatchPayload,
    db: AsyncSession = Depends(get_db),
) -> BatchUpdateResponse:
    update_fields = payload.model_dump(exclude_unset=True)
    update_fields.pop("ids", None)
    return await PhoneNumberService.batch_update(db, payload, update_fields=update_fields)


@phone_numbers_router.post("", response_model=PhoneNumberResponse, status_code=status.HTTP_201_CREATED)
async def create_phone_number(
    payload: PhoneNumberCreate,
    db: AsyncSession = Depends(get_db),
) -> PhoneNumberResponse:
    return await PhoneNumberService.create_phone_number(db, payload)


@phone_numbers_router.get("/{phone_id}", response_model=PhoneNumberResponse)
async def get_phone_number(
    phone_id: str,
    db: AsyncSession = Depends(get_db),
) -> PhoneNumberResponse:
    return await PhoneNumberService.get_phone_number(db, phone_id)


@phone_numbers_router.put("/{phone_id}", response_model=PhoneNumberResponse)
async def update_phone_number(
    phone_id: str,
    payload: PhoneNumberUpdate,
    db: AsyncSession = Depends(get_db),
) -> PhoneNumberResponse:
    update_fields = payload.model_dump(exclude_unset=True)
    return await PhoneNumberService.update_phone_number(
        db, phone_id, payload, update_fields=update_fields
    )


@phone_numbers_router.delete("/{phone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_phone_number(
    phone_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await PhoneNumberService.delete_phone_number(db, phone_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
