"""
Embedded page schemas and validation.
"""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


EmbeddedPageLocation = Literal["chat_auxiliary", "call_screen_pop"]
EmbeddedPageType = Literal["iframe", "react_code"]

# Mirrors the controlled React runtime blocklist used by the web runtime
# (script tags, module imports, network/browser globals, prototype tricks).
UNSUPPORTED_REACT_CODE_PATTERNS = [
    re.compile(r"<\s*script\b", re.IGNORECASE),
    re.compile(r"\bimport\s*(?:\(|[^;\n]+from\b)", re.IGNORECASE),
    re.compile(r"\b(?:eval|fetch|XMLHttpRequest|WebSocket|EventSource|importScripts)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:window|document|globalThis|localStorage|sessionStorage|indexedDB|navigator|location|parent|top|opener)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:Function|constructor|__proto__|prototype)\b"),
]


def validate_react_code_source(code: str) -> bool:
    return bool(re.search(r"\bexport\s+default\b", code)) and not any(
        pattern.search(code) for pattern in UNSUPPORTED_REACT_CODE_PATTERNS
    )


class EmbeddedPageBase(BaseModel):
    location: EmbeddedPageLocation = "chat_auxiliary"
    name: str
    page_type: EmbeddedPageType
    url: str | None = None
    react_code: str | None = None
    config: dict = Field(default_factory=dict)
    enabled: bool = False
    default_focus: bool = False
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Name is required")
        if len(value) > 40:
            raise ValueError("Name must be at most 40 characters")
        return value

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        value = v.strip()
        if not value:
            return None
        if len(value) > 2000:
            raise ValueError("URL must be at most 2000 characters")
        if not value.startswith(("https://", "http://")):
            raise ValueError("URL must start with https:// or http://")
        return value

    @field_validator("config")
    @classmethod
    def validate_config(cls, v: dict) -> dict:
        if not isinstance(v, dict):
            raise ValueError("Config must be a JSON object")
        return v

    @model_validator(mode="after")
    def validate_source_by_type(self) -> "EmbeddedPageBase":
        if self.page_type == "iframe" and not self.url:
            raise ValueError("URL is required for iframe pages")
        if self.page_type == "react_code":
            if not self.react_code or not self.react_code.strip():
                raise ValueError("React code is required for react_code pages")
            if not validate_react_code_source(self.react_code):
                raise ValueError("React code must export a default component and must not use blocked browser capabilities")
        return self


class EmbeddedPageCreate(EmbeddedPageBase):
    pass


class EmbeddedPageUpdate(EmbeddedPageBase):
    pass


class EmbeddedPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    location: EmbeddedPageLocation
    name: str
    page_type: EmbeddedPageType
    url: str | None = None
    react_code: str | None = None
    config: dict
    enabled: bool
    default_focus: bool
    sort_order: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    default_focus_overridden: bool = False


class EmbeddedPageListResponse(BaseModel):
    items: list[EmbeddedPageResponse]
    total: int


class EmbeddedPageWorkspaceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    page_type: EmbeddedPageType
    url: str | None = None
    react_code: str | None = None
    config: dict
    default_focus: bool
    sort_order: int


class EmbeddedPageAgentSummary(BaseModel):
    id: int
    name: str
    email: str


class EmbeddedPageWorkspaceResponse(BaseModel):
    items: list[EmbeddedPageWorkspaceItem]
    agent: EmbeddedPageAgentSummary
