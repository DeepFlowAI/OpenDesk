"""
Pydantic schemas for ticket change timeline.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.base import PaginatedResponse, TimestampSchema
from app.schemas.ticket import CustomFieldValue


class TicketChangeEntryItem(BaseModel):
    """One field change inside a batch update (field_key = __batch__)."""
    model_config = ConfigDict(extra="ignore")

    field_key: str
    field_label: str
    field_source: str = "ticket"
    old_value: CustomFieldValue = None
    new_value: CustomFieldValue = None


class TicketChangeResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    ticket_id: int
    actor_type: str
    actor_id: int | None = None
    actor_name: str | None = None
    # Filled from Employee.avatar when actor_type is "user" (not stored on the row)
    actor_avatar: str | None = None
    field_key: str
    field_label: str
    field_source: str
    old_value: CustomFieldValue = None
    new_value: CustomFieldValue = None
    # Populated for batch records; omitted for legacy per-field rows.
    entries: list[TicketChangeEntryItem] | None = None


class TicketChangeListResponse(PaginatedResponse):
    items: list[TicketChangeResponse]
