"""Schemas for online quality review execution."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class QualityLLMResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_type: Literal["option", "not_applicable", "insufficient_evidence"]
    option_id: int | None
    reason: str = Field(min_length=1, max_length=4000)
    evidence_message_ids: list[int] = Field(default_factory=list, max_length=20)


class QualityMaterializeResponse(BaseModel):
    created_reviews: int
    queued_calls: int


class QualityRetryResponse(BaseModel):
    review_id: int
    queued_calls: int


class QualityHumanItemPayload(BaseModel):
    review_item_id: int
    result_type: Literal["option", "not_applicable", "unanswered"]
    option_id: int | None = None
    judgment: str | None = Field(default=None, max_length=4000)
    change_reason: str | None = Field(default=None, max_length=1000)
    evidence_message_ids: list[int] = Field(default_factory=list, max_length=20)


class QualityDraftPayload(BaseModel):
    version: int = Field(ge=0)
    overall_comment: str | None = Field(default=None, max_length=2000)
    items: list[QualityHumanItemPayload]


class QualityUnablePayload(BaseModel):
    version: int = Field(ge=0)
    reason: str = Field(min_length=10, max_length=1000)
    overall_comment: str | None = Field(default=None, max_length=2000)
    items: list[QualityHumanItemPayload]


class QualityReassignPayload(BaseModel):
    reviewer_id: int


class QualityReviewListItem(BaseModel):
    id: int
    plan_id: int
    conversation_id: int
    target_agent_id: int
    agent_name: str | None = None
    status: str
    result_source: str | None = None
    score: Decimal | None = None
    outcome: str | None = None
    issue_count: int | None = None
    route_reasons: list[str] = Field(default_factory=list)
    assigned_reviewer_id: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class QualityReviewListResponse(BaseModel):
    items: list[QualityReviewListItem]
    total: int
    page: int
    per_page: int
    pages: int


class QualityWorkbenchResponse(BaseModel):
    review: QualityReviewListItem
    conversation_snapshot: dict[str, Any]
    message_snapshot: list[dict[str, Any]]
    draft_version: int
    draft_status: str
    overall_comment: str | None = None
    items: list[dict[str, Any]]


class QualityStatisticsResponse(BaseModel):
    total: int
    ai_completed: int
    pending_human: int
    human_completed: int
    unable: int
    failed: int
    average_score: Decimal | None = None
    pass_rate: Decimal | None = None


class QualityReviewDetailResponse(QualityWorkbenchResponse):
    unable_reason: str | None = None
    audits: list[dict[str, Any]] = Field(default_factory=list)
