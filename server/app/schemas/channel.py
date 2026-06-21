"""
Channel Pydantic schemas
"""
from datetime import datetime
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.open_agent_settings import OpenAgentWelcomeMessage
from app.schemas.welcome_message_rule import WelcomeMessagePublic


DEFAULT_OFFLINE_TITLE = "当前客服不在线"
DEFAULT_OFFLINE_MESSAGE = "您好，当前客服不在线，您可以稍后再来咨询，我们会尽快为您服务。"
DEFAULT_OUTSIDE_SERVICE_HOURS_STRATEGY = "offline_message"
DEFAULT_LEAVE_MESSAGE_PROMPT = "请留下您的问题和联系方式，我们上线后会尽快联系您。"
DEFAULT_QUEUE_MESSAGE = (
    "您已进入人工客服队列。当前排队人数：{{current_queue_count}} 位，请稍候。"
    "客服接入后会立即回复您。"
)
DEFAULT_QUEUE_FULL_MESSAGE = "当前排队人数较多，暂时无法进入排队。您可以稍后再试，或点击留言，我们上线后会尽快联系您。"
DEFAULT_QUEUE_FULL_LEAVE_MESSAGE_BUTTON_LABEL = "留言"
DEFAULT_OPEN_AGENT_BOT_STRATEGY = "always"
DEFAULT_OPEN_AGENT_INPUT_PLACEHOLDER = "输入消息..."
DEFAULT_OPEN_AGENT_HANDOFF_LABEL = "转人工"
DEFAULT_OPEN_AGENT_HANDOFF_AFTER_MESSAGES = 2
DEFAULT_OPEN_AGENT_HANDOFF_BEHAVIOR = "confirm"
OPEN_AGENT_BOT_STRATEGIES = {"always", "service_hours"}
OPEN_AGENT_HANDOFF_BEHAVIORS = {"confirm", "auto"}
OUTSIDE_SERVICE_HOURS_STRATEGIES = {"offline_message", "leave_message"}
MAX_CUSTOM_BUTTONS = 8
ASSIST_PANEL_UNSUPPORTED_PATTERNS = (
    r"<\s*script\b",
    r"\bimport\s*(?:\(|[^;\n]+from\b)",
    r"\b(?:eval|fetch|XMLHttpRequest|WebSocket|EventSource|importScripts)\b",
    r"\b(?:window|document|globalThis|localStorage|sessionStorage|indexedDB|navigator|location|parent|top|opener)\b",
    r"\b(?:constructor|__proto__|prototype)\b",
)
ASSIST_PANEL_UNSUPPORTED_CASE_SENSITIVE_PATTERNS = (
    r"\bFunction\b",
)


def strip_rich_text(value: str) -> str:
    """Strip basic HTML markup to validate rich text emptiness."""
    return re.sub(r"<[^>]*>", "", value).replace("&nbsp;", " ").strip()


