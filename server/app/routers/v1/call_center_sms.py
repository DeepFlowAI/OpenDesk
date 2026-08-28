"""
Tenant-side SMS APIs: granted template views (admin console), workspace
single-send and send-record queries.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_permission, require_permission_short_session
from app.schemas.permission import EffectivePrincipal
from app.schemas.sms import (
    SmsSendRecordDetail,
    SmsSendRecordListResponse,
    SmsSendRequest,
    SmsSendResponse,
    SmsTenantTemplateDetail,
    SmsTenantTemplateListResponse,
    SmsWorkspaceTemplateListResponse,
)
from app.services.sms_service import (
    SmsSendRecordService,
    SmsTenantTemplateService,
    SmsWorkspaceService,
)

router = APIRouter(prefix="/call-center/sms", tags=["Call Center SMS"])


@router.get(
    "/templates",
    response_model=SmsTenantTemplateListResponse,
    dependencies=[Depends(require_permission("call.admin.sms.manage"))],
)
async def list_templates(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    principal: EffectivePrincipal = Depends(require_permission("call.admin.sms.manage")),
    db: AsyncSession = Depends(get_db),
) -> SmsTenantTemplateListResponse:
    return await SmsTenantTemplateService.list_for_tenant(
        db, tenant_id=principal.tenant_id, page=page, per_page=per_page, q=q
    )


@router.get(
    "/templates/{template_id}",
    response_model=SmsTenantTemplateDetail,
    dependencies=[Depends(require_permission("call.admin.sms.manage"))],
)
async def get_template(
    template_id: int,
    principal: EffectivePrincipal = Depends(require_permission("call.admin.sms.manage")),
    db: AsyncSession = Depends(get_db),
) -> SmsTenantTemplateDetail:
    return await SmsTenantTemplateService.get_for_tenant(
        db, tenant_id=principal.tenant_id, template_id=template_id
    )


@router.get(
    "/workspace/templates",
    response_model=SmsWorkspaceTemplateListResponse,
    dependencies=[Depends(require_permission("call.workspace.sms.send"))],
)
async def list_workspace_templates(
    principal: EffectivePrincipal = Depends(require_permission("call.workspace.sms.send")),
    db: AsyncSession = Depends(get_db),
) -> SmsWorkspaceTemplateListResponse:
    return await SmsWorkspaceService.list_available_for_workspace(db, tenant_id=principal.tenant_id)


@router.post("/send", response_model=SmsSendResponse)
async def send_sms(
    payload: SmsSendRequest,
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.workspace.sms.send")
    ),
) -> SmsSendResponse:
    # Short-session auth only: the channel call runs without a DB session held.
    return await SmsWorkspaceService.send_managed(
        tenant_id=principal.tenant_id, employee_id=principal.user_id, payload=payload
    )


@router.get(
    "/records",
    response_model=SmsSendRecordListResponse,
    dependencies=[Depends(require_permission("call.sms_record.view"))],
)
async def list_send_records(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
    principal: EffectivePrincipal = Depends(require_permission("call.sms_record.view")),
    db: AsyncSession = Depends(get_db),
) -> SmsSendRecordListResponse:
    return await SmsSendRecordService.list_for_tenant(
        db, tenant_id=principal.tenant_id, page=page, per_page=per_page, q=q, status=status, source=source
    )


@router.get(
    "/records/{record_id}",
    response_model=SmsSendRecordDetail,
    dependencies=[Depends(require_permission("call.sms_record.view"))],
)
async def get_send_record(
    record_id: int,
    principal: EffectivePrincipal = Depends(require_permission("call.sms_record.view")),
    db: AsyncSession = Depends(get_db),
) -> SmsSendRecordDetail:
    return await SmsSendRecordService.get_for_tenant(
        db, tenant_id=principal.tenant_id, record_id=record_id
    )
