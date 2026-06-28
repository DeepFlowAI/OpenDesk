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


class ReceptionParticipant(BaseModel):
    agent_id: int
    name: str | None = None


class SessionRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: str
    share_code: str
    session_type: str | None = None
    bot_handoff_status: str | None = None
    visitor: SessionRecordVisitor | None = None
    agent: SessionRecordAgent | None = None
    channel: SessionRecordChannel | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    ended_by: str | None = None
    duration_seconds: int | None = None
    visitor_system: str | None = None
    visitor_browser: str | None = None
    visitor_ip: str | None = None
    created_at: datetime | None = None
    message_count: int = 0
    visitor_message_count: int = 0
    agent_message_count: int = 0
    bot_phase_message_count: int = 0
    human_phase_message_count: int = 0
    human_phase_visitor_message_count: int = 0
    human_phase_agent_message_count: int = 0
    satisfaction: SatisfactionSummaryResponse | None = None
    last_assigned_queue: QueueRecordBrief | None = None
    queue_duration_seconds: int | None = None
    first_human_response_seconds: int | None = None
    agent_response_count: int | None = None
    agent_avg_response_seconds: int | None = None
    has_queue: bool = False
    queue_entered_at: datetime | None = None
    queue_assigned_at: datetime | None = None
    queue_result: str | None = None
    reception_segment_count: int = 0
    reception_transfer_count: int = 0
    reception_final_agent_id: int | None = None
    reception_participants: list[ReceptionParticipant] = Field(default_factory=list)
    reception_generation_status: str | None = None


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


class SessionRecordSegmentResponse(BaseModel):
    seq_no: int
    agent_id: int | None = None
    agent_name: str | None = None
    group_id: int | None = None
    group_name: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    entry_reason: str
    end_reason: str | None = None
    from_agent_id: int | None = None
    to_agent_id: int | None = None
    visitor_message_count: int = 0
    agent_message_count: int = 0
    first_response_seconds: int | None = None
    avg_response_seconds: int | None = None


class ReceptionTrajectoryResponse(BaseModel):
    conversation_id: int
    conversation_status: str
    generation_status: str | None = None
    segments: list[SessionRecordSegmentResponse] = Field(default_factory=list)
