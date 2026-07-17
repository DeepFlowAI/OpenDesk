"""Schemas for creating OpenAgent knowledge-base QA from conversations."""
import re

from pydantic import BaseModel, Field, field_validator, model_validator


_ACCESS_KEYWORD_RE = re.compile(r"^[A-Za-z0-9_]+$")


def normalize_access_keywords(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip().lower()
        if not value or not _ACCESS_KEYWORD_RE.fullmatch(value):
            raise ValueError("Permission keywords may contain only ASCII letters, numbers, and underscores")
        if value not in seen:
            normalized.append(value)
            seen.add(value)
    if len(normalized) > 50:
        raise ValueError("Permission keywords may contain at most 50 items")
    return normalized


class RobotQaSettingPayload(BaseModel):
    enabled: bool
    knowledge_base_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_target_when_enabled(self) -> "RobotQaSettingPayload":
        if self.enabled and self.knowledge_base_id is None:
            raise ValueError("Knowledge base is required when robot QA is enabled")
        return self


class RobotQaSettingResponse(BaseModel):
    enabled: bool = False
    knowledge_base_id: int | None = None
    knowledge_base_name: str | None = None


class RobotQaKnowledgeBase(BaseModel):
    id: int
    name: str
    description: str | None = None
    status: str


class RobotQaKnowledgeBaseListResponse(BaseModel):
    items: list[RobotQaKnowledgeBase] = Field(default_factory=list)


class RobotQaDirectory(BaseModel):
    id: int
    parent_id: int | None = None
    name: str
    sort_order: int
    depth: int
    path: list[str] = Field(default_factory=list)


class RobotQaDirectoryListResponse(BaseModel):
    knowledge_base_id: int
    knowledge_base_name: str
    items: list[RobotQaDirectory] = Field(default_factory=list)


class RobotQaRuntimeResponse(BaseModel):
    enabled: bool = False
    available: bool = False
    knowledge_base_id: int | None = None
    knowledge_base_name: str | None = None


class RobotQaCreatePayload(BaseModel):
    directory_id: int = Field(ge=1)
    question: str = Field(min_length=1, max_length=500)
    answer_markdown: str = Field(min_length=1, max_length=7000)
    access_keywords: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("question", "answer_markdown", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value must not be blank")
        return normalized

    @field_validator("access_keywords")
    @classmethod
    def validate_access_keywords(cls, value: list[str]) -> list[str]:
        return normalize_access_keywords(value)


class RobotQaCreateResponse(BaseModel):
    id: int
    knowledge_base_id: int
    directory_id: int
    process_status: str
