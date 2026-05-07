"""
ServiceHours Pydantic schemas
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator


class TimeSlot(BaseModel):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid time format: {v}, expected HH:MM")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError(f"Invalid time value: {v}")
        return v


class WeeklySchedule(BaseModel):
    day_of_week: int
    slots: list[TimeSlot] = []

    @field_validator("day_of_week")
    @classmethod
    def validate_day(cls, v: int) -> int:
        if not 1 <= v <= 7:
            raise ValueError("day_of_week must be 1 (Mon) to 7 (Sun)")
        return v


class HolidayEntry(BaseModel):
    name: str = ""
    start: str
    end: str


class MakeupDayEntry(BaseModel):
    name: str = ""
    start: str
    end: str


class ServiceHoursCreate(BaseModel):
    name: str
    description: str | None = None
    weekly_schedules: list[WeeklySchedule] = []
    holidays: list[HolidayEntry] = []
    makeup_days: list[MakeupDayEntry] = []

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 64:
            raise ValueError("Name must be at most 64 characters")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        if v and len(v) > 256:
            raise ValueError("Description must be at most 256 characters")
        return v


class ServiceHoursUpdate(ServiceHoursCreate):
    pass


class ServiceHoursResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    weekly_schedules: list[WeeklySchedule] = []
    holidays: list[HolidayEntry] = []
    makeup_days: list[MakeupDayEntry] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
