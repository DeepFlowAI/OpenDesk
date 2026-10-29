"""Call monitor router."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_current_principal, get_db, require_permission
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import RESOURCE_CALL_RECORD

from ..lib.scope import build_report_scope
from ..schemas import CallMonitorResponse
from ..services import call_monitor_service

router = APIRouter(prefix="/reports/call-monitor", tags=["Reports"])


@router.get("", response_model=CallMonitorResponse)
async def get_call_monitor(
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.monitor.view")),
) -> dict:
    report_scope = await build_report_scope(db, principal, RESOURCE_CALL_RECORD)
    return await call_monitor_service.get_call_monitor(
        db,
        principal.tenant_id,
        report_scope=report_scope,
    )
