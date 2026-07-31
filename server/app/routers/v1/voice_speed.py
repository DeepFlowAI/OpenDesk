"""
VoiceSpeed proxy router — read-only agent listing for flow/routing config.
"""
from fastapi import APIRouter, Depends

from app.db.deps import require_permission_short_session
from app.schemas.open_agent_settings import VoiceSpeedAgentListResponse
from app.schemas.permission import EffectivePrincipal
from app.services.open_agent_settings_service import OpenAgentSettingsService

router = APIRouter(prefix="/voice-speed", tags=["VoiceSpeed"])


@router.get("/agents", response_model=VoiceSpeedAgentListResponse)
async def list_voice_speed_agents(
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.admin.flow.manage")
    ),
):
    """List enabled VoiceSpeed agents through saved tenant credentials."""
    return await OpenAgentSettingsService.list_voice_speed_agents_managed(principal.tenant_id)
