"""
Message Pydantic schemas
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FileMessageContent(BaseModel):
    schema_version: Literal[1] = 1
    file_id: str = Field(..., min_length=1, max_length=512)
    name: str = Field(..., min_length=1, max_length=255)
    size: int = Field(..., gt=0, le=100 * 1024 * 1024)
    mime_type: str = Field(..., min_length=1, max_length=255)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    thumbnail_file_id: str | None = Field(default=None, max_length=512)
    hash: str | None = Field(default=None, max_length=128)


class MessageCreate(BaseModel):
    content_type: Literal["text", "rich_text", "image", "file", "system", "internal_note"] = "text"
    content: str = Field(..., max_length=20000)
    quoted_message_id: int | None = Field(default=None, gt=0)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    sender_type: str
    sender_id: int | None = None
    sender_name: str | None = None
    sender_avatar: str | None = None
    content_type: str
    content: str
    is_recalled: bool = False
    recalled_at: datetime | None = None
    recalled_by_type: str | None = None
    recalled_by_id: int | None = None
    recalled_by_name: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    status: Literal["unread", "read"] | None = None
    event_type: str | None = None
    satisfaction_record_id: int | None = None
    config_version: int | None = None


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    has_more: bool


class PublicMessageResponse(BaseModel):
    id: int
    conversation_public_id: str
    sender_type: str
    sender_id: int | None = None
    sender_name: str | None = None
    sender_avatar: str | None = None
    content_type: str
    content: str
    is_recalled: bool = False
    recalled_at: datetime | None = None
    recalled_by_type: str | None = None
    recalled_by_id: int | None = None
    recalled_by_name: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    status: Literal["unread", "read"] | None = None
    event_type: str | None = None
    satisfaction_record_id: int | None = None
    config_version: int | None = None


class PublicMessageListResponse(BaseModel):
    items: list[PublicMessageResponse]
    has_more: bool


class VisitorConversationHistoryItem(BaseModel):
    conversation_public_id: str
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    last_message_at: datetime | None = None
    created_at: datetime | None = None
    agent_name: str | None = None
    agent_avatar: str | None = None
    messages: list[PublicMessageResponse]
    messages_truncated: bool = False


class VisitorConversationHistoryResponse(BaseModel):
    items: list[VisitorConversationHistoryItem]
    has_more: bool


class VisitorUnreadOfflineReplyItem(VisitorConversationHistoryItem):
    offline_message_public_id: str
    customer_unread_at: datetime
    customer_unread_message_id: int | None = None
    offline_reply_unread: bool = True


class VisitorUnreadOfflineReplyResponse(BaseModel):
    items: list[VisitorUnreadOfflineReplyItem]
    has_more: bool


class CustomerReadResponse(BaseModel):
    ok: bool = True


class WorkspaceHistoryChannel(BaseModel):
    id: int
    name: str
    channel_type: str


class WorkspaceHistoryAgent(BaseModel):
    id: int
    display_name: str | None = None
    name: str
    avatar: str | None = None


class WorkspaceConversationHistoryItem(BaseModel):
    id: int
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    last_message_at: datetime | None = None
    created_at: datetime | None = None
    channel: WorkspaceHistoryChannel | None = None
    agent: WorkspaceHistoryAgent | None = None
    messages: list[MessageResponse]
    messages_truncated: bool = False


class WorkspaceConversationHistoryResponse(BaseModel):
    items: list[WorkspaceConversationHistoryItem]
    has_more: bool


class WorkspaceMessageSearchConversation(BaseModel):
    id: int
    share_code: str
    status: str
    started_at: datetime | None = None
    channel: WorkspaceHistoryChannel | None = None


class WorkspaceMessageSearchResult(BaseModel):
    id: int
    conversation_id: int
    sender_type: str
    sender_id: int | None = None
    sender_name: str | None = None
    sender_avatar: str | None = None
    content_type: str
    content: str
    is_recalled: bool = False
    recalled_at: datetime | None = None
    recalled_by_type: str | None = None
    recalled_by_id: int | None = None
    recalled_by_name: str | None = None
    created_at: datetime
    conversation: WorkspaceMessageSearchConversation


class WorkspaceMessageSearchResponse(BaseModel):
    items: list[WorkspaceMessageSearchResult]
    total: int
    has_more: bool
