"""
Ticket workflow router.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_current_user, get_db
from app.schemas.ticket_workflow import (
    GraphValidationResult,
    TicketWorkflowCreate,
    TicketWorkflowListResponse,
    TicketWorkflowReorderRequest,
    TicketWorkflowResponse,
    TicketWorkflowUpdate,
    TicketWorkflowValidateRequest,
    TicketWorkflowVersionDetail,
    TicketWorkflowVersionListResponse,
)
from app.services.audit_actor_service import AuditActorService
from app.services.ticket_workflow_service import TicketWorkflowService

router = APIRouter(prefix="/ticket-workflows", tags=["TicketWorkflows"])


@router.get("", response_model=TicketWorkflowListResponse)
async def list_ticket_workflows(
    page: int = 1,
    per_page: int = 20,
    keyword: str | None = None,
    include_deleted: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TicketWorkflowService.get_paginated(
        db,
        current_user["tenant_id"],
        page,
        per_page,
        keyword,
        include_deleted,
    )


@router.post("", response_model=TicketWorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket_workflow(
    body: TicketWorkflowCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    actor = await AuditActorService.resolve_current_employee(
        db,
        tenant_id,
        current_user.get("user_id"),
    )
    return await TicketWorkflowService.create(db, tenant_id, actor, body)


@router.post("/reorder")
async def reorder_ticket_workflows(
    body: TicketWorkflowReorderRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await TicketWorkflowService.reorder(db, current_user["tenant_id"], body.ids)
    return {"message": "Reordered successfully"}


@router.get("/{workflow_id}", response_model=TicketWorkflowResponse)
async def get_ticket_workflow(
    workflow_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TicketWorkflowService.get_by_id(db, workflow_id, current_user["tenant_id"])


@router.put("/{workflow_id}", response_model=TicketWorkflowResponse)
async def update_ticket_workflow(
    workflow_id: int,
    body: TicketWorkflowUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    actor = await AuditActorService.resolve_current_employee(
        db,
        tenant_id,
        current_user.get("user_id"),
    )
    return await TicketWorkflowService.update(db, workflow_id, tenant_id, actor, body)


@router.delete("/{workflow_id}")
async def delete_ticket_workflow(
    workflow_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await TicketWorkflowService.delete(db, workflow_id, current_user["tenant_id"])
    return {"message": "Deleted successfully"}


@router.post("/{workflow_id}/validate", response_model=GraphValidationResult)
async def validate_ticket_workflow(
    workflow_id: int,
    body: TicketWorkflowValidateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # workflow_id is kept for future contextual validation.
    return await TicketWorkflowService.validate(db, current_user["tenant_id"], body.graph_json)


@router.get("/{workflow_id}/versions", response_model=TicketWorkflowVersionListResponse)
async def list_ticket_workflow_versions(
    workflow_id: int,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TicketWorkflowService.list_versions(
        db,
        workflow_id,
        current_user["tenant_id"],
        min(limit, 200),
    )


@router.get("/{workflow_id}/versions/{version_no}", response_model=TicketWorkflowVersionDetail)
async def get_ticket_workflow_version(
    workflow_id: int,
    version_no: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TicketWorkflowService.get_version(
        db,
        workflow_id,
        version_no,
        current_user["tenant_id"],
    )


@router.post("/{workflow_id}/rollback/{version_no}", response_model=TicketWorkflowResponse)
async def rollback_ticket_workflow(
    workflow_id: int,
    version_no: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    actor = await AuditActorService.resolve_current_employee(
        db,
        tenant_id,
        current_user.get("user_id"),
    )
    return await TicketWorkflowService.rollback_to_version(
        db,
        workflow_id,
        version_no,
        tenant_id,
        actor,
    )
