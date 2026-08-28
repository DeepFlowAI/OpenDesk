"""Schemas and stable event codes for auto outbound task webhooks."""
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AUTO_OUTBOUND_EVENT_TYPES = (
    "auto_outbound.task.updated",
    "auto_outbound.task.started",
    "auto_outbound.task.paused",
    "auto_outbound.task.resumed",
    "auto_outbound.task.completed",
    "auto_outbound.task.archived",
    "auto_outbound.task.deleted",
    "auto_outbound.call.started",
    "auto_outbound.call.answered",
    "auto_outbound.call.ended",
    "auto_outbound.business_record.submitted",
    "auto_outbound.business_record.updated",
)
AUTO_OUTBOUND_EVENT_TYPE_SET = frozenset(AUTO_OUTBOUND_EVENT_TYPES)


class AutoOutboundEventSubscriptionSave(BaseModel):
    enabled: bool
    subscription_public_id: UUID | None = None
    event_types: list[str] = Field(default_factory=list, max_length=len(AUTO_OUTBOUND_EVENT_TYPES))

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip() for value in values))
        invalid = [value for value in normalized if value not in AUTO_OUTBOUND_EVENT_TYPE_SET]
        if invalid:
            raise ValueError("Unsupported auto outbound event type")
        return normalized

    @model_validator(mode="after")
    def validate_enabled_binding(self) -> "AutoOutboundEventSubscriptionSave":
        if self.enabled and self.subscription_public_id is None:
            raise ValueError("Select an event subscription")
        if self.enabled and not self.event_types:
            raise ValueError("Select at least one event")
        return self


class AutoOutboundEventSubscriptionOption(BaseModel):
    public_id: UUID
    name: str
    is_active: bool


class AutoOutboundEventSubscriptionBinding(BaseModel):
    subscription_public_id: UUID
    subscription_name: str
    subscription_is_active: bool
    event_types: list[str]


class AutoOutboundEventSubscriptionResponse(BaseModel):
    task_id: int
    task_name: str
    enabled: bool
    binding: AutoOutboundEventSubscriptionBinding | None = None
    options: list[AutoOutboundEventSubscriptionOption]
    can_manage_global: bool


class AutoOutboundEventModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AutoOutboundActorSnapshot(AutoOutboundEventModel):
    type: Literal["system", "employee", "api_key"]
    name: str | None = None


class AutoOutboundNamedSnapshot(AutoOutboundEventModel):
    name: str


class AutoOutboundUserSnapshot(AutoOutboundEventModel):
    public_id: str


class AutoOutboundFieldDefinitionSnapshot(AutoOutboundEventModel):
    key: str
    name: str
    field_type: str
    required: bool
    agent_editable: bool


class AutoOutboundFieldValueSnapshot(AutoOutboundFieldDefinitionSnapshot):
    value: Any = None


class AutoOutboundTaskScheduleSnapshot(AutoOutboundEventModel):
    start_date: str
    end_date: str
    daily_time_windows: list[dict[str, Any]]


class AutoOutboundDialStrategySnapshot(AutoOutboundEventModel):
    max_concurrency: int
    retry_policy: dict[str, Any]
    daily_per_number_limit: int
    auto_resume_on_target_append: bool


class AutoOutboundTaskStatsSnapshot(AutoOutboundEventModel):
    total_targets: int
    finished_targets: int
    call_count: int
    answered_count: int


class AutoOutboundTaskSnapshot(AutoOutboundEventModel):
    id: int
    name: str
    description: str | None
    status: str
    execution_mode: str
    owner: AutoOutboundNamedSnapshot | None
    template_name: str
    fields: list[AutoOutboundFieldDefinitionSnapshot]
    schedule: AutoOutboundTaskScheduleSnapshot
    dial_strategy: AutoOutboundDialStrategySnapshot
    stats: AutoOutboundTaskStatsSnapshot
    updated_at: str | None


class AutoOutboundTaskStatusChange(AutoOutboundEventModel):
    previous_status: str
    current_status: str
    reason: str | None = None
    changed_at: str


class AutoOutboundTaskEventPayload(AutoOutboundEventModel):
    task: AutoOutboundTaskSnapshot
    actor: AutoOutboundActorSnapshot
    changed_fields: list[str] | None = None
    status_change: AutoOutboundTaskStatusChange | None = None


class AutoOutboundCallTaskSnapshot(AutoOutboundEventModel):
    id: int
    name: str
    execution_mode: str


class AutoOutboundCallTargetSnapshot(AutoOutboundEventModel):
    id: int
    phone_number: str
    user: AutoOutboundUserSnapshot | None
    status: str
    last_call_result: str | None
    next_call_at: str | None
    remaining_retries: int
    updated_at: str | None


class AutoOutboundCallSnapshot(AutoOutboundEventModel):
    id: int
    attempt_id: str | None
    attempt_no: int
    call_record_public_id: str | None
    started_at: str | None
    answered_at: str | None
    ended_at: str | None
    duration_ms: int
    terminal_state: str | None
    reception_type: str | None
    agent: AutoOutboundNamedSnapshot | None
    reception: dict[str, bool] | None


class AutoOutboundCallEventPayload(AutoOutboundEventModel):
    task: AutoOutboundCallTaskSnapshot
    target: AutoOutboundCallTargetSnapshot
    call: AutoOutboundCallSnapshot


class AutoOutboundBusinessTaskSnapshot(AutoOutboundEventModel):
    id: int
    name: str
    template_name: str


class AutoOutboundBusinessTargetSnapshot(AutoOutboundEventModel):
    id: int
    phone_number: str
    user: AutoOutboundUserSnapshot | None
    fields: list[AutoOutboundFieldValueSnapshot]
    updated_at: str | None


class AutoOutboundBusinessCallSnapshot(AutoOutboundEventModel):
    id: int
    call_record_public_id: str | None


class AutoOutboundBusinessRecordEventPayload(AutoOutboundEventModel):
    task: AutoOutboundBusinessTaskSnapshot
    target: AutoOutboundBusinessTargetSnapshot
    call: AutoOutboundBusinessCallSnapshot | None
    actor: AutoOutboundActorSnapshot
    submitted_keys: list[str] | None = None
    changed_keys: list[str] | None = None
    occurred_at: str
