"""
Workspace conversation collaboration router.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.db.deps import get_current_principal, get_db, get_redis, require_permission
from app.schemas.conversation_collaboration import (
    CollaborationInvitationCreate,
    CollaborationInvitationListResponse,
    CollaborationInvitationRespond,
    CollaborationInvitationRespondResponse,
    CollaborationInvitationResponse,
    CollaborationTargetListResponse,
)
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_collaboration_service import ConversationCollaborationService

router = APIRouter(
    prefix="/workspace",
    tags=["Conversation Collaboration"],
    dependencies=[Depends(require_permission("chat.workspace.use"))],
)


@router.get("/collaboration-targets", response_model=CollaborationTargetListResponse)
async def list_collaboration_targets(
    conversation_id: int = Query(..., gt=0),
    keyword: str | None = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Return agents that can be invited to collaborate on a conversation."""
    return await ConversationCollaborationService.list_targets(
        db,
        r,
        tenant_id=principal.tenant_id,
        conversation_id=conversation_id,
        keyword=keyword,
        principal=principal,
    )


@router.get(
    "/collaboration-invitations/pending",
    response_model=CollaborationInvitationListResponse,
)
async def list_pending_collaboration_invitations(
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Return pending collaboration invitations for the current agent."""
    return await ConversationCollaborationService.list_pending_invitations(
        db,
        tenant_id=principal.tenant_id,
        principal=principal,
    )


@router.post(
    "/conversations/{conversation_id}/collaboration-invitations",
    response_model=CollaborationInvitationResponse,
)
async def create_collaboration_invitation(
    conversation_id: int,
    body: CollaborationInvitationCreate,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Invite an agent to join a conversation as a collaborator."""
    return await ConversationCollaborationService.create_invitation(
        db,
        r,
        tenant_id=principal.tenant_id,
        conversation_id=conversation_id,
        invitee_id=body.invitee_id,
        principal=principal,
    )


@router.post(
    "/collaboration-invitations/{invitation_id}/respond",
    response_model=CollaborationInvitationRespondResponse,
)
async def respond_collaboration_invitation(
    invitation_id: int,
    body: CollaborationInvitationRespond,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Accept or decline a collaboration invitation."""
    return await ConversationCollaborationService.respond_invitation(
        db,
        tenant_id=principal.tenant_id,
        invitation_id=invitation_id,
        action=body.action,
        principal=principal,
    )
