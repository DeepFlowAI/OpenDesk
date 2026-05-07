"""
Public API router — endpoints accessible without authentication.

Used by the visitor-facing chat widget to fetch channel config, messages, and files.
"""
from fastapi import APIRouter, Depends, File, Query, UploadFile
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_redis
from app.schemas.channel import ChannelPublicResponse
from app.schemas.conversation_file import ConversationFileAccessResponse, ConversationFileUploadResponse
from app.schemas.message import MessageListResponse, VisitorConversationHistoryResponse
from app.services.channel_service import ChannelService
from app.services.conversation_file_service import ConversationFileService
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/public", tags=["Public"])


@router.get("/channels/{channel_id}", response_model=ChannelPublicResponse)
async def get_channel_public(
    channel_id: int,
    visitor_external_id: str | None = Query(None, min_length=1),
    current_conversation_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Get channel config for the visitor chat widget. No auth required."""
    return await ChannelService.get_public_config_with_availability(
        db,
        r,
        channel_id,
        visitor_external_id=visitor_external_id,
        current_conversation_id=current_conversation_id,
    )


@router.get(
    "/channels/{channel_id}/conversation-history",
    response_model=VisitorConversationHistoryResponse,
)
async def get_visitor_conversation_history_public(
    channel_id: int,
    visitor_external_id: str = Query(..., min_length=1),
    current_conversation_id: int | None = Query(None),
    before_id: int | None = Query(None),
    limit: int = Query(10, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
):
    """Get visitor conversation history for the current web channel."""
    return await ConversationService.get_visitor_history(
        db,
        channel_id=channel_id,
        visitor_external_id=visitor_external_id,
        current_conversation_id=current_conversation_id,
        before_id=before_id,
        limit=limit,
    )


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages_public(
    conversation_id: int,
    before_id: int | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get messages for a conversation. No auth required (visitor access)."""
    return await ConversationService.get_messages(db, conversation_id, before_id=before_id, limit=limit)


@router.post(
    "/conversations/{conversation_id}/files",
    response_model=ConversationFileUploadResponse,
)
async def upload_conversation_file_public(
    conversation_id: int,
    tenant_id: int = Query(...),
    visitor_external_id: str = Query(..., min_length=1),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a visitor file bound to a conversation."""
    return await ConversationFileService.upload_visitor_file(
        db,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        visitor_external_id=visitor_external_id,
        file=file,
    )


@router.get(
    "/conversation-files/{file_id}/url",
    response_model=ConversationFileAccessResponse,
)
async def get_conversation_file_url_public(
    file_id: str,
    conversation_id: int = Query(...),
    download_name: str | None = Query(None),
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Get a short-lived URL for a conversation file."""
    return await ConversationFileService.get_temporary_url(
        db,
        conversation_id=conversation_id,
        file_id=file_id,
        download_name=download_name,
        download=download,
    )
