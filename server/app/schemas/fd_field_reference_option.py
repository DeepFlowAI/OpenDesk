"""
Read-only reference options used by field value editors.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.base import PaginatedResponse


class FieldReferenceEmployeeGroupOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    member_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FieldReferenceEmployeeGroupOptionList(PaginatedResponse):
    items: list[FieldReferenceEmployeeGroupOption]


class FieldReferenceEmployeeOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    nickname: str | None = None
    job_number: str | None = None
    username: str
    email: str | None = None
    phone: str | None = None


class FieldReferenceEmployeeOptionList(PaginatedResponse):
    items: list[FieldReferenceEmployeeOption]
