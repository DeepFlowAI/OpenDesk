from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_EVENTS_PER_BATCH = 100
SCHEMA_MAX_EVENTS_PER_BATCH = 200
MAX_KEYS_PER_DICT = 32
SCHEMA_MAX_KEYS_PER_DICT = 64
SCHEMA_MAX_VALUE_CHARS = 1024
MAX_KEY_CHARS = 64
MAX_VALUE_CHARS = 256

TelemetryLevel = Literal["info", "warn", "error"]


class TelemetryCommon(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str = Field(..., min_length=1, max_length=64)
    device_id: str = Field(..., min_length=1, max_length=64)
    user_id: str | None = Field(None, max_length=128)
    release: str | None = Field(None, max_length=32)
    url: str | None = Field(None, max_length=1024)
    user_agent: str | None = Field(None, max_length=512)
    network_type: str | None = Field(None, max_length=32)
    viewport: str | None = Field(None, max_length=32)
    sdk_name: str | None = Field(None, max_length=32)
    sdk_version: str | None = Field(None, max_length=32)
    ts_offset_ms: int | None = None


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    ts: int = Field(..., description="Client epoch milliseconds")
    level: TelemetryLevel = "info"
    trace_id: str | None = Field(None, max_length=64)
    conversation_external_id: str | None = Field(None, max_length=128)
    request_id: str | None = Field(None, max_length=64)
    client_message_id: str | None = Field(None, max_length=64)
    props: dict[str, str | int | float | bool] | None = Field(
        default=None,
        max_length=SCHEMA_MAX_KEYS_PER_DICT,
    )
    metrics: dict[str, int | float] | None = Field(
        default=None,
        max_length=SCHEMA_MAX_KEYS_PER_DICT,
    )

    @model_validator(mode="after")
    def _bound_string_value_lengths(self) -> "TelemetryEvent":
        if not self.props:
            return self
        for key, value in self.props.items():
            if isinstance(value, str) and len(value) > SCHEMA_MAX_VALUE_CHARS:
                raise ValueError(
                    f"props[{key[:32]!r}] value exceeds {SCHEMA_MAX_VALUE_CHARS} chars"
                )
        return self


class TelemetryBatchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    common: TelemetryCommon
    events: list[TelemetryEvent] = Field(
        default_factory=list,
        max_length=SCHEMA_MAX_EVENTS_PER_BATCH,
    )


class TelemetryBatchResponse(BaseModel):
    accepted: int
    dropped: int
