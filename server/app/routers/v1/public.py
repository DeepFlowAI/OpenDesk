"""
Public API router — endpoints accessible without authentication.

Used by the visitor-facing chat widget to fetch channel config, messages, and files.
"""
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi import Header
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_redis
from app.schemas.channel import ChannelPublicResponse
from app.schemas.conversation_file import ConversationFileAccessResponse, ConversationFileUploadResponse
from app.schemas.message import PublicMessageListResponse, VisitorConversationHistoryResponse
from app.schemas.satisfaction_survey_record import (
    PublicSatisfactionInvitation,
    PublicSatisfactionSubmitResponse,
    SatisfactionSubmissionPayload,
)
from app.schemas.visitor_session import VisitorSessionRequest, VisitorSessionResponse
from app.services.channel_service import ChannelService
from app.services.conversation_file_service import ConversationFileService
from app.services.conversation_service import ConversationService
from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService

router = APIRouter(prefix="/public", tags=["Public"])


async def get_visitor_context(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.core.exceptions import UnauthorizedError

    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid visitor session")
    return await ChannelService.validate_visitor_session_token(db, authorization[7:])


@router.get("/channels/{channel_key}", response_model=ChannelPublicResponse)
async def get_channel_public(
    channel_key: str,
    visitor_external_id: str | None = Query(None, min_length=1),
    current_conversation_public_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Get channel config for the visitor chat widget. No auth required."""
    return await ChannelService.get_public_config_with_availability_by_key(
        db,
        r,
        channel_key,
        visitor_external_id=visitor_external_id,
        current_conversation_public_id=current_conversation_public_id,
    )


@router.post(
    "/channels/{channel_key}/visitor-session",
    response_model=VisitorSessionResponse,
)
async def create_visitor_session(
    channel_key: str,
    body: VisitorSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a visitor session token bound to the public channel key."""
    return await ChannelService.create_visitor_session(db, channel_key, body)


@router.get(
    "/conversations/history",
    response_model=VisitorConversationHistoryResponse,
)
async def get_visitor_conversation_history_public(
    current_conversation_public_id: str | None = Query(None),
    before_public_id: str | None = Query(None),
    limit: int = Query(10, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Get visitor conversation history for the current web channel."""
    return await ConversationService.get_visitor_history_for_session(
        db,
        visitor_context=visitor_context,
        current_conversation_public_id=current_conversation_public_id,
        before_public_id=before_public_id,
        limit=limit,
    )


@router.get("/conversations/{conversation_public_id}/messages", response_model=PublicMessageListResponse)
async def get_conversation_messages_public(
    conversation_public_id: str,
    before_id: int | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Get messages for a visitor-owned public conversation."""
    return await ConversationService.get_public_messages_for_session(
        db,
        conversation_public_id,
        visitor_context,
        before_id=before_id,
        limit=limit,
    )


@router.get(
    "/conversations/{conversation_public_id}/satisfaction",
    response_model=PublicSatisfactionInvitation,
)
async def get_conversation_satisfaction_public(
    conversation_public_id: str,
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Get the active satisfaction invitation for a visitor-owned conversation."""
    return await SatisfactionSurveyRecordService.get_public_invitation(
        db,
        conversation_public_id=conversation_public_id,
        visitor_context=visitor_context,
    )


@router.post(
    "/conversations/{conversation_public_id}/satisfaction/invitations",
    response_model=PublicSatisfactionInvitation,
)
async def create_conversation_satisfaction_public(
    conversation_public_id: str,
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Create a visitor-initiated satisfaction survey for the current conversation."""
    return await SatisfactionSurveyRecordService.create_user_initiated_invitation(
        db,
        conversation_public_id=conversation_public_id,
        visitor_context=visitor_context,
    )


@router.post(
    "/conversations/{conversation_public_id}/satisfaction/submissions",
    response_model=PublicSatisfactionSubmitResponse,
)
async def submit_conversation_satisfaction_public(
    conversation_public_id: str,
    body: SatisfactionSubmissionPayload,
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Submit satisfaction feedback for a visitor-owned invitation."""
    return await SatisfactionSurveyRecordService.submit_public_feedback(
        db,
        conversation_public_id=conversation_public_id,
        visitor_context=visitor_context,
        payload=body,
    )


@router.post(
    "/conversations/{conversation_public_id}/files",
    response_model=ConversationFileUploadResponse,
)
async def upload_conversation_file_public(
    conversation_public_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Upload a visitor file bound to a conversation."""
    return await ConversationFileService.upload_visitor_file_for_session(
        db,
        conversation_public_id=conversation_public_id,
        visitor_context=visitor_context,
        file=file,
    )


@router.get(
    "/conversation-files/{file_id}/url",
    response_model=ConversationFileAccessResponse,
)
async def get_conversation_file_url_public(
    file_id: str,
    conversation_public_id: str = Query(...),
    download_name: str | None = Query(None),
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Get a short-lived URL for a conversation file."""
    return await ConversationFileService.get_temporary_url_for_visitor_session(
        db,
        conversation_public_id=conversation_public_id,
        visitor_context=visitor_context,
        file_id=file_id,
        download_name=download_name,
        download=download,
    )
