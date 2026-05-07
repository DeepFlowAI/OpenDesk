"""
Channel Pydantic schemas
"""
from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, field_validator


DEFAULT_OFFLINE_TITLE = "当前客服不在线"
DEFAULT_OFFLINE_MESSAGE = "您好，当前客服不在线，您可以稍后再来咨询，我们会尽快为您服务。"


def strip_rich_text(value: str) -> str:
    """Strip basic HTML markup to validate rich text emptiness."""
    return re.sub(r"<[^>]*>", "", value).replace("&nbsp;", " ").strip()


class ChannelConfig(BaseModel):
    title: str | None = None
    document_title: str | None = None
    page_bg_color: str | None = None
    header_gradient_start: str | None = None
    header_gradient_end: str | None = None
    header_title_color: str | None = None
    message_area_bg_color: str | None = None
    agent_bubble_bg_color: str | None = None
    agent_bubble_text_color: str | None = None
    agent_bubble_border_color: str | None = None
    agent_bubble_radius: list[float] = [10, 10, 10, 10]
    use_agent_avatar: bool = False
    user_bubble_bg_color: str | None = None
    user_bubble_text_color: str | None = None
    user_bubble_border_color: str | None = None
    user_bubble_radius: list[float] = [10, 10, 10, 10]
    embed_button_bg_color: str | None = None
    embed_button_icon_color: str | None = None
    send_button_bg_color: str | None = None
    input_placeholder: str | None = None
    service_hours_enabled: bool = False
    service_hours_id: int | None = None
    offline_title: str = DEFAULT_OFFLINE_TITLE
    offline_message: str = DEFAULT_OFFLINE_MESSAGE

    @field_validator("agent_bubble_radius", "user_bubble_radius")
    @classmethod
    def validate_radius(cls, v: list[float]) -> list[float]:
        if len(v) != 4:
            raise ValueError("Radius must have exactly 4 values")
        if any(r < 0 for r in v):
            raise ValueError("Radius values must be >= 0")
        return v

    @field_validator("input_placeholder")
    @classmethod
    def validate_placeholder(cls, v: str | None) -> str | None:
        if v and len(v) > 50:
            raise ValueError("Input placeholder must be at most 50 characters")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        if v and len(v) > 32:
            raise ValueError("Title must be at most 32 characters")
        return v

    @field_validator("document_title")
    @classmethod
    def validate_document_title(cls, v: str | None) -> str | None:
        if v and len(v) > 128:
            raise ValueError("Document title must be at most 128 characters")
        return v

    @field_validator("offline_title", mode="before")
    @classmethod
    def normalize_offline_title(cls, v: str | None) -> str:
        if v is None:
            return DEFAULT_OFFLINE_TITLE
        return v

    @field_validator("offline_title")
    @classmethod
    def validate_offline_title(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Offline title is required")
        if len(value) > 64:
            raise ValueError("Offline title must be at most 64 characters")
        return value

    @field_validator("offline_message", mode="before")
    @classmethod
    def normalize_offline_message(cls, v: str | None) -> str:
        if v is None:
            return DEFAULT_OFFLINE_MESSAGE
        return v

    @field_validator("offline_message")
    @classmethod
    def validate_offline_message(cls, v: str) -> str:
        if not strip_rich_text(v):
            raise ValueError("Offline message is required")
        if len(v) > 5000:
            raise ValueError("Offline message must be at most 5000 characters")
        return v


class ChannelAvailability(BaseModel):
    can_start_conversation: bool
    reason: str
    offline_title: str
    offline_message: str
    checked_at: datetime | None = None


class ChannelCreate(BaseModel):
    name: str
    channel_type: str = "web"
    access_mode: str = "url"
    logo_url: str | None = None
    favicon_url: str | None = None
    config: ChannelConfig = ChannelConfig()

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 64:
            raise ValueError("Name must be at most 64 characters")
        return v

    @field_validator("access_mode")
    @classmethod
    def validate_access_mode(cls, v: str) -> str:
        if v not in ("url", "embed"):
            raise ValueError("Access mode must be 'url' or 'embed'")
        return v


class ChannelUpdate(ChannelCreate):
    pass


class ChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    channel_type: str
    access_mode: str = "url"
    logo_url: str | None = None
    favicon_url: str | None = None
    config: ChannelConfig = ChannelConfig()
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChannelPublicResponse(BaseModel):
    """Public channel info for visitor-facing chat widget (no auth required)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    name: str
    channel_type: str
    access_mode: str = "url"
    logo_url: str | None = None
    favicon_url: str | None = None
    config: ChannelConfig = ChannelConfig()
    availability: ChannelAvailability | None = None
    has_conversation_history: bool = False
