"""
Schemas for auto outbound task APIs.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.outbound_task import OutboundTaskField


AutoOutboundTaskStatus = Literal["draft", "active", "paused", "completed", "archived"]
AutoOutboundExecutionMode = Literal["ivr", "bot", "agent"]
AutoOutboundPacingMode = Literal["progressive", "ratio", "predictive"]
AutoOutboundAbandonPrompt = Literal["play_wait", "hangup"]
AutoOutboundTargetStatus = Literal["pending", "calling", "redial_pending", "completed", "invalid"]
# Manual target edits must not force engine-owned states like "calling".
AutoOutboundTargetEditableStatus = Literal["pending", "invalid", "redial_pending"]
AutoOutboundTerminalState = Literal[
    "answered", "no_answer", "busy", "power_off", "invalid_number", "failed"
]
AutoOutboundReceptionType = Literal["ivr", "bot", "agent", "none"]

DEFAULT_DAILY_TIME_WINDOWS = [
    {"start": "09:00", "end": "12:00"},
    {"start": "14:00", "end": "20:00"},
]
DEFAULT_RETRY_POLICY = {
    "no_answer": {"max_retries": 2, "interval_minutes": 120},
    "busy": {"max_retries": 2, "interval_minutes": 120},
    "power_off": {"max_retries": 2, "interval_minutes": 120},
}


class DailyTimeWindow(BaseModel):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def validate_hhmm(cls, value: str) -> str:
        value = value.strip()
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("Time window must use HH:mm format")
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError as exc:
            raise ValueError("Time window must use HH:mm format") from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Time window must use HH:mm format")
        return f"{hour:02d}:{minute:02d}"

    @model_validator(mode="after")
    def validate_order(self) -> "DailyTimeWindow":
        if self.end <= self.start:
            raise ValueError("Time window end must be after start")
        return self


class RetryPolicyItem(BaseModel):
    max_retries: int = Field(default=2, ge=0, le=5)
    interval_minutes: int = Field(default=120, ge=1, le=24 * 60)


class RetryPolicy(BaseModel):
    no_answer: RetryPolicyItem = Field(default_factory=RetryPolicyItem)
    busy: RetryPolicyItem = Field(default_factory=RetryPolicyItem)
    power_off: RetryPolicyItem = Field(default_factory=RetryPolicyItem)


class AutoOutboundTaskBase(BaseModel):
    name: str
    description: str | None = None
    owner_id: int | None = None
    execution_mode: AutoOutboundExecutionMode
    voice_flow_id: int | None = None
    voice_flow_name: str | None = None
    transfer_queue_id: int | None = None
    voicespeed_agent_id: str | None = None
    voicespeed_agent_name: str | None = None
    intent_result_field_key: str | None = None
    queue_id: int | None = None
    pacing_mode: AutoOutboundPacingMode | None = None
    dial_ratio: int | None = None
    dial_intensity: Decimal | None = None
    abandon_rate_limit: Decimal | None = None
    abandon_prompt: AutoOutboundAbandonPrompt | None = None
    wrapup_seconds: int = Field(default=60, ge=15, le=300)
    start_date: date
    end_date: date
    daily_time_windows: list[DailyTimeWindow] = Field(default_factory=lambda: list(DEFAULT_DAILY_TIME_WINDOWS))
    caller_number_id: str | None = None
    max_concurrency: int = Field(default=10, ge=1, le=500)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    daily_per_number_limit: int = Field(default=3, ge=1, le=10)
    auto_resume_on_target_append: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Please enter a task name")
        if len(value) > 80:
            raise ValueError("Name must be at most 80 characters")
        return value

    @field_validator("voicespeed_agent_id", "voicespeed_agent_name", "intent_result_field_key", "caller_number_id")
    @classmethod
    def strip_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_config(self) -> "AutoOutboundTaskBase":
        if self.end_date < self.start_date:
            raise ValueError("End date must not be earlier than start date")
        if not self.daily_time_windows:
            raise ValueError("Please configure daily call time windows")

        if self.execution_mode == "ivr":
            if self.voice_flow_id is None:
                raise ValueError("Please select a reception target")
        elif self.execution_mode == "bot":
            if not self.voicespeed_agent_id or self.transfer_queue_id is None:
                raise ValueError("Please select a reception target")
        elif self.execution_mode == "agent":
            if self.queue_id is None or self.pacing_mode is None:
                raise ValueError("Please select a reception target")
            if self.pacing_mode == "ratio":
                if self.dial_ratio is None or not (2 <= self.dial_ratio <= 5):
                    raise ValueError("Dial ratio must be between 2 and 5")
                if self.abandon_prompt is None:
                    raise ValueError("Abandon prompt is required for ratio pacing")
            elif self.pacing_mode == "predictive":
                if self.dial_intensity is None or not (Decimal("1.0") <= self.dial_intensity <= Decimal("3.0")):
                    raise ValueError("Dial intensity must be between 1.0 and 3.0")
                if self.abandon_rate_limit is None:
                    raise ValueError("Abandon rate limit is required for predictive pacing")
                if self.abandon_prompt is None:
                    raise ValueError("Abandon prompt is required for predictive pacing")
            if not (15 <= self.wrapup_seconds <= 300):
                raise ValueError("Wrap-up seconds must be between 15 and 300")
        return self


class AutoOutboundTaskCreate(AutoOutboundTaskBase):
    template_id: int
    fields: list[OutboundTaskField] | None = None


class AutoOutboundTaskUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    owner_id: int | None = None
    execution_mode: AutoOutboundExecutionMode | None = None
    voice_flow_id: int | None = None
    voice_flow_name: str | None = None
    transfer_queue_id: int | None = None
    voicespeed_agent_id: str | None = None
    voicespeed_agent_name: str | None = None
    intent_result_field_key: str | None = None
    queue_id: int | None = None
    pacing_mode: AutoOutboundPacingMode | None = None
    dial_ratio: int | None = None
    dial_intensity: Decimal | None = None
    abandon_rate_limit: Decimal | None = None
    abandon_prompt: AutoOutboundAbandonPrompt | None = None
    wrapup_seconds: int | None = Field(default=None, ge=15, le=300)
    start_date: date | None = None
    end_date: date | None = None
    daily_time_windows: list[DailyTimeWindow] | None = None
    caller_number_id: str | None = None
    max_concurrency: int | None = Field(default=None, ge=1, le=500)
    retry_policy: RetryPolicy | None = None
    daily_per_number_limit: int | None = Field(default=None, ge=1, le=10)
    auto_resume_on_target_append: bool | None = None
    fields: list[OutboundTaskField] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Please enter a task name")
        if len(value) > 80:
            raise ValueError("Name must be at most 80 characters")
        return value

    @field_validator("auto_resume_on_target_append")
    @classmethod
    def validate_auto_resume_on_target_append(
        cls, value: bool | None
    ) -> bool | None:
        if value is None:
            raise ValueError("Auto-resume setting must be true or false")
        return value

    @model_validator(mode="after")
    def validate_partial(self) -> "AutoOutboundTaskUpdate":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must not be earlier than start date")
        if self.daily_time_windows is not None and not self.daily_time_windows:
            raise ValueError("Please configure daily call time windows")
        if self.dial_ratio is not None and not (2 <= self.dial_ratio <= 5):
            raise ValueError("Dial ratio must be between 2 and 5")
        if self.dial_intensity is not None and not (Decimal("1.0") <= self.dial_intensity <= Decimal("3.0")):
            raise ValueError("Dial intensity must be between 1.0 and 3.0")
        return self


class AutoOutboundTaskStats(BaseModel):
    total_targets: int = 0
    finished_targets: int = 0
    call_count: int = 0
    answered_count: int = 0
    answer_rate: float | None = None
    transfer_count: int = 0
    abandon_count: int = 0
    abandon_rate: float | None = None
    current_concurrency: int | None = None


class AutoOutboundTaskListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    execution_mode: AutoOutboundExecutionMode
    reception_target_name: str | None = None
    status: AutoOutboundTaskStatus
    out_of_window: bool = False
    auto_pause_reason: str | None = None
    owner_name: str | None = None
    total_targets: int = 0
    finished_targets: int = 0
    call_count: int = 0
    answered_count: int = 0
    answer_rate: float | None = None
    updated_at: datetime | None = None


class AutoOutboundTaskResponse(AutoOutboundTaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    template_id: int | None = None
    template_name: str
    fields: list[OutboundTaskField] = Field(default_factory=list)
    status: AutoOutboundTaskStatus
    auto_pause_reason: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_by_id: int | None = None
    updated_by_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    out_of_window: bool = False
    owner_name: str | None = None
    reception_target_name: str | None = None
    stats: AutoOutboundTaskStats = Field(default_factory=AutoOutboundTaskStats)


class AutoOutboundTargetCreate(BaseModel):
    phone_number: str
    user_id: int | None = None
    field_values: dict[str, Any] = Field(default_factory=dict)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Phone number is required")
        if len(value) > 64:
            raise ValueError("Phone number must be at most 64 characters")
        return value


class AutoOutboundTargetBulkCreateRequest(BaseModel):
    targets: list[AutoOutboundTargetCreate] = Field(min_length=1, max_length=5000)


class AutoOutboundTargetUpdate(BaseModel):
    phone_number: str | None = None
    user_id: int | None = None
    status: AutoOutboundTargetEditableStatus | None = None
    field_values: dict[str, Any] | None = None
    next_call_at: datetime | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Phone number is required")
        if len(value) > 64:
            raise ValueError("Phone number must be at most 64 characters")
        return value

    @field_validator("next_call_at")
    @classmethod
    def validate_next_call_at_tz_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("next_call_at must be timezone-aware")
        return value


class AutoOutboundTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    task_id: int
    phone_number: str
    user_id: int | None = None
    user_name: str | None = None
    status: AutoOutboundTargetStatus
    field_values: dict[str, Any]
    call_count: int
    answered_count: int
    retry_counts: dict[str, Any] = Field(default_factory=dict)
    remaining_retries: int = 0
    last_called_at: datetime | None = None
    last_call_result: str | None = None
    next_call_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    task_auto_resumed: bool = False


class AutoOutboundTargetBulkCreateResponse(BaseModel):
    created: int
    items: list[AutoOutboundTargetResponse]
    task_auto_resumed: bool = False


class AutoOutboundTargetImportError(BaseModel):
    row_number: int
    phone_number: str | None = None
    reason: str


class AutoOutboundTargetImportResponse(BaseModel):
    total: int
    created: int
    failed: int
    skipped_rate_limited: int = 0
    errors: list[AutoOutboundTargetImportError] = Field(default_factory=list)
    task_auto_resumed: bool = False


class AutoOutboundRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    task_id: int
    target_id: int
    call_record_id: int | None = None
    call_record_public_id: str | None = None
    phone_number: str
    attempt_id: str | None = None
    attempt_no: int
    started_at: datetime
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int
    terminal_state: AutoOutboundTerminalState | None = None
    reception_type: AutoOutboundReceptionType | None = None
    agent_id: int | None = None
    agent_name: str | None = None
    reception_result: dict[str, Any] | None = None
    fail_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DailyTrendPoint(BaseModel):
    date: date
    call_count: int = 0
    answered_count: int = 0
    answer_rate: float | None = None


class TerminalStateDistributionItem(BaseModel):
    terminal_state: str
    count: int


class AutoOutboundTaskDetailStats(BaseModel):
    daily_trend: list[DailyTrendPoint] = Field(default_factory=list)
    terminal_state_distribution: list[TerminalStateDistributionItem] = Field(default_factory=list)
    result_distribution: dict[str, Any] = Field(default_factory=dict)
    abandon_stats: dict[str, Any] = Field(default_factory=dict)
    abandon_over_limit: bool = False


class DialCapacitySourceBreakdown(BaseModel):
    task: int | None = None
    tenant: int | None = None
    flowkit: int | None = None
    trunk: int | None = None
    batch: int | None = None
    reception: int | None = None


class DialCapacityResponse(BaseModel):
    dialable: int = 0
    sources: DialCapacitySourceBreakdown = Field(default_factory=DialCapacitySourceBreakdown)


class AutoOutboundMonitorResponse(BaseModel):
    in_progress_calls: int = 0
    ready_agents: int | None = None
    in_call_agents: int | None = None
    queued_count: int | None = None
    abandon_rate: float | None = None
    abandon_over_limit: bool = False
    no_ready_agents: bool = False
    dial_capacity: DialCapacityResponse | None = None


class AutoOutboundWrapupRequest(BaseModel):
    """Agent wrap-up payload: business field values written to the target."""

    reception_result: dict[str, Any] = Field(default_factory=dict)
    field_values: dict[str, Any] | None = None


class AutoOutboundAgentContextRecord(BaseModel):
    """Slim call-record slice for the agent workspace wrap-up panel."""

    id: int
    target_id: int
    field_values: dict[str, Any] = Field(default_factory=dict)
    reception_result: dict[str, Any] | None = None


class AutoOutboundAgentContextResponse(BaseModel):
    """Task summary + linked record for agents with call.workspace.use only."""

    task_id: int
    task_name: str
    template_name: str
    fields: list[OutboundTaskField] = Field(default_factory=list)
    wrapup_seconds: int
    record: AutoOutboundAgentContextRecord | None = None
    opening_script_text: str | None = None
    last_utterance: str | None = None
    target_name: str | None = None
    target_phone: str | None = None
    assignment_type: str | None = None


class PaginatedAutoOutboundTasks(BaseModel):
    items: list[AutoOutboundTaskListItem]
    total: int
    page: int
    page_size: int
    pages: int


class PaginatedAutoOutboundTargets(BaseModel):
    items: list[AutoOutboundTargetResponse]
    total: int
    page: int
    page_size: int
    pages: int


class PaginatedAutoOutboundRecords(BaseModel):
    items: list[AutoOutboundRecordResponse]
    total: int
    page: int
    page_size: int
    pages: int
