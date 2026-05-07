"""
Pydantic schemas for end-user (visitor/customer) management
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema, PaginatedResponse
from app.schemas.user_view import ConditionItem

CustomFieldValue = str | int | float | bool | list | dict | None


class UserResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: int
    external_id: str
    name: str                      # also serves as "nickname" system field
    email: str | None = None
    phone: str | None = None
    gender: str | None = None
    address: str | None = None
    remark: str | None = None
    web_id: str | None = None
    avatar_color: str | None = None
    channel_id: int | None = None
    organization_id: int | None = None
    created_by: dict | None = None
    updated_by: dict | None = None
    custom_fields: dict[str, CustomFieldValue] = Field(default_factory=dict)


class UserCreate(BaseModel):
    """Create a new end user."""
    name: str = Field(..., min_length=1, max_length=64)
    email: str | None = Field(None, max_length=254)
    phone: str | None = Field(None, max_length=32)
    gender: str | None = Field(None, max_length=16)
    address: str | None = Field(None, max_length=256)
    remark: str | None = Field(None, max_length=2000)
    web_id: str | None = Field(None, max_length=128)
    organization_id: int | None = None
    custom_fields: dict[str, CustomFieldValue] = Field(default_factory=dict)


class UserUpdate(BaseModel):
    """Partial update of an end user."""
    name: str | None = Field(None, min_length=1, max_length=64)
    email: str | None = Field(None, max_length=254)
    phone: str | None = Field(None, max_length=32)
    gender: str | None = Field(None, max_length=16)
    address: str | None = Field(None, max_length=256)
    remark: str | None = Field(None, max_length=2000)
    web_id: str | None = Field(None, max_length=128)
    organization_id: int | None = None
    custom_fields: dict[str, CustomFieldValue] | None = None


class UserListResponse(PaginatedResponse):
    items: list[UserResponse]


class UserQueryRequest(BaseModel):
    """POST body for querying users with optional temp filters."""
    view_id: int | None = None
    search: str | None = Field(None, max_length=256)
    temp_conditions: list[ConditionItem] = Field(default_factory=list)
    temp_condition_logic: str = Field(default="and", max_length=8)
    group_value: str | None = None
    sort_by: str | None = None
    sort_order: str = Field(default="desc", max_length=4)
    page: int = 1
    per_page: int = 20


class ViewCountItem(BaseModel):
    view_id: int
    count: int


class ViewCountsResponse(BaseModel):
    total_count: int = 0
    items: list[ViewCountItem]
