"""LingoMaster settings schemas."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants.lingomaster import (
    DEFAULT_AGENT_TRANSLATION_PROMPT,
    DEFAULT_VISITOR_TRANSLATION_PROMPT,
)


def validate_translation_prompt(value: str) -> str:
    """Validate a tenant-configurable translation prompt template."""
    normalized = value.strip()
    if not normalized:
        raise ValueError("Translation prompt is required")
    if "{{message}}" not in normalized:
        raise ValueError("Translation prompt must contain {{message}}")
    return normalized


class LingoMasterSettingsUpdate(BaseModel):
    enabled: bool
    visitor_prompt: str = Field(min_length=1, max_length=2000)
    agent_prompt: str = Field(min_length=1, max_length=2000)

    @field_validator("visitor_prompt", "agent_prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return validate_translation_prompt(value)


class LingoMasterSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool = False
    visitor_prompt: str = DEFAULT_VISITOR_TRANSLATION_PROMPT
    agent_prompt: str = DEFAULT_AGENT_TRANSLATION_PROMPT
    default_visitor_prompt: str = DEFAULT_VISITOR_TRANSLATION_PROMPT
    default_agent_prompt: str = DEFAULT_AGENT_TRANSLATION_PROMPT
