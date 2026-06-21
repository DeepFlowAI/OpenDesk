"""
Visitor timeout auto-close schemas and validation.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DEFAULT_FIRST_REMINDER_CONTENT = "您已长时间未响应客服对话，稍后将结束对话！"
DEFAULT_CLOSE_REMINDER_CONTENT = "您过长时间未响应客服，系统已结束您的对话，欢迎下次咨询！"


class VisitorTimeoutClosePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    first_normal_minutes: int = Field(default=110, ge=1, le=1440)
    close_normal_minutes: int = Field(default=120, ge=2, le=1440)
    vip_enabled: bool = False
    first_vip_minutes: int = Field(default=110, ge=1, le=1440)
    close_vip_minutes: int = Field(default=120, ge=2, le=1440)
    first_reminder_content: str = Field(default=DEFAULT_FIRST_REMINDER_CONTENT, min_length=1, max_length=500)
    close_reminder_content: str = Field(default=DEFAULT_CLOSE_REMINDER_CONTENT, min_length=1, max_length=500)
    notify_agent: bool = True
    notify_visitor: bool = True

    @field_validator("first_reminder_content", "close_reminder_content", mode="before")
    @classmethod
    def trim_content(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def validate_thresholds(self) -> "VisitorTimeoutClosePayload":
        if self.close_normal_minutes <= self.first_normal_minutes:
            raise ValueError("Auto-close time must be later than the first reminder time")
        if self.vip_enabled and self.close_vip_minutes <= self.first_vip_minutes:
            raise ValueError("VIP auto-close time must be later than the first reminder time")
        if not self.notify_agent and not self.notify_visitor:
            raise ValueError("Please select at least one reminder target")
        return self


class VisitorTimeoutCloseResponse(VisitorTimeoutClosePayload):
    id: int | None = None
    tenant_id: int | None = None
    configured: bool
    version: int
    updated_by_id: int | None = None
    updated_by_name: str | None = None
    updated_at: datetime | None = None
