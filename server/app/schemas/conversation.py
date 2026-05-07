"""
Conversation Pydantic schemas
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VisitorBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
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
    unread_count: int = 0
    has_history_conversations: bool = False
    created_at: datetime | None = None


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int


class EndConversationRequest(BaseModel):
    pass


# -- Visitor-initiated conversation --

class CreateConversationRequest(BaseModel):
    """Sent from visitor SDK to create a new conversation."""
    channel_id: int
    visitor_name: str | None = None
    visitor_external_id: str
    metadata: dict | None = None
