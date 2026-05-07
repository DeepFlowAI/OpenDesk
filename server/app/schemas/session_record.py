"""
Session record schemas — read-only views of historical conversations
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SessionRecordVisitor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    name: str
    avatar_color: str | None = None


class SessionRecordAgent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_name: str | None = None
    avatar: str | None = None


class SessionRecordChannel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    channel_type: str


class SessionRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    visitor: SessionRecordVisitor | None = None
    agent: SessionRecordAgent | None = None
    channel: SessionRecordChannel | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    ended_by: str | None = None
    created_at: datetime | None = None


class SessionRecordListResponse(BaseModel):
    items: list[SessionRecordResponse]
    total: int
    page: int
    per_page: int
    pages: int


class SessionRecordDetailResponse(SessionRecordResponse):
    """Extended detail with group info."""
    last_message_preview: str | None = None


class SessionRecordMessageResponse(BaseModel):
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


class SessionRecordMessageListResponse(BaseModel):
    items: list[SessionRecordMessageResponse]
    has_more: bool