class ChannelCustomButton(BaseModel):
    label: str
    action_type: Literal["send_message", "link"] = "send_message"
    message: str | None = None
    url: str | None = None
    enabled: bool = True

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, v: str | None) -> str:
        if v is None:
            return ""
        return v.strip()

    @field_validator("message", "url", mode="before")
    @classmethod
    def normalize_optional_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        value = v.strip()
        return value or None

    @field_validator("label")
    @classmethod
    def validate_label(cls, v: str) -> str:
        if not v:
            raise ValueError("Custom button label is required")
        if len(v) > 16:
            raise ValueError("Custom button label must be at most 16 characters")
        return v

    @model_validator(mode="after")
    def validate_action_payload(self) -> "ChannelCustomButton":
        if self.action_type == "send_message":
            if not self.message:
                raise ValueError("Custom button message is required")
            if len(self.message) > 500:
                raise ValueError("Custom button message must be at most 500 characters")
            self.url = None
            return self

        if not self.url:
            raise ValueError("Custom button URL is required")
        if len(self.url) > 512:
            raise ValueError("Custom button URL must be at most 512 characters")
        if not re.match(r"^https?://", self.url, flags=re.IGNORECASE):
            raise ValueError("Custom button URL must start with http:// or https://")
        self.message = None
        return self


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
    outside_service_hours_strategy: str = DEFAULT_OUTSIDE_SERVICE_HOURS_STRATEGY
    offline_title: str = DEFAULT_OFFLINE_TITLE
    offline_message: str = DEFAULT_OFFLINE_MESSAGE
    leave_message_prompt: str = DEFAULT_LEAVE_MESSAGE_PROMPT
    queue_message: str = DEFAULT_QUEUE_MESSAGE
    queue_full_message: str = DEFAULT_QUEUE_FULL_MESSAGE
    queue_full_show_leave_message_button: bool = True
    queue_full_leave_message_button_label: str = DEFAULT_QUEUE_FULL_LEAVE_MESSAGE_BUTTON_LABEL
    open_agent_enabled: bool = False
    open_agent_agent_id: int | None = None
    open_agent_agent_name: str | None = None
    open_agent_bot_strategy: str = DEFAULT_OPEN_AGENT_BOT_STRATEGY
    open_agent_bot_service_hours_id: int | None = None
    open_agent_avatar_url: str | None = None
    open_agent_input_placeholder: str | None = None
    open_agent_handoff_enabled: bool = True
    open_agent_handoff_label: str = DEFAULT_OPEN_AGENT_HANDOFF_LABEL
    open_agent_handoff_after_messages: int = DEFAULT_OPEN_AGENT_HANDOFF_AFTER_MESSAGES
    open_agent_handoff_behavior: str = DEFAULT_OPEN_AGENT_HANDOFF_BEHAVIOR
    open_agent_custom_buttons_enabled: bool = False
    open_agent_custom_buttons: list[ChannelCustomButton] = Field(default_factory=list)
    human_custom_buttons_enabled: bool = False
    human_custom_buttons: list[ChannelCustomButton] = Field(default_factory=list)
    assist_panel_enabled: bool = False
    assist_panel_title: str | None = None
    assist_panel_react_code: str | None = None
    assist_panel_config: dict[str, Any] = Field(default_factory=dict)

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

    @field_validator("outside_service_hours_strategy")
    @classmethod
    def validate_outside_service_hours_strategy(cls, v: str) -> str:
        if v not in OUTSIDE_SERVICE_HOURS_STRATEGIES:
            raise ValueError("Outside service hours strategy is invalid")
        return v

    @field_validator("open_agent_agent_name", "open_agent_avatar_url", "open_agent_input_placeholder", mode="before")
    @classmethod
    def normalize_optional_open_agent_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        value = v.strip()
        return value or None

    @field_validator("open_agent_agent_name")
    @classmethod
    def validate_open_agent_agent_name(cls, v: str | None) -> str | None:
        if v and len(v) > 128:
            raise ValueError("OpenAgent agent name must be at most 128 characters")
        return v

    @field_validator("open_agent_avatar_url")
    @classmethod
    def validate_open_agent_avatar_url(cls, v: str | None) -> str | None:
        if v and len(v) > 512:
            raise ValueError("OpenAgent avatar URL must be at most 512 characters")
        return v

    @field_validator("open_agent_input_placeholder")
    @classmethod
    def validate_open_agent_input_placeholder(cls, v: str | None) -> str | None:
        if v and len(v) > 50:
            raise ValueError("OpenAgent input placeholder must be at most 50 characters")
        return v

    @field_validator("open_agent_bot_strategy")
    @classmethod
    def validate_open_agent_bot_strategy(cls, v: str) -> str:
        if v not in OPEN_AGENT_BOT_STRATEGIES:
            raise ValueError("OpenAgent bot strategy is invalid")
        return v

    @field_validator("open_agent_handoff_behavior")
    @classmethod
    def validate_open_agent_handoff_behavior(cls, v: str) -> str:
        if v not in OPEN_AGENT_HANDOFF_BEHAVIORS:
            raise ValueError("OpenAgent handoff behavior is invalid")
        return v

    @field_validator("open_agent_custom_buttons", "human_custom_buttons")
    @classmethod
    def validate_custom_button_count(cls, v: list[ChannelCustomButton]) -> list[ChannelCustomButton]:
        if len(v) > MAX_CUSTOM_BUTTONS:
            raise ValueError("Custom button group must contain at most 8 buttons")
        return v

    @field_validator("assist_panel_title", "assist_panel_react_code", mode="before")
    @classmethod
    def normalize_optional_assist_panel_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        value = v.strip()
        return value or None

    @field_validator("assist_panel_title")
    @classmethod
    def validate_assist_panel_title(cls, v: str | None) -> str | None:
        if v and len(v) > 40:
            raise ValueError("Assist panel title must be at most 40 characters")
        return v

    @field_validator("assist_panel_react_code")
    @classmethod
    def validate_assist_panel_react_code(cls, v: str | None) -> str | None:
        if not v:
            return v
        if not re.search(r"\bexport\s+default\b", v):
            raise ValueError("Assist panel React code must export a default component")
        for pattern in ASSIST_PANEL_UNSUPPORTED_PATTERNS:
            if re.search(pattern, v, flags=re.IGNORECASE):
                raise ValueError("Assist panel React code uses unsupported capabilities")
        for pattern in ASSIST_PANEL_UNSUPPORTED_CASE_SENSITIVE_PATTERNS:
            if re.search(pattern, v):
                raise ValueError("Assist panel React code uses unsupported capabilities")
        return v

    @field_validator("open_agent_handoff_label", mode="before")
    @classmethod
    def normalize_open_agent_handoff_label(cls, v: str | None) -> str:
        if v is None:
            return DEFAULT_OPEN_AGENT_HANDOFF_LABEL
        return v.strip()

    @model_validator(mode="after")
    def validate_open_agent_config(self) -> "ChannelConfig":
        if not self.open_agent_enabled:
            if self.assist_panel_enabled and not self.assist_panel_react_code:
                raise ValueError("Assist panel React code is required when enabled")
            return self

        if self.open_agent_agent_id is None:
            raise ValueError("OpenAgent agent is required when bot is enabled")

        if self.open_agent_bot_strategy == "service_hours" and self.open_agent_bot_service_hours_id is None:
            raise ValueError("OpenAgent bot service hours is required for service-hours strategy")

        if self.open_agent_handoff_enabled:
            if not self.open_agent_handoff_label:
                raise ValueError("OpenAgent handoff label is required")
            if len(self.open_agent_handoff_label) > 16:
                raise ValueError("OpenAgent handoff label must be at most 16 characters")
            if not 1 <= self.open_agent_handoff_after_messages <= 99:
                raise ValueError("OpenAgent handoff threshold must be between 1 and 99")

        if self.assist_panel_enabled and not self.assist_panel_react_code:
            raise ValueError("Assist panel React code is required when enabled")

        return self

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

    @field_validator("leave_message_prompt", mode="before")
    @classmethod
    def normalize_leave_message_prompt(cls, v: str | None) -> str:
        if v is None:
            return DEFAULT_LEAVE_MESSAGE_PROMPT
        return v

    @field_validator("leave_message_prompt")
    @classmethod
    def validate_leave_message_prompt(cls, v: str) -> str:
        if not strip_rich_text(v):
            raise ValueError("Leave message prompt is required")
        if len(v) > 5000:
            raise ValueError("Leave message prompt must be at most 5000 characters")
        return v

    @field_validator("queue_message", mode="before")
    @classmethod
    def normalize_queue_message(cls, v: str | None) -> str:
        if v is None:
            return DEFAULT_QUEUE_MESSAGE
        return v

    @field_validator("queue_message")
    @classmethod
    def validate_queue_message(cls, v: str) -> str:
        if not strip_rich_text(v):
            raise ValueError("Queue message is required")
        if len(v) > 5000:
            raise ValueError("Queue message must be at most 5000 characters")
        return v

    @field_validator("queue_full_message", mode="before")
    @classmethod
    def normalize_queue_full_message(cls, v: str | None) -> str:
        if v is None:
            return DEFAULT_QUEUE_FULL_MESSAGE
        return v

    @field_validator("queue_full_message")
    @classmethod
    def validate_queue_full_message(cls, v: str) -> str:
        if not strip_rich_text(v):
            raise ValueError("Queue full message is required")
        if len(v) > 5000:
            raise ValueError("Queue full message must be at most 5000 characters")
        return v

    @field_validator("queue_full_leave_message_button_label", mode="before")
    @classmethod
    def normalize_queue_full_leave_message_button_label(cls, v: str | None) -> str:
        if v is None:
            return DEFAULT_QUEUE_FULL_LEAVE_MESSAGE_BUTTON_LABEL
        return v.strip()

    @model_validator(mode="after")
    def validate_queue_full_button_config(self) -> "ChannelConfig":
        if not self.queue_full_show_leave_message_button:
            return self
        if not self.queue_full_leave_message_button_label:
            raise ValueError("Queue full leave-message button label is required")
        if len(self.queue_full_leave_message_button_label) > 16:
            raise ValueError("Queue full leave-message button label must be at most 16 characters")
        return self


class ChannelAvailability(BaseModel):
    can_start_conversation: bool
    reason: str
    offline_title: str
    offline_message: str
    outside_service_hours_strategy: str = DEFAULT_OUTSIDE_SERVICE_HOURS_STRATEGY
    leave_message_prompt: str = DEFAULT_LEAVE_MESSAGE_PROMPT
    queue_message: str = DEFAULT_QUEUE_MESSAGE
    queue_full_message: str = DEFAULT_QUEUE_FULL_MESSAGE
    queue_full_show_leave_message_button: bool = True
    queue_full_leave_message_button_label: str = DEFAULT_QUEUE_FULL_LEAVE_MESSAGE_BUTTON_LABEL
    current_queue_count: int | None = None
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
    channel_key: str
    channel_key_version: int = 1
    public_access_enabled: bool = True
    key_rotated_at: datetime | None = None
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

    channel_key: str
    name: str
    channel_type: str
    access_mode: str = "url"
    logo_url: str | None = None
    favicon_url: str | None = None
    config: ChannelConfig = ChannelConfig()
    availability: ChannelAvailability | None = None
    has_conversation_history: bool = False
    welcome_message: WelcomeMessagePublic | None = None
    open_agent_welcome_message: OpenAgentWelcomeMessage | None = None
