"""
Call-center schemas — agent_status, call_record, agent_webrtc_session.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import PaginatedResponse
from app.schemas.queue import QueueRecordBrief
from app.schemas.ticket import RelatedTicketResponse


# ─────────────── Agent status ───────────────

AgentStatusValue = Literal["ready", "busy", "break", "after_call_work", "offline"]
AgentResourceState = Literal[
    "idle",
    "reserved",
    "ringing",
    "in_call",
    "after_call_work",
    "unavailable",
]
CallDirection = Literal["inbound", "outbound"]


class AgentStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: int
    status: AgentStatusValue
    reason: str | None = None
    status_changed_at: datetime | None = None
    updated_at: datetime | None = None
    resource_state: AgentResourceState | None = None
    current_call_id: str | None = None
    offer_id: str | None = None
    queue_id: int | None = None
    direction: CallDirection | None = None
    reserved_until: datetime | None = None
    resource_updated_at: datetime | None = None
    last_release_reason: str | None = None


class AgentStatusUpdate(BaseModel):
    status: AgentStatusValue
    reason: str | None = Field(None, max_length=120)


class OnlineAgentItem(BaseModel):
    employee_id: int
    name: str | None = None
    webrtc_call_id: str
    status: AgentStatusValue


class OnlineAgentList(BaseModel):
    items: list[OnlineAgentItem]


# ─────────────── Call record ───────────────


CallUserAssociationStatus = Literal[
    "unknown",
    "unlinked",
    "linked",
    "created",
    "multiple",
    "failed",
]


class CallRecordUserBrief(BaseModel):
    id: int
    public_id: str
    name: str | None = None
    phone: str | None = None
    email: str | None = None


class CallRecordListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    call_id: str
    direction: str
    state: str
    from_number: str | None = None
    to_number: str | None = None
    employee_group_id: int | None = None
    agent_id: int | None = None
    agent_name: str | None = None
    user_id: int | None = None
    user_public_id: str | None = None
    user_name: str | None = None
    user_phone: str | None = None
    user_association_status: CallUserAssociationStatus = "unlinked"
    started_at: datetime
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    ring_duration_ms: int | None = None
    talk_duration_ms: int | None = None
    last_assigned_queue: QueueRecordBrief | None = None
    queue_duration_seconds: int | None = None


class CallRecordListResponse(PaginatedResponse):
    items: list[CallRecordListItem]


class CallRecordDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    call_id: str
    conversation_id: str | None = None
    root_call_id: str | None = None
    direction: str
    state: str
    from_number: str | None = None
    to_number: str | None = None
    voice_flow_id: int | None = None
    voice_flow_version_id: int | None = None
    employee_group_id: int | None = None
    agent_id: int | None = None
    agent_name: str | None = None
    user_id: int | None = None
    user_public_id: str | None = None
    user_name: str | None = None
    user_phone: str | None = None
    user_association_status: CallUserAssociationStatus = "unlinked"
    associated_user_candidates: list[CallRecordUserBrief] = Field(default_factory=list)
    started_at: datetime
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    ring_duration_ms: int | None = None
    talk_duration_ms: int | None = None
    hangup_reason: str | None = None
    recording_url: str | None = None
    recording_duration_ms: int | None = None
    related_tickets: list[RelatedTicketResponse] = Field(default_factory=list)
    last_assigned_queue: QueueRecordBrief | None = None
    queue_duration_seconds: int | None = None
    metadata: dict = {}


class CallUserAssociationResponse(BaseModel):
    record_id: int
    call_id: str
    identified_number: str | None = None
    normalized_number: str | None = None
    status: CallUserAssociationStatus
    user: CallRecordUserBrief | None = None
    candidates: list[CallRecordUserBrief] = Field(default_factory=list)


class CallRecordUserLinkRequest(BaseModel):
    user_id: int


# ─────────────── WebRTC session ───────────────


class WebRTCSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    webrtc_call_id: str
    state: str
    started_at: datetime
    ended_at: datetime | None = None


class WebRTCSessionOpenRequest(BaseModel):
    webrtc_call_id: str = Field(..., min_length=1, max_length=80)


class WebRTCOfferRequest(BaseModel):
    """Browser SDP offer forwarded by the agent workspace."""

    sdp: str = Field(..., min_length=1)


class WebRTCOfferResponse(BaseModel):
    """FlowKit's SDP answer + the real call_id we should bind to the session."""

    call_id: str
    sdp: str


class WebRTCIceCandidate(BaseModel):
    """ICE candidate payload — Browser ↔ FlowKit. Forwarded verbatim."""

    candidate: str
    sdp_mid: str | None = None
    sdp_m_line_index: int | None = None


class WebRTCIceRequest(BaseModel):
    call_id: str
    candidate: WebRTCIceCandidate


class AcceptOfferRequest(BaseModel):
    """Agent accepting a ring-on-demand offer.

    Browser already ran getUserMedia + createOffer locally; we forward the
    SDP to FlowKit (webrtc.offer + call.answer), persist the resulting
    call_id, then resolve the pending offer so the workflow proceeds.
    """

    offer_id: str = Field(..., min_length=1, max_length=64)
    sdp: str = Field(..., min_length=1)


class AcceptOfferResponse(BaseModel):
    ok: bool
    call_id: str | None = None
    sdp: str | None = None
    error: str | None = None


class RejectOfferRequest(BaseModel):
    offer_id: str = Field(..., min_length=1, max_length=64)


class DialOutboundRequest(BaseModel):
    """Agent-initiated outbound call.

    - `outbound_phone_number_id` MUST be assigned to the agent's tenant and
      have "outbound" in its call_types. The number's bound trunk_id and
      the number itself (as caller_id) are forwarded to FlowKit.
    - `destination` is the dialed number (E.164 or carrier-local form).
      FlowKit applies the trunk's callee_prefix as needed.
    """

    outbound_phone_number_id: str = Field(..., min_length=1, max_length=64)
    destination: str = Field(..., min_length=1, max_length=64)


class DialOutboundResponse(BaseModel):
    call_id: str
    conversation_id: str | None = None
    status: str = "originating"


class CancelOutboundRequest(BaseModel):
    """Agent cancelling an in-flight outbound call (the cancel button in
    the outbound_ringing UI). `call_id` is the FlowKit SIP call id that
    /dial returned to the browser."""

    call_id: str = Field(..., min_length=1, max_length=64)


class DialWebRTCOfferRequest(BaseModel):
    """Agent's browser posting an SDP offer for the outbound call's audio leg.

    Sent immediately after `/dial` returns; the SIP leg is still ringing.
    We pair this WebRTC leg with the outbound SIP call_id so the backend
    can bridge them the moment the carrier answers.
    """

    outbound_call_id: str = Field(..., min_length=1, max_length=64)
    sdp: str = Field(..., min_length=1)


class DialWebRTCOfferResponse(BaseModel):
    webrtc_call_id: str
    sdp: str
