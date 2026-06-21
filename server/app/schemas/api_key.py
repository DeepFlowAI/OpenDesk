"""
Schemas for API Key management and Open API context tokens.
"""
import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=40)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Name must be at least 2 characters")
        if len(normalized) > 40:
            raise ValueError("Name must be at most 40 characters")
        return normalized


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    masked_key: str
    key_version: int
    is_active: bool
    disabled_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApiKeySecretResponse(BaseModel):
    record: ApiKeyResponse
    api_key: str


class ContextTokenRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    channel_key: str = Field(min_length=1, max_length=64, alias="channelKey")
    customer: dict | None = None
    session_summary: dict | None = Field(default=None, alias="sessionSummary")
    business_records: list[dict] | None = Field(default=None, max_length=5, alias="businessRecords")
    expires_seconds: int | None = Field(default=None, ge=300, le=1800, alias="expiresSeconds")

    @field_validator("customer", "session_summary")
    @classmethod
    def validate_context_payload_size(cls, value: dict | None, info):
        if value is None:
            return value
        try:
            encoded = json.dumps(value, ensure_ascii=False)
        except TypeError as exc:
            raise ValueError("Context payload must be JSON serializable") from exc
        if len(encoded.encode("utf-8")) > 16 * 1024:
            raise ValueError("Context payload must be at most 16KB")
        if info.field_name == "session_summary":
            fields = value.get("fields")
            if fields is not None:
                if not isinstance(fields, dict):
                    raise ValueError("sessionSummary.fields must be an object")
                if len(fields) > 50:
                    raise ValueError("sessionSummary.fields must contain at most 50 fields")
        return value


class ContextTokenResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    context_token: str = Field(alias="contextToken")
    expires_in: int = Field(alias="expiresIn")
