"""
System settings router
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user, require_permission
from app.schemas.permission import EffectivePrincipal
from app.schemas.system_settings import (
    SystemSettingsUpdate,
    OrganizationSettingsUpdate,
    CallTranscriptionSettingsUpdate,
    SystemSettingsResponse,
)
from app.schemas.call_prompt_tone import (
    CallPromptToneSettingsResponse,
    CallPromptToneSettingsUpdate,
)
from app.services.system_settings_service import SystemSettingsService
from app.services.call_prompt_tone_service import CallPromptToneService

CALL_SETTINGS_PERMISSION = "call.admin.settings.manage"

router = APIRouter(prefix="/system-settings", tags=["SystemSettings"])


@router.get("", response_model=SystemSettingsResponse)
async def get_system_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get system settings for the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await SystemSettingsService.get_settings(db, tenant_id)


@router.put("", response_model=SystemSettingsResponse)
async def update_system_settings(
    body: SystemSettingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update system settings for the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await SystemSettingsService.update_settings(db, tenant_id, body)


@router.put("/organization", response_model=SystemSettingsResponse)
async def update_organization_settings(
    body: OrganizationSettingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle organization feature for the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await SystemSettingsService.update_organization_settings(db, tenant_id, body)


@router.put("/call-transcription", response_model=SystemSettingsResponse)
async def update_call_transcription_settings(
    body: CallTranscriptionSettingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle agent-workstation live transcription for the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await SystemSettingsService.update_call_transcription(db, tenant_id, body.enabled)


@router.get("/call-prompt-tones", response_model=CallPromptToneSettingsResponse)
async def get_call_prompt_tones(
    principal: EffectivePrincipal = Depends(require_permission(CALL_SETTINGS_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    """Read the four customer-facing call prompt tones for the current tenant."""
    return await CallPromptToneService.get_settings(db, principal.tenant_id)


@router.put("/call-prompt-tones", response_model=CallPromptToneSettingsResponse)
async def update_call_prompt_tones(
    body: CallPromptToneSettingsUpdate,
    principal: EffectivePrincipal = Depends(require_permission(CALL_SETTINGS_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    """Save the four customer-facing call prompt tones for the current tenant."""
    return await CallPromptToneService.update_settings(db, principal.tenant_id, body)
