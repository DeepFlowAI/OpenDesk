"""
Engagement center APIs.
"""
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_principal, get_current_principal_short_session
from app.db.session import AsyncSessionLocal
from app.schemas.outbound_task import (
    BulkAssignRequest,
    BulkAssignResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    OutboundRecordCreate,
    OutboundRecordResponse,
    OutboundTaskCreate,
    OutboundTaskResponse,
    OutboundTaskUpdate,
    OutboundTargetCreate,
    OutboundTargetExecutionUpdate,
    OutboundTargetImportResponse,
    OutboundTargetResponse,
    OutboundTargetUpdate,
    OutboundTemplateCreate,
    OutboundTemplateResponse,
    OutboundTemplateUpdate,
    PaginatedOutboundRecords,
    PaginatedOutboundTargets,
    PaginatedOutboundTargetsWithTask,
    PaginatedOutboundTasks,
    PaginatedOutboundTemplates,
)
from app.schemas.permission import EffectivePrincipal
from app.services.outbound_task_service import OutboundTaskService

router = APIRouter(prefix="/engagement", tags=["Engagement"])


@router.get("/outbound-task-templates", response_model=PaginatedOutboundTemplates)
async def list_outbound_task_templates(
    page: int = 1,
    per_page: int = 20,
    q: str | None = None,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.list_templates(db, principal, page, per_page, q)


@router.post(
    "/outbound-task-templates",
    response_model=OutboundTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_outbound_task_template(
    body: OutboundTemplateCreate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.create_template(db, principal, body)


@router.get("/outbound-task-templates/{template_id}", response_model=OutboundTemplateResponse)
async def get_outbound_task_template(
    template_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.get_template(db, principal, template_id)


@router.put("/outbound-task-templates/{template_id}", response_model=OutboundTemplateResponse)
async def update_outbound_task_template(
    template_id: int,
    body: OutboundTemplateUpdate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.update_template(db, principal, template_id, body)


@router.delete("/outbound-task-templates/{template_id}")
async def delete_outbound_task_template(
    template_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    await OutboundTaskService.delete_template(db, principal, template_id)
    return {"message": "Deleted successfully"}


@router.get("/outbound-tasks", response_model=PaginatedOutboundTasks)
async def list_outbound_tasks(
    page: int = 1,
    per_page: int = 20,
    q: str | None = None,
    status: str | None = None,
    template_id: int | None = None,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.list_tasks(db, principal, page, per_page, q, status, template_id)


@router.post("/outbound-tasks", response_model=OutboundTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_outbound_task(
    body: OutboundTaskCreate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.create_task(db, principal, body)


@router.get("/outbound-tasks/{task_id}", response_model=OutboundTaskResponse)
async def get_outbound_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.get_task(db, principal, task_id)


@router.put("/outbound-tasks/{task_id}", response_model=OutboundTaskResponse)
async def update_outbound_task(
    task_id: int,
    body: OutboundTaskUpdate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.update_task(db, principal, task_id, body)


@router.post("/outbound-tasks/{task_id}/publish", response_model=OutboundTaskResponse)
async def publish_outbound_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.transition_task(db, principal, task_id, "publish")


@router.post("/outbound-tasks/{task_id}/pause", response_model=OutboundTaskResponse)
async def pause_outbound_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.transition_task(db, principal, task_id, "pause")


@router.post("/outbound-tasks/{task_id}/resume", response_model=OutboundTaskResponse)
async def resume_outbound_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.transition_task(db, principal, task_id, "resume")


@router.post("/outbound-tasks/{task_id}/archive", response_model=OutboundTaskResponse)
async def archive_outbound_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.transition_task(db, principal, task_id, "archive")


@router.get("/outbound-tasks/{task_id}/targets", response_model=PaginatedOutboundTargets)
async def list_outbound_targets(
    task_id: int,
    page: int = 1,
    per_page: int = 20,
    q: str | None = None,
    status: str | None = None,
    assignee_id: int | None = None,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.list_targets(db, principal, task_id, page, per_page, q, status, assignee_id)


@router.post(
    "/outbound-tasks/{task_id}/targets",
    response_model=OutboundTargetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_outbound_target(
    task_id: int,
    body: OutboundTargetCreate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.create_target(db, principal, task_id, body)


@router.post("/outbound-tasks/{task_id}/targets/import", response_model=OutboundTargetImportResponse)
async def import_outbound_targets(
    task_id: int,
    file: UploadFile = File(...),
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
):
    content = await file.read()
    async with AsyncSessionLocal() as db:
        return await OutboundTaskService.import_targets(
            db,
            principal,
            task_id,
            file.filename or "outbound-targets.xlsx",
            content,
        )


@router.put("/outbound-targets/{target_id}", response_model=OutboundTargetResponse)
async def update_outbound_target(
    target_id: int,
    body: OutboundTargetUpdate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.update_target(db, principal, target_id, body)


@router.post("/outbound-tasks/{task_id}/targets/bulk-assign", response_model=BulkAssignResponse)
async def bulk_assign_outbound_targets(
    task_id: int,
    body: BulkAssignRequest,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.bulk_assign(db, principal, task_id, body)


@router.post("/outbound-tasks/{task_id}/targets/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_outbound_targets(
    task_id: int,
    body: BulkDeleteRequest,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.bulk_delete_targets(db, principal, task_id, body)


@router.get("/outbound-tasks/{task_id}/records", response_model=PaginatedOutboundRecords)
async def list_outbound_records(
    task_id: int,
    page: int = 1,
    per_page: int = 20,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.list_records(db, principal, task_id, page, per_page)


@router.get("/my-outbound-targets", response_model=PaginatedOutboundTargetsWithTask)
async def list_my_outbound_targets(
    page: int = 1,
    per_page: int = 20,
    task_id: int | None = None,
    status: str | None = None,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.list_my_targets(db, principal, page, per_page, task_id, status)


@router.patch("/my-outbound-targets/{target_id}", response_model=OutboundTargetResponse)
async def update_my_outbound_target(
    target_id: int,
    body: OutboundTargetExecutionUpdate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.update_my_target(db, principal, target_id, body)


@router.post(
    "/outbound-targets/{target_id}/records",
    response_model=OutboundRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_outbound_record(
    target_id: int,
    body: OutboundRecordCreate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.create_record(db, principal, target_id, body)
