"""
Workspace conversation transfer router.

Two endpoints:
    GET  /api/v1/workspace/transfer-targets
        — list candidate employees (with realtime online status) for the
          transfer modal
    POST /api/v1/workspace/conversations/{conversation_id}/transfer
        — execute a forced transfer
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.exceptions import ForbiddenError
from app.db.deps import get_current_user, get_db, get_redis
from app.schemas.conversation import ConversationResponse
from app.schemas.transfer import (
    TransferConversationRequest,
    TransferTargetListResponse,
)
from app.services.transfer_service import TransferService

router = APIRouter(prefix="/workspace", tags=["Transfer"])


def _ensure_workspace_access(user: dict) -> None:
    """Both ``agent`` and ``admin`` roles can use the transfer feature."""
    roles = user.get("roles", [])
    if not any(role in {"agent", "admin"} for role in roles):
        raise ForbiddenError("No permission to access workspace transfer")


@router.get("/transfer-targets", response_model=TransferTargetListResponse)
async def list_transfer_targets(
    keyword: str | None = Query(None, max_length=64),
    conversation_id: int | None = Query(
        None,
        gt=0,
        description="When provided, the conversation's current owner is also excluded",
    ),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    user: dict = Depends(get_current_user),
):
    """Return colleagues eligible to receive a transferred conversation."""
    _ensure_workspace_access(user)
    return await TransferService.list_targets(
        db,
        r,
        tenant_id=user["tenant_id"],
        current_user_id=user["user_id"],
        keyword=keyword,
        conversation_id=conversation_id,
        roles=user.get("roles", []),
    )


@router.post(
    "/conversations/{conversation_id}/transfer",
    response_model=ConversationResponse,
)
async def transfer_conversation(
    conversation_id: int,
    body: TransferConversationRequest,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    user: dict = Depends(get_current_user),
):
    """Force-transfer a conversation to the chosen online colleague.

    The service returns a dict already shaped like ``ConversationResponse`` so
    we don't need a second permission-checked fetch (the requester may no
    longer own the conversation by the time we'd query it back).
    """
    _ensure_workspace_access(user)
    return await TransferService.transfer_conversation(
        db,
        r,
        conversation_id=conversation_id,
        target_agent_id=body.target_agent_id,
        current_user_id=user["user_id"],
        tenant_id=user["tenant_id"],
        roles=user.get("roles", []),
    )
