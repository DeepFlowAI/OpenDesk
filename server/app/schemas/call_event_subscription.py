"""Schemas and stable event codes for call event subscription rules."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.constants.call_center import CallSource

CALL_EVENT_TYPES = (
    "call.created",
    "call.customer.connected",
    "call.ended",
    "call.queue.entered",
    "call.agent.connected",
    "call.agent.disconnected",
    "call.transfer.completed",
    "call.recording.completed",
    "call.recording.failed",
    "call.satisfaction.completed",
)
CALL_EVENT_TYPE_SET = frozenset(CALL_EVENT_TYPES)
CALL_DIRECTIONS = ("inbound", "outbound")
CALL_SOURCES = tuple(source.value for source in CallSource)
MAX_CALL_EVENT_RULES = 10


def _normalize_choices(values: list[str], allowed: tuple[str, ...], label: str) -> list[str]:
    selected = {value.strip() for value in values}
    invalid = selected.difference(allowed)
    if invalid:
        raise ValueError(f"Unsupported {label}")
    if not selected:
        raise ValueError(f"Select at least one {label}")
    # Persist an explicit list in canonical order so later additions never auto-join.
    return [value for value in allowed if value in selected]


class CallEventRuleSave(BaseModel):
    name: str = Field(..., max_length=200)
    subscription_public_id: UUID
    event_types: list[str] = Field(..., max_length=len(CALL_EVENT_TYPES) * 2)
    directions: list[str] = Field(..., max_length=len(CALL_DIRECTIONS) * 2)
    call_sources: list[str] = Field(..., max_length=len(CALL_SOURCES) * 2)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not 2 <= len(value) <= 50:
            raise ValueError("Rule name must be 2 to 50 characters")
        return value

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, values: list[str]) -> list[str]:
        return _normalize_choices(values, CALL_EVENT_TYPES, "event")

    @field_validator("directions")
    @classmethod
    def validate_directions(cls, values: list[str]) -> list[str]:
        return _normalize_choices(values, CALL_DIRECTIONS, "direction")

    @field_validator("call_sources")
    @classmethod
    def validate_call_sources(cls, values: list[str]) -> list[str]:
        return _normalize_choices(values, CALL_SOURCES, "call source")


class CallEventRuleSubscription(BaseModel):
    public_id: UUID
    name: str
    is_active: bool


class CallEventRuleResponse(BaseModel):
    public_id: UUID
    name: str
    subscription: CallEventRuleSubscription
    event_types: list[str]
    directions: list[str]
    call_sources: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CallEventRuleListResponse(BaseModel):
    items: list[CallEventRuleResponse]
    total: int
    page: int
    per_page: int
    pages: int
    tenant_rule_count: int
    max_rules: int = MAX_CALL_EVENT_RULES


class CallEventRuleOption(BaseModel):
    public_id: UUID
    name: str
    is_active: bool
    used_by_rule_name: str | None = None


class CallEventRuleOptionsResponse(BaseModel):
    options: list[CallEventRuleOption]
    can_manage_global: bool
