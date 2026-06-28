"""
Public API router — endpoints accessible without authentication.

Used by the visitor-facing chat widget to fetch channel config, messages, and files.
"""
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi import Header
from fastapi.routing import APIRoute
from starlette.responses import StreamingResponse
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.db.deps import get_db, get_redis
from app.db.session import AsyncSessionLocal
from app.schemas.channel import ChannelPublicResponse
from app.schemas.conversation_file import ConversationFileAccessResponse, ConversationFileUploadResponse
from app.schemas.emoji_setting import EmojiTargetConfigResponse
from app.schemas.message import (
    CustomerReadResponse,
    PublicMessageListResponse,
    PublicMessageResponse,
    VisitorConversationHistoryResponse,
    VisitorUnreadOfflineReplyResponse,
)
from app.schemas.offline_message import (
    OfflineMessageCreateRequest,
    OfflineMessageSendRequest,
    PublicOfflineMessageResponse,
)
from app.schemas.open_agent_conversation import (
    OpenAgentChatRequest,
    OpenAgentFeedbackRequest,
    OpenAgentFeedbackResponse,
)
from app.schemas.satisfaction_survey_record import (
    PublicSatisfactionInvitation,
    PublicSatisfactionSubmitResponse,
    SatisfactionSubmissionPayload,
)
from app.schemas.telemetry import TelemetryBatchRequest, TelemetryBatchResponse
from app.schemas.visitor_session import (
    VisitorContextSyncRequest,
    VisitorContextSyncResponse,
    VisitorSessionRequest,
    VisitorSessionResponse,
)
from app.services.channel_service import ChannelService
from app.services.conversation_file_service import ConversationFileService
from app.services.conversation_service import ConversationService
from app.services.emoji_setting_service import EmojiSettingService
from app.services.open_agent_conversation_service import OpenAgentConversationService
from app.services.offline_message_service import OfflineMessageService
from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService
from app.services.telemetry_service import TelemetryService
from app.services.web_sdk_context_service import WebSdkContextService

router = APIRouter(prefix="/public", tags=["Public"])
_TELEMETRY_BODY_BYTES_CAP = 256 * 1024


async def _read_body_with_cap(request: Request, cap: int) -> None:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > cap:
                raise ValidationError(
                    f"Telemetry batch too large: {content_length} bytes (limit {cap})"
                )
            return
        except ValueError:
            pass

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > cap:
            raise ValidationError(f"Telemetry batch too large: stream exceeded {cap} bytes")
        chunks.append(chunk)
    request._body = b"".join(chunks)  # type: ignore[attr-defined]


class _TelemetryRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def cap_then_handle(request: Request) -> Response:
            await _read_body_with_cap(request, _TELEMETRY_BODY_BYTES_CAP)
            return await original_handler(request)

        return cap_then_handle


_telemetry_router = APIRouter(route_class=_TelemetryRoute)


