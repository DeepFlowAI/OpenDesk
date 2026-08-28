"""Conversation-level LingoMaster schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ConversationTranslationSettingsUpdate(BaseModel):
    visitor_language_mode: Literal["auto", "manual"] | None = None
    visitor_language: str | None = Field(default=None, min_length=2, max_length=35)
    visitor_translation_enabled: bool | None = None
    agent_translation_enabled: bool | None = None
    visitor_target_mode: Literal["agent", "fixed"] | None = None
    visitor_target_language: str | None = Field(default=None, min_length=2, max_length=35)

    @model_validator(mode="after")
    def validate_language_modes(self) -> "ConversationTranslationSettingsUpdate":
        if self.visitor_language_mode == "manual" and not self.visitor_language:
            raise ValueError("visitor_language is required in manual mode")
        if self.visitor_target_mode == "fixed" and not self.visitor_target_language:
            raise ValueError("visitor_target_language is required in fixed mode")
        return self


class ConversationTranslationSettingsResponse(BaseModel):
    global_enabled: bool
    visitor_language: str | None = None
    visitor_language_source: Literal["browser", "detected", "manual"] | None = None
    visitor_language_locked: bool = False
    visitor_translation_enabled: bool = False
    agent_translation_enabled: bool = False
    visitor_translation_preference: bool = True
    agent_translation_preference: bool = True
    visitor_target_mode: Literal["agent", "fixed"] = "agent"
    visitor_target_language: str | None = None
    resolved_visitor_target_language: str | None = None
    agent_language: str
    updated_by: int | None = None
    updated_at: datetime | None = None
