"""
Knowledge base schemas.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import PaginatedResponse, TimestampSchema

KnowledgeDocumentStatus = Literal["draft", "published"]
KnowledgeDocumentDisplayStatus = Literal["draft", "published", "expired"]
KnowledgeValidityType = Literal["permanent", "scheduled"]
KnowledgeRecommendationStatus = Literal["no_conversation", "updating", "no_vector", "ready", "failed"]


class ActorRef(BaseModel):
    actor_type: str | None = None
    actor_id: int | None = None
    actor_name: str | None = None


class KnowledgeDirectoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Directory name is required")
        return normalized


class KnowledgeDirectoryCreate(KnowledgeDirectoryBase):
    pass


class KnowledgeDirectoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Directory name is required")
        return normalized


class KnowledgeDirectoryMove(BaseModel):
    parent_id: int | None = None
    sort_order: int | None = Field(None, ge=0)


class KnowledgeDirectoryResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    parent_id: int | None = None
    name: str
    sort_order: int
    depth: int = 1
    document_count: int = 0
    created_by: ActorRef | None = None
    updated_by: ActorRef | None = None


class KnowledgeDirectoryNode(KnowledgeDirectoryResponse):
    children: list["KnowledgeDirectoryNode"] = Field(default_factory=list)


class KnowledgeDirectoryListResponse(BaseModel):
    items: list[KnowledgeDirectoryNode]


class KnowledgeDirectoryPathItem(BaseModel):
    id: int
    name: str


class KnowledgeDocumentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    directory_id: int
    content_html: str = Field(..., min_length=1)
    status: KnowledgeDocumentStatus = "draft"
    validity_type: KnowledgeValidityType = "permanent"
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Document title is required")
        return normalized


class KnowledgeDocumentCreate(KnowledgeDocumentBase):
    pass


class KnowledgeDocumentUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=120)
    directory_id: int | None = None
    content_html: str | None = Field(None, min_length=1)
    status: KnowledgeDocumentStatus | None = None
    validity_type: KnowledgeValidityType | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Document title is required")
        return normalized


class KnowledgeDocumentResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    directory_id: int
    directory_path: list[KnowledgeDirectoryPathItem] = Field(default_factory=list)
    title: str
    content_html: str
    status: KnowledgeDocumentStatus
    display_status: KnowledgeDocumentDisplayStatus
    validity_type: KnowledgeValidityType
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    created_by: ActorRef | None = None
    updated_by: ActorRef | None = None


class KnowledgeDocumentListResponse(PaginatedResponse):
    items: list[KnowledgeDocumentResponse]


class KnowledgeRecommendationResponse(BaseModel):
    status: KnowledgeRecommendationStatus
    items: list[KnowledgeDocumentResponse] = Field(default_factory=list)
    limit: int = 5
    vector_updated_at: datetime | None = None
    message: str | None = None


KnowledgeDirectoryNode.model_rebuild()
