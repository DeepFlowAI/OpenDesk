"""
Pydantic schemas for conversation minutes configuration
"""
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema, PaginatedResponse


# ── Config ──

class CsSummaryConfigResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: int
    status: str


# ── Config Field ──

class CsSummaryConfigFieldCreate(BaseModel):
    field_definition_id: int | None = None
    field_key: str | None = None
    is_active: bool = True


class CsSummaryConfigFieldUpdate(BaseModel):
    is_active: bool | None = None
    sort_order: int | None = None


class CsSummaryConfigFieldResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    config_id: int
    field_definition_id: int | None = None
    field_key: str | None = None
    sort_order: int
    is_active: bool


class CsSummaryConfigFieldListResponse(BaseModel):
    items: list[CsSummaryConfigFieldResponse]
    total: int


class CsSummaryFieldSortItem(BaseModel):
    id: int
    sort_order: int


class CsSummaryFieldSortRequest(BaseModel):
    items: list[CsSummaryFieldSortItem]


# ── Interaction Rule ──

class CsSummaryInteractionRuleBase(BaseModel):
    name: str | None = Field(None, max_length=128)
    condition_logic: str = Field(default="and", max_length=8)
    conditions: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    is_enabled: bool = True
    sort_order: int = 0


class CsSummaryInteractionRuleCreate(CsSummaryInteractionRuleBase):
    pass


class CsSummaryInteractionRuleUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    condition_logic: str | None = Field(None, max_length=8)
    conditions: list[dict] | None = None
    actions: list[dict] | None = None
    is_enabled: bool | None = None
    sort_order: int | None = None


class CsSummaryInteractionRuleResponse(CsSummaryInteractionRuleBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    config_id: int


class CsSummaryInteractionRuleListResponse(PaginatedResponse):
    items: list[CsSummaryInteractionRuleResponse]


class CsSummaryRuleSortItem(BaseModel):
    id: int
    sort_order: int


class CsSummaryRuleSortRequest(BaseModel):
    items: list[CsSummaryRuleSortItem]
