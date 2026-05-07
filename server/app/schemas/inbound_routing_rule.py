"""
Inbound routing rule schemas and routing condition validation
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.base import PaginatedResponse


ConditionType = Literal["caller_number", "callee_number", "call_time"]


class RoutingCondition(BaseModel):
    condition_type: ConditionType
    operator: str
    value: str

    @field_validator("value")
    @classmethod
    def strip_value(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else str(v)

    @model_validator(mode="after")
    def validate_operator_and_value(self) -> "RoutingCondition":
        ct = self.condition_type
        op = self.operator
        val = self.value

        if ct in ("caller_number", "callee_number"):
            if op not in ("eq", "ne"):
                raise ValueError("Invalid operator for number condition")
            if not val.isdigit():
                raise ValueError("Phone value must contain digits only")
            if not (1 <= len(val) <= 32):
                raise ValueError("Phone value length must be 1-32")
        elif ct == "call_time":
            if op not in ("in_schedule", "not_in_schedule"):
                raise ValueError("Invalid operator for call time condition")
            if not val.isdigit():
                raise ValueError("Service hours id must be numeric")
            sid = int(val)
            if sid < 1:
                raise ValueError("Invalid service hours id")
            self.value = str(sid)
        return self


class InboundRoutingRuleCreate(BaseModel):
    name: str
    enabled: bool = True
    conditions: list[RoutingCondition] = []
    target_voice_flow_id: int

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 64:
            raise ValueError("Name must be at most 64 characters")
        return v


class InboundRoutingRuleUpdate(BaseModel):
    name: str
    enabled: bool = True
    conditions: list[RoutingCondition] = []
    target_voice_flow_id: int

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 64:
            raise ValueError("Name must be at most 64 characters")
        return v


class InboundRoutingRuleEnabledPatch(BaseModel):
    enabled: bool


class InboundRoutingRuleReorder(BaseModel):
    ordered_ids: list[int]

    @field_validator("ordered_ids")
    @classmethod
    def non_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("ordered_ids must not be empty")
        return v


class InboundRoutingRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    priority: int
    name: str
    enabled: bool
    conditions: list[dict]
    target_voice_flow_id: int
    target_flow_name: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class InboundRoutingRuleListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    priority: int
    name: str
    enabled: bool
    target_voice_flow_id: int
    target_flow_name: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class InboundRoutingRuleListResponse(PaginatedResponse):
    items: list[InboundRoutingRuleListItem]
