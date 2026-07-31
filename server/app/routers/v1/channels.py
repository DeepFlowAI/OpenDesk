"""
Channel router — CRUD endpoints for channel management
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.db.deps import get_current_principal_short_session, get_db, require_all_permissions
from app.schemas.channel import (
    ChannelCreate,
    ChannelUpdate,
    ChannelResponse,
)
from app.schemas.permission import EffectivePrincipal
from app.services.channel_service import ChannelService

router = APIRouter(prefix="/channels", tags=["Channels"])
CHANNEL_MANAGEMENT_PERMISSIONS = [
    "admin.access",
    "chat.admin.channel.manage",
]
require_channel_management = require_all_permissions(CHANNEL_MANAGEMENT_PERMISSIONS)


async def require_channel_management_short_session(
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
) -> EffectivePrincipal:
    """Authorize channel writes without retaining the auth DB session."""
    if not principal.has_all_permissions(CHANNEL_MANAGEMENT_PERMISSIONS):
        raise ForbiddenError("Permission denied")
    return principal


@router.get("", response_model=list[ChannelResponse])
async def list_channels(
    principal: EffectivePrincipal = Depends(require_channel_management),
    db: AsyncSession = Depends(get_db),
):
    """List all channels for the current tenant."""
    return await ChannelService.list_by_tenant(db, principal.tenant_id)


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreate,
    principal: EffectivePrincipal = Depends(require_channel_management_short_session),
):
    """Create a new channel."""
    return await ChannelService.create_managed(principal.tenant_id, body)


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: int,
    principal: EffectivePrincipal = Depends(require_channel_management),
    db: AsyncSession = Depends(get_db),
):
    """Get channel by ID."""
    return await ChannelService.get_by_id(db, channel_id, principal.tenant_id)


@router.post("/{channel_id}/copy", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def copy_channel(
    channel_id: int,
    principal: EffectivePrincipal = Depends(require_channel_management),
    db: AsyncSession = Depends(get_db),
):
    """Copy a channel configuration into a new channel."""
    return await ChannelService.copy(db, channel_id, principal.tenant_id)


@router.put("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    body: ChannelUpdate,
    principal: EffectivePrincipal = Depends(require_channel_management_short_session),
):
    """Update channel configuration."""
    return await ChannelService.update_managed(channel_id, principal.tenant_id, body)


@router.delete("/{channel_id}", status_code=status.HTTP_200_OK)
async def delete_channel(
    channel_id: int,
    principal: EffectivePrincipal = Depends(require_channel_management),
    db: AsyncSession = Depends(get_db),
):
    """Delete channel."""
    await ChannelService.delete(db, channel_id, principal.tenant_id)
    return {"message": "Deleted successfully"}


@router.post("/{channel_id}/rotate-key", response_model=ChannelResponse)
async def rotate_channel_key(
    channel_id: int,
    principal: EffectivePrincipal = Depends(require_channel_management),
    db: AsyncSession = Depends(get_db),
):
    """Rotate a channel's public access key."""
    return await ChannelService.rotate_key(db, channel_id, principal.tenant_id)
