"""
Ticket workflow API schemas.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import PaginatedResponse
from app.schemas.ticket_workflow_graph import (
    GraphError,
    GraphValidationResult,
    TicketWorkflowGraph,
)


def _validate_name(v: str) -> str:
    value = v.strip()
    if not value:
        raise ValueError("Name is required")
    if len(value) > 80:
        raise ValueError("Name must be at most 80 characters")
    return value


def _validate_description(v: str | None) -> str | None:
    if v is None:
        return None
    value = v.strip()
    if len(value) > 500:
        raise ValueError("Description must be at most 500 characters")
    return value or None


class TicketWorkflowCreate(BaseModel):
    name: str = "未命名流程"
    description: str | None = None
    enabled: bool = False

    _v_name = field_validator("name")(lambda cls, v: _validate_name(v))
    _v_desc = field_validator("description")(lambda cls, v: _validate_description(v))


class TicketWorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    graph_json: TicketWorkflowGraph | None = None

    @field_validator("name")
    @classmethod
    def validate_name_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_name(v)

    @field_validator("description")
    @classmethod
    def validate_description_optional(cls, v: str | None) -> str | None:
        return _validate_description(v)


class TicketWorkflowValidateRequest(BaseModel):
    graph_json: TicketWorkflowGraph


class TicketWorkflowReorderRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1)

    @field_validator("ids")
    @classmethod
    def unique_ids(cls, v: list[int]) -> list[int]:
        if len(set(v)) != len(v):
            raise ValueError("Workflow ids must be unique")
        return v


class TicketWorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    enabled: bool
    sort_order: int
    current_version_no: int | None = None
    trigger_event_types: list[str] = []
    graph_json: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TicketWorkflowListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    enabled: bool
    sort_order: int
    current_version_no: int | None = None
    trigger_event_types: list[str] = []
    updated_at: datetime | None = None


class TicketWorkflowListResponse(PaginatedResponse):
    items: list[TicketWorkflowListItem]


class TicketWorkflowVersionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_no: int
    comment: str | None = None
    is_current: bool
    created_at: datetime | None = None
    created_by_actor_name: str | None = None


class TicketWorkflowVersionListResponse(BaseModel):
    items: list[TicketWorkflowVersionItem]
    current_version_no: int | None = None


class TicketWorkflowVersionDetail(BaseModel):
    id: int
    version_no: int
    graph_json: dict
    comment: str | None = None
    created_at: datetime | None = None
    created_by_actor_name: str | None = None
    is_current: bool


__all__ = [
    "TicketWorkflowCreate",
    "TicketWorkflowUpdate",
    "TicketWorkflowValidateRequest",
    "TicketWorkflowReorderRequest",
    "TicketWorkflowResponse",
    "TicketWorkflowListItem",
    "TicketWorkflowListResponse",
    "TicketWorkflowVersionItem",
    "TicketWorkflowVersionListResponse",
    "TicketWorkflowVersionDetail",
    "GraphError",
    "GraphValidationResult",
    "TicketWorkflowGraph",
]
