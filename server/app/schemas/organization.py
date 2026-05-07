"""
Pydantic schemas for organization management
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema, PaginatedResponse
from app.schemas.organization_view import ConditionItem

CustomFieldValue = str | int | float | bool | list | dict | None


class OrganizationResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: int
    name: str
    description: str | None = None
    created_by: dict | None = None
    updated_by: dict | None = None
    custom_fields: dict[str, CustomFieldValue] = Field(default_factory=dict)
    user_count: int = 0


class OrganizationCreate(BaseModel):
    """Create a new organization."""
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(None, max_length=2000)
    custom_fields: dict[str, CustomFieldValue] = Field(default_factory=dict)


class OrganizationUpdate(BaseModel):
    """Partial update of an organization."""
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=2000)
    custom_fields: dict[str, CustomFieldValue] | None = None


class OrganizationListResponse(PaginatedResponse):
    items: list[OrganizationResponse]


class OrganizationQueryRequest(BaseModel):
    """POST body for querying organizations with optional temp filters."""
    view_id: int | None = None
    search: str | None = Field(None, max_length=256)
    temp_conditions: list[ConditionItem] = Field(default_factory=list)
    temp_condition_logic: str = Field(default="and", max_length=8)
    group_value: str | None = None
    sort_by: str | None = None
    sort_order: str = Field(default="desc", max_length=4)
    page: int = 1
    per_page: int = 20


class OrgViewCountItem(BaseModel):
    view_id: int
    count: int


class OrgViewCountsResponse(BaseModel):
    total_count: int = 0
    items: list[OrgViewCountItem]
