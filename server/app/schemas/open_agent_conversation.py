"""
Schemas for public OpenAgent conversation proxy APIs.
"""
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class OpenAgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    quoted_message_id: int | None = Field(default=None, gt=0)
    client_message_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    last_event_id: str | None = Field(default=None, max_length=128, pattern=r"^r\d+-e\d+$")
    resume: bool = False


class HumanHandoffRequest(BaseModel):
    handoff_payload: dict[str, Any] | None = None


class OpenAgentFeedbackRequest(BaseModel):
    message_id: int = Field(..., gt=0)
    step_id: int = Field(..., gt=0)
    rating: Literal["like", "dislike"]
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("comment", mode="before")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        trimmed = value.strip()
        return trimmed or None


class OpenAgentFeedbackResponse(BaseModel):
    message: dict[str, Any]
    step_id: int
    rating: Literal["like", "dislike"]
    comment: str | None = None
    updated_at: str | None = None
