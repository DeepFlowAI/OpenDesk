"""
OpenAgent settings router.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_current_user, get_db
from app.schemas.open_agent_settings import (
    OpenAgentAgentListResponse,
    OpenAgentConnectionTestRequest,
    OpenAgentConnectionTestResponse,
    OpenAgentSettingsResponse,
    OpenAgentSettingsUpdate,
)
from app.services.open_agent_settings_service import OpenAgentSettingsService

router = APIRouter(prefix="/open-agent-settings", tags=["OpenAgentSettings"])


@router.get("", response_model=OpenAgentSettingsResponse)
async def get_open_agent_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get OpenAgent settings for the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await OpenAgentSettingsService.get_settings(db, tenant_id)


@router.put("", response_model=OpenAgentSettingsResponse)
async def update_open_agent_settings(
    body: OpenAgentSettingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update OpenAgent settings for the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await OpenAgentSettingsService.update_settings(db, tenant_id, body)


@router.post("/test", response_model=OpenAgentConnectionTestResponse)
async def test_open_agent_connection(
    body: OpenAgentConnectionTestRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test OpenAgent connection through the backend."""
    tenant_id = current_user["tenant_id"]
    return await OpenAgentSettingsService.test_connection(db, tenant_id, body)


@router.get("/agents", response_model=OpenAgentAgentListResponse)
async def list_open_agent_agents(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List active OpenAgent agents through saved tenant credentials."""
    tenant_id = current_user["tenant_id"]
    return await OpenAgentSettingsService.list_active_agents(db, tenant_id)
