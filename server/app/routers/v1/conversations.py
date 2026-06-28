"""
Conversation router — agent-facing REST APIs for conversation management
"""
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.db.deps import (
    get_current_principal,
    get_current_user,
    get_db,
    get_redis,
    require_permission,
    require_permission_short_session,
)
from app.schemas.permission import EffectivePrincipal
from app.schemas.conversation import (
    ConversationResponse,
    ConversationHistoryListResponse,
    ConversationListResponse,
    StartConversationFromHistoryResponse,
    VisitorWebStatusResponse,
)
from app.schemas.conversation_user_statistics import ConversationUserStatisticsResponse
from app.schemas.conversation_file import ConversationFileUploadResponse
from app.schemas.conversation_file import ConversationFileAccessResponse
from app.schemas.message import (
    MessageCreate,
    MessageResponse,
    MessageListResponse,
    WorkspaceConversationHistoryResponse,
    WorkspaceMessageSearchResponse,
)
from app.schemas.agent_status import (
    AgentMaxConcurrentUpdate,
    AgentStatsResponse,
    AgentStatusResponse,
    AgentStatusUpdate,
)
from app.schemas.satisfaction_survey_record import (
    SatisfactionConversationState,
    SatisfactionInviteRequest,
)
from app.services.conversation_file_service import ConversationFileService
from app.services.conversation_service import ConversationService
from app.services.conversation_user_stat_service import ConversationUserStatService
from app.services.agent_status_service import AgentStatusService
from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService
from app.services.visitor_web_status_service import VisitorWebStatusService
from app.enums import AgentOnlineStatus, MessageSenderType

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
    dependencies=[Depends(require_permission("chat.workspace.use"))],
)

