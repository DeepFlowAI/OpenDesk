"""
Pydantic schemas for field definition management
"""
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema, PaginatedResponse


# ── Field Option schemas ──


class FdFieldOptionBase(BaseModel):
    label: str = Field(..., min_length=1, max_length=128)
    value: str = Field(..., min_length=1, max_length=128)
    color: str | None = Field(None, max_length=16)
    sort_order: int = 0


class FdFieldOptionCreate(FdFieldOptionBase):
    pass


class FdFieldOptionUpdate(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=128)
    value: str | None = Field(None, min_length=1, max_length=128)
    color: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class FdFieldOptionResponse(FdFieldOptionBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int | None = None
    field_definition_id: int | None = None
    is_active: bool


# ── Tree Node schemas ──


class FdTreeNodeBase(BaseModel):
    label: str = Field(..., min_length=1, max_length=128)
    value: str = Field(..., min_length=1, max_length=128)
    parent_id: int | None = None
    sort_order: int = 0


class FdTreeNodeCreate(FdTreeNodeBase):
    """When batch-creating field tree_nodes, set parent_index to the parent's index in the same list."""

    parent_index: int | None = None


class FdTreeNodeUpdate(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=128)
    value: str | None = Field(None, min_length=1, max_length=128)
    parent_id: int | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class FdTreeNodeResponse(FdTreeNodeBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    field_definition_id: int
    is_active: bool


# ── Field Definition schemas ──


class FdFieldDefinitionBase(BaseModel):
    domain: str = Field(..., max_length=32)
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    help_text: str | None = None
    field_type: str = Field(..., max_length=32)
    type_config: dict = Field(default_factory=dict)
    applicable_modules: list[str] | None = None
    show_in_workspace: bool | None = None
    sort_order: int = 0


class FdFieldDefinitionCreate(FdFieldDefinitionBase):
    source: str = Field(default="custom", max_length=16)
    options: list[FdFieldOptionCreate] | None = None
    tree_nodes: list[FdTreeNodeCreate] | None = None


class FdFieldDefinitionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = None
    help_text: str | None = None
    type_config: dict | None = None
    applicable_modules: list[str] | None = None
    show_in_workspace: bool | None = None
    status: str | None = None
    sort_order: int | None = None


class FdFieldDefinitionResponse(FdFieldDefinitionBase, TimestampSchema):
    """Response for a custom field (stored in fd_field_definitions)."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: int
    source: str
    slot_column: str
    status: str
    key: str | None = None
    options: list[FdFieldOptionResponse] = []
    tree_nodes: list[FdTreeNodeResponse] = []


class SystemFieldResponse(BaseModel):
    """Response for a hardcoded system field (not in fd_field_definitions)."""
    key: str
    id: None = None
    domain: str
    source: str = "system"
    name: str
    description: str | None = None
    help_text: str | None = None
    field_type: str
    type_config: dict = Field(default_factory=dict)
    applicable_modules: list[str] | None = None
    slot_column: None = None
    show_in_workspace: bool = True
    sort_order: int = 0
    status: str = "active"
    options: list[FdFieldOptionResponse] = []
    tree_nodes: list[FdTreeNodeResponse] = []
    created_at: str | None = None
    updated_at: str | None = None


class SystemFieldListResponse(BaseModel):
    items: list[SystemFieldResponse]
    total: int


class UnifiedFieldResponse(BaseModel):
    """Union type: either system field or custom field."""
    key: str | None = None
    id: int | None = None
    domain: str
    source: str
    name: str
    description: str | None = None
    help_text: str | None = None
    field_type: str
    type_config: dict = Field(default_factory=dict)
    applicable_modules: list[str] | None = None
    slot_column: str | None = None
    show_in_workspace: bool | None = None
    sort_order: int = 0
    status: str = "active"
    options: list[FdFieldOptionResponse] = []
    tree_nodes: list[FdTreeNodeResponse] = []
    created_at: str | None = None
    updated_at: str | None = None


class UnifiedFieldListResponse(PaginatedResponse):
    items: list[UnifiedFieldResponse]


class FdFieldDefinitionListResponse(PaginatedResponse):
    items: list[FdFieldDefinitionResponse]


# ── System field override schemas ──


class SystemFieldOverrideUpdate(BaseModel):
    show_in_workspace: bool | None = None
    sort_order: int | None = None
    status: str | None = None


# ── Sort request ──


class SortItem(BaseModel):
    id: int | None = None
    key: str | None = None
    sort_order: int


class SortRequest(BaseModel):
    items: list[SortItem]
