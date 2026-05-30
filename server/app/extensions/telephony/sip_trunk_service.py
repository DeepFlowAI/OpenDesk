"""
SIP Trunk service — business logic for platform trunk catalog.
"""
import logging
import uuid
from math import ceil

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.repositories.phone_number_repository import PhoneNumberRepository
from app.repositories.sip_trunk_repository import SipTrunkRepository

from .schemas import (
    SipTrunkCreate,
    SipTrunkListResponse,
    SipTrunkOption,
    SipTrunkResponse,
    SipTrunkUpdate,
)


logger = logging.getLogger(__name__)


def _to_response(row) -> SipTrunkResponse:
    endpoints = row.peer_endpoints or []
    return SipTrunkResponse(
        id=row.id,
        supplier_name=row.supplier_name,
        trunk_name=row.trunk_name,
        trunk_types=list(row.trunk_types or []),
        remark=row.remark,
        status=row.status,
        peer_endpoints=endpoints,
        peer_endpoint_count=len(endpoints),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _notify_catalog_changed() -> None:
    """Best-effort push of the updated SipTrunk set to FlowKit's Catalog.

    Runs after every CUD on a trunk so multi-trunk deployments see the new
    config immediately, no restart. Failures are logged and swallowed —
    the heartbeat-driven sync will eventually catch up on its own (within
    the heartbeat interval, ~30s).
    """
    try:
        from app.services.call_center.orchestrator import get_orchestrator

        await get_orchestrator().reload_catalog()
    except Exception:  # noqa: BLE001
        logger.exception("orchestrator.reload_catalog after trunk write failed")


class SipTrunkService:

    @staticmethod
    async def list_trunks(
        db: AsyncSession,
        page: int,
        per_page: int,
        q: str | None = None,
        status: str | None = None,
    ) -> SipTrunkListResponse:
        total = await SipTrunkRepository.count_filtered(db, q=q, status=status)
        offset = (page - 1) * per_page
        items = await SipTrunkRepository.list_filtered(
            db, q=q, status=status, offset=offset, limit=per_page
        )
        pages = ceil(total / per_page) if total else 0
        return SipTrunkListResponse(
            items=[_to_response(item) for item in items],
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
        )

    @staticmethod
    async def list_all_for_export(
        db: AsyncSession,
        q: str | None = None,
        status: str | None = None,
    ) -> list[SipTrunkResponse]:
        items = await SipTrunkRepository.list_filtered(db, q=q, status=status)
        return [_to_response(item) for item in items]

    @staticmethod
    async def list_options(db: AsyncSession, only_enabled: bool = True) -> list[SipTrunkOption]:
        items = await SipTrunkRepository.list_options(db, only_enabled=only_enabled)
        return [
            SipTrunkOption(
                id=it.id,
                trunk_name=it.trunk_name,
                supplier_name=it.supplier_name,
                status=it.status,
                trunk_types=list(it.trunk_types or []),
            )
            for it in items
        ]

    @staticmethod
    async def get_trunk(db: AsyncSession, trunk_id: str) -> SipTrunkResponse:
        row = await SipTrunkRepository.get_by_id(db, trunk_id)
        if not row:
            raise NotFoundError("SIP trunk not found")
        return _to_response(row)

    @staticmethod
    async def create_trunk(db: AsyncSession, payload: SipTrunkCreate) -> SipTrunkResponse:
        existing = await SipTrunkRepository.get_by_trunk_name(db, payload.trunk_name)
        if existing:
            raise BusinessError(
                "Trunk name already exists",
                status_code=409,
                code="DUPLICATE_TRUNK_NAME",
            )
        row = await SipTrunkRepository.create(
            db,
            {
                "id": f"trunk_{uuid.uuid4().hex[:12]}",
                "supplier_name": payload.supplier_name.strip(),
                "trunk_name": payload.trunk_name.strip(),
                "trunk_types": list(payload.trunk_types),
                "remark": (payload.remark or "").strip() or None,
                "status": payload.status,
                "peer_endpoints": [ep.model_dump() for ep in payload.peer_endpoints],
            },
        )
        await _notify_catalog_changed()
        return _to_response(row)

    @staticmethod
    async def update_trunk(
        db: AsyncSession, trunk_id: str, payload: SipTrunkUpdate
    ) -> SipTrunkResponse:
        row = await SipTrunkRepository.get_by_id(db, trunk_id)
        if not row:
            raise NotFoundError("SIP trunk not found")
        existing = await SipTrunkRepository.get_by_trunk_name(db, payload.trunk_name)
        if existing and existing.id != trunk_id:
            raise BusinessError(
                "Trunk name already exists",
                status_code=409,
                code="DUPLICATE_TRUNK_NAME",
            )
        row = await SipTrunkRepository.update(
            db,
            row,
            {
                "supplier_name": payload.supplier_name.strip(),
                "trunk_name": payload.trunk_name.strip(),
                "trunk_types": list(payload.trunk_types),
                "remark": (payload.remark or "").strip() or None,
                "status": payload.status,
                "peer_endpoints": [ep.model_dump() for ep in payload.peer_endpoints],
            },
        )
        await _notify_catalog_changed()
        return _to_response(row)

    @staticmethod
    async def delete_trunk(db: AsyncSession, trunk_id: str) -> None:
        row = await SipTrunkRepository.get_by_id(db, trunk_id)
        if not row:
            raise NotFoundError("SIP trunk not found")
        count = await PhoneNumberRepository.count_by_trunk_id(db, trunk_id)
        if count > 0:
            raise BusinessError(
                "Trunk still has assigned phone numbers; reassign or remove them first",
                status_code=409,
                code="TRUNK_HAS_NUMBERS",
            )
        await SipTrunkRepository.delete(db, row)
        await _notify_catalog_changed()

    @staticmethod
    async def assert_trunk_assignable(
        db: AsyncSession,
        trunk_id: str | None,
        *,
        call_types: list[str] | None = None,
    ) -> None:
        if not trunk_id:
            return
        row = await SipTrunkRepository.get_by_id(db, trunk_id)
        if not row:
            raise ValidationError("SIP trunk not found")
        if row.status != "enabled":
            raise ValidationError("SIP trunk is disabled")
        if call_types:
            trunk_types = set(row.trunk_types or [])
            if not set(call_types).issubset(trunk_types):
                raise ValidationError("Call types are not supported by the selected SIP trunk")
