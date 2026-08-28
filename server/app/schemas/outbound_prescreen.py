"""Schemas for outbound prescreen intent configuration and classification."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OutboundPrescreenIntentDraft(BaseModel):
    intent_key: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=2, max_length=20)
    enabled: bool = False
    similarity_threshold: float = Field(default=0.86, ge=0.50, le=0.99)
    is_system: bool = False
    positive_examples: list[str] = Field(default_factory=list, max_length=200)
    negative_examples: list[str] = Field(default_factory=list, max_length=200)


class OutboundPrescreenConfigDraft(BaseModel):
    intents: list[OutboundPrescreenIntentDraft] = Field(min_length=1, max_length=20)


class OutboundPrescreenIntentResponse(OutboundPrescreenIntentDraft):
    model_config = ConfigDict(from_attributes=True)

    id: int
    intent_key: str
    embeddings_ready: bool
    created_at: datetime
    updated_at: datetime


class OutboundPrescreenConfigResponse(BaseModel):
    intents: list[OutboundPrescreenIntentResponse]


class OutboundPrescreenTestRequest(BaseModel):
    config: OutboundPrescreenConfigDraft
    text: str = Field(min_length=1, max_length=500)
    voiced_ms: int | None = Field(default=None, ge=0)
    voice_match: bool | None = None


class OutboundPrescreenDecision(BaseModel):
    result: str
    auto_hangup: bool
    intent_key: str | None = None
    intent_name: str | None = None
    similarity: float | None = None
    threshold: float | None = None
    matched_positive: str | None = None
    matched_negative: str | None = None
    negative_similarity: float | None = None
    reason: str | None = None
