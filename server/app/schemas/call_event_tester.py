"""Schemas for the per-user call event test receiver."""
from typing import Any

from pydantic import BaseModel, Field


class CallEventTesterReceiverResponse(BaseModel):
    token: str
    webhook_path: str
    has_secret: bool
    created_at: str
    expires_in_seconds: int


class CallEventTesterSecretRequest(BaseModel):
    # Empty or null clears the secret so every delivery is accepted.
    secret: str | None = Field(default=None, max_length=512)


class CallEventTesterEvent(BaseModel):
    seq: int
    received_at: str
    delivery_id: str | None = None
    user_agent: str | None = None
    secret_checked: bool
    secret_ok: bool
    duplicate: bool
    body: Any = None


class CallEventTesterEventListResponse(BaseModel):
    items: list[CallEventTesterEvent]
    last_seq: int
