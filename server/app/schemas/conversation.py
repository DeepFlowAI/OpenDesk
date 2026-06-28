"""
Conversation Pydantic schemas
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VisitorBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: str
    external_id: str
    name: str
    avatar_color: str | None = None


class AgentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str | None = None
    name: str
    avatar: str | None = None


class ChannelBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    channel_type: str


class GroupBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: str
    share_code: str
    tenant_id: int
    visitor: VisitorBrief | None = None
    agent: AgentBrief | None = None
    channel: ChannelBrief | None = None
    group: GroupBrief | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    ended_by: str | None = None
    last_message_at: datetime | None = None
    last_message_preview: str | None = None
    visitor_system: str | None = None
    visitor_browser: str | None = None
    visitor_ip: str | None = None
    unread_count: int = 0
    is_pinned: bool = False
    pinned_at: datetime | None = None
    is_timeout_locked: bool = False
    timeout_locked_at: datetime | None = None
    timeout_locked_by_id: int | None = None
    has_history_conversations: bool = False
    viewer_relation: Literal["own", "peer", "collaborator"] | None = None
    collaborated_by_current_user: bool = False
    collaborators: list[AgentBrief] = Field(default_factory=list)
    created_at: datetime | None = None


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int


class ConversationHistoryListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    has_more: bool


class StartConversationFromHistoryResponse(BaseModel):
    conversation: ConversationResponse
    is_new: bool
    already_active: bool = False


class VisitorWebStatusResponse(BaseModel):
    conversation_id: int
    status: Literal["online", "offline", "unknown"]
    can_display: bool
    checked_at: datetime


class EndConversationRequest(BaseModel):
    pass


# -- Visitor-initiated conversation --

class CreateConversationRequest(BaseModel):
    """Sent from visitor SDK to create a new conversation."""
    channel_id: int
    visitor_name: str | None = None
    visitor_external_id: str
    metadata: dict | None = None