file_router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    scope: Literal["my", "peers"] = Query("my", description="Conversation list scope"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Get all active conversations for the current agent."""
    items = await ConversationService.get_agent_conversations(
        db,
        tenant_id=principal.tenant_id,
        agent_id=principal.user_id,
        principal=principal,
        scope=scope,
    )
    return {"items": items, "total": len(items)}


@router.get("/history", response_model=ConversationHistoryListResponse)
async def list_history_conversations(
    before_id: int | None = Query(None, description="Cursor: load conversations before this ID"),
    limit: int = Query(20, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Get recently ended conversations handled by the current agent."""
    return await ConversationService.get_agent_history_conversations(
        db,
        tenant_id=principal.tenant_id,
        agent_id=principal.user_id,
        before_id=before_id,
        limit=limit,
    )


@router.get("/history/{conversation_id}", response_model=ConversationResponse)
async def get_history_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Get one closed conversation handled by the current agent."""
    return await ConversationService.get_agent_history_conversation(
        db,
        conversation_id=conversation_id,
        tenant_id=principal.tenant_id,
        agent_id=principal.user_id,
    )


@router.post("/history/{conversation_id}/start", response_model=StartConversationFromHistoryResponse)
async def start_conversation_from_history(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Start a new active conversation from a closed conversation."""
    return await ConversationService.start_new_from_history(
        db,
        r,
        conversation_id,
        principal=principal,
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Get a single conversation by ID."""
    return await ConversationService.get_agent_conversation(
        db,
        conversation_id=conversation_id,
        tenant_id=principal.tenant_id,
        agent_id=principal.user_id,
        principal=principal,
    )


@router.get("/{conversation_id}/user-statistics", response_model=ConversationUserStatisticsResponse)
async def get_conversation_user_statistics(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Get visible user statistics for a workspace conversation."""
    return await ConversationUserStatService.get_statistics(db, conversation_id, principal)


@router.post("/{conversation_id}/end", response_model=ConversationResponse)
async def end_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """End a conversation (agent-initiated)."""
    return await ConversationService.end_conversation(
        db,
        r,
        conversation_id,
        ended_by="agent",
        principal=principal,
    )


@router.post("/{conversation_id}/pin", response_model=ConversationResponse)
async def pin_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Pin a workspace conversation for the current agent."""
    return await ConversationService.pin_agent_conversation(
        db,
        conversation_id=conversation_id,
        principal=principal,
    )


@router.delete("/{conversation_id}/pin", response_model=ConversationResponse)
async def unpin_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Unpin a workspace conversation for the current agent."""
    return await ConversationService.unpin_agent_conversation(
        db,
        conversation_id=conversation_id,
        principal=principal,
    )


@router.post("/{conversation_id}/timeout-lock", response_model=ConversationResponse)
async def lock_conversation_timeout(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.conversation.lock")),
):
    """Pause visitor timeout auto-close for the current agent's conversation."""
    return await ConversationService.lock_agent_conversation_timeout(
        db,
        conversation_id=conversation_id,
        principal=principal,
    )


@router.delete("/{conversation_id}/timeout-lock", response_model=ConversationResponse)
async def unlock_conversation_timeout(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.conversation.lock")),
):
    """Unlock a conversation and restart visitor timeout auto-close timing."""
    return await ConversationService.unlock_agent_conversation_timeout(
        db,
        conversation_id=conversation_id,
        principal=principal,
    )


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def list_messages(
    conversation_id: int,
    before_id: int | None = Query(None, description="Cursor: load messages before this ID"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Get messages for a conversation (cursor-based pagination)."""
    return await ConversationService.get_messages(
        db,
        conversation_id,
        before_id=before_id,
        limit=limit,
        tenant_id=principal.tenant_id,
        principal=principal,
    )


@router.get("/{conversation_id}/history", response_model=WorkspaceConversationHistoryResponse)
async def list_conversation_history(
    conversation_id: int,
    q: str | None = Query(None, description="Keyword to search within visible history conversations"),
    before_id: int | None = Query(None, description="Cursor: load history before this conversation ID"),
    limit: int = Query(10, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Get read-only visitor history for the current workspace conversation."""
    return await ConversationService.get_workspace_visitor_history(
        db,
        conversation_id=conversation_id,
        tenant_id=principal.tenant_id,
        agent_id=principal.user_id,
        before_id=before_id,
        limit=limit,
        q=q,
        principal=principal,
    )


@router.get("/{conversation_id}/message-search", response_model=WorkspaceMessageSearchResponse)
async def search_conversation_messages(
    conversation_id: int,
    q: str | None = Query(None, description="Keyword to search within visible messages"),
    before_id: int | None = Query(None, description="Cursor: load messages before this message ID"),
    limit: int = Query(30, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Search visible visitor messages from the selected workspace conversation."""
    return await ConversationService.search_workspace_visitor_messages(
        db,
        conversation_id=conversation_id,
        tenant_id=principal.tenant_id,
        principal=principal,
        q=q,
        before_id=before_id,
        limit=limit,
    )


@router.get("/{conversation_id}/visitor-web-status", response_model=VisitorWebStatusResponse)
async def get_visitor_web_status(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Get the selected conversation's visitor Web SDK online status."""
    return await VisitorWebStatusService.get_conversation_status(
        db,
        r,
        conversation_id=conversation_id,
        tenant_id=principal.tenant_id,
        agent_id=principal.user_id,
        principal=principal,
    )


@router.get("/{conversation_id}/satisfaction", response_model=SatisfactionConversationState)
async def get_conversation_satisfaction(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Get satisfaction survey state for a workspace conversation."""
    return await SatisfactionSurveyRecordService.get_conversation_state(
        db,
        conversation_id=conversation_id,
        tenant_id=principal.tenant_id,
        user=user,
        principal=principal,
    )


@router.post("/{conversation_id}/satisfaction/invitations", response_model=SatisfactionConversationState)
async def send_satisfaction_invitation(
    conversation_id: int,
    body: SatisfactionInviteRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Create or resend a satisfaction survey invitation."""
    return await SatisfactionSurveyRecordService.send_agent_invitation(
        db,
        conversation_id=conversation_id,
        tenant_id=principal.tenant_id,
        user=user,
        force=bool(body and body.force),
        principal=principal,
    )


@file_router.post(
    "/{conversation_id}/files",
    response_model=ConversationFileUploadResponse,
)
async def upload_conversation_file(
    conversation_id: int,
    file: UploadFile = File(...),
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("chat.workspace.use"),
    ),
):
    """Upload an agent file bound to a conversation."""
    return await ConversationFileService.upload_agent_file_managed(
        conversation_id=conversation_id,
        tenant_id=principal.tenant_id,
        agent_id=principal.user_id,
        file=file,
        principal=principal,
    )


@router.get(
    "/{conversation_id}/files/{file_id}/url",
    response_model=ConversationFileAccessResponse,
)
async def get_conversation_file_url(
    conversation_id: int,
    file_id: str,
    download_name: str | None = Query(None),
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Get a short-lived URL for an agent-accessible conversation file."""
    return await ConversationFileService.get_temporary_url_for_agent(
        db,
        conversation_id=conversation_id,
        tenant_id=principal.tenant_id,
        agent_id=principal.user_id,
        file_id=file_id,
        download_name=download_name,
        download=download,
        principal=principal,
    )


@router.post("/{conversation_id}/messages/{message_id}/recall", response_model=MessageResponse)
async def recall_message(
    conversation_id: int,
    message_id: int,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Recall an agent-owned public message in a Web conversation."""
    msg, _conversation, _conversation_update = await ConversationService.recall_agent_message(
        db,
        conversation_id=conversation_id,
        message_id=message_id,
        tenant_id=principal.tenant_id,
        principal=principal,
    )
    from app.repositories.employee_repository import EmployeeRepository
    employee = await EmployeeRepository.get_by_id(db, principal.user_id)
    return ConversationService._message_response_payload(
        msg,
        conversation_id=msg.conversation_id,
        sender_name=employee.display_name or employee.name if employee else None,
        sender_avatar=employee.avatar if employee else None,
        viewer_agent_id=principal.user_id,
    )


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=201)
async def send_message(
    conversation_id: int,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Send a message in a conversation (agent sends via REST fallback)."""
    msg = await ConversationService.send_message(
        db,
        conversation_id=conversation_id,
        sender_type=MessageSenderType.AGENT.value,
        sender_id=principal.user_id,
        content_type=body.content_type,
        content=body.content,
        tenant_id=principal.tenant_id,
        principal=principal,
        quoted_message_id=body.quoted_message_id,
    )
    from app.repositories.employee_repository import EmployeeRepository
    employee = await EmployeeRepository.get_by_id(db, principal.user_id)
    return ConversationService._message_response_payload(
        msg,
        conversation_id=msg.conversation_id,
        sender_name=employee.display_name or employee.name if employee else None,
        sender_avatar=employee.avatar if employee else None,
        viewer_agent_id=principal.user_id,
    )


# -- Agent status endpoints (grouped under /conversations for convenience) --

agent_router = APIRouter(
    prefix="/agent",
    tags=["AgentStatus"],
    dependencies=[Depends(require_permission("chat.workspace.use"))],
)


@agent_router.get("/status", response_model=AgentStatusResponse)
async def get_agent_status(
    r: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get current agent online status."""
    from app.repositories.employee_repository import EmployeeRepository
    u = await EmployeeRepository.get_by_id(db, user["user_id"])
    max_c = u.max_concurrent if u else 10
    return await AgentStatusService.get_status(r, user["tenant_id"], user["user_id"], max_c)


@agent_router.put("/status", response_model=AgentStatusResponse)
async def update_agent_status(
    body: AgentStatusUpdate,
    r: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update agent online status (online/busy/offline)."""
    from app.repositories.conversation_repository import ConversationRepository
    from app.repositories.employee_repository import EmployeeRepository

    active_count = await ConversationRepository.count_active_by_agent(
        db,
        user["tenant_id"],
        user["user_id"],
    )
    await AgentStatusService.set_status(
        r,
        user["tenant_id"],
        user["user_id"],
        body.status,
        current_count=active_count,
    )
    # Becoming online is a capacity-gain event: pull any queued work the agent
    # is now eligible for, mirroring the Socket.IO update_status backfill so
    # agents who toggle online via REST also receive queued conversations.
    if body.status == AgentOnlineStatus.ONLINE.value:
        await AgentStatusService.trigger_queue_backfill(r, user["tenant_id"], user["user_id"])
    u = await EmployeeRepository.get_by_id(db, user["user_id"])
    max_c = u.max_concurrent if u else 10
    return await AgentStatusService.get_status(r, user["tenant_id"], user["user_id"], max_c)


@agent_router.get("/stats", response_model=AgentStatsResponse)
async def get_agent_stats(
    r: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get agent reception statistics."""
    from app.repositories.employee_repository import EmployeeRepository
    u = await EmployeeRepository.get_by_id(db, user["user_id"])
    max_c = u.max_concurrent if u else 10
    status = await AgentStatusService.get_status(r, user["tenant_id"], user["user_id"], max_c)
    return {"current_count": status["current_count"], "max_concurrent": max_c}


@agent_router.put("/max-concurrent", response_model=AgentStatsResponse)
async def update_agent_max_concurrent(
    body: AgentMaxConcurrentUpdate,
    r: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
    _principal: EffectivePrincipal = Depends(require_permission("chat.workspace.max_concurrent.edit")),
):
    """Update the current agent's max concurrent session limit."""
    return await AgentStatusService.update_own_max_concurrent(
        db,
        r,
        user["tenant_id"],
        user["user_id"],
        body.max_concurrent,
    )
