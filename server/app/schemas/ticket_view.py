"""
Pydantic schemas for ticket view management
"""
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema, PaginatedResponse


class ConditionItem(BaseModel):
    field_id: int | None = None
    field_key: str | None = None
    operator: str
    value: str | int | float | list | dict | bool | None = None


class ColumnConfigItem(BaseModel):
    field_id: int | None = None
    field_key: str | None = None
    visible: bool = True
    sort_order: int = 0


class TicketViewBase(BaseModel):
    name: str = Field(..., max_length=128)
    condition_logic: str = Field(default="and", max_length=8)
    conditions: list[ConditionItem] = Field(default_factory=list)
    group_field_id: int | None = None
    custom_columns_enabled: bool = False
    columns_config: list[ColumnConfigItem] = Field(default_factory=list)


class TicketViewCreate(TicketViewBase):
    pass


class TicketViewUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    condition_logic: str | None = Field(None, max_length=8)
    conditions: list[ConditionItem] | None = None
    group_field_id: int | None = None
    custom_columns_enabled: bool | None = None
    columns_config: list[ColumnConfigItem] | None = None


class TicketViewResponse(TicketViewBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: int
    is_enabled: bool
    sort_order: int


class TicketViewListResponse(PaginatedResponse):
    items: list[TicketViewResponse]


class TicketViewToggleRequest(BaseModel):
    is_enabled: bool


class TicketViewSortItem(BaseModel):
    id: int
    sort_order: int


class TicketViewSortRequest(BaseModel):
    items: list[TicketViewSortItem]
