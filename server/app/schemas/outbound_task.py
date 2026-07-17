"""
Schemas for manual outbound task APIs.
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import FieldType


OutboundTaskStatus = Literal["draft", "active", "paused", "completed", "archived"]
OutboundTargetStatus = Literal["pending", "calling", "redial", "completed", "do_not_call", "invalid_number"]


class OutboundTaskField(BaseModel):
    key: str
    name: str
    field_type: FieldType
    required: bool = False
    agent_editable: bool = False
    show_in_list: bool = False
    enabled: bool = True
    type_config: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field key is required")
        if len(value) > 64:
            raise ValueError("Field key must be at most 64 characters")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field name is required")
        if len(value) > 64:
            raise ValueError("Field name must be at most 64 characters")
        return value


class OutboundTemplateBase(BaseModel):
    name: str
    description: str | None = None
    fields: list[OutboundTaskField] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        if len(value) > 80:
            raise ValueError("Name must be at most 80 characters")
        return value

    @model_validator(mode="after")
    def validate_field_keys(self) -> "OutboundTemplateBase":
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Field keys must be unique")
        return self


class OutboundTemplateCreate(OutboundTemplateBase):
    pass


class OutboundTemplateUpdate(OutboundTemplateBase):
    pass


class OutboundTemplateResponse(OutboundTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    created_by_id: int | None = None
    updated_by_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OutboundTaskBase(BaseModel):
    name: str
    description: str | None = None
    owner_id: int | None = None
    starts_at: datetime | None = None
    due_at: datetime | None = None
    allow_self_claim: bool = False
    default_redial_interval_minutes: int | None = None
    assignment_mode: str = "manual"
    assignee_scope_ids: list[int] = Field(default_factory=list)
    fields: list[OutboundTaskField] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        if len(value) > 80:
            raise ValueError("Name must be at most 80 characters")
        return value

    @model_validator(mode="after")
    def validate_times(self) -> "OutboundTaskBase":
        if self.starts_at and self.due_at and self.due_at < self.starts_at:
            raise ValueError("Due time must not be earlier than start time")
        return self


class OutboundTaskCreate(OutboundTaskBase):
    template_id: int
    publish: bool = False


class OutboundTaskUpdate(OutboundTaskBase):
    name: str | None = None


class OutboundTaskStats(BaseModel):
    total_targets: int = 0
    pending_targets: int = 0
    completed_targets: int = 0
    call_count: int = 0
    answered_count: int = 0


class OutboundTaskResponse(OutboundTaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    template_id: int | None = None
    template_name: str
    status: OutboundTaskStatus
    created_by_id: int | None = None
    updated_by_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    stats: OutboundTaskStats = Field(default_factory=OutboundTaskStats)


class OutboundTargetCreate(BaseModel):
    phone_number: str
    user_id: int | None = None
    assignee_id: int | None = None
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


class OutboundTargetUpdate(BaseModel):
    phone_number: str | None = None
    user_id: int | None = None
    assignee_id: int | None = None
    status: OutboundTargetStatus | None = None
    field_values: dict[str, Any] | None = None
    next_follow_up_at: datetime | None = None


class OutboundTargetExecutionUpdate(BaseModel):
    status: OutboundTargetStatus | None = None
    field_values: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> "OutboundTargetExecutionUpdate":
        if self.status is None and self.field_values is None:
            raise ValueError("At least one change is required")
        return self


class OutboundTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    task_id: int
    phone_number: str
    user_id: int | None = None
    assignee_id: int | None = None
    status: OutboundTargetStatus
    field_values: dict[str, Any]
    call_count: int
    answered_count: int
    last_called_at: datetime | None = None
    last_call_result: str | None = None
    next_follow_up_at: datetime | None = None
    total_talk_duration_ms: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OutboundTargetWithTaskResponse(OutboundTargetResponse):
    task: OutboundTaskResponse


class OutboundRecordCreate(BaseModel):
    call_record_id: int | None = None
    started_at: datetime | None = None
    duration_ms: int | None = None
    answered: bool = False
    result: str | None = None
    notes: str | None = None
    target_status: OutboundTargetStatus = "completed"
    next_follow_up_at: datetime | None = None
    field_values: dict[str, Any] = Field(default_factory=dict)


class OutboundRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    task_id: int
    target_id: int
    call_record_id: int | None = None
    agent_id: int | None = None
    phone_number: str
    started_at: datetime
    duration_ms: int | None = None
    answered: bool
    result: str | None = None
    notes: str | None = None
    field_values: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BulkAssignRequest(BaseModel):
    target_ids: list[int]
    assignee_id: int | None = None
    overwrite: bool = False


class BulkAssignResponse(BaseModel):
    updated: int


class BulkDeleteRequest(BaseModel):
    target_ids: list[int] = Field(min_length=1, max_length=5000)

    @field_validator("target_ids")
    @classmethod
    def validate_target_ids(cls, value: list[int]) -> list[int]:
        if any(target_id <= 0 for target_id in value):
            raise ValueError("Target IDs must be positive integers")
        return list(dict.fromkeys(value))


class BulkDeleteResponse(BaseModel):
    deleted: int


class OutboundTargetImportError(BaseModel):
    row_number: int
    phone_number: str | None = None
    reason: str


class OutboundTargetImportResponse(BaseModel):
    total: int
    created: int
    failed: int
    errors: list[OutboundTargetImportError] = Field(default_factory=list)


class PaginatedOutboundTemplates(BaseModel):
    items: list[OutboundTemplateResponse]
    total: int
    page: int
    per_page: int
    pages: int


class PaginatedOutboundTasks(BaseModel):
    items: list[OutboundTaskResponse]
    total: int
    page: int
    per_page: int
    pages: int


class PaginatedOutboundTargets(BaseModel):
    items: list[OutboundTargetResponse]
    total: int
    page: int
    per_page: int
    pages: int


class PaginatedOutboundTargetsWithTask(BaseModel):
    items: list[OutboundTargetWithTaskResponse]
    total: int
    page: int
    per_page: int
    pages: int


class PaginatedOutboundRecords(BaseModel):
    items: list[OutboundRecordResponse]
    total: int
    page: int
    per_page: int
    pages: int
