"""Schemas for append-only call trajectory events and timeline responses."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CallEventCreate(BaseModel):
    """Internal event payload before tenant and call ownership are resolved."""

    event_id: str = Field(min_length=1, max_length=96)
    event_type: str = Field(min_length=1, max_length=64)
    event_category: str = Field(min_length=1, max_length=24)
    actor_type: str = Field(min_length=1, max_length=24)
    source: str = Field(min_length=1, max_length=24)
    occurred_at: datetime
    sequence_no: int | None = Field(default=None, ge=1)
    schema_version: int = Field(default=1, ge=1)
    operation_id: str | None = Field(default=None, max_length=96)
    call_leg_id: str | None = Field(default=None, max_length=96)
    parent_leg_id: str | None = Field(default=None, max_length=96)
    participant_role: str | None = Field(default=None, max_length=32)
    actor_id: str | None = Field(default=None, max_length=80)
    actor_name_snapshot: str | None = Field(default=None, max_length=255)
    target_type: str | None = Field(default=None, max_length=32)
    target_id: str | None = Field(default=None, max_length=80)
    target_name_snapshot: str | None = Field(default=None, max_length=255)
    queue_type: str | None = Field(default=None, max_length=24)
    queue_id: int | None = None
    queue_name_snapshot: str | None = Field(default=None, max_length=255)
    result: str | None = Field(default=None, max_length=24)
    reason_code: str | None = Field(default=None, max_length=48)
    reason_detail: str | None = Field(default=None, max_length=1000)
    duration_ms: int | None = Field(default=None, ge=0)
    source_event_id: str | None = Field(default=None, max_length=128)
    trace_id: str | None = Field(default=None, max_length=128)
    is_synthetic: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class CallEventResponse(BaseModel):
    """Serialized event returned by the trajectory query API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    tenant_id: int
    call_record_id: int
    root_call_id: str
    event_type: str
    event_category: str
    schema_version: int
    occurred_at: datetime
    sequence_no: int
    operation_id: str | None = None
    call_leg_id: str | None = None
    parent_leg_id: str | None = None
    participant_role: str | None = None
    actor_type: str
    actor_id: str | None = None
    actor_name_snapshot: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    target_name_snapshot: str | None = None
    queue_type: str | None = None
    queue_id: int | None = None
    queue_name_snapshot: str | None = None
    result: str | None = None
    reason_code: str | None = None
    reason_detail: str | None = None
    duration_ms: int | None = None
    source: str
    source_event_id: str | None = None
    trace_id: str | None = None
    is_synthetic: bool
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class CallTrajectoryOperation(BaseModel):
    operation_id: str
    event_ids: list[str]
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    result: str | None = None


class CallTrajectoryWarning(BaseModel):
    code: str
    message: str


class CallTrajectoryResponse(BaseModel):
    call_record_public_id: UUID
    call_id: str
    lifecycle_status: str
    is_live: bool
    is_complete: bool
    last_updated_at: datetime | None = None
    total: int
    events: list[CallEventResponse]
    operations: list[CallTrajectoryOperation]
    settlement: CallEventResponse | None = None
    warnings: list[CallTrajectoryWarning]
