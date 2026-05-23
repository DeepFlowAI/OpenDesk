"""
Welcome message rule schemas and condition validation.
"""
from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.base import PaginatedResponse


WelcomeMessageConditionType = Literal["channel", "web_sdk"]


def strip_rich_text(value: str) -> str:
    """Strip basic HTML markup to validate rich text emptiness."""
    return re.sub(r"<[^>]*>", "", value).replace("&nbsp;", " ").strip()


class WelcomeMessageCondition(BaseModel):
    condition_type: WelcomeMessageConditionType
    operator: str
    value: str | list[str]

    @model_validator(mode="after")
    def validate_operator_and_value(self) -> "WelcomeMessageCondition":
        ct = self.condition_type
        op = self.operator
        val = self.value

        if ct == "channel":
            if op not in ("eq", "ne"):
                raise ValueError("Invalid operator for channel condition; expected 'eq' or 'ne'")
            if val not in ("websdk", "web", "sdk"):
                raise ValueError("Channel value must be 'websdk'")
            self.value = "websdk"
            return self

        if op in ("eq", "ne"):
            if not isinstance(val, str) or not val.strip():
                raise ValueError("Web SDK value must be a non-empty string for eq/ne")
            self.value = val.strip()
        elif op in ("any_eq", "any_ne"):
            if not isinstance(val, list) or len(val) == 0:
                raise ValueError("Web SDK value must be a non-empty list for any_eq/any_ne")
            normalized = []
            for item in val:
                item_value = str(item).strip()
                if not item_value:
                    raise ValueError("Each SDK value must be a non-empty string")
                normalized.append(item_value)
            self.value = normalized
        else:
            raise ValueError("Invalid operator for web_sdk condition")

        return self


class WelcomeMessageRuleBase(BaseModel):
    name: str
    enabled: bool = True
    conditions: list[WelcomeMessageCondition] = []
    content: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Name is required")
        if len(value) > 64:
            raise ValueError("Name must be at most 64 characters")
        return value

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        value = v.strip()
        if not strip_rich_text(value):
            raise ValueError("Welcome message content is required")
        if len(value) > 5000:
            raise ValueError("Welcome message content must be at most 5000 characters")
        return value


class WelcomeMessageRuleCreate(WelcomeMessageRuleBase):
    pass


class WelcomeMessageRuleUpdate(WelcomeMessageRuleBase):
    pass


class WelcomeMessageRuleEnabledPatch(BaseModel):
    enabled: bool


class WelcomeMessageRuleReorder(BaseModel):
    ordered_ids: list[int]

    @field_validator("ordered_ids")
    @classmethod
    def non_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("ordered_ids must not be empty")
        return v


class WelcomeMessagePublic(BaseModel):
    id: int
    name: str
    content: str


class WelcomeMessageRuleListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    priority: int
    name: str
    enabled: bool
    conditions: list[dict]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WelcomeMessageRuleResponse(WelcomeMessageRuleListItem):
    content: str


class WelcomeMessageRuleListResponse(PaginatedResponse):
    items: list[WelcomeMessageRuleListItem]
