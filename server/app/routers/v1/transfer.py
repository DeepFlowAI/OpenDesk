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

from app.db.deps import get_current_user, get_current_principal, get_db, get_redis, require_permission
from app.schemas.permission import EffectivePrincipal
from app.schemas.conversation import ConversationResponse
from app.schemas.transfer import (
    TransferConversationRequest,
    TransferTargetListResponse,
)
from app.services.transfer_service import TransferService

router = APIRouter(
    prefix="/workspace",
    tags=["Transfer"],
    dependencies=[Depends(require_permission("chat.conversation.transfer"))],
)


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
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Return colleagues eligible to receive a transferred conversation."""
    return await TransferService.list_targets(
        db,
        r,
        tenant_id=principal.tenant_id,
        current_user_id=principal.user_id,
        keyword=keyword,
        conversation_id=conversation_id,
        principal=principal,
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
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Force-transfer a conversation to the chosen online colleague.

    The service returns a dict already shaped like ``ConversationResponse`` so
    we don't need a second permission-checked fetch (the requester may no
    longer own the conversation by the time we'd query it back).
    """
    return await TransferService.transfer_conversation(
        db,
        r,
        conversation_id=conversation_id,
        target_agent_id=body.target_agent_id,
        current_user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        principal=principal,
    )