def _first_client_ip(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    first = value.split(",", 1)[0].strip()
    return first or None


def _client_ip_from_request(request: Request) -> str | None:
    for key in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip"):
        ip = _first_client_ip(request.headers.get(key))
        if ip:
            return ip
    return _first_client_ip(request.client.host if request.client else None)


async def get_visitor_context(
    request: Request,
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.core.exceptions import UnauthorizedError

    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid visitor session")
    context = await ChannelService.validate_visitor_session_token(db, authorization[7:])
    visitor_ip = _client_ip_from_request(request)
    if visitor_ip:
        context["visitor_ip"] = visitor_ip
    return context


async def get_visitor_context_short_session(
    request: Request,
    authorization: str | None,
) -> dict:
    from app.core.exceptions import UnauthorizedError

    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid visitor session")
    async with AsyncSessionLocal() as db:
        context = await ChannelService.validate_visitor_session_token(db, authorization[7:])
    visitor_ip = _client_ip_from_request(request)
    if visitor_ip:
        context["visitor_ip"] = visitor_ip
    return context


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


@router.get("/emojis", response_model=EmojiTargetConfigResponse)
async def get_public_emoji_settings(
    db: AsyncSession = Depends(get_db),
):
    """Get visitor-side emoji panel settings for the default tenant."""
    return await EmojiSettingService.get_public_user_config(db)


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


@_telemetry_router.post(
    "/channels/{channel_key}/telemetry/events",
    response_model=TelemetryBatchResponse,
)
async def post_telemetry_events(
    channel_key: str,
    body: TelemetryBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Batch-ingest visitor Web SDK telemetry events."""
    channel = await ChannelService.get_public_channel_by_key(db, channel_key)
    return await TelemetryService.ingest(channel=channel, body=body)


@router.post("/offline-messages", response_model=PublicOfflineMessageResponse)
async def create_offline_message_public(
    body: OfflineMessageCreateRequest | None = None,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Create or continue a visitor-owned offline message thread."""
    payload = body or OfflineMessageCreateRequest()
    return await OfflineMessageService.create_or_continue_for_session(
        db,
        r,
        visitor_context,
        visitor_name=payload.visitor_name,
        metadata=payload.metadata,
        visitor_system=payload.system,
        visitor_browser=payload.browser,
    )


@router.get("/offline-messages/current", response_model=PublicOfflineMessageResponse | None)
async def get_current_offline_message_public(
    before_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Get the visitor's current pending offline message without creating one."""
    return await OfflineMessageService.get_current_for_session(
        db,
        visitor_context,
        before_id=before_id,
        limit=limit,
    )


@router.post("/offline-messages/messages")
async def create_and_send_offline_message_public(
    body: OfflineMessageSendRequest,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Create or continue an offline message thread and append visitor content."""
    return await OfflineMessageService.create_or_continue_and_send_for_session(
        db,
        r,
        visitor_context,
        content_type=body.content_type,
        content=body.content,
        visitor_system=body.system,
        visitor_browser=body.browser,
    )


@router.get("/offline-messages/{offline_message_public_id}/messages", response_model=PublicOfflineMessageResponse)
async def get_offline_message_messages_public(
    offline_message_public_id: str,
    before_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Get messages for a visitor-owned offline message thread."""
    return await OfflineMessageService.get_public_response(
        db,
        offline_message_public_id,
        visitor_context,
        before_id=before_id,
        limit=limit,
    )


@router.post("/offline-messages/{offline_message_public_id}/messages")
async def send_offline_message_public(
    offline_message_public_id: str,
    body: OfflineMessageSendRequest,
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Append a visitor message to an offline message thread."""
    message = await OfflineMessageService.send_public_message(
        db,
        offline_message_public_id,
        visitor_context,
        content_type=body.content_type,
        content=body.content,
        visitor_system=body.system,
        visitor_browser=body.browser,
    )
    return {"ok": True, "message": message}


@router.post(
    "/conversations/{conversation_public_id}/context",
    response_model=VisitorContextSyncResponse,
)
async def sync_conversation_context_public(
    conversation_public_id: str,
    body: VisitorContextSyncRequest,
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Synchronize signed Web SDK context for a visitor-owned conversation."""
    result = await WebSdkContextService.sync_for_conversation(
        db,
        context_token=body.context_token,
        visitor_context=visitor_context,
        conversation_public_id=conversation_public_id,
        require_active_api_key=False,
    )
    return result.to_dict()


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


@router.get(
    "/conversations/unread-offline-replies",
    response_model=VisitorUnreadOfflineReplyResponse,
)
async def get_unread_offline_replies_public(
    limit: int = Query(3, ge=1, le=3),
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Get visitor-owned offline-message reply conversations pending customer display."""
    return await ConversationService.get_unread_offline_replies_for_session(
        db,
        visitor_context=visitor_context,
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


@router.post(
    "/conversations/{conversation_public_id}/messages/{message_id}/recall",
    response_model=PublicMessageResponse,
)
async def recall_conversation_message_public(
    conversation_public_id: str,
    message_id: int,
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Recall a visitor-owned public message in the current Web conversation."""
    msg, conversation, _conversation_update = await ConversationService.recall_visitor_message_for_session(
        db,
        conversation_public_id=conversation_public_id,
        visitor_context=visitor_context,
        message_id=message_id,
    )
    return ConversationService._message_response_payload(
        msg,
        conversation_public_id=conversation.public_id,
        sender_name=conversation.visitor.name if conversation.visitor else None,
        sender_avatar=None,
        visitor_facing=True,
    )


@router.post(
    "/conversations/{conversation_public_id}/customer-read",
    response_model=CustomerReadResponse,
)
async def mark_conversation_customer_read_public(
    conversation_public_id: str,
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Mark visitor-visible offline-message replies as read."""
    return await ConversationService.mark_customer_read_for_session(
        db,
        visitor_context=visitor_context,
        conversation_public_id=conversation_public_id,
    )


@router.post("/conversations/{conversation_public_id}/open-agent/chat")
async def chat_open_agent_public(
    conversation_public_id: str,
    body: OpenAgentChatRequest,
    request: Request,
    authorization: str | None = Header(None),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Proxy OpenAgent chat SSE for a visitor-owned bot conversation."""
    visitor_context = await get_visitor_context_short_session(request, authorization)
    stream = OpenAgentConversationService.stream_chat_for_session_managed(
        conversation_public_id=conversation_public_id,
        visitor_context=visitor_context,
        body=body,
        redis=redis,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/conversations/{conversation_public_id}/open-agent/feedback",
    response_model=OpenAgentFeedbackResponse,
)
async def submit_open_agent_feedback_public(
    conversation_public_id: str,
    body: OpenAgentFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Submit visitor feedback for a bot answer owned by this visitor session."""
    return await OpenAgentConversationService.submit_feedback_for_session(
        db,
        conversation_public_id=conversation_public_id,
        visitor_context=visitor_context,
        body=body,
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


@router.post("/offline-messages/files")
async def create_and_send_offline_message_file_public(
    file: UploadFile = File(...),
    system: str | None = Form(None, max_length=64),
    browser: str | None = Form(None, max_length=128),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Create or continue an offline message thread and append a visitor file."""
    return await OfflineMessageService.create_or_continue_and_send_file_for_session(
        db,
        r,
        visitor_context,
        file,
        visitor_system=system,
        visitor_browser=browser,
    )


@router.post(
    "/offline-messages/{offline_message_public_id}/files",
    response_model=ConversationFileUploadResponse,
)
async def upload_offline_message_file_public(
    offline_message_public_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Upload a visitor file bound to an offline message thread."""
    return await OfflineMessageService.upload_public_file(
        db,
        offline_message_public_id,
        visitor_context,
        file,
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


@router.get(
    "/offline-message-files/{file_id}/url",
    response_model=ConversationFileAccessResponse,
)
async def get_offline_message_file_url_public(
    file_id: str,
    offline_message_public_id: str = Query(...),
    download_name: str | None = Query(None),
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    visitor_context: dict = Depends(get_visitor_context),
):
    """Get a short-lived URL for an offline message file."""
    return await OfflineMessageService.get_temporary_url_for_public(
        db,
        offline_message_public_id,
        visitor_context,
        file_id=file_id,
        download_name=download_name,
        download=download,
    )


router.include_router(_telemetry_router)
