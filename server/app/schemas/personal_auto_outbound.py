"""Schemas for the agent-owned personal auto-outbound workflow."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.voice_flow import AudioAssetResponse

RecordingType = Literal["opening", "closing"]


class PersonalOutboundTaskOption(BaseModel):
    id: int
    name: str
    callable_count: int


class PersonalOutboundPhoneOption(BaseModel):
    id: str
    phone_number: str


class PersonalOutboundGroupOption(BaseModel):
    id: int
    name: str
    ready_agent_count: int = 0


class PersonalOutboundRecordingResponse(BaseModel):
    recording_type: RecordingType
    audio: AudioAssetResponse
    script_text: str | None = None


class PersonalOpeningScriptUpdate(BaseModel):
    script_text: str | None = Field(default=None, max_length=200)


class PersonalAutoOutboundConfigResponse(BaseModel):
    tasks: list[PersonalOutboundTaskOption]
    phone_numbers: list[PersonalOutboundPhoneOption]
    fallback_groups: list[PersonalOutboundGroupOption]
    recordings: dict[str, PersonalOutboundRecordingResponse]
    has_enabled_prescreen_intents: bool


class PersonalAutoOutboundStartRequest(BaseModel):
    task_id: int
    outbound_phone_number_id: str
    fallback_group_id: int | None = None
    configured_concurrency: int = Field(default=4, ge=1, le=10)


class PersonalAutoOutboundSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    outbound_phone_number_id: str
    fallback_group_id: int | None
    opening_audio_asset_id: int
    closing_audio_asset_id: int
    opening_script_text: str | None = None
    configured_concurrency: int
    effective_concurrency: int
    status: str
    pause_reason: str | None
    started_at: datetime
    paused_at: datetime | None
    stopping_at: datetime | None
    stopped_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PersonalAutoOutboundMetrics(BaseModel):
    ringing_current: int = 0
    ringing_total: int = 0
    screening_current: int = 0
    screening_total: int = 0
    human_current: int = 0
    human_total: int = 0
    filtered_current: int = 0
    filtered_total: int = 0


class PersonalAutoOutboundCallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_id: int
    call_record_id: int | None
    target_name: str | None = None
    phone_number: str
    stage: str
    prescreen_result: str | None
    intent_key: str | None
    similarity: float | None
    degraded_reason: str | None
    assigned_agent_id: int | None
    assignment_type: str | None
    hangup_reason: str | None
    last_utterance: str | None = None
    started_at: datetime
    answered_at: datetime | None
    ended_at: datetime | None


class PersonalAutoOutboundSessionEnvelope(BaseModel):
    session: PersonalAutoOutboundSessionResponse | None
    metrics: PersonalAutoOutboundMetrics = Field(default_factory=PersonalAutoOutboundMetrics)
    calls: list[PersonalAutoOutboundCallResponse] = Field(default_factory=list)
    gate_reason: str | None = None
