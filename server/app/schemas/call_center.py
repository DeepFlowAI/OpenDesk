"""
Call-center schemas — agent_status, call_record, agent_webrtc_session.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import PaginatedResponse
from app.schemas.queue import QueueRecordBrief
from app.schemas.ticket import RelatedTicketResponse


# ─────────────── Agent status ───────────────
# Keep in sync with app.constants.call_center.AgentStatus / AgentResourceState.

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
    # In-call control restore after browser refresh (from Redis InCallLegs).
    consult_active: bool = False
    consult_target_employee_id: int | None = None
    # none | ringing | active — see constants.ConsultState
    consult_state: str | None = None
    # When the agent entered in_call (Redis). Used to restore the live timer for
    # consult targets that have no CallRecord of their own.
    in_call_since: datetime | None = None
    # After-call work deadline (Redis epoch, fixed at hangup). Drives the
    # wrap-up countdown; null when not in wrap-up or no deadline applies.
    wrap_up_until: datetime | None = None
    wrap_up_call_id: str | None = None
    # Server-owned call-screen context restored after refresh/reconnect.
    source: str | None = None
    task_id: int | None = None
    record_id: int | None = None


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


class ConsultableAgent(BaseModel):
    """A workspace agent that can be a consult / transfer / conference target."""

    model_config = ConfigDict(from_attributes=True)

    employee_id: int
    name: str | None = None
    avatar: str | None = None
    status: AgentStatusValue
    # Employee groups (queues) this agent belongs to — shown in the target
    # picker so an operator can spot colleagues from their own queue.
    group_names: list[str] = []


class TransferQueue(BaseModel):
    """A queue that can be a blind-transfer target, with live availability."""

    queue_type: str  # always "employee_group"
    queue_id: int
    name: str
    available_agent_count: int


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


class CallRecordingItem(BaseModel):
    recording_id: str
    call_leg_id: str | None = None
    phase: str | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    access_url: str | None = None


class CallSatisfactionAnswerDetail(BaseModel):
    question_node_id: str
    question_name: str
    option_id: str | None = None
    option_label: str | None = None
    answered_at: datetime | None = None


class CallSatisfactionDetail(BaseModel):
    status: str
    trigger_source: str
    flow_name: str
    flow_version_no: int
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    agent_id: int | None = None
    agent_name: str | None = None
    queue_type: str | None = None
    queue_id: int | None = None
    queue_name: str | None = None
    termination_reason: str | None = None
    answers: list[CallSatisfactionAnswerDetail] = Field(default_factory=list)


class CallRecordListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: UUID
    call_id: str
    direction: str
    call_source: str
    source: str | None = None
    task_id: int | None = None
    record_id: int | None = None
    customer_number: str | None = None
    service_number: str | None = None
    lifecycle_status: str
    finalization_status: str | None = None
    actual_reception_type: str | None = None
    call_result: str | None = None
    hangup_party: str | None = None
    hangup_reason_code: str | None = None
    initiator_agent_id: int | None = None
    initiator_agent_name: str | None = None
    last_serving_agent_id: int | None = None
    last_serving_agent_name: str | None = None
    user_id: int | None = None
    user_public_id: str | None = None
    user_name: str | None = None
    user_phone: str | None = None
    user_association_status: CallUserAssociationStatus = "unlinked"
    started_at: datetime
    customer_connected_at: datetime | None = None
    first_agent_connected_at: datetime | None = None
    ended_at: datetime | None = None
    human_service_ended_at: datetime | None = None
    total_duration_ms: int | None = None
    customer_ring_duration_ms: int | None = None
    agent_wait_duration_ms: int | None = None
    customer_agent_talk_duration_ms: int | None = None
    satisfaction_result: str | None = None
    satisfaction_trigger_source: str | None = None
    satisfaction_primary_option_id: str | None = None
    satisfaction_primary_option_label: str | None = None
    satisfaction_answer_count: int | None = None
    satisfaction_duration_ms: int | None = None
    recording_status: str
    last_queue: QueueRecordBrief | None = None


class CallRecordListResponse(PaginatedResponse):
    items: list[CallRecordListItem]


class CallRecordAgentFilterOption(BaseModel):
    id: int
    name: str


class CallRecordQueueFilterOption(BaseModel):
    queue_type: Literal["employee_group", "employee"]
    queue_id: int
    name: str


class CallRecordFilterOptionsResponse(BaseModel):
    agents: list[CallRecordAgentFilterOption] = Field(default_factory=list)
    queues: list[CallRecordQueueFilterOption] = Field(default_factory=list)


class CallRecordDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: UUID
    call_id: str
    conversation_id: str | None = None
    root_call_id: str | None = None
    direction: str
    call_source: str
    custom_business_info: str | None = None
    external_context: dict | None = None
    customer_number: str | None = None
    service_number: str | None = None
    voice_flow_id: int | None = None
    voice_flow_version_id: int | None = None
    initiator_agent_id: int | None = None
    initiator_agent_name: str | None = None
    last_serving_agent_id: int | None = None
    last_serving_agent_name: str | None = None
    lifecycle_status: str
    finalization_status: str | None = None
    result_rule_version: int | None = None
    finalized_at: datetime | None = None
    actual_reception_type: str | None = None
    call_result: str | None = None
    hangup_party: str | None = None
    hangup_reason_code: str | None = None
    user_id: int | None = None
    user_public_id: str | None = None
    user_name: str | None = None
    user_phone: str | None = None
    user_association_status: CallUserAssociationStatus = "unlinked"
    associated_user_candidates: list[CallRecordUserBrief] = Field(default_factory=list)
    started_at: datetime
    customer_connected_at: datetime | None = None
    first_agent_connected_at: datetime | None = None
    ended_at: datetime | None = None
    human_service_ended_at: datetime | None = None
    total_duration_ms: int | None = None
    customer_ring_duration_ms: int | None = None
    agent_wait_duration_ms: int | None = None
    customer_agent_talk_duration_ms: int | None = None
    satisfaction_result: str | None = None
    satisfaction_trigger_source: str | None = None
    satisfaction_primary_option_id: str | None = None
    satisfaction_primary_option_label: str | None = None
    satisfaction_answer_count: int | None = None
    satisfaction_duration_ms: int | None = None
    satisfaction: CallSatisfactionDetail | None = None
    recording_status: str
    recordings: list[CallRecordingItem] = Field(default_factory=list)
    related_tickets: list[RelatedTicketResponse] = Field(default_factory=list)
    last_queue: QueueRecordBrief | None = None


class CallTranscriptSegmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    text: str
    seq: int | None = None
    created_at: datetime


class CallTranscriptResponse(BaseModel):
    call_id: str | None = None
    segments: list[CallTranscriptSegmentSchema] = Field(default_factory=list)


class CallUserAssociationResponse(BaseModel):
    record_public_id: UUID
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


class MediaReconnectRequest(BaseModel):
    """Browser SDP offer to rebuild the agent's media leg mid-call."""

    sdp: str = Field(..., min_length=1)


class MediaReconnectResponse(BaseModel):
    call_id: str
    sdp: str
    consult_active: bool = False
    consult_target_employee_id: int | None = None
