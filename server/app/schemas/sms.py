"""
SMS schemas: platform signature/template/grant APIs and tenant-side views.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import PaginatedResponse

# ---------------------------------------------------------------------------
# Shared enums-as-literals (kept as str sets in models/sms.py)
# ---------------------------------------------------------------------------

SMS_PROVIDERS = {"aliyun"}
SMS_TEMPLATE_TYPES = {"notify", "promo"}
SMS_ENTITY_STATUSES = {"enabled", "disabled"}
SMS_SEND_STATUSES = {"pending", "submitted", "delivered", "failed"}


# ---------------------------------------------------------------------------
# Signature (platform API)
# ---------------------------------------------------------------------------


class SmsSignatureCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    provider: str = Field(min_length=1, max_length=32)
    provider_sign_name: str = Field(min_length=1, max_length=128)
    status: str = Field(default="enabled")


class SmsSignatureUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    provider_sign_name: str | None = Field(default=None, min_length=1, max_length=128)
    status: str | None = None


class SmsSignatureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    provider: str
    provider_sign_name: str
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SmsSignatureListResponse(PaginatedResponse):
    items: list[SmsSignatureResponse]


# ---------------------------------------------------------------------------
# Template (platform API)
# ---------------------------------------------------------------------------


class SmsVariableDef(BaseModel):
    key: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=32)
    required: bool = False
    max_length: int | None = Field(default=None, ge=1, le=100)


class SmsTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: str = Field(default="notify")
    signature_id: int
    body: str = Field(min_length=1, max_length=500)
    variables: list[SmsVariableDef] = Field(default_factory=list)
    provider: str = Field(min_length=1, max_length=32)
    provider_template_code: str = Field(min_length=1, max_length=64)
    status: str = Field(default="enabled")


class SmsTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    type: str | None = None
    signature_id: int | None = None
    body: str | None = Field(default=None, min_length=1, max_length=500)
    variables: list[SmsVariableDef] | None = None
    provider: str | None = Field(default=None, min_length=1, max_length=32)
    provider_template_code: str | None = Field(default=None, min_length=1, max_length=64)
    status: str | None = None


class SmsTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    signature_id: int
    signature_name: str | None = None
    body: str
    variables: list[SmsVariableDef]
    provider: str
    provider_template_code: str
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SmsTemplateListResponse(PaginatedResponse):
    items: list[SmsTemplateResponse]


# ---------------------------------------------------------------------------
# Tenant grants (platform API)
# ---------------------------------------------------------------------------


class SmsTemplateGrantBatch(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    template_ids: list[int] = Field(min_length=1, max_length=100)


class SmsTemplateGrantResult(BaseModel):
    granted: list[int]
    skipped: list[int]


class SmsTemplateRevokeResult(BaseModel):
    revoked: list[int]


class SmsGrantedTemplateItem(BaseModel):
    template_id: int
    name: str
    type: str
    sign_name: str
    body: str
    variables: list[SmsVariableDef]
    availability: str  # available | template_disabled
    granted_at: datetime | None = None
    updated_at: datetime | None = None


class SmsGrantedTemplateListResponse(BaseModel):
    items: list[SmsGrantedTemplateItem]


# ---------------------------------------------------------------------------
# Tenant-side views (admin console / workspace)
# ---------------------------------------------------------------------------


class SmsTenantTemplateItem(BaseModel):
    id: int
    name: str
    sign_name: str
    type: str
    variables: list[SmsVariableDef]
    status: str  # available | unavailable
    updated_at: datetime | None = None


class SmsTenantTemplateListResponse(PaginatedResponse):
    items: list[SmsTenantTemplateItem]


class SmsTenantTemplateDetail(SmsTenantTemplateItem):
    body: str


# ---------------------------------------------------------------------------
# Workspace single-send
# ---------------------------------------------------------------------------

CN_MOBILE_PATTERN = r"^1[3-9]\d{9}$"


class SmsWorkspaceTemplateItem(BaseModel):
    id: int
    name: str
    sign_name: str
    type: str
    variables: list[SmsVariableDef]
    body: str


class SmsWorkspaceTemplateListResponse(BaseModel):
    items: list[SmsWorkspaceTemplateItem]


class SmsSendRequest(BaseModel):
    phone: str = Field(pattern=CN_MOBILE_PATTERN)
    template_id: int
    variables: dict[str, str] = Field(default_factory=dict)
    call_id: str | None = Field(default=None, max_length=80)
    client_request_id: str | None = Field(default=None, max_length=64)


class SmsSendResponse(BaseModel):
    id: int
    status: str  # submitted | failed
    fail_reason: str | None = None
    error_code: str | None = None
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Send records (service operations)
# ---------------------------------------------------------------------------


class SmsSendRecordItem(BaseModel):
    id: int
    phone: str
    template_name: str
    template_type: str
    sign_name: str
    status: str  # pending | submitted | delivered | failed
    employee_name: str
    source: str = "single"  # single | bulk
    bulk_task_id: int | None = None
    call_record_id: int | None = None
    call_record_public_id: str | None = None
    call_id: str | None = None
    created_at: datetime | None = None


class SmsSendRecordListResponse(PaginatedResponse):
    items: list[SmsSendRecordItem]


class SmsSendRecordDetail(SmsSendRecordItem):
    body_snapshot: str
    variables_snapshot: dict[str, str]
    fail_reason: str | None = None
    provider: str
    provider_biz_id: str | None = None
