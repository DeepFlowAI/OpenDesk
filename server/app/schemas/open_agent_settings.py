"""
OpenAgent settings schemas.
"""
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_BASE_URL_LENGTH = 512
MAX_API_KEY_LENGTH = 512


def normalize_base_url(value: str) -> str:
    """Trim and validate an OpenAgent base URL."""
    normalized = value.strip().rstrip("/")
    if not normalized:
        raise ValueError("OpenAgent base URL is required")
    if len(normalized) > MAX_BASE_URL_LENGTH:
        raise ValueError("OpenAgent base URL must be at most 512 characters")

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("OpenAgent base URL must be a valid http or https URL")
    return normalized


def normalize_api_key(value: str | None) -> str | None:
    """Trim API key input; blank means not provided."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_API_KEY_LENGTH:
        raise ValueError("OpenAgent API key must be at most 512 characters")
    return normalized


class OpenAgentSettingsUpdate(BaseModel):
    base_url: str
    api_key: str | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return normalize_base_url(value)

    @field_validator("api_key", mode="before")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        return normalize_api_key(value)


class OpenAgentConnectionTestRequest(BaseModel):
    base_url: str
    api_key: str | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return normalize_base_url(value)

    @field_validator("api_key", mode="before")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        return normalize_api_key(value)


class OpenAgentSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_url: str | None = None
    has_api_key: bool = False
    updated_at: datetime | None = None


class OpenAgentConnectionTestResponse(BaseModel):
    ok: bool
    message: str


class OpenAgentAgentSummary(BaseModel):
    id: int
    name: str
    description: str | None = None
    status: str


class OpenAgentWelcomeMessageBlock(BaseModel):
    type: Literal["markdown", "embed"]
    content: str | None = None
    embed_code: str | None = None
    height: int | None = None

    @model_validator(mode="after")
    def normalize_block(self) -> "OpenAgentWelcomeMessageBlock":
        if self.type == "markdown":
            self.content = self.content or ""
            self.embed_code = None
            self.height = None
        else:
            self.content = None
            self.embed_code = self.embed_code or ""
            self.height = self.height if self.height and self.height > 0 else 360
        return self


class OpenAgentFAQQuestion(BaseModel):
    text: str


class OpenAgentFAQCategory(BaseModel):
    name: str
    questions: list[OpenAgentFAQQuestion] = Field(default_factory=list)


class OpenAgentFAQ(BaseModel):
    enabled: bool = False
    title: str = "常见问题"
    categories: list[OpenAgentFAQCategory] = Field(default_factory=list)


class OpenAgentWelcomeMessage(BaseModel):
    enabled: bool = False
    blocks: list[OpenAgentWelcomeMessageBlock] = Field(default_factory=list)
    faq: OpenAgentFAQ | None = None


class OpenAgentAgentListResponse(BaseModel):
    items: list[OpenAgentAgentSummary]
    total: int
    page: int
    per_page: int
    pages: int
