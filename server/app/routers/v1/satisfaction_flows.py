"""Administration API for call satisfaction flows."""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_all_permissions
from app.schemas.permission import EffectivePrincipal
from app.schemas.satisfaction_flow import (
    GraphValidationResult,
    SatisfactionFlowCreate,
    SatisfactionFlowEnableRequest,
    SatisfactionFlowListResponse,
    SatisfactionFlowResponse,
    SatisfactionFlowSave,
    SatisfactionFlowValidateRequest,
    SatisfactionFlowVersionDetail,
    SatisfactionFlowVersionListResponse,
)
from app.services.audit_actor_service import AuditActorService
from app.services.satisfaction_flow_service import SatisfactionFlowService

router = APIRouter(prefix="/satisfaction-flows", tags=["SatisfactionFlows"])
manage_satisfaction_flows = require_all_permissions(
    ["admin.access", "call.admin.flow.manage"]
)


@router.get("", response_model=SatisfactionFlowListResponse)
async def list_satisfaction_flows(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=50),
    enabled: bool | None = None,
    principal: EffectivePrincipal = Depends(manage_satisfaction_flows),
    db: AsyncSession = Depends(get_db),
):
    return await SatisfactionFlowService.get_paginated(
        db, principal.tenant_id, page, per_page, keyword, enabled
    )


@router.post(
    "", response_model=SatisfactionFlowResponse, status_code=status.HTTP_201_CREATED
)
async def create_satisfaction_flow(
    body: SatisfactionFlowCreate,
    principal: EffectivePrincipal = Depends(manage_satisfaction_flows),
    db: AsyncSession = Depends(get_db),
):
    actor = await AuditActorService.resolve_current_employee(
        db, principal.tenant_id, principal.user_id
    )
    return await SatisfactionFlowService.create(db, principal.tenant_id, actor, body)


@router.post("/{flow_id}/validate", response_model=GraphValidationResult)
async def validate_satisfaction_flow(
    flow_id: int,
    body: SatisfactionFlowValidateRequest,
    principal: EffectivePrincipal = Depends(manage_satisfaction_flows),
):
    del flow_id, principal
    return SatisfactionFlowService.validate(body.graph_json, body.settings)


@router.post("/{flow_id}/copy", response_model=SatisfactionFlowResponse)
async def copy_satisfaction_flow(
    flow_id: int,
    principal: EffectivePrincipal = Depends(manage_satisfaction_flows),
    db: AsyncSession = Depends(get_db),
):
    actor = await AuditActorService.resolve_current_employee(
        db, principal.tenant_id, principal.user_id
    )
    return await SatisfactionFlowService.copy(
        db, flow_id, principal.tenant_id, actor
    )


@router.post("/{flow_id}/enable", response_model=SatisfactionFlowResponse)
async def enable_satisfaction_flow(
    flow_id: int,
    body: SatisfactionFlowEnableRequest,
    principal: EffectivePrincipal = Depends(manage_satisfaction_flows),
    db: AsyncSession = Depends(get_db),
):
    return await SatisfactionFlowService.enable(
        db, flow_id, principal.tenant_id, body.replace_active
    )


@router.post("/{flow_id}/disable", response_model=SatisfactionFlowResponse)
async def disable_satisfaction_flow(
    flow_id: int,
    principal: EffectivePrincipal = Depends(manage_satisfaction_flows),
    db: AsyncSession = Depends(get_db),
):
    return await SatisfactionFlowService.disable(db, flow_id, principal.tenant_id)


@router.get(
    "/{flow_id}/versions", response_model=SatisfactionFlowVersionListResponse
)
async def list_satisfaction_flow_versions(
    flow_id: int,
    limit: int = Query(50, ge=1, le=200),
    principal: EffectivePrincipal = Depends(manage_satisfaction_flows),
    db: AsyncSession = Depends(get_db),
):
    return await SatisfactionFlowService.list_versions(
        db, flow_id, principal.tenant_id, limit
    )


@router.get(
    "/{flow_id}/versions/{version_no}", response_model=SatisfactionFlowVersionDetail
)
async def get_satisfaction_flow_version(
    flow_id: int,
    version_no: int,
    principal: EffectivePrincipal = Depends(manage_satisfaction_flows),
    db: AsyncSession = Depends(get_db),
):
    return await SatisfactionFlowService.get_version(
        db, flow_id, version_no, principal.tenant_id
    )


@router.post(
    "/{flow_id}/rollback/{version_no}", response_model=SatisfactionFlowResponse
)
async def rollback_satisfaction_flow(
    flow_id: int,
    version_no: int,
    principal: EffectivePrincipal = Depends(manage_satisfaction_flows),
    db: AsyncSession = Depends(get_db),
):
    actor = await AuditActorService.resolve_current_employee(
        db, principal.tenant_id, principal.user_id
    )
    return await SatisfactionFlowService.rollback(
        db, flow_id, version_no, principal.tenant_id, actor
    )


@router.get("/{flow_id}", response_model=SatisfactionFlowResponse)
async def get_satisfaction_flow(
    flow_id: int,
    principal: EffectivePrincipal = Depends(manage_satisfaction_flows),
    db: AsyncSession = Depends(get_db),
):
    return await SatisfactionFlowService.get_by_id(db, flow_id, principal.tenant_id)


@router.put("/{flow_id}", response_model=SatisfactionFlowResponse)
async def save_satisfaction_flow(
    flow_id: int,
    body: SatisfactionFlowSave,
    principal: EffectivePrincipal = Depends(manage_satisfaction_flows),
    db: AsyncSession = Depends(get_db),
):
    actor = await AuditActorService.resolve_current_employee(
        db, principal.tenant_id, principal.user_id
    )
    return await SatisfactionFlowService.save(
        db, flow_id, principal.tenant_id, actor, body
    )


@router.delete("/{flow_id}")
async def delete_satisfaction_flow(
    flow_id: int,
    principal: EffectivePrincipal = Depends(manage_satisfaction_flows),
    db: AsyncSession = Depends(get_db),
):
    await SatisfactionFlowService.delete(db, flow_id, principal.tenant_id)
    return {"message": "Deleted successfully"}
