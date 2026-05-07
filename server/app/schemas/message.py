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
    content_type: Literal["text", "image", "file", "system"] = "text"
    content: str = Field(..., max_length=20000)


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
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    has_more: bool


class VisitorConversationHistoryItem(BaseModel):
    id: int
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    last_message_at: datetime | None = None
    created_at: datetime | None = None
    agent_name: str | None = None
    agent_avatar: str | None = None
    messages: list[MessageResponse]
    messages_truncated: bool = False


class VisitorConversationHistoryResponse(BaseModel):
    items: list[VisitorConversationHistoryItem]
    has_more: bool


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
