"""
Scheduling Center Pydantic schemas.
"""
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, field_serializer


def _parse_hhmm(v: str) -> str:
    parts = v.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {v}, expected HH:MM")
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid time format: {v}, expected HH:MM") from None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Invalid time value: {v}")
    return f"{h:02d}:{m:02d}"


def hhmm_to_time(v: str) -> time:
    h, m = v.split(":")
    return time(int(h), int(m))


class ShiftCreate(BaseModel):
    name: str
    shift_type: Literal["work", "leave"] = "work"
    start_time: str | None = None
    end_time: str | None = None
    color: str
    sort_order: int
    is_enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 20:
            raise ValueError("Name must be at most 20 characters")
        return v

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _parse_hhmm(v)

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 32:
            raise ValueError("Color is required and must be at most 32 characters")
        return v

    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, v: int) -> int:
        if not 1 <= v <= 999:
            raise ValueError("Sort order must be between 1 and 999")
        return v


class ShiftUpdate(BaseModel):
    name: str | None = None
    shift_type: Literal["work", "leave"] | None = None
    start_time: str | None = None
    end_time: str | None = None
    color: str | None = None
    sort_order: int | None = None
    is_enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return ShiftCreate.validate_name(v)

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _parse_hhmm(v)

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return ShiftCreate.validate_color(v)

    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, v: int | None) -> int | None:
        if v is None:
            return v
        return ShiftCreate.validate_sort_order(v)


class ShiftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    shift_type: Literal["work", "leave"] = "work"
    start_time: time
    end_time: time
    color: str
    sort_order: int
    is_enabled: bool
    has_assignments: bool = False
    has_references: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_serializer("start_time", "end_time")
    @classmethod
    def serialize_time(cls, v: time) -> str:
        return v.strftime("%H:%M")


class ShiftListResponse(BaseModel):
    items: list[ShiftResponse]


class MessageResponse(BaseModel):
    message: str


class PoolMemberItem(BaseModel):
    id: int
    name: str
    job_number: str | None = None


class PoolMemberListResponse(BaseModel):
    items: list[PoolMemberItem]


class AssignmentShiftInfo(BaseModel):
    id: int
    name: str
    shift_type: Literal["work", "leave"] = "work"
    color: str
    start_time: time
    end_time: time
    is_enabled: bool

    @field_serializer("start_time", "end_time")
    @classmethod
    def serialize_time(cls, v: time) -> str:
        return v.strftime("%H:%M")


class AssignmentEmployeeInfo(BaseModel):
    id: int
    name: str
    job_number: str | None = None


class AssignmentResponse(BaseModel):
    id: int
    date: date
    shift: AssignmentShiftInfo
    employee: AssignmentEmployeeInfo
    created_at: datetime | None = None


class AssignmentListResponse(BaseModel):
    items: list[AssignmentResponse]


class AssignmentWriteItem(BaseModel):
    employee_id: int
    shift_id: int
    date: date


class AssignmentBulkCreateRequest(BaseModel):
    group_ids: list[int] = Field(min_length=1)
    items: list[AssignmentWriteItem] = Field(min_length=1, max_length=2000)
    allow_soft: bool = False
    replace_conflicts: bool = False


class AssignmentBulkCreateResponse(BaseModel):
    created: int
    skipped: int
    replaced: int = 0


class AssignmentBulkDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=2000)


class AssignmentBulkDeleteResponse(BaseModel):
    deleted: int


class CopyWeekRequest(BaseModel):
    week_start: date
    mode: Literal["skip", "overwrite"] = "skip"
    group_ids: list[int] = Field(min_length=1)
    allow_soft: bool = False


class CopyWeekResponse(BaseModel):
    copied: int
    skipped_cells: int
    skipped_leave_conflicts: int = 0


class PublishRequest(BaseModel):
    """Any date within the target week; the service normalizes to its Monday."""

    date: date


class PublishStatusResponse(BaseModel):
    week_start: date
    state: Literal["unpublished", "published", "dirty"]
    published_at: datetime | None = None
    published_by_name: str | None = None


class PublishResetResponse(BaseModel):
    week_start: date
    deleted: int
    restored: int


class MyScheduleShiftResponse(BaseModel):
    id: int
    name: str
    shift_type: Literal["work", "leave"] = "work"
    start_time: str | None = None
    end_time: str | None = None
    color: str
    is_deleted: bool = False


class MyScheduleDayResponse(BaseModel):
    date: date
    shifts: list[MyScheduleShiftResponse]


class MyScheduleResponse(BaseModel):
    week_start: date
    week_end: date
    today: date
    is_published: bool
    published_at: datetime | None = None
    days: list[MyScheduleDayResponse]
