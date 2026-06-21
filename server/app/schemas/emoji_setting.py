"""
Emoji setting schemas and validation.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_EMOJI_ITEMS = 48


class EmojiItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emoji: str
    name: str
    name_en: str | None = None
    alias: str | None = None
    alias_en: str | None = None
    keywords: list[str] = Field(default_factory=list)

    @field_validator("emoji", "name", "name_en", "alias", "alias_en", mode="before")
    @classmethod
    def trim_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("emoji")
    @classmethod
    def validate_emoji(cls, value: str) -> str:
        if not value:
            raise ValueError("Emoji is required")
        if len(value) > 16:
            raise ValueError("Emoji value is too long")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value:
            raise ValueError("Emoji name is required")
        if len(value) > 32:
            raise ValueError("Emoji name must be at most 32 characters")
        return value

    @field_validator("name_en", "alias", "alias_en")
    @classmethod
    def validate_optional_text_length(cls, value: str | None) -> str | None:
        if value and len(value) > 64:
            raise ValueError("Emoji text fields must be at most 64 characters")
        return value

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        keywords: list[str] = []
        for item in value:
            normalized = str(item).strip()
            if normalized and normalized not in keywords:
                keywords.append(normalized[:32])
        return keywords[:20]


class EmojiSettingTargetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    emojis: list[EmojiItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_emojis(self) -> "EmojiSettingTargetPayload":
        if len(self.emojis) > MAX_EMOJI_ITEMS:
            raise ValueError("You can select up to 48 emojis")
        values = [item.emoji for item in self.emojis]
        if len(values) != len(set(values)):
            raise ValueError("Duplicate emojis are not allowed")
        if self.enabled and not self.emojis:
            raise ValueError("Please select at least one emoji")
        return self


class EmojiSettingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: EmojiSettingTargetPayload
    agent: EmojiSettingTargetPayload


class EmojiSettingResponse(EmojiSettingPayload):
    id: int | None = None
    tenant_id: int | None = None
    configured: bool
    updated_by_id: int | None = None
    updated_by_name: str | None = None
    updated_at: datetime | None = None


class EmojiTargetConfigResponse(BaseModel):
    target: Literal["user", "agent"]
    configured: bool
    enabled: bool
    emojis: list[EmojiItem]
    updated_at: datetime | None = None
