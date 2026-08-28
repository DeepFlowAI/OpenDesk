"""Schemas for custom dashboard lifecycle and configuration APIs."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.base import PaginatedResponse


DASHBOARD_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
MAX_COMPONENTS = 20
MAX_FILTERS = 8
MAX_CODE_BYTES = 64 * 1024


def _clean_required(value: str, *, label: str, max_length: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label} is required")
    if len(cleaned) > max_length:
        raise ValueError(f"{label} must be at most {max_length} characters")
    return cleaned


class DashboardFilterConfig(BaseModel):
    """Public filter configuration stored in a dashboard snapshot."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=64)
    type: Literal["date_range", "field_option"]
    name: str = Field(min_length=1, max_length=80)


class DashboardComponentConfig(BaseModel):
    """Programmable component and its twelve-column layout."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=80)
    code: str
    x: int = Field(default=0, ge=0, le=11)
    y: int = Field(default=0, ge=0)
    w: int = Field(default=6, ge=3, le=12)
    h: int = Field(default=8, ge=4, le=24)

    @model_validator(mode="after")
    def validate_layout_and_code(self) -> "DashboardComponentConfig":
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("Component title is required")
        if self.x + self.w > 12:
            raise ValueError("Component layout exceeds the 12-column canvas")
        if len(self.code.encode("utf-8")) > MAX_CODE_BYTES:
            raise ValueError("Component code must be at most 64KB")
        return self


class DashboardSnapshotInput(BaseModel):
    """Editable fields contained in the current draft snapshot."""

    name: str
    description: str | None = None
    icon: str = "chart-bar"
    filters: list[DashboardFilterConfig] = Field(default_factory=list, max_length=MAX_FILTERS)
    components: list[DashboardComponentConfig] = Field(
        default_factory=list,
        max_length=MAX_COMPONENTS,
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _clean_required(value, label="Name", max_length=80)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) > 300:
            raise ValueError("Description must be at most 300 characters")
        return cleaned or None

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, value: str) -> str:
        return _clean_required(value, label="Icon", max_length=64)

    @model_validator(mode="after")
    def validate_unique_config_ids(self) -> "DashboardSnapshotInput":
        filter_ids = [item.id for item in self.filters]
        component_ids = [item.id for item in self.components]
        if len(filter_ids) != len(set(filter_ids)):
            raise ValueError("Filter ids must be unique")
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("Component ids must be unique")
        return self


class CustomDashboardCreate(DashboardSnapshotInput):
    slug: str

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        cleaned = value.strip()
        if not DASHBOARD_SLUG_RE.fullmatch(cleaned):
            raise ValueError(
                "Slug must start with a lowercase letter and contain only lowercase letters, numbers, and underscores"
            )
        return cleaned


class CustomDashboardUpdate(DashboardSnapshotInput):
    pass


class CustomDashboardCopyRequest(BaseModel):
    slug: str
    name: str | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        return CustomDashboardCreate.validate_slug(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_required(value, label="Name", max_length=80)


class CustomDashboardReorderRequest(BaseModel):
    ids: list[int] = Field(min_length=1)

    @field_validator("ids")
    @classmethod
    def validate_unique_ids(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("Dashboard ids must be unique")
        return value


class DashboardSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revision: int
    name: str
    description: str | None = None
    icon: str
    filters: list[dict]
    components: list[dict]
    updated_at: datetime | None = None


class CustomDashboardListItem(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None = None
    icon: str
    status: Literal["draft", "published", "disabled"]
    sort_order: int
    component_count: int
    published_at: datetime | None = None
    updated_at: datetime | None = None


class CustomDashboardListResponse(PaginatedResponse):
    items: list[CustomDashboardListItem]


class CustomDashboardResponse(CustomDashboardListItem):
    draft: DashboardSnapshotResponse
    published_revision: int | None = None


class WorkspaceDashboardListItem(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None = None
    icon: str
    sort_order: int
    component_count: int
    published_at: datetime


class WorkspaceDashboardListResponse(BaseModel):
    items: list[WorkspaceDashboardListItem]
    total: int


class WorkspaceDashboardResponse(WorkspaceDashboardListItem):
    revision: int
    timezone: str
    filters: list[dict]
    components: list[dict]
