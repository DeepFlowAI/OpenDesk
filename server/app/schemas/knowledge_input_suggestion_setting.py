"""
Knowledge input suggestion setting schemas.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeInputSuggestionSettingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    trigger_length: int = Field(default=2, ge=1, le=10)


class KnowledgeInputSuggestionSettingResponse(KnowledgeInputSuggestionSettingPayload):
    id: int | None = None
    tenant_id: int | None = None
    configured: bool
    updated_by_id: int | None = None
    updated_by_name: str | None = None
    updated_at: datetime | None = None
