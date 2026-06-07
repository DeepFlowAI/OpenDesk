"""
Session record schemas — read-only views of historical conversations
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.satisfaction_survey_record import SatisfactionSummaryResponse
from app.schemas.ticket import RelatedTicketResponse
from app.schemas.queue import QueueRecordBrief


class SessionRecordVisitor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: str
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
    public_id: str
    share_code: str
    visitor: SessionRecordVisitor | None = None
    agent: SessionRecordAgent | None = None
    channel: SessionRecordChannel | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    ended_by: str | None = None
    created_at: datetime | None = None
    satisfaction: SatisfactionSummaryResponse | None = None
    last_assigned_queue: QueueRecordBrief | None = None
    queue_duration_seconds: int | None = None


class SessionRecordListResponse(BaseModel):
    items: list[SessionRecordResponse]
    total: int
    page: int
    per_page: int
    pages: int


class SessionRecordDetailResponse(SessionRecordResponse):
    """Extended detail with group info."""
    last_message_preview: str | None = None
    related_tickets: list[RelatedTicketResponse] = Field(default_factory=list)


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
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    event_type: str | None = None
    satisfaction_record_id: int | None = None
    config_version: int | None = None


class SessionRecordMessageListResponse(BaseModel):
    items: list[SessionRecordMessageResponse]
    has_more: bool
