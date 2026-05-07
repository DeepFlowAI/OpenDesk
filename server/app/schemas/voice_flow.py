"""
Voice flow Pydantic schemas
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.base import PaginatedResponse


class VoiceFlowCreate(BaseModel):
    name: str
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 50:
            raise ValueError("Name must be at most 50 characters")
        return v


class VoiceFlowUpdate(BaseModel):
    name: str
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 50:
            raise ValueError("Name must be at most 50 characters")
        return v


class VoiceFlowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VoiceFlowListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VoiceFlowListResponse(PaginatedResponse):
    items: list[VoiceFlowListItem]


class VoiceFlowSelectItem(BaseModel):
    """Minimal shape for dropdowns"""

    id: int
    name: str


class VoiceFlowSelectListResponse(BaseModel):
    items: list[VoiceFlowSelectItem]
