"""
Satisfaction survey configuration schemas and validation.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.base import PaginatedResponse


RatingMode = Literal["stars", "text", "emoji"]
RemarkRequirement = Literal["hidden", "optional", "required"]
TagSelectionMode = Literal["single", "multiple"]


class SatisfactionRatingOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = ""
    enabled: bool = True
    name: str = ""
    is_default: bool = False
    score: int = Field(gt=0)
    labels: list[str] = Field(default_factory=list)
    remark_requirement: RemarkRequirement = "optional"

    @field_validator("key", "name")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def validate_name_length(cls, value: str) -> str:
        if len(value) > 32:
            raise ValueError("Rating option name must be at most 32 characters")
        return value

    @field_validator("labels")
    @classmethod
    def normalize_labels(cls, value: list[str]) -> list[str]:
        labels: list[str] = []
        for label in value:
            normalized = str(label).strip()
            if normalized and normalized not in labels:
                labels.append(normalized[:32])
        return labels[:20]


class SatisfactionTypeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    section_title: str = ""
    popup_title: str = ""
    rating_mode: RatingMode = "stars"
    rating_options: list[SatisfactionRatingOption] = Field(default_factory=list)
    tag_selection_mode: TagSelectionMode = "multiple"
    remark_enabled: bool = True
    remark_placeholder: str = "欢迎补充更多反馈"

    @field_validator("section_title", "popup_title", "remark_placeholder")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_enabled_settings(self) -> "SatisfactionTypeSettings":
        if not self.enabled:
            return self
        validate_satisfaction_type_settings(self)
        return self


class ServiceSatisfactionSettings(SatisfactionTypeSettings):
    show_resolution: bool = True


class ProductSatisfactionSettings(SatisfactionTypeSettings):
    pass


class SatisfactionTriggerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_invite: bool = True
    user_initiated: bool = False
    session_end_invite: bool = True
    limit_one_response_per_type: bool = True

    @model_validator(mode="before")
    @classmethod
    def normalize_trigger_fields(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if "agent_invite" in data or "user_initiated" in data or "session_end_invite" in data:
            return data
        legacy_keys = {"proactive_invitation", "chat_popup", "popup_timing"}
        if not any(key in data for key in legacy_keys):
            return data

        proactive = bool(data.get("proactive_invitation"))
        chat_popup = bool(data.get("chat_popup"))
        timing = str(data.get("popup_timing") or "conversation_end")
        return {
            "agent_invite": proactive,
            "user_initiated": chat_popup and timing in {"user_initiated", "first_agent_reply"},
            "session_end_invite": chat_popup and timing == "conversation_end",
            "limit_one_response_per_type": data.get("limit_one_response_per_type", True),
        }

    @model_validator(mode="after")
    def validate_trigger(self) -> "SatisfactionTriggerSettings":
        if not self.agent_invite and not self.user_initiated and not self.session_end_invite:
            raise ValueError("Please select at least one trigger mode")
        return self


class SatisfactionSurveyConfigPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    enabled: bool = True
    triggers: SatisfactionTriggerSettings
    service: ServiceSatisfactionSettings
    product: ProductSatisfactionSettings

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Please enter a survey name")
        if len(name) > 64:
            raise ValueError("Survey name must be at most 64 characters")
        return name

    @model_validator(mode="after")
    def validate_enabled_types(self) -> "SatisfactionSurveyConfigPayload":
        if not self.service.enabled and not self.product.enabled:
            raise ValueError("Please enable at least one satisfaction type")
        return self


class SatisfactionSurveyConfigResponse(SatisfactionSurveyConfigPayload):
    id: int | None = None
    tenant_id: int | None = None
    configured: bool
    current_version: int | None = None
    updated_by_id: int | None = None
    updated_by_name: str | None = None
    updated_at: datetime | None = None


class SatisfactionSurveyEnabledPatch(BaseModel):
    enabled: bool


class SatisfactionSurveyVersionListItem(BaseModel):
    id: int
    version: int
    is_current: bool
    survey_types: list[str]
    rating_modes: dict[str, str]
    trigger_modes: list[str]
    updated_by_id: int | None = None
    updated_by_name: str | None = None
    published_at: datetime | None = None


class SatisfactionSurveyVersionListResponse(PaginatedResponse):
    items: list[SatisfactionSurveyVersionListItem]
    current_version: int | None = None


class SatisfactionSurveyVersionDetail(BaseModel):
    id: int
    version: int
    is_current: bool
    snapshot: SatisfactionSurveyConfigPayload
    updated_by_id: int | None = None
    updated_by_name: str | None = None
    published_at: datetime | None = None


def validate_satisfaction_type_settings(settings: SatisfactionTypeSettings) -> None:
    if not settings.section_title:
        raise ValueError("Please enter a section title")
    if len(settings.section_title) > 32:
        raise ValueError("Section title must be at most 32 characters")
    if not settings.popup_title:
        raise ValueError("Please enter a popup title")
    if len(settings.popup_title) > 50:
        raise ValueError("Popup title must be at most 50 characters")
    if len(settings.remark_placeholder) > 50:
        raise ValueError("Remark placeholder must be at most 50 characters")

    enabled_options = [option for option in settings.rating_options if option.enabled]
    if len(enabled_options) < 2:
        raise ValueError("Please enable at least 2 rating options")

    names = [option.name for option in enabled_options]
    if any(not name for name in names):
        raise ValueError("Rating option name is required")
    if len(set(names)) != len(names):
        raise ValueError("Rating option names must be unique")

    default_options = [option for option in settings.rating_options if option.is_default]
    if len(default_options) > 1:
        raise ValueError("Only one default rating option is allowed")
    if default_options and not default_options[0].enabled:
        raise ValueError("The default option must be enabled")
