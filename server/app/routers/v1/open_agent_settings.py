"""
OpenAgent settings router.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.db.deps import (
    get_current_principal_short_session,
    get_db,
    require_permission,
    require_permission_short_session,
)
from app.schemas.open_agent_settings import (
    OpenAgentAgentListResponse,
    OpenAgentAttachmentHandoffStatus,
    OpenAgentConnectionTestRequest,
    OpenAgentConnectionTestResponse,
    OpenAgentSettingsResponse,
    OpenAgentSettingsUpdate,
    VoiceSpeedConnectionTestRequest,
    VoiceSpeedConnectionTestResponse,
    VoiceSpeedSettingsResponse,
    VoiceSpeedSettingsUpdate,
)
from app.schemas.permission import EffectivePrincipal
from app.services.open_agent_settings_service import OpenAgentSettingsService

router = APIRouter(prefix="/open-agent-settings", tags=["OpenAgentSettings"])

OPEN_AGENT_OR_CHANNEL_PERMISSIONS = [
    "settings.open_agent.manage",
    "chat.admin.channel.manage",
]


async def require_open_agent_or_channel_short_session(
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
) -> EffectivePrincipal:
    """Authorize agent lookup without retaining the auth DB session."""
    if not principal.has_any_permission(OPEN_AGENT_OR_CHANNEL_PERMISSIONS):
        raise ForbiddenError("Permission denied")
    return principal


@router.get("", response_model=OpenAgentSettingsResponse)
async def get_open_agent_settings(
    principal: EffectivePrincipal = Depends(require_permission("settings.open_agent.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Get OpenAgent settings for the current tenant."""
    return await OpenAgentSettingsService.get_settings(db, principal.tenant_id)


@router.put("", response_model=OpenAgentSettingsResponse)
async def update_open_agent_settings(
    body: OpenAgentSettingsUpdate,
    principal: EffectivePrincipal = Depends(require_permission("settings.open_agent.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Update OpenAgent settings for the current tenant."""
    return await OpenAgentSettingsService.update_settings(db, principal.tenant_id, body)


@router.post("/test", response_model=OpenAgentConnectionTestResponse)
async def test_open_agent_connection(
    body: OpenAgentConnectionTestRequest,
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("settings.open_agent.manage")
    ),
):
    """Test OpenAgent connection through the backend."""
    return await OpenAgentSettingsService.test_connection_managed(principal.tenant_id, body)


@router.get("/voice-speed", response_model=VoiceSpeedSettingsResponse)
async def get_voice_speed_settings(
    principal: EffectivePrincipal = Depends(require_permission("settings.open_agent.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Get VoiceSpeed settings for the current tenant."""
    return await OpenAgentSettingsService.get_voice_speed_settings(db, principal.tenant_id)


@router.put("/voice-speed", response_model=VoiceSpeedSettingsResponse)
async def update_voice_speed_settings(
    body: VoiceSpeedSettingsUpdate,
    principal: EffectivePrincipal = Depends(require_permission("settings.open_agent.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Update VoiceSpeed settings for the current tenant."""
    return await OpenAgentSettingsService.update_voice_speed_settings(db, principal.tenant_id, body)


@router.post("/voice-speed/test", response_model=VoiceSpeedConnectionTestResponse)
async def test_voice_speed_connection(
    body: VoiceSpeedConnectionTestRequest,
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("settings.open_agent.manage")
    ),
):
    """Test VoiceSpeed connection through the backend."""
    return await OpenAgentSettingsService.test_voice_speed_connection_managed(
        principal.tenant_id, body
    )


@router.get("/agents", response_model=OpenAgentAgentListResponse)
async def list_open_agent_agents(
    principal: EffectivePrincipal = Depends(require_open_agent_or_channel_short_session),
):
    """List active OpenAgent agents through saved tenant credentials."""
    return await OpenAgentSettingsService.list_active_agents_managed(principal.tenant_id)


@router.get(
    "/agents/{agent_id}/attachment-handoff",
    response_model=OpenAgentAttachmentHandoffStatus,
)
async def get_open_agent_attachment_handoff_status(
    agent_id: int,
    principal: EffectivePrincipal = Depends(require_open_agent_or_channel_short_session),
):
    """Check whether the selected agent supports attachment handoff."""
    return await OpenAgentSettingsService.get_attachment_handoff_status_managed(
        principal.tenant_id,
        agent_id,
    )
