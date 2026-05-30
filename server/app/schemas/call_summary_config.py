"""
Pydantic schemas for call summary configuration
"""
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema, PaginatedResponse


# -- Config --

class CallSummaryConfigResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: int
    status: str


# -- Config Field --

class CallSummaryConfigFieldCreate(BaseModel):
    field_definition_id: int | None = None
    field_key: str | None = Field(None, max_length=64)
    is_active: bool = True


class CallSummaryConfigFieldUpdate(BaseModel):
    is_active: bool | None = None
    sort_order: int | None = None


class CallSummaryConfigFieldResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    config_id: int
    field_definition_id: int | None = None
    field_key: str | None = None
    sort_order: int
    is_active: bool


class CallSummaryConfigFieldListResponse(BaseModel):
    items: list[CallSummaryConfigFieldResponse]
    total: int


class CallSummaryFieldSortItem(BaseModel):
    id: int
    sort_order: int


class CallSummaryFieldSortRequest(BaseModel):
    items: list[CallSummaryFieldSortItem]


# -- Interaction Rule --

class CallSummaryInteractionRuleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    condition_logic: str = Field(default="and", max_length=8)
    conditions: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    is_enabled: bool = True
    sort_order: int = 0


class CallSummaryInteractionRuleCreate(CallSummaryInteractionRuleBase):
    pass


class CallSummaryInteractionRuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    condition_logic: str | None = Field(None, max_length=8)
    conditions: list[dict] | None = None
    actions: list[dict] | None = None
    is_enabled: bool | None = None
    sort_order: int | None = None


class CallSummaryInteractionRuleResponse(CallSummaryInteractionRuleBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    config_id: int


class CallSummaryInteractionRuleListResponse(PaginatedResponse):
    items: list[CallSummaryInteractionRuleResponse]


class CallSummaryRuleSortItem(BaseModel):
    id: int
    sort_order: int


class CallSummaryRuleSortRequest(BaseModel):
    items: list[CallSummaryRuleSortItem]
