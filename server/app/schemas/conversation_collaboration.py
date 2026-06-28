"""
Conversation collaboration schemas.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.conversation import AgentBrief, ConversationResponse


class CollaborationTarget(BaseModel):
    id: int
    name: str
    display_name: str | None = None
    job_number: str | None = None
    avatar: str | None = None
    online_status: Literal["online", "busy", "offline"]
    current_count: int
    max_concurrent: int
    available: bool
    disabled_reason: str | None = None


class CollaborationTargetListResponse(BaseModel):
    items: list[CollaborationTarget]
    total: int


class CollaborationInvitationCreate(BaseModel):
    invitee_id: int


class CollaborationInvitationRespond(BaseModel):
    action: Literal["accept", "decline"]


class CollaborationInvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    status: str
    inviter: AgentBrief | None = None
    invitee: AgentBrief | None = None
    owner: AgentBrief | None = None
    visitor_name: str | None = None
    channel_name: str | None = None
    last_message_preview: str | None = None
    expires_at: datetime
    responded_at: datetime | None = None
    created_at: datetime


class CollaborationInvitationListResponse(BaseModel):
    items: list[CollaborationInvitationResponse]
    total: int


class CollaborationInvitationRespondResponse(BaseModel):
    invitation: CollaborationInvitationResponse
    conversation: ConversationResponse | None = None
