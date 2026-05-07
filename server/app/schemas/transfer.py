"""
Conversation transfer Pydantic schemas
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TransferTarget(BaseModel):
    """Candidate employee shown in the transfer modal."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_name: str | None = None
    job_number: str | None = None
    avatar: str | None = None
    online_status: Literal["online", "busy", "offline"]
    current_count: int = 0
    max_concurrent: int = 10


class TransferTargetListResponse(BaseModel):
    items: list[TransferTarget]
    total: int


class TransferConversationRequest(BaseModel):
    target_agent_id: int = Field(..., gt=0)
