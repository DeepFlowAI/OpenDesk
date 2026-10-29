"""Public export task payloads; never serialize storage keys or snapshots."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator


class ExportTaskCreate(BaseModel):
    idempotency_key: UUID
    kind: str = Field(min_length=1, max_length=64)
    config: dict = Field(default_factory=dict)
    language: Literal["zh", "en"] = "zh"
    timezone: str = Field(default="UTC", max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Invalid timezone") from exc
        return value


class ExportTaskResponse(BaseModel):
    id: UUID
    kind: str
    name: dict[str, str]
    business_type: dict[str, str]
    summary: dict[str, str]
    status: Literal["pending", "running", "completed", "failed", "cancelled", "expired"]
    error_code: str | None
    error_field: str | None = None
    row_count: int | None
    file_name: str | None
    file_size: int | None
    created_at: datetime
    expires_at: datetime | None
    scope_reduced: bool
    can_download: bool
    viewed: bool


class ExportTaskDownload(BaseModel):
    url: str


class ExportTaskList(BaseModel):
    items: list[ExportTaskResponse]
    total: int
    page: int
    per_page: int
    pages: int


class ExportTaskStatus(BaseModel):
    visible: bool
    unread: int
    server_time: datetime


class ExportTaskIDs(BaseModel):
    ids: list[UUID] = Field(max_length=100)


class ExportNotificationRequest(BaseModel):
    since: datetime

    @field_validator("since")
    @classmethod
    def aware_since(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        return value


class ExportNotifications(BaseModel):
    items: list[ExportTaskResponse]
    server_time: datetime
