"""
Pydantic schemas for interaction rule management
"""
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import TimestampSchema, PaginatedResponse


class FdInteractionRuleBase(BaseModel):
    name: str | None = Field(None, max_length=128)
    condition_logic: str = Field(default="and", max_length=8)
    conditions: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    is_enabled: bool = True
    sort_order: int = 0


class FdInteractionRuleCreate(FdInteractionRuleBase):
    pass


class FdInteractionRuleUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    condition_logic: str | None = Field(None, max_length=8)
    conditions: list[dict] | None = None
    actions: list[dict] | None = None
    is_enabled: bool | None = None
    sort_order: int | None = None


class FdInteractionRuleResponse(FdInteractionRuleBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    layout_id: int


class FdInteractionRuleListResponse(PaginatedResponse):
    items: list[FdInteractionRuleResponse]


class InteractionRuleSortItem(BaseModel):
    id: int
    sort_order: int


class InteractionRuleSortRequest(BaseModel):
    items: list[InteractionRuleSortItem]
