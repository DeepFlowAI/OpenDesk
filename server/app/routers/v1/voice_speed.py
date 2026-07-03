"""
VoiceSpeed proxy router — read-only agent listing for flow/routing config.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_permission
from app.schemas.open_agent_settings import VoiceSpeedAgentListResponse
from app.schemas.permission import EffectivePrincipal
from app.services.open_agent_settings_service import OpenAgentSettingsService

router = APIRouter(prefix="/voice-speed", tags=["VoiceSpeed"])


@router.get("/agents", response_model=VoiceSpeedAgentListResponse)
async def list_voice_speed_agents(
    principal: EffectivePrincipal = Depends(require_permission("call.admin.flow.manage")),
    db: AsyncSession = Depends(get_db),
):
    """List enabled VoiceSpeed agents through saved tenant credentials."""
    return await OpenAgentSettingsService.list_voice_speed_agents(db, principal.tenant_id)
