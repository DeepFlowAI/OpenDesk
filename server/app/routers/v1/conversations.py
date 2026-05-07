"""
Conversation router — agent-facing REST APIs for conversation management
"""
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.db.deps import get_db, get_redis, get_current_user
from app.schemas.conversation import (
    ConversationResponse,
    ConversationListResponse,
)
from app.schemas.conversation_file import ConversationFileUploadResponse
from app.schemas.message import (
    MessageCreate,
    MessageResponse,
    MessageListResponse,
    WorkspaceConversationHistoryResponse,
)
from app.schemas.agent_status import AgentStatusResponse, AgentStatusUpdate, AgentStatsResponse
from app.services.conversation_file_service import ConversationFileService
from app.services.conversation_service import ConversationService
from app.services.agent_status_service import AgentStatusService
from app.enums import MessageSenderType

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get all active conversations for the current agent."""
    items = await ConversationService.get_agent_conversations(
        db,
        tenant_id=user["tenant_id"],
        agent_id=user["user_id"],
        roles=user.get("roles", ["agent"]),
    )
    return {"items": items, "total": len(items)}


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get a single conversation by ID."""
    return await ConversationService.get_agent_conversation(
        db,
        conversation_id=conversation_id,
        tenant_id=user["tenant_id"],
        agent_id=user["user_id"],
        roles=user.get("roles", ["agent"]),
    )


@router.post("/{conversation_id}/end", response_model=ConversationResponse)
async def end_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    user: dict = Depends(get_current_user),
):
    """End a conversation (agent-initiated)."""
    return await ConversationService.end_conversation(db, r, conversation_id, ended_by="agent")


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def list_messages(
    conversation_id: int,
    before_id: int | None = Query(None, description="Cursor: load messages before this ID"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get messages for a conversation (cursor-based pagination)."""
    return await ConversationService.get_messages(db, conversation_id, before_id=before_id, limit=limit)


@router.get("/{conversation_id}/history", response_model=WorkspaceConversationHistoryResponse)
async def list_conversation_history(
    conversation_id: int,
    before_id: int | None = Query(None, description="Cursor: load history before this conversation ID"),
    limit: int = Query(10, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get read-only visitor history for the current workspace conversation."""
    return await ConversationService.get_workspace_visitor_history(
        db,
        conversation_id=conversation_id,
        tenant_id=user["tenant_id"],
        agent_id=user["user_id"],
        roles=user.get("roles", ["agent"]),
        before_id=before_id,
        limit=limit,
    )


@router.post(
    "/{conversation_id}/files",
    response_model=ConversationFileUploadResponse,
)
async def upload_conversation_file(
    conversation_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Upload an agent file bound to a conversation."""
    return await ConversationFileService.upload_agent_file(
        db,
        conversation_id=conversation_id,
        tenant_id=user["tenant_id"],
        agent_id=user["user_id"],
        file=file,
    )


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=201)
async def send_message(
    conversation_id: int,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Send a message in a conversation (agent sends via REST fallback)."""
    msg = await ConversationService.send_message(
        db,
        conversation_id=conversation_id,
        sender_type=MessageSenderType.AGENT.value,
        sender_id=user["user_id"],
        content_type=body.content_type,
        content=body.content,
        tenant_id=user["tenant_id"],
    )
    from app.repositories.employee_repository import EmployeeRepository
    employee = await EmployeeRepository.get_by_id(db, user["user_id"])
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "sender_type": msg.sender_type,
        "sender_id": msg.sender_id,
        "sender_name": employee.display_name or employee.name if employee else None,
        "sender_avatar": employee.avatar if employee else None,
        "content_type": msg.content_type,
        "content": msg.content,
        "created_at": msg.created_at,
    }


# -- Agent status endpoints (grouped under /conversations for convenience) --

agent_router = APIRouter(prefix="/agent", tags=["AgentStatus"])


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
    await AgentStatusService.set_status(r, user["tenant_id"], user["user_id"], body.status)
    from app.repositories.employee_repository import EmployeeRepository
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
