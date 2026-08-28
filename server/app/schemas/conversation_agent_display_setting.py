"""
Conversation agent display-name setting schemas.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

AgentDisplayMode = Literal["name", "nickname"]


class ConversationAgentDisplaySettingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_mode: AgentDisplayMode = "name"


class ConversationAgentDisplaySettingResponse(ConversationAgentDisplaySettingPayload):
    id: int | None = None
    tenant_id: int | None = None
    configured: bool
    updated_by_id: int | None = None
    updated_by_name: str | None = None
    updated_at: datetime | None = None


class ConversationAgentDisplayTargetResponse(BaseModel):
    display_mode: AgentDisplayMode
    sender_name: str | None = None
