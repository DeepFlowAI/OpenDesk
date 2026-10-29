"""Online monitor router (SR3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_current_principal, get_db, get_redis, require_permission
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import RESOURCE_SESSION_RECORD

from ..lib.scope import build_report_scope
from ..services import online_monitor_service

router = APIRouter(prefix="/reports/online-monitor", tags=["Reports"])


@router.get("")
async def get_online_monitor(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    principal: EffectivePrincipal = Depends(require_permission("chat.online_monitor.view")),
) -> dict:
    report_scope = await build_report_scope(db, principal, RESOURCE_SESSION_RECORD)
    return await online_monitor_service.get_online_monitor(
        db,
        redis,
        principal.tenant_id,
        report_scope=report_scope,
    )
