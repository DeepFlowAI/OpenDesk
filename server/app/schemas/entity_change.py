"""
Pydantic schemas for user and organization change timelines.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.base import PaginatedResponse, TimestampSchema
from app.schemas.ticket import CustomFieldValue


class EntityChangeEntryItem(BaseModel):
    """One field change inside a batch update or create record."""
    model_config = ConfigDict(extra="ignore")

    field_key: str
    field_label: str
    old_value: CustomFieldValue = None
    new_value: CustomFieldValue = None


class EntityChangeResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    entity_type: str
    entity_id: int
    actor_type: str
    actor_id: int | None = None
    actor_name: str | None = None
    actor_avatar: str | None = None
    field_key: str
    field_label: str
    field_source: str
    old_value: CustomFieldValue = None
    new_value: CustomFieldValue = None
    entries: list[EntityChangeEntryItem] | None = None


class EntityChangeListResponse(PaginatedResponse):
    items: list[EntityChangeResponse]
