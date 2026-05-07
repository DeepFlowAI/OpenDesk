"""
Channel router — CRUD endpoints for channel management
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.channel import (
    ChannelCreate,
    ChannelUpdate,
    ChannelResponse,
)
from app.services.channel_service import ChannelService

router = APIRouter(prefix="/channels", tags=["Channels"])


@router.get("", response_model=list[ChannelResponse])
async def list_channels(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all channels for the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await ChannelService.list_by_tenant(db, tenant_id)


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new channel."""
    tenant_id = current_user["tenant_id"]
    return await ChannelService.create(db, tenant_id, body)


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get channel by ID."""
    tenant_id = current_user["tenant_id"]
    return await ChannelService.get_by_id(db, channel_id, tenant_id)


@router.put("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    body: ChannelUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update channel configuration."""
    tenant_id = current_user["tenant_id"]
    return await ChannelService.update(db, channel_id, tenant_id, body)


@router.delete("/{channel_id}", status_code=status.HTTP_200_OK)
async def delete_channel(
    channel_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete channel."""
    tenant_id = current_user["tenant_id"]
    await ChannelService.delete(db, channel_id, tenant_id)
    return {"message": "Deleted successfully"}
