"""Schemas for tenant event subscription management."""
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import PaginatedResponse


def _validate_endpoint_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("Endpoint URL must be a valid HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("Endpoint URL must not contain credentials")
    if parsed.fragment:
        raise ValueError("Endpoint URL must not contain a fragment")
    return normalized


class EventSubscriptionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    endpoint_url: str = Field(min_length=1, max_length=2048)
    description: str | None = Field(default=None, max_length=200)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Name must be at least 2 characters")
        return normalized

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, value: str) -> str:
        return _validate_endpoint_url(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class EventSubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    endpoint_url: str | None = Field(default=None, min_length=1, max_length=2048)
    description: str | None = Field(default=None, max_length=200)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Name must be at least 2 characters")
        return normalized

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, value: str | None) -> str | None:
        return _validate_endpoint_url(value) if value is not None else None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class EventSubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    name: str
    endpoint_url: str
    description: str | None = None
    masked_secret: str
    secret_version: int
    is_active: bool
    disabled_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    recent_delivery: "EventDeliverySummary | None" = None


class EventSubscriptionSecretResponse(BaseModel):
    record: EventSubscriptionResponse
    secret: str


class EventSubscriptionListResponse(PaginatedResponse):
    items: list[EventSubscriptionResponse]


class EventDeliverySummary(BaseModel):
    status: Literal["pending", "processing", "succeeded", "failed"]
    http_status: int | None = None
    duration_ms: int | None = None
    error_type: str | None = None
    attempted_at: datetime | None = None


class EventSubscriptionTestResponse(BaseModel):
    delivery_id: UUID
    status: Literal["succeeded", "failed"]
    http_status: int | None = None
    duration_ms: int
    error_type: str | None = None


EventSubscriptionResponse.model_rebuild()


EventSubscriptionStatusFilter = Literal["active", "disabled"]
