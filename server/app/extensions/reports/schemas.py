"""Shared Pydantic schemas for the reports extension.

These are consumed by SR1 (overall report), SR2 (employee report), SR3
(online monitor) routers — kept here to ensure all sub-requirements speak the
same metric vocabulary.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class TrendTypeEnum(str, Enum):
    HALF_HOUR = "half_hour"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class MetricKeyEnum(str, Enum):
    SESSION_COUNT = "session_count"
    MESSAGE_COUNT = "message_count"
    USER_MESSAGE_COUNT = "user_message_count"
    AGENT_MESSAGE_COUNT = "agent_message_count"
    AVG_DURATION_SECONDS = "avg_duration_seconds"
    BOT_SESSION_COUNT = "bot_session_count"
    BOT_HANDOFF_COUNT = "bot_handoff_count"
    QUEUED_SESSION_COUNT = "queued_session_count"
    AVG_QUEUE_DURATION_SECONDS = "avg_queue_duration_seconds"
    OFFLINE_MESSAGE_COUNT = "offline_message_count"


class MetricFormat(str, Enum):
    """How the frontend renders a metric value.

    The backend never sends display text; it sends a stable key plus this format
    so the frontend can localize the label and format the value.
    """
    INTEGER = "integer"
    DURATION_SECONDS = "duration_seconds"
    PERCENT = "percent"


class MetricLevel(str, Enum):
    """Display tier within a metric group.

    PRIMARY metrics surface in the group overview block; AUXILIARY metrics live
    in detail tables / tooltips.
    """
    PRIMARY = "primary"
    AUXILIARY = "auxiliary"


class MetricResult(BaseModel):
    """A single self-describing metric in the report framework.

    The backend is the single source of truth for value, caliber, group
    membership and availability (permission/config gating). The response is a
    flat list — the frontend groups by ``group`` for layout. ``available`` is
    server-authoritative; the frontend hides metrics it cannot show.
    """
    key: str
    value: float | None = None
    format: MetricFormat = MetricFormat.INTEGER
    level: MetricLevel = MetricLevel.PRIMARY
    group: str
    available: bool = True


class MetricDistributionSlice(BaseModel):
    """One slice inside a distribution chart."""
    key: str
    label: str
    value: int = 0


class MetricDistribution(BaseModel):
    """Optional distribution data for a metric group summary."""
    key: str
    group: str
    total: int = 0
    slices: list[MetricDistributionSlice] = Field(default_factory=list)


class OverallSummaryResponse(BaseModel):
    """Overall session report summary as a flat, self-describing metric list."""
    metrics: list[MetricResult]
    distributions: list[MetricDistribution] = Field(default_factory=list)
    as_of: str


class OverallTrendMetricValue(BaseModel):
    """A metric value inside one trend bucket (no level — the bucket only varies value)."""
    key: str
    value: float | None = None
    format: MetricFormat = MetricFormat.INTEGER


class OverallTrendBucket(BaseModel):
    """One bucket on the grouped trend chart, carrying every metric of the group."""
    label: str
    bucket_start: str
    bucket_end: str
    metrics: list[OverallTrendMetricValue]


class OverallTrendResponse(BaseModel):
    """Trend for one metric group: chart shows one metric, detail table shows all."""
    trend: TrendTypeEnum
    group: str
    metrics: list[MetricResult]
    buckets: list[OverallTrendBucket]
    as_of: str


class CallMetricKeyEnum(str, Enum):
    TOTAL_CALLS = "total_calls"
    INBOUND_CALLS = "inbound_calls"
    ANSWERED_INBOUND_CALLS = "answered_inbound_calls"
    OUTBOUND_CALLS = "outbound_calls"
    ANSWERED_OUTBOUND_CALLS = "answered_outbound_calls"
    AVG_INBOUND_TALK_SECONDS = "avg_inbound_talk_seconds"
    AVG_OUTBOUND_TALK_SECONDS = "avg_outbound_talk_seconds"


class OverviewMetrics(BaseModel):
    """Overview metrics for a single scope.

    Average values are floats in seconds; frontend formats them to ``mm:ss`` or
    ``HH:mm:ss``. Business supplement metrics are used by the overall report and
    intentionally remain defaulted for employee-scoped views.
    """
    session_count: int = 0
    message_count: int = 0
    user_message_count: int = 0
    agent_message_count: int = 0
    avg_duration_seconds: float | None = None
    bot_session_count: int = 0
    bot_handoff_count: int = 0
    queued_session_count: int = 0
    avg_queue_duration_seconds: float | None = None
    offline_message_count: int | None = None
    can_view_offline_messages: bool = False
    # Reception-segment calibers (overall + employee scope). Attributed by the
    # conversation start time, scoped by the segment's agent.
    reception_segment_count: int = 0
    reception_participated_session_count: int = 0
    reception_final_session_count: int = 0
    reception_transfer_in_count: int = 0
    reception_transfer_out_count: int = 0


class CallOverviewMetrics(BaseModel):
    """All seven overall call report metrics.

    Average talk-time values are in seconds. The frontend formats them to
    ``mm:ss`` or ``HH:mm:ss`` and renders ``None`` as no data.
    """

    total_calls: int = 0
    inbound_calls: int = 0
    answered_inbound_calls: int = 0
    outbound_calls: int = 0
    answered_outbound_calls: int = 0
    avg_inbound_talk_seconds: float | None = None
    avg_outbound_talk_seconds: float | None = None


class CallOverviewResponse(CallOverviewMetrics):
    as_of: str


class TrendBucketResult(BaseModel):
    """One bucket on the trend chart, carrying all five metrics."""
    label: str = Field(..., description="X-axis label, e.g. '00:00', '2026-05-19'")
    bucket_start: str = Field(..., description="ISO 8601 datetime in tenant tz")
    bucket_end: str = Field(..., description="ISO 8601 datetime in tenant tz, exclusive")
    metrics: OverviewMetrics


class CallTrendBucketResult(BaseModel):
    """One call-report trend bucket carrying all seven metrics."""

    label: str = Field(..., description="X-axis label, e.g. '00:00', '2026-05-19'")
    bucket_start: str = Field(..., description="ISO 8601 datetime in tenant tz")
    bucket_end: str = Field(..., description="ISO 8601 datetime in tenant tz, exclusive")
    metrics: CallOverviewMetrics


class CallTrendResponse(BaseModel):
    trend: TrendTypeEnum
    buckets: list[CallTrendBucketResult]
    as_of: str


CallReportCoverageStatus = Literal["available", "partial", "unavailable"]


class CallReportCoverage(BaseModel):
    """Historical coverage of the grouped call report."""

    effective_at: str
    requested_start: str
    requested_end: str
    actual_start: str | None = None
    actual_end: str | None = None
    truncated: bool = False
    status: CallReportCoverageStatus = "available"


class CallReportDataQuality(BaseModel):
    """Finalization and satisfaction projection gaps in the current sample."""

    pending: int = 0
    incomplete: int = 0
    failed: int = 0
    satisfaction_pending: int = 0


class CallOverallSummaryResponse(BaseModel):
    """Grouped call-report summary."""

    metrics: list[MetricResult]
    distributions: list[MetricDistribution] = Field(default_factory=list)
    data_quality: CallReportDataQuality = Field(default_factory=CallReportDataQuality)
    coverage: CallReportCoverage
    as_of: str


class CallOverallTrendResponse(BaseModel):
    """Trend response for one grouped call-report provider."""

    trend: TrendTypeEnum
    group: str
    metrics: list[MetricResult]
    buckets: list[OverallTrendBucket]
    coverage: CallReportCoverage
    as_of: str


class EmployeeBrief(BaseModel):
    """Minimum employee identity for table rendering."""
    id: int
    name: str
    username: str | None = None
    display_name: str | None = None
    email: str | None = None
    avatar: str | None = None
    is_active: bool = True
    status: Literal["active", "inactive", "deleted"] = "active"


class EmployeeOverviewRow(BaseModel):
    """Used by SR2 employee list and SR3 online monitor employee table."""
    employee: EmployeeBrief
    metrics: OverviewMetrics


QueueTypeLiteral = Literal["employee_group"]
QueueStatusLiteral = Literal["active", "inactive", "deleted"]
QueueMetricGroupLiteral = Literal["queue_access", "human_messages", "service_efficiency", "satisfaction"]


class QueueBrief(BaseModel):
    """Minimum queue identity for queue-report list/detail rendering."""

    queue_type: QueueTypeLiteral
    queue_id: int
    name: str
    status: QueueStatusLiteral = "active"


class QueueReportMetrics(BaseModel):
    """Queue report metrics for one queue and one date range."""

    queued_session_count: int = 0
    assigned_queue_session_count: int = 0
    unassigned_queue_session_count: int = 0
    queue_assign_rate: float | None = None
    avg_queue_duration_seconds: float | None = None
    max_queue_duration_seconds: float | None = None
    final_session_count: int = 0
    effective_session_count: int = 0
    user_message_count: int = 0
    agent_message_count: int = 0
    unreplied_session_count: int = 0
    visitor_silent_session_count: int = 0
    avg_first_human_response_seconds: float | None = None
    avg_agent_response_seconds: float | None = None
    avg_human_session_duration_seconds: float | None = None
    satisfaction_invitation_count: int = 0
    satisfaction_submission_count: int = 0
    satisfaction_participation_rate: float | None = None
    satisfaction_submission_rate: float | None = None
    product_satisfaction_count: int = 0


class QueueOverviewRow(BaseModel):
    """Queue identity plus queue-report metrics."""

    queue: QueueBrief
    metrics: QueueReportMetrics


class QueueListResponse(BaseModel):
    """Paginated queue report list response."""

    items: list[QueueOverviewRow]
    total: int
    page: int
    per_page: int
    pages: int
    sort: str
    order: str
    as_of: str


class QueueDetailResponse(BaseModel):
    """Single queue report overview response."""

    queue: QueueBrief
    metrics: QueueReportMetrics
    distributions: list[MetricDistribution] = Field(default_factory=list)
    as_of: str


class QueueTrendResponse(BaseModel):
    """Queue report trend for one metric group."""

    trend: TrendTypeEnum
    group: QueueMetricGroupLiteral
    metrics: list[MetricResult]
    buckets: list[OverallTrendBucket]
    as_of: str


class CallEmployeeOverviewRow(BaseModel):
    """Employee identity plus core comparison metrics."""

    employee: EmployeeBrief
    metrics: "CallAgentOverviewMetrics"


class CallAgentOverviewMetrics(BaseModel):
    participated_call_count: int = 0
    handled_call_count: int = 0
    reception_segment_count: int = 0
    inbound_handled_call_count: int = 0
    outbound_attempt_count: int = 0
    outbound_customer_answered_count: int = 0
    outbound_handled_call_count: int = 0
    transfer_in_segment_count: int = 0
    offered_call_count: int = 0
    offer_attempt_count: int = 0
    offer_accepted_count: int = 0
    offer_accept_rate: float | None = None
    offer_rejected_count: int = 0
    offer_timeout_count: int = 0
    offer_timeout_rate: float | None = None
    avg_offer_response_seconds: float | None = None
    total_talk_seconds: float | None = None
    avg_talk_seconds: float | None = None
    held_segment_count: int = 0
    total_hold_seconds: float | None = None
    avg_hold_seconds: float | None = None
    total_after_call_work_seconds: float | None = None
    avg_after_call_work_seconds: float | None = None
    avg_handle_seconds: float | None = None
    transfer_attempt_count: int = 0
    transfer_completed_count: int = 0
    transfer_success_rate: float | None = None
    transfer_failed_count: int = 0
    consult_attempt_count: int = 0
    consult_connected_count: int = 0
    consult_success_rate: float | None = None
    conference_join_count: int = 0


class CallAgentDataQuality(BaseModel):
    processing: int = 0
    reception_incomplete: int = 0
    offer_incomplete: int = 0
    after_call_work_incomplete: int = 0
    failed: int = 0


class CallEmployeesListResponse(BaseModel):
    """Paginated employee call-report list response."""

    items: list[CallEmployeeOverviewRow]
    total: int
    page: int
    per_page: int
    pages: int
    sort: str
    order: str
    data_quality: CallAgentDataQuality = Field(default_factory=CallAgentDataQuality)
    coverage: CallReportCoverage
    as_of: str


class CallEmployeeSummaryResponse(BaseModel):
    employee: EmployeeBrief
    group_names: list[str] = Field(default_factory=list)
    metrics: list[MetricResult]
    distributions: list[MetricDistribution] = Field(default_factory=list)
    data_quality: CallAgentDataQuality = Field(default_factory=CallAgentDataQuality)
    coverage: CallReportCoverage
    as_of: str


class CallEmployeeTrendResponse(BaseModel):
    trend: TrendTypeEnum
    group: str
    metrics: list[MetricResult]
    buckets: list[OverallTrendBucket]
    coverage: CallReportCoverage
    as_of: str


CallQueueTypeLiteral = Literal["employee_group", "employee"]
CallQueueStatusLiteral = Literal["active", "inactive", "deleted"]


class CallQueueBrief(BaseModel):
    """Queue identity shown by call queue reports."""

    queue_type: CallQueueTypeLiteral
    queue_id: int
    name: str
    status: CallQueueStatusLiteral = "active"


class CallQueueOverviewMetrics(BaseModel):
    """All queue comparison metrics for one list row."""

    queue_call_count: int = 0
    queue_entry_count: int = 0
    first_queue_entry_count: int = 0
    transfer_in_entry_count: int = 0
    queue_answered_count: int = 0
    queue_answer_rate: float | None = None
    queue_abandoned_count: int = 0
    queue_abandon_rate: float | None = None
    queue_short_abandon_count: int = 0
    queue_short_abandon_rate: float | None = None
    queue_timeout_count: int = 0
    queue_transfer_out_count: int = 0
    avg_answer_wait_seconds: float | None = None
    avg_abandon_wait_seconds: float | None = None
    avg_queue_wait_seconds: float | None = None
    max_queue_wait_seconds: float | None = None
    queue_service_level_20s: float | None = None
    offered_call_count: int = 0
    offer_attempt_count: int = 0
    offer_accepted_count: int = 0
    offer_rejected_count: int = 0
    offer_timeout_count: int = 0
    offer_accept_rate: float | None = None


class CallQueueOverviewRow(BaseModel):
    queue: CallQueueBrief
    metrics: CallQueueOverviewMetrics


class CallQueueDataQuality(BaseModel):
    pending: int = 0
    incomplete: int = 0
    failed: int = 0


class CallQueueListResponse(BaseModel):
    items: list[CallQueueOverviewRow]
    total: int
    page: int
    per_page: int
    pages: int
    sort: str
    order: str
    data_quality: CallQueueDataQuality = Field(default_factory=CallQueueDataQuality)
    coverage: CallReportCoverage
    as_of: str


class CallQueueSummaryResponse(BaseModel):
    queue: CallQueueBrief
    metrics: list[MetricResult]
    distributions: list[MetricDistribution] = Field(default_factory=list)
    data_quality: CallQueueDataQuality = Field(default_factory=CallQueueDataQuality)
    coverage: CallReportCoverage
    as_of: str


class CallQueueTrendResponse(BaseModel):
    trend: TrendTypeEnum
    group: str
    metrics: list[MetricResult]
    buckets: list[OverallTrendBucket]
    coverage: CallReportCoverage
    as_of: str


class CallMonitorToday(BaseModel):
    """Today's tenant-wide call monitor counters."""

    range_label: str
    total_calls: int = 0
    inbound_calls: int = 0
    answered_inbound_calls: int = 0
    outbound_calls: int = 0
    answered_outbound_calls: int = 0


