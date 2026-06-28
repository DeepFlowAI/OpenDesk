"""
Conversation read-status setting schemas.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ConversationReadStatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_workspace_enabled: bool = True
    web_sdk_enabled: bool = True


class ConversationReadStatusResponse(ConversationReadStatusPayload):
    id: int | None = None
    tenant_id: int | None = None
    configured: bool
    updated_by_id: int | None = None
    updated_by_name: str | None = None
    updated_at: datetime | None = None


class ConversationReadStatusTargetResponse(BaseModel):
    target: Literal["agent_workspace", "web_sdk"]
    configured: bool
    enabled: bool
    updated_at: datetime | None = None


class ConversationReadStatusPublicResponse(BaseModel):
    web_sdk_enabled: bool = True
