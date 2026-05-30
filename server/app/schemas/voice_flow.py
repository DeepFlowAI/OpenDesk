"""
Voice flow Pydantic schemas (header / metadata layer).

Graph schema lives in app/schemas/voice_flow_graph.py.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import PaginatedResponse
from app.schemas.voice_flow_graph import GraphError, GraphValidationResult, VoiceFlowGraph


def _validate_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Name is required")
    if len(v) > 50:
        raise ValueError("Name must be at most 50 characters")
    return v


def _validate_description(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if len(v) > 200:
        raise ValueError("Description must be at most 200 characters")
    return v or None


class VoiceFlowCreate(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True

    _v_name = field_validator("name")(lambda cls, v: _validate_name(v))
    _v_desc = field_validator("description")(lambda cls, v: _validate_description(v))


class VoiceFlowUpdate(BaseModel):
    """Update payload — any subset of fields. graph_json present triggers a new version."""

    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    graph_json: VoiceFlowGraph | None = None

    @field_validator("name")
    @classmethod
    def validate_name_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_name(v)

    @field_validator("description")
    @classmethod
    def validate_desc_optional(cls, v: str | None) -> str | None:
        return _validate_description(v)


class VoiceFlowValidateRequest(BaseModel):
    graph_json: VoiceFlowGraph


class VoiceFlowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    enabled: bool
    current_version_no: int | None = None
    graph_json: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VoiceFlowListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    enabled: bool
    current_version_no: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VoiceFlowListResponse(PaginatedResponse):
    items: list[VoiceFlowListItem]


class VoiceFlowSelectItem(BaseModel):
    id: int
    name: str


class VoiceFlowSelectListResponse(BaseModel):
    items: list[VoiceFlowSelectItem]


# ──────────────── System variables (read-only reference) ────────────────


class SystemVariableItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    display_name_zh: str
    display_name_en: str
    value_type: str
    description_zh: str
    description_en: str
    sort_order: int


class SystemVariableListResponse(BaseModel):
    items: list[SystemVariableItem]


# ──────────────── Audio assets ────────────────


class VoiceFlowVersionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_no: int
    comment: str | None = None
    is_current: bool
    created_at: datetime | None = None
    created_by_actor_name: str | None = None


class VoiceFlowVersionListResponse(BaseModel):
    items: list[VoiceFlowVersionItem]
    current_version_no: int | None = None


class VoiceFlowVersionDetail(BaseModel):
    id: int
    version_no: int
    graph_json: dict
    comment: str | None = None
    created_at: datetime | None = None
    created_by_actor_name: str | None = None
    is_current: bool


class AudioAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    mime_type: str
    size_bytes: int
    duration_ms: int | None = None
    preview_url: str | None = None
    created_at: datetime | None = None


# Re-export so router only needs to import from this module.
__all__ = [
    "VoiceFlowCreate",
    "VoiceFlowUpdate",
    "VoiceFlowValidateRequest",
    "VoiceFlowResponse",
    "VoiceFlowListItem",
    "VoiceFlowListResponse",
    "VoiceFlowSelectItem",
    "VoiceFlowSelectListResponse",
    "SystemVariableItem",
    "SystemVariableListResponse",
    "AudioAssetResponse",
    "VoiceFlowVersionItem",
    "VoiceFlowVersionListResponse",
    "VoiceFlowVersionDetail",
    "GraphError",
    "GraphValidationResult",
    "VoiceFlowGraph",
]