# Persistent call-center status from ``agent_status``.
CallCenterStatusLiteral = Literal["ready", "busy", "break", "after_call_work", "offline"]


class CallMonitorEmployeeRow(BaseModel):
    """Single employee row for the call monitor table."""

    employee: EmployeeBrief
    call_center_status: CallCenterStatusLiteral = "offline"
    answered_inbound_calls: int = 0
    outbound_calls: int = 0
    answered_outbound_calls: int = 0


class CallMonitorResponse(BaseModel):
    """Enterprise call monitor page payload."""

    today: CallMonitorToday
    employees: list[CallMonitorEmployeeRow]
    as_of: str


class DateRangeParams(BaseModel):
    """Reusable query param holder; validated separately."""
    start: str = Field(..., description="YYYY-MM-DD")
    end: str = Field(..., description="YYYY-MM-DD")


# Sentinel for SR3 — agent online status (mirror of AgentOnlineStatus + 'unknown')
OnlineStatusLiteral = Literal["online", "busy", "offline", "unknown"]


# ── Supervisor call intervention (live monitoring) ───────────────────────────

# Call phase of a live customer call, as far as the current backend can tell.
# ``single`` is the only phase reliably derivable from persisted state today;
# the finer phases require live media-kernel state that is not yet exposed (see
# the phase GAP note in ``lib/active_calls.py``).
CallPhaseLiteral = Literal[
    "single",        # 通话中 (single customer + agent leg)
    "customer_hold", # 客户保持
    "consulting",    # 咨询中 / 咨询呼叫已接通
    "three_way",     # 三方通话
    "transferring",  # 转接提交中 / 通话结束中
]

