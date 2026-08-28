"""
SMS platform routers — signature/template/grant APIs for the Tenant Platform.

Authenticated via X-API-Key (same key as /api/v1/tenants and /api/v1/sip-trunks).
"""
import hmac

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import UnauthorizedError
from app.db.deps import get_db
from app.schemas.sms import (
    SmsGrantedTemplateListResponse,
    SmsSignatureCreate,
    SmsSignatureListResponse,
    SmsSignatureResponse,
    SmsSignatureUpdate,
    SmsTemplateCreate,
    SmsTemplateGrantBatch,
    SmsTemplateGrantResult,
    SmsTemplateListResponse,
    SmsTemplateResponse,
    SmsTemplateRevokeResult,
    SmsTemplateUpdate,
)
from app.services.sms_platform_service import (
    SmsSignatureService,
    SmsTemplateGrantService,
    SmsTemplateService,
)


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    expected = settings.TENANT_API_KEY or ""
    if not hmac.compare_digest(x_api_key.strip(), expected):
        raise UnauthorizedError("Invalid or missing API Key")
    return x_api_key


sms_signatures_router = APIRouter(
    prefix="/sms-signatures",
    tags=["SMS Signatures"],
    dependencies=[Depends(verify_api_key)],
)

sms_templates_router = APIRouter(
    prefix="/sms-templates",
    tags=["SMS Templates"],
    dependencies=[Depends(verify_api_key)],
)

sms_template_grants_router = APIRouter(
    prefix="/sms-template-grants",
    tags=["SMS Template Grants"],
    dependencies=[Depends(verify_api_key)],
)


# ---------------------------------------------------------------------------
# Signatures
# ---------------------------------------------------------------------------


@sms_signatures_router.post(
    "", response_model=SmsSignatureResponse, status_code=status.HTTP_201_CREATED
)
async def create_signature(
    body: SmsSignatureCreate,
    db: AsyncSession = Depends(get_db),
) -> SmsSignatureResponse:
    return await SmsSignatureService.create(db, body)


@sms_signatures_router.get("", response_model=SmsSignatureListResponse)
async def list_signatures(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> SmsSignatureListResponse:
    return await SmsSignatureService.list_paginated(
        db, page=page, per_page=per_page, q=q, status=status
    )


@sms_signatures_router.get("/{signature_id}", response_model=SmsSignatureResponse)
async def get_signature(
    signature_id: int,
    db: AsyncSession = Depends(get_db),
) -> SmsSignatureResponse:
    return await SmsSignatureService.get_by_id(db, signature_id)


@sms_signatures_router.put("/{signature_id}", response_model=SmsSignatureResponse)
async def update_signature(
    signature_id: int,
    body: SmsSignatureUpdate,
    db: AsyncSession = Depends(get_db),
) -> SmsSignatureResponse:
    return await SmsSignatureService.update(db, signature_id, body)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@sms_templates_router.post(
    "", response_model=SmsTemplateResponse, status_code=status.HTTP_201_CREATED
)
async def create_template(
    body: SmsTemplateCreate,
    db: AsyncSession = Depends(get_db),
) -> SmsTemplateResponse:
    return await SmsTemplateService.create(db, body)


@sms_templates_router.get("", response_model=SmsTemplateListResponse)
async def list_templates(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> SmsTemplateListResponse:
    return await SmsTemplateService.list_paginated(
        db, page=page, per_page=per_page, q=q, status=status, type_=type
    )


@sms_templates_router.get("/{template_id}", response_model=SmsTemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
) -> SmsTemplateResponse:
    return await SmsTemplateService.get_detail(db, template_id)


@sms_templates_router.put("/{template_id}", response_model=SmsTemplateResponse)
async def update_template(
    template_id: int,
    body: SmsTemplateUpdate,
    db: AsyncSession = Depends(get_db),
) -> SmsTemplateResponse:
    return await SmsTemplateService.update(db, template_id, body)


# ---------------------------------------------------------------------------
# Tenant grants
# ---------------------------------------------------------------------------


@sms_template_grants_router.post("", response_model=SmsTemplateGrantResult)
async def grant_templates(
    body: SmsTemplateGrantBatch,
    db: AsyncSession = Depends(get_db),
) -> SmsTemplateGrantResult:
    return await SmsTemplateGrantService.grant(
        db, tenant_id=body.tenant_id, template_ids=body.template_ids
    )


@sms_template_grants_router.delete("", response_model=SmsTemplateRevokeResult)
async def revoke_templates(
    body: SmsTemplateGrantBatch,
    db: AsyncSession = Depends(get_db),
) -> SmsTemplateRevokeResult:
    return await SmsTemplateGrantService.revoke(
        db, tenant_id=body.tenant_id, template_ids=body.template_ids
    )


@sms_template_grants_router.get("", response_model=SmsGrantedTemplateListResponse)
async def list_granted_templates(
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> SmsGrantedTemplateListResponse:
    return await SmsTemplateGrantService.list_granted_templates(db, tenant_id=tenant_id)
