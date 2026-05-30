"""
Schemas for public OpenAgent conversation proxy APIs.
"""
from typing import Any

from pydantic import BaseModel, Field


class OpenAgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    client_message_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    last_event_id: str | None = Field(default=None, max_length=128, pattern=r"^r\d+-e\d+$")
    resume: bool = False


class HumanHandoffRequest(BaseModel):
    handoff_payload: dict[str, Any] | None = None
