"""
EmployeeGroup Pydantic schemas
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.base import PaginatedResponse


class EmployeeGroupMemberInfo(BaseModel):
    """Member info returned in group detail"""
    model_config = ConfigDict(from_attributes=True)

    employee_id: int
    name: str = ""
    username: str
    display_name: str | None = None


class EmployeeGroupCreate(BaseModel):
    name: str
    description: str | None = None
    member_ids: list[int] = []

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 50:
            raise ValueError("Name must be at most 50 characters")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        if v and len(v) > 256:
            raise ValueError("Description must be at most 256 characters")
        return v


class EmployeeGroupUpdate(BaseModel):
    name: str
    description: str | None = None
    member_ids: list[int] = []

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 50:
            raise ValueError("Name must be at most 50 characters")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        if v and len(v) > 256:
            raise ValueError("Description must be at most 256 characters")
        return v


class EmployeeGroupResponse(BaseModel):
    """Response for group detail (includes members)"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    member_count: int = 0
    members: list[EmployeeGroupMemberInfo] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EmployeeGroupListItem(BaseModel):
    """Response for list view (no member details, just count)"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    member_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EmployeeGroupListResponse(PaginatedResponse):
    items: list[EmployeeGroupListItem]


class EmployeeSelectListItem(BaseModel):
    """Employee info for member selection"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = ""
    username: str
    display_name: str | None = None


class EmployeeSelectListResponse(PaginatedResponse):
    items: list[EmployeeSelectListItem]
