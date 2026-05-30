"""
Tenant phone number schemas — admin list + tag editing.
"""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

MAX_TAGS = 20
MAX_TAG_LENGTH = 32


def _normalize_tags(value: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in value:
        tag = raw.strip()
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise ValueError("Tag must be at most 32 characters")
        key = tag.lower()
        if key in seen:
            raise ValueError("Duplicate tag")
        seen.add(key)
        normalized.append(tag)
    if len(normalized) > MAX_TAGS:
        raise ValueError("At most 20 tags are allowed")
    return normalized


class TenantPhoneNumberTagsUpdate(BaseModel):
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        return _normalize_tags(v)


class OutboundTimeSlot(BaseModel):
    start: str
    end: str


class TenantPhoneNumberResponse(BaseModel):
    id: str
    phone_number: str
    call_types: list[str]
    tags: list[str] = Field(default_factory=list)
    outbound_time_slots: list[OutboundTimeSlot] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TenantPhoneNumberListResponse(BaseModel):
    items: list[TenantPhoneNumberResponse]
    total: int
    page: int
    per_page: int
    pages: int
