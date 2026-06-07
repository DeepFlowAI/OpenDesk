"""
Unified queue engine schemas.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import (
    QueueAssignmentStrategy,
    QueueAssignmentType,
    QueueChannel,
    QueuePolicyScopeType,
    QueueTaskStatus,
    QueueTaskType,
    QueueType,
)
from app.schemas.base import PaginatedResponse


QUEUE_ASSIGNMENT_STRATEGIES_BY_CHANNEL: dict[QueueChannel, set[QueueAssignmentStrategy]] = {
    QueueChannel.ONLINE_CHAT: {
        QueueAssignmentStrategy.ROUND_ROBIN,
        QueueAssignmentStrategy.FIXED_ORDER,
        QueueAssignmentStrategy.RANDOM,
        QueueAssignmentStrategy.CURRENT_LOAD_LOW,
    },
    QueueChannel.CALL_CENTER: {
        QueueAssignmentStrategy.ROUND_ROBIN,
        QueueAssignmentStrategy.FIXED_ORDER,
        QueueAssignmentStrategy.RANDOM,
    },
}


def normalize_queue_assignment_strategy(channel: str, strategy: str | None) -> str | None:
    if strategy is None:
        return None
    try:
        channel_value = QueueChannel(channel)
        strategy_value = QueueAssignmentStrategy(strategy)
    except ValueError:
        return None
    if strategy_value not in QUEUE_ASSIGNMENT_STRATEGIES_BY_CHANNEL[channel_value]:
        return None
    return strategy_value.value


class QueuePolicyUpsert(BaseModel):
    channel: QueueChannel
    scope_type: QueuePolicyScopeType
    scope_id: int | None = None
    enabled: bool = True
    assignment_strategy: QueueAssignmentStrategy | None = None
    max_waiting_count: int | None = Field(default=None, ge=1, le=99999)
    max_wait_seconds: int | None = Field(default=None, ge=1, le=86400)
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_scope(self) -> "QueuePolicyUpsert":
        if self.scope_type == QueuePolicyScopeType.GLOBAL:
            self.scope_id = None
        elif self.scope_id is None or self.scope_id <= 0:
                raise ValueError("scope_id is required for non-global policies")
        if self.scope_type == QueuePolicyScopeType.EMPLOYEE:
            self.assignment_strategy = None
            return self
        if self.assignment_strategy is None:
            self.assignment_strategy = QueueAssignmentStrategy.ROUND_ROBIN
        supported = QUEUE_ASSIGNMENT_STRATEGIES_BY_CHANNEL[self.channel]
        if self.assignment_strategy not in supported:
            raise ValueError(f"{self.assignment_strategy.value} is not supported for {self.channel.value}")
        return self


class QueuePolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    channel: str
    scope_type: str
    scope_id: int | None = None
    enabled: bool
    assignment_strategy: str | None = None
    max_waiting_count: int | None = None
    max_wait_seconds: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QueuePolicyListResponse(PaginatedResponse):
    items: list[QueuePolicyResponse]


class QueueEnqueueRequest(BaseModel):
    channel: QueueChannel
    task_type: QueueTaskType
    task_ref_id: str = Field(min_length=1, max_length=128)
    task_ref_public_id: str | None = Field(default=None, max_length=128)
    queue_type: QueueType
    queue_id: int = Field(gt=0)
    priority: int = Field(default=5, ge=1, le=10)
    source_type: str = Field(default="manual_api", min_length=1, max_length=64)
    source_context: dict[str, Any] = Field(default_factory=dict)
    assignment_strategy: QueueAssignmentStrategy | None = None
    deadline_at: datetime | None = None

    @field_validator("task_ref_id", "source_type")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value is required")
        return value

    @model_validator(mode="after")
    def validate_assignment_strategy(self) -> "QueueEnqueueRequest":
        if self.queue_type == QueueType.EMPLOYEE:
            self.assignment_strategy = None
            return self
        if self.assignment_strategy is not None:
            supported = QUEUE_ASSIGNMENT_STRATEGIES_BY_CHANNEL[self.channel]
            if self.assignment_strategy not in supported:
                raise ValueError(f"{self.assignment_strategy.value} is not supported for {self.channel.value}")
        return self


class QueueTaskActionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class QueueAdminAssignRequest(BaseModel):
    agent_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=500)


class QueuePullRequest(BaseModel):
    queue_type: QueueType | None = None
    queue_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_queue_filter(self) -> "QueuePullRequest":
        if (self.queue_type is None) != (self.queue_id is None):
            raise ValueError("queue_type and queue_id must be provided together")
        return self


class QueueDispatchRequest(BaseModel):
    channel: QueueChannel
    queue_type: QueueType
    queue_id: int = Field(gt=0)


class QueueTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    channel: str
    task_type: str
    task_ref_id: str
    task_ref_public_id: str | None = None
    queue_type: str
    queue_id: int
    priority: int
    status: str
    source_type: str
    source_context: dict[str, Any] = Field(default_factory=dict)
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    assignment_strategy: str | None = None
    assigned_agent_id: int | None = None
    assigned_by: str | None = None
    attempts: int
    last_error: str | None = None
    enqueued_at: datetime | None = None
    assigning_at: datetime | None = None
    assigned_at: datetime | None = None
    canceled_at: datetime | None = None
    timeout_at: datetime | None = None
    deadline_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QueueRecordBrief(BaseModel):
    queue_type: str
    queue_id: int
    name: str


class QueueHistorySummary(BaseModel):
    last_assigned_queue: QueueRecordBrief | None = None
    queue_duration_seconds: int | None = Field(default=None, ge=1)


class QueuePositionResponse(BaseModel):
    task_id: int
    position_overall: int | None = None
    position_in_priority: int | None = None


class QueuePriorityStat(BaseModel):
    priority: int
    waiting_count: int
    earliest_enqueued_at: datetime | None = None
    longest_wait_seconds: int | None = None


class QueueStateResponse(BaseModel):
    queue_type: str
    queue_id: int
    channel: str
    waiting_count: int
    assigning_count: int
    priority_stats: list[QueuePriorityStat]
    available_agent_count: int
    active_agent_count: int
    effective_strategy: str | None = None
    effective_strategy_source: str | None = None
    max_waiting_count: int | None = None
    max_wait_seconds: int | None = None
    position_overall: int | None = None
    position_in_priority: int | None = None


class QueueEnqueueResponse(BaseModel):
    accepted: bool
    duplicate: bool = False
    task: QueueTaskResponse
    position: QueuePositionResponse


class QueueDispatchResponse(BaseModel):
    dispatched: bool
    task: QueueTaskResponse | None = None
    agent_id: int | None = None
    status: QueueTaskStatus | str | None = None
    reason: str | None = None


class QueueAssignmentResult(BaseModel):
    assignment_type: QueueAssignmentType
    task: QueueTaskResponse
