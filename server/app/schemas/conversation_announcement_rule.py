"""
Conversation announcement rule schemas and validation.
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.base import PaginatedResponse
from app.schemas.welcome_message_rule import WelcomeMessageCondition, strip_rich_text


AnnouncementTimeRangeType = Literal["permanent", "limited"]
AnnouncementBackgroundColor = Literal["yellow", "green", "blue", "pink", "purple", "gray"]
AnnouncementTimeStatus = Literal["permanent", "active", "not_started", "expired"]


def _ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class ConversationAnnouncementRuleBase(BaseModel):
    name: str
    enabled: bool = True
    time_range_type: AnnouncementTimeRangeType = "permanent"
    start_at: datetime | None = None
    end_at: datetime | None = None
    conditions: list[WelcomeMessageCondition] = Field(default_factory=list)
    auto_popup: bool = True
    background_color: AnnouncementBackgroundColor = "yellow"
    summary_html: str
    detail_html: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Name is required")
        if len(value) > 64:
            raise ValueError("Name must be at most 64 characters")
        return value

    @field_validator("start_at", "end_at", mode="after")
    @classmethod
    def normalize_datetime(cls, v: datetime | None) -> datetime | None:
        return _ensure_aware(v)

    @field_validator("summary_html")
    @classmethod
    def validate_summary_html(cls, v: str) -> str:
        value = v.strip()
        plain = strip_rich_text(value)
        if not plain:
            raise ValueError("Announcement summary is required")
        if len(plain) > 120:
            raise ValueError("Announcement summary must be at most 120 characters")
        if len(value) > 2000:
            raise ValueError("Announcement summary HTML must be at most 2000 characters")
        return value

    @field_validator("detail_html")
    @classmethod
    def validate_detail_html(cls, v: str) -> str:
        value = v.strip()
        if not strip_rich_text(value):
            raise ValueError("Announcement detail is required")
        if len(value) > 10000:
            raise ValueError("Announcement detail must be at most 10000 characters")
        return value

    @model_validator(mode="after")
    def validate_time_range(self) -> "ConversationAnnouncementRuleBase":
        if self.time_range_type == "permanent":
            self.start_at = None
            self.end_at = None
            return self

        if self.start_at is None:
            raise ValueError("Start time is required for limited announcements")
        if self.end_at is None:
            raise ValueError("End time is required for limited announcements")
        if self.end_at <= self.start_at:
            raise ValueError("End time must be later than start time")
        return self


class ConversationAnnouncementRuleCreate(ConversationAnnouncementRuleBase):
    pass


class ConversationAnnouncementRuleUpdate(ConversationAnnouncementRuleBase):
    pass


class ConversationAnnouncementRuleEnabledPatch(BaseModel):
    enabled: bool


class ConversationAnnouncementRuleReorder(BaseModel):
    ordered_ids: list[int]

    @field_validator("ordered_ids")
    @classmethod
    def non_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("ordered_ids must not be empty")
        return v


class ConversationAnnouncementPublic(BaseModel):
    id: int
    name: str
    summary_html: str
    detail_html: str
    auto_popup: bool
    background_color: AnnouncementBackgroundColor


class ConversationAnnouncementRuleListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    priority: int
    name: str
    enabled: bool
    time_range_type: AnnouncementTimeRangeType
    start_at: datetime | None = None
    end_at: datetime | None = None
    conditions: list[dict]
    auto_popup: bool
    background_color: AnnouncementBackgroundColor
    time_status: AnnouncementTimeStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationAnnouncementRuleResponse(ConversationAnnouncementRuleListItem):
    summary_html: str
    detail_html: str


class ConversationAnnouncementRuleListResponse(PaginatedResponse):
    items: list[ConversationAnnouncementRuleListItem]
