"""
Offline message schemas.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.conversation import AgentBrief, ChannelBrief, ConversationResponse, GroupBrief, VisitorBrief
from app.schemas.message import MessageResponse, PublicMessageResponse


class OfflineMessageCreateRequest(BaseModel):
    visitor_name: str | None = Field(default=None, max_length=128)
    metadata: dict | None = None
    system: str | None = Field(default=None, max_length=64)
    browser: str | None = Field(default=None, max_length=128)


class OfflineMessageSendRequest(BaseModel):
    content_type: Literal["text", "image", "file"] = "text"
    content: str = Field(..., max_length=20000)
    system: str | None = Field(default=None, max_length=64)
    browser: str | None = Field(default=None, max_length=128)


class OfflineMessageEntryResponse(BaseModel):
    id: int
    offline_message_id: int
    sender_type: str
    sender_id: int | None = None
    sender_name: str | None = None
    sender_avatar: str | None = None
    content_type: str
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class OfflineMessageBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: str
    tenant_id: int
    status: Literal["pending", "converted"]
    visitor: VisitorBrief | None = None
    channel: ChannelBrief | None = None
    target_group: GroupBrief | None = None
    conversation: ConversationResponse | None = None
    visitor_external_id: str
    visitor_name: str | None = None
    handled_by_id: int | None = None
    handled_at: datetime | None = None
    last_message_at: datetime | None = None
    last_message_preview: str | None = None
    message_count: int = 0
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None


class OfflineMessageDetail(OfflineMessageBrief):
    messages: list[OfflineMessageEntryResponse] = Field(default_factory=list)
    has_more_messages: bool = False
    can_assign_self: bool = False
    can_assign_other: bool = False


class OfflineMessageListResponse(BaseModel):
    items: list[OfflineMessageBrief]
    has_more: bool
    total: int | None = None


class OfflineMessageCountResponse(BaseModel):
    total: int


class PublicOfflineMessageResponse(BaseModel):
    offline_message_public_id: str
    status: Literal["pending", "converted"]
    messages: list[PublicMessageResponse] = Field(default_factory=list)
    has_more: bool = False
    conversation_public_id: str | None = None


class OfflineMessageAssignSelfRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class OfflineMessageAssignRequest(OfflineMessageAssignSelfRequest):
    agent_id: int


class OfflineMessageConvertResponse(BaseModel):
    offline_message: OfflineMessageBrief
    conversation: ConversationResponse
    messages: list[MessageResponse] = Field(default_factory=list)
    assigned_to_current_user: bool = True
    assigned_agent: AgentBrief | None = None
