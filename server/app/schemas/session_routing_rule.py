"""
Session routing rule schemas and condition validation
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.base import PaginatedResponse


SessionConditionType = Literal["channel", "web_sdk", "current_time"]


class SessionRoutingCondition(BaseModel):
    condition_type: SessionConditionType
    operator: str
    value: str | list[str]

    @model_validator(mode="after")
    def validate_operator_and_value(self) -> "SessionRoutingCondition":
        ct = self.condition_type
        op = self.operator
        val = self.value

        if ct == "channel":
            if op not in ("eq", "ne"):
                raise ValueError("Invalid operator for channel condition; expected 'eq' or 'ne'")
            if val not in ("web", "sdk"):
                raise ValueError("Channel value must be 'web' or 'sdk'")

        elif ct == "web_sdk":
            if op in ("eq", "ne"):
                if not isinstance(val, str) or not val.strip():
                    raise ValueError("Web SDK value must be a non-empty string for eq/ne")
            elif op in ("any_eq", "any_ne"):
                if not isinstance(val, list) or len(val) == 0:
                    raise ValueError("Web SDK value must be a non-empty list for any_eq/any_ne")
                for item in val:
                    if not isinstance(item, str) or not item.strip():
                        raise ValueError("Each SDK value must be a non-empty string")
            else:
                raise ValueError("Invalid operator for web_sdk condition")

        elif ct == "current_time":
            if op not in ("in_schedule", "not_in_schedule"):
                raise ValueError("Invalid operator for current_time condition")
            str_val = val if isinstance(val, str) else str(val)
            if not str_val.isdigit() or int(str_val) < 1:
                raise ValueError("Service hours id must be a positive integer")
            self.value = str_val

        return self


class SessionRoutingRuleCreate(BaseModel):
    name: str
    enabled: bool = True
    conditions: list[SessionRoutingCondition] = []
    target_group_id: int

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 64:
            raise ValueError("Name must be at most 64 characters")
        return v


class SessionRoutingRuleUpdate(BaseModel):
    name: str
    enabled: bool = True
    conditions: list[SessionRoutingCondition] = []
    target_group_id: int

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 64:
            raise ValueError("Name must be at most 64 characters")
        return v


class SessionRoutingRuleEnabledPatch(BaseModel):
    enabled: bool


class SessionRoutingRuleReorder(BaseModel):
    ordered_ids: list[int]

    @field_validator("ordered_ids")
    @classmethod
    def non_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("ordered_ids must not be empty")
        return v


class SessionRoutingRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    priority: int
    name: str
    enabled: bool
    conditions: list[dict]
    target_group_id: int
    target_group_name: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SessionRoutingRuleListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    priority: int
    name: str
    enabled: bool
    target_group_id: int
    target_group_name: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SessionRoutingRuleListResponse(PaginatedResponse):
    items: list[SessionRoutingRuleListItem]
