"""
Schemas for workspace user statistic display settings and counts.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ConversationUserStatFieldSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    show_session_count: bool = True
    show_call_count: bool = True
    show_unresolved_ticket_count: bool = True
    show_total_ticket_count: bool = True


class ConversationUserStatFieldSettingsResponse(ConversationUserStatFieldSettingsPayload):
    id: int | None = None
    tenant_id: int | None = None
    configured: bool
    updated_by_id: int | None = None
    updated_by_name: str | None = None
    updated_at: datetime | None = None


class ConversationUserStatisticItem(BaseModel):
    key: Literal["calls", "sessions", "tickets"]
    value: int | None = None
    unresolved_value: int | None = None
    total_value: int | None = None


class ConversationUserStatisticsResponse(BaseModel):
    conversation_id: int
    user_id: int | None = None
    items: list[ConversationUserStatisticItem]
