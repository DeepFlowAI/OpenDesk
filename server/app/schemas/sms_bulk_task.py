"""
Bulk SMS task schemas: engagement-center task CRUD, state transitions and targets.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.base import PaginatedResponse
from app.schemas.sms import CN_MOBILE_PATTERN, SmsVariableDef

SMS_BULK_TASK_STATUSES = {"draft", "scheduled", "sending", "paused", "completed", "archived"}
SMS_BULK_TARGET_STATUSES = {"pending", "sending", "submitted", "delivered", "failed"}
SMS_BULK_SEND_TYPES = {"immediate", "scheduled"}


# ---------------------------------------------------------------------------
# Template picker
# ---------------------------------------------------------------------------


class SmsBulkTemplateItem(BaseModel):
    id: int
    name: str
    sign_name: str
    type: str
    variables: list[SmsVariableDef]
    body: str


class SmsBulkTemplateListResponse(BaseModel):
    items: list[SmsBulkTemplateItem]


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


class SmsBulkTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    template_id: int
    send_type: str = Field(default="immediate")
    scheduled_at: datetime | None = None

    @model_validator(mode="after")
    def _check_send_time(self) -> "SmsBulkTaskCreate":
        if self.send_type not in SMS_BULK_SEND_TYPES:
            raise ValueError("Invalid send_type")
        if self.send_type == "scheduled" and self.scheduled_at is None:
            raise ValueError("scheduled_at is required when send_type is scheduled")
        return self


class SmsBulkTaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    template_id: int | None = None
    send_type: str | None = None
    scheduled_at: datetime | None = None

    @model_validator(mode="after")
    def _check_send_type(self) -> "SmsBulkTaskUpdate":
        if self.send_type is not None and self.send_type not in SMS_BULK_SEND_TYPES:
            raise ValueError("Invalid send_type")
        return self


class SmsBulkTaskStats(BaseModel):
    total: int = 0
    pending: int = 0
    submitted: int = 0
    delivered: int = 0
    failed: int = 0


class SmsBulkTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    status: str
    send_type: str
    scheduled_at: datetime | None = None
    template_id: int | None = None
    template_name: str
    template_type: str
    sign_name: str
    body: str
    variables: list[SmsVariableDef]
    pause_reason: str | None = None
    published_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_by_id: int | None = None
    created_by_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SmsBulkTaskListItem(SmsBulkTaskResponse):
    stats: SmsBulkTaskStats


class PaginatedSmsBulkTasks(PaginatedResponse):
    items: list[SmsBulkTaskListItem]


class SmsBulkTaskDetail(SmsBulkTaskResponse):
    stats: SmsBulkTaskStats


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


class SmsBulkTargetCreate(BaseModel):
    phone: str = Field(pattern=CN_MOBILE_PATTERN)
    variable_values: dict[str, str] = Field(default_factory=dict)


class SmsBulkTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    variable_values: dict[str, str]
    status: str
    fail_reason: str | None = None
    submitted_at: datetime | None = None
    delivered_at: datetime | None = None
    created_at: datetime | None = None


class PaginatedSmsBulkTargets(PaginatedResponse):
    items: list[SmsBulkTargetResponse]


class SmsBulkTargetDetail(SmsBulkTargetResponse):
    body_rendered: str
    send_record_id: int | None = None
    provider_biz_id: str | None = None


class SmsBulkTargetBulkDeleteRequest(BaseModel):
    target_ids: list[int] = Field(min_length=1, max_length=500)


class SmsBulkTargetBulkDeleteResponse(BaseModel):
    deleted: int
    skipped: int


class SmsBulkTargetResendResponse(BaseModel):
    reset: int


# ---------------------------------------------------------------------------
# Target import
# ---------------------------------------------------------------------------


class SmsBulkImportParseResponse(BaseModel):
    token: str
    headers: list[str]
    sample_rows: list[list[str]]


class SmsBulkImportMapping(BaseModel):
    token: str = Field(min_length=1)
    phone_column: str = Field(min_length=1)
    variable_columns: dict[str, str] = Field(default_factory=dict)


class SmsBulkImportRowError(BaseModel):
    row_number: int
    phone: str | None = None
    reason: str


class SmsBulkImportValidateResponse(BaseModel):
    total: int
    valid: int
    duplicate: int
    invalid: int
    errors: list[SmsBulkImportRowError]


class SmsBulkImportExecuteResponse(BaseModel):
    success: int
    duplicate: int
    failed: int
