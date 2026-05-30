"""
Pydantic schemas for ticket CRUD + workspace queries
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema, PaginatedResponse
from app.schemas.ticket_view import ConditionItem

CustomFieldValue = str | int | float | bool | list | dict | None


class RelatedTicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_number: str | None = None


class TicketResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: int
    ticket_number: str | None = None
    layout_id: int | None = None
    conversation_id: int | None = None
    conversation_public_id: str | None = None
    call_record_id: int | None = None
    call_record_call_id: str | None = None
    user_id: int | None = None
    agent_id: int | None = None
    assignee_group_id: int | None = None
    title: str
    description: str | None = None
    status: str = "open"
    priority: str | None = None
    created_by: dict | None = None
    updated_by: dict | None = None
    custom_fields: dict[str, CustomFieldValue] = Field(default_factory=dict)


class TicketCreate(BaseModel):
    """Create a new ticket — system + custom fields."""
    title: str = Field(..., min_length=1, max_length=256)
    description: str | None = Field(None, max_length=5000)
    status: str = Field(default="open", max_length=32)
    priority: str | None = Field(default="medium", max_length=16)
    layout_id: int | None = None
    conversation_id: int | None = None
    call_record_id: int | None = None
    user_id: int | None = None
    agent_id: int | None = None
    assignee_group_id: int | None = None
    custom_fields: dict[str, CustomFieldValue] = Field(default_factory=dict)


class TicketUpdate(BaseModel):
    """Partial update of a ticket."""
    title: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = Field(None, max_length=5000)
    status: str | None = Field(None, max_length=32)
    priority: str | None = Field(None, max_length=16)
    conversation_id: int | None = None
    call_record_id: int | None = None
    user_id: int | None = None
    agent_id: int | None = None
    assignee_group_id: int | None = None
    custom_fields: dict[str, CustomFieldValue] | None = None


class TicketListResponse(PaginatedResponse):
    items: list[TicketResponse]


class TicketQueryRequest(BaseModel):
    """POST body for querying tickets with optional view + temp filters."""
    view_id: int | None = None
    search: str | None = Field(None, max_length=256)
    temp_conditions: list[ConditionItem] = Field(default_factory=list)
    temp_condition_logic: str = Field(default="and", max_length=8)
    group_value: str | None = None
    sort_by: str | None = None
    sort_order: str = Field(default="desc", max_length=4)
    page: int = 1
    per_page: int = 20


class TicketViewCountItem(BaseModel):
    view_id: int
    count: int


class TicketViewCountsResponse(BaseModel):
    total_count: int = 0
    items: list[TicketViewCountItem]
