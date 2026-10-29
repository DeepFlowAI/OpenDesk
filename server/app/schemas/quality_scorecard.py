"""Schemas for online quality scorecards."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

QualitySeverity = Literal["normal", "notice", "issue", "serious", "fatal"]
EvidencePolicy = Literal["none", "issue_only", "always"]
ScorecardStatus = Literal["draft", "published", "disabled"]


class QualityScorecardOptionInput(BaseModel):
    name: str = Field(max_length=30)
    description: str = Field(max_length=500)
    points: Decimal = Field(ge=0, le=100)
    severity: QualitySeverity

    @field_validator("name", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class QualityScorecardCriterionInput(BaseModel):
    stable_key: UUID | None = None
    name: str = Field(max_length=100)
    rubric: str = Field(max_length=2000)
    max_points: Decimal = Field(ge=0, le=100, decimal_places=2)
    is_required: bool = True
    evidence_policy: EvidencePolicy = "issue_only"
    options: list[QualityScorecardOptionInput] = Field(default_factory=list, max_length=5)

    @field_validator("name", "rubric")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class QualityScorecardSectionInput(BaseModel):
    name: str = Field(max_length=50)
    criteria: list[QualityScorecardCriterionInput] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class QualityScorecardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    pass_score: Decimal | None = Field(default=Decimal("80"), ge=0, le=100, decimal_places=1)
    sections: list[QualityScorecardSectionInput] | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class QualityScorecardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    pass_score: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=1)
    sections: list[QualityScorecardSectionInput] | None = None


class QualityScorecardOptionResponse(QualityScorecardOptionInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sort_order: int


class QualityScorecardCriterionResponse(QualityScorecardCriterionInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    stable_key: UUID
    sort_order: int
    options: list[QualityScorecardOptionResponse]


class QualityScorecardSectionResponse(QualityScorecardSectionInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sort_order: int
    criteria: list[QualityScorecardCriterionResponse]


class QualityScorecardVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version_number: int
    status: ScorecardStatus
    pass_score: Decimal | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    sections: list[QualityScorecardSectionResponse]


class QualityScorecardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    status: ScorecardStatus
    current_version_number: int
    created_at: datetime
    updated_at: datetime
    versions: list[QualityScorecardVersionResponse]


class QualityScorecardListItem(BaseModel):
    id: int
    name: str
    description: str | None
    status: ScorecardStatus
    current_version_number: int
    current_version_id: int
    criterion_count: int
    scored_count: int
    observation_count: int
    pass_score: Decimal | None
    updated_at: datetime


class QualityScorecardListResponse(BaseModel):
    items: list[QualityScorecardListItem]
    total: int
    page: int
    per_page: int
    pages: int