# Supervisor intervention modes.
InterventionModeLiteral = Literal["listen", "whisper", "barge", "takeover", "force_hangup"]

CallDirectionLiteral = Literal["inbound", "outbound"]


class SupervisorBrief(BaseModel):
    """Identity of a supervisor currently monitoring a call."""

    employee_id: int
    name: str
    mode: InterventionModeLiteral


class LiveCallRow(BaseModel):
    """One in-progress customer call visible in the supervisor live-call table.

    ``masked_customer_number`` is already masked by the backend; the raw number
    is never returned. ``current_supervisor`` is ``None`` when no supervisor is
    monitoring the call.
    """

    call_id: str
    conversation_id: str | None = None
    agent: EmployeeBrief
    masked_customer_number: str
    direction: CallDirectionLiteral
    queue_name: str | None = None
    phase: CallPhaseLiteral = "single"
    answered_at: str | None = None
    talk_duration_seconds: int = 0
    current_supervisor: SupervisorBrief | None = None


class LiveCallsResponse(BaseModel):
    """Data-scope-filtered list of in-progress calls for supervisor monitoring."""

    items: list[LiveCallRow]
    as_of: str


class InterventionReasonRequest(BaseModel):
    """Reason payload for takeover / force-hangup confirmations.

    ``reason`` is a stable key (e.g. ``customer_escalation``); ``note`` is an
    optional free-text supplement, required by the UI when ``reason`` is
    ``other`` (the frontend enforces that; the backend stores whatever arrives).
    """

    reason: str = Field(..., min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=200)


class InterventionResult(BaseModel):
    """Outcome of an intervention request.

    ``ok`` reports whether the media action was actually carried out. When the
    media kernel cannot perform the mode (rooms disabled), the endpoint raises
    501 instead of returning this with ``ok=False``.
    """

    ok: bool
    call_id: str
    mode: InterventionModeLiteral
    supervisor_id: int


class SupervisorWebRTCOfferRequest(BaseModel):
    """Supervisor browser SDP offer to negotiate the supervisor's media leg."""

    sdp: str = Field(..., min_length=1)


class SupervisorWebRTCOfferResponse(BaseModel):
    """SDP answer plus the negotiated supervisor media-leg id for the call."""

    call_id: str
    supervisor_call_id: str
    sdp: str


class SupervisorIceRequest(BaseModel):
    """One trickled browser ICE candidate for the supervisor's media leg."""

    candidate: str
    sdp_mid: str | None = None
    sdp_m_line_index: int | None = None
