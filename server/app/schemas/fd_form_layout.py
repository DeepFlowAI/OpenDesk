"""
Pydantic schemas for form layout management

Hierarchy: Layout → Tab → Section → Field
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema, PaginatedResponse

SceneType = Literal["new_ticket", "ticket_detail"]
LabelPositionType = Literal["top", "left"]
FieldSourceType = Literal["ticket", "ticket_metadata", "user", "organization"]
DefaultStateType = Literal["required", "optional", "readonly", "hidden"]


# ── Field schemas ──


class FdFormLayoutFieldCreate(BaseModel):
    field_definition_id: int | None = None
    field_key: str | None = Field(None, max_length=64)
    field_source: FieldSourceType = Field(default="ticket")
    default_state: DefaultStateType = Field(default="optional")
    column_span: int = Field(default=1, ge=1, le=4)
    sort_order: int = Field(default=0, ge=0)


class FdFormLayoutFieldResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    section_id: int
    field_definition_id: int | None = None
    field_key: str | None = None
    field_source: str = "ticket"
    default_state: str = "optional"
    column_span: int = 1
    sort_order: int = 0


# ── Section schemas ──


class FdFormLayoutSectionCreate(BaseModel):
    name: str = Field(..., min_length=0, max_length=64)
    sort_order: int = 0
    is_collapsed: bool = False
    fields: list[FdFormLayoutFieldCreate] | None = None


class FdFormLayoutSectionResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tab_id: int
    name: str
    sort_order: int
    is_collapsed: bool
    fields: list[FdFormLayoutFieldResponse] = []


# ── Tab schemas ──


class FdFormLayoutTabCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    sort_order: int = 0
    sections: list[FdFormLayoutSectionCreate] | None = None


class FdFormLayoutTabResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    layout_id: int
    name: str
    sort_order: int
    sections: list[FdFormLayoutSectionResponse] = []


# ── Layout schemas ──


class FdFormLayoutBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scene: SceneType = Field(...)
    columns_per_row: int = Field(default=1, ge=1, le=4)
    label_position: LabelPositionType = Field(default="top")


class FdFormLayoutCreate(FdFormLayoutBase):
    tabs: list[FdFormLayoutTabCreate] | None = None


class FdFormLayoutUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    columns_per_row: int | None = Field(None, ge=1, le=4)
    label_position: LabelPositionType | None = Field(None)
    status: str | None = None
    tabs: list[FdFormLayoutTabCreate] | None = None


class FdFormLayoutResponse(FdFormLayoutBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: int
    status: str
    tabs: list[FdFormLayoutTabResponse] = []


class FdFormLayoutListResponse(PaginatedResponse):
    items: list[FdFormLayoutResponse]


class FdFormLayoutSummaryResponse(FdFormLayoutBase, TimestampSchema):
    """Lightweight response for list page (no nested tabs/sections/fields)."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: int
    status: str


class FdFormLayoutSummaryListResponse(PaginatedResponse):
    items: list[FdFormLayoutSummaryResponse]
