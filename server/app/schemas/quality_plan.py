"""Schemas for online quality plans."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RunMode = Literal["continuous", "one_time"]
PlanStatus = Literal["draft", "running", "paused", "completed", "partial_failed", "failed"]


class QualityPlanPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    run_mode: RunMode = "continuous"
    deadline_at: datetime | None = None
    range_start_at: datetime | None = None
    range_end_at: datetime | None = None
    group_ids: list[int] = Field(default_factory=list)
    agent_ids: list[int] = Field(default_factory=list)
    coverage_mode: Literal["all", "percentage"] = "all"
    sample_rate: Decimal = Field(default=Decimal("100"), ge=1, le=100)
    scorecard_version_id: int
    execution_strategy: Literal["ai", "human"] = "ai"
    manual_route_severity: Literal["notice", "issue", "serious", "fatal"] | None = "issue"
    normal_review_rate: Decimal = Field(default=Decimal("10"), ge=0, le=100)
    reviewer_ids: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_range(self):
        if self.run_mode == "one_time":
            if not self.range_start_at or not self.range_end_at or self.range_start_at >= self.range_end_at:
                raise ValueError("A valid historical range is required")
        if self.execution_strategy == "ai" and self.manual_route_severity is None:
            raise ValueError("Manual route severity is required for AI plans")
        return self


class QualityPlanReviewersPayload(BaseModel):
    reviewer_ids: list[int] = Field(min_length=1)


class QualityPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: int
    name: str
    description: str | None
    run_mode: RunMode
    status: PlanStatus
    deadline_at: datetime | None
    range_start_at: datetime | None
    range_end_at: datetime | None
    group_ids: list[int]
    agent_ids: list[int]
    coverage_mode: str
    sample_rate: Decimal
    scorecard_version_id: int
    execution_strategy: str
    manual_route_severity: str | None
    normal_review_rate: Decimal
    reviewer_ids: list[int]
    estimate_result: dict
    estimated_at: datetime | None
    activated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class QualityPlanListResponse(BaseModel):
    items: list[QualityPlanResponse]
    total: int
    page: int
    per_page: int
    pages: int


class QualityPlanEstimateResponse(BaseModel):
    candidate_count: int
    target_agent_count: int
    estimated_review_count: int
    reference_days: int | None = None
    estimated_daily_count: Decimal | None = None
