"""API schemas for versioned call satisfaction flows."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.base import PaginatedResponse
from app.schemas.satisfaction_flow_graph import (
    GraphError,
    GraphValidationResult,
    SatisfactionFlowGraph,
    default_satisfaction_graph,
)


def _clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Name is required")
    if len(value) > 50:
        raise ValueError("Name must be at most 50 characters")
    return value


def _clean_description(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) > 200:
        raise ValueError("Description must be at most 200 characters")
    return value or None


class SatisfactionFlowSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_transfer: bool = False
    agent_invite: bool = True
    inbound: bool = True
    outbound: bool = False

    @model_validator(mode="after")
    def validate_choices(self) -> "SatisfactionFlowSettings":
        if not self.auto_transfer and not self.agent_invite:
            raise ValueError("At least one trigger must be enabled")
        if not self.inbound and not self.outbound:
            raise ValueError("At least one direction must be enabled")
        return self


class SatisfactionFlowDraft(BaseModel):
    name: str = "未命名满意度流程"
    description: str | None = None
    graph_json: SatisfactionFlowGraph = Field(
        default_factory=lambda: SatisfactionFlowGraph.model_validate(default_satisfaction_graph())
    )
    settings: SatisfactionFlowSettings = Field(default_factory=SatisfactionFlowSettings)
    comment: str | None = Field(None, max_length=200)

    _validate_name = field_validator("name")(_clean_name)
    _validate_description = field_validator("description")(_clean_description)


class SatisfactionFlowCreate(SatisfactionFlowDraft):
    pass


class SatisfactionFlowSave(SatisfactionFlowDraft):
    pass


class SatisfactionFlowValidateRequest(BaseModel):
    graph_json: SatisfactionFlowGraph
    settings: SatisfactionFlowSettings


class SatisfactionFlowEnableRequest(BaseModel):
    replace_active: bool = False


class SatisfactionFlowListItem(BaseModel):
    id: int
    name: str
    description: str | None = None
    enabled: bool
    triggers: list[str]
    directions: list[str]
    question_count: int
    current_version_no: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SatisfactionFlowListResponse(PaginatedResponse):
    items: list[SatisfactionFlowListItem]


class SatisfactionFlowResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    enabled: bool
    current_version_no: int | None = None
    graph_json: dict | None = None
    settings: SatisfactionFlowSettings | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SatisfactionFlowVersionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version_no: int
    name_snapshot: str
    comment: str | None = None
    is_current: bool
    question_count: int
    created_at: datetime | None = None
    created_by_actor_name: str | None = None


class SatisfactionFlowVersionListResponse(BaseModel):
    items: list[SatisfactionFlowVersionItem]
    current_version_no: int | None = None


class SatisfactionFlowVersionDetail(BaseModel):
    id: int
    version_no: int
    name_snapshot: str
    description_snapshot: str | None = None
    graph_json: dict
    settings: SatisfactionFlowSettings
    question_count: int
    comment: str | None = None
    created_at: datetime | None = None
    created_by_actor_name: str | None = None
    is_current: bool


__all__ = [
    "GraphError",
    "GraphValidationResult",
    "SatisfactionFlowCreate",
    "SatisfactionFlowDraft",
    "SatisfactionFlowEnableRequest",
    "SatisfactionFlowListResponse",
    "SatisfactionFlowResponse",
    "SatisfactionFlowSave",
    "SatisfactionFlowSettings",
    "SatisfactionFlowValidateRequest",
    "SatisfactionFlowVersionDetail",
    "SatisfactionFlowVersionListResponse",
]
