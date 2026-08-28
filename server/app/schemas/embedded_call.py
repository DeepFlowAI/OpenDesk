"""Schemas for embedded call integrations and short-lived authentication."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EmbeddedCallIntegrationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    allowed_origins: list[str] = Field(..., min_length=1, max_length=20)
    is_enabled: bool = False


class EmbeddedCallIntegrationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    allowed_origins: list[str] | None = Field(None, min_length=1, max_length=20)
    is_enabled: bool | None = None


class EmbeddedCallIntegrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    name: str
    integration_key: str
    allowed_origins: list[str]
    is_enabled: bool
    secret_last_four: str
    secret_rotated_at: datetime
    previous_secret_last_four: str | None = None
    previous_secret_expires_at: datetime | None = None
    last_used_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error_code: str | None = None
    created_at: datetime
    updated_at: datetime


class EmbeddedCallIntegrationListResponse(BaseModel):
    items: list[EmbeddedCallIntegrationResponse]
    total: int


class EmbeddedCallIntegrationSecretResponse(BaseModel):
    integration: EmbeddedCallIntegrationResponse
    server_secret: str


class EmbeddedCallSecretRotateRequest(BaseModel):
    grace_period_hours: int = Field(24, ge=0, le=24)


class EmbedSignatureRequest(BaseModel):
    integration_key: str = Field(..., min_length=1, max_length=48)
    employee_identifier: str = Field(..., min_length=1, max_length=128)
    origin: str = Field(..., min_length=1, max_length=512)
    nonce: str = Field(..., min_length=16, max_length=128)


class EmbedSignatureResponse(BaseModel):
    embed_signature: str
    expires_in: int


class EmbedSessionRequest(BaseModel):
    embed_signature: str = Field(..., min_length=32, max_length=256)
    origin: str = Field(..., min_length=1, max_length=512)
    nonce: str = Field(..., min_length=16, max_length=128)
    instance_id: str = Field(..., min_length=8, max_length=128)


class EmbeddedAgentBrief(BaseModel):
    name: str
    display_name: str | None = None
    default_language: str
    permissions: list[str]


class EmbedSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    integration_key: str
    agent: EmbeddedAgentBrief


class EmbeddedCallDialRequest(BaseModel):
    number: str = Field(..., min_length=1, max_length=64)
    outbound_number_id: str = Field(..., min_length=1, max_length=64)
    external_context: dict | None = None
    custom_business_info: str | None = Field(None, max_length=32768)
    idempotency_key: str | None = Field(None, min_length=1, max_length=128)


class EmbeddedCallCommandResponse(BaseModel):
    command_id: str
    call_id: str | None = None
    status: str


class EmbeddedCallControlRequest(BaseModel):
    instance_id: str = Field(..., min_length=8, max_length=128)
    surface: str = Field("embedded_call", min_length=1, max_length=32)
    lease_token: str | None = Field(None, min_length=16, max_length=128)


class EmbeddedCallControlResponse(BaseModel):
    is_owner: bool
    owner_instance_id: str | None = None
    owner_surface: str | None = None
    lease_token: str | None = None
    expires_in: int
