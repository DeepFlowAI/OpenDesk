"""LingoMaster management router."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_permission
from app.schemas.lingomaster import LingoMasterSettingsResponse, LingoMasterSettingsUpdate
from app.schemas.permission import EffectivePrincipal
from app.services.lingomaster_settings_service import LingoMasterSettingsService

LINGOMASTER_MANAGE_PERMISSION = "chat.admin.lingomaster.manage"

router = APIRouter(prefix="/lingomaster", tags=["LingoMaster"])


@router.get("/settings", response_model=LingoMasterSettingsResponse)
async def get_lingomaster_settings(
    principal: EffectivePrincipal = Depends(require_permission(LINGOMASTER_MANAGE_PERMISSION)),
    db: AsyncSession = Depends(get_db),
) -> LingoMasterSettingsResponse:
    """Read the current tenant's translation settings."""
    return await LingoMasterSettingsService.get_settings(db, principal.tenant_id)


@router.put("/settings", response_model=LingoMasterSettingsResponse)
async def update_lingomaster_settings(
    body: LingoMasterSettingsUpdate,
    principal: EffectivePrincipal = Depends(require_permission(LINGOMASTER_MANAGE_PERMISSION)),
    db: AsyncSession = Depends(get_db),
) -> LingoMasterSettingsResponse:
    """Update the current tenant's translation settings."""
    return await LingoMasterSettingsService.update_settings(db, principal.tenant_id, body)
