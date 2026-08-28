"""
Engagement Open API router authenticated by tenant API keys.

Exposes outbound templates plus manual and automatic task management.
"""

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db
from app.db.open_api_deps import (
    get_open_api_context,
    get_open_api_task_principal,
    get_open_api_task_principal_short_session,
)
from app.db.session import AsyncSessionLocal
from app.schemas.auto_outbound import (
    AutoOutboundMonitorResponse,
    AutoOutboundRecordResponse,
    AutoOutboundTargetBulkCreateRequest,
    AutoOutboundTargetBulkCreateResponse,
    AutoOutboundTargetCreate,
    AutoOutboundTargetImportResponse,
    AutoOutboundTargetResponse,
    AutoOutboundTargetUpdate,
    AutoOutboundTaskCreate,
    AutoOutboundTaskDetailStats,
    AutoOutboundTaskResponse,
    AutoOutboundTaskUpdate,
    PaginatedAutoOutboundRecords,
    PaginatedAutoOutboundTargets,
    PaginatedAutoOutboundTasks,
)
from app.schemas.open_api import OpenApiContext, OpenApiTaskPrincipal
from app.schemas.outbound_task import (
    BulkAssignRequest,
    BulkAssignResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    OutboundTaskCreate,
    OutboundTaskResponse,
    OutboundTaskUpdate,
    OutboundTargetBulkCreateRequest,
    OutboundTargetBulkCreateResponse,
    OutboundTargetCreate,
    OutboundTargetImportResponse,
    OutboundTargetResponse,
    OutboundTargetUpdate,
    OutboundTemplateCreate,
    OutboundTemplateResponse,
    OutboundTemplateScriptResponse,
    OutboundTemplateScriptUpdate,
    OutboundTemplateUpdate,
    PaginatedOutboundRecords,
    PaginatedOutboundTargets,
    PaginatedOutboundTasks,
    PaginatedOutboundTemplates,
)
from app.services.auto_outbound_task_service import AutoOutboundTaskService
from app.services.outbound_task_service import OutboundTaskService

router = APIRouter(prefix="/open/engagement", tags=["OpenEngagement"])


@router.get("/outbound-task-templates", response_model=PaginatedOutboundTemplates)
async def list_open_outbound_task_templates(
    page: int = 1,
    per_page: int = 20,
    q: str | None = None,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """List outbound task templates for the API key tenant."""
    return await OutboundTaskService.list_templates_for_tenant(
        db, context.tenant_id, page, per_page, q
    )


@router.post(
    "/outbound-task-templates",
    response_model=OutboundTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_open_outbound_task_template(
    body: OutboundTemplateCreate,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Create an outbound task template (including optional outbound script)."""
    return await OutboundTaskService.create_template_for_tenant(
        db, context.tenant_id, body
    )


@router.get(
    "/outbound-task-templates/{template_id}",
    response_model=OutboundTemplateResponse,
)
async def get_open_outbound_task_template(
    template_id: int,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Get an outbound task template including its outbound script."""
    return await OutboundTaskService.get_template_for_tenant(
        db, context.tenant_id, template_id
    )


@router.put(
    "/outbound-task-templates/{template_id}",
    response_model=OutboundTemplateResponse,
)
async def update_open_outbound_task_template(
    template_id: int,
    body: OutboundTemplateUpdate,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Update an outbound task template (including outbound script)."""
    return await OutboundTaskService.update_template_for_tenant(
        db, context.tenant_id, template_id, body
    )


@router.delete(
    "/outbound-task-templates/{template_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_open_outbound_task_template(
    template_id: int,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Delete an outbound task template."""
    await OutboundTaskService.delete_template_for_tenant(
        db, context.tenant_id, template_id
    )
    return {"message": "Deleted successfully"}


@router.get(
    "/outbound-task-templates/{template_id}/script",
    response_model=OutboundTemplateScriptResponse,
)
async def get_open_outbound_task_template_script(
    template_id: int,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Get the outbound script configured on a task template."""
    return await OutboundTaskService.get_template_script_for_tenant(
        db, context.tenant_id, template_id
    )


@router.put(
    "/outbound-task-templates/{template_id}/script",
    response_model=OutboundTemplateScriptResponse,
)
async def update_open_outbound_task_template_script(
    template_id: int,
    body: OutboundTemplateScriptUpdate,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Replace or clear the outbound script on a task template."""
    return await OutboundTaskService.update_template_script_for_tenant(
        db, context.tenant_id, template_id, body
    )


# Manual outbound task management


@router.get("/outbound-tasks", response_model=PaginatedOutboundTasks)
async def list_open_outbound_tasks(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    q: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    template_id: int | None = None,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.list_tasks(
        db, principal, page, per_page, q, status_filter, template_id
    )


@router.post(
    "/outbound-tasks",
    response_model=OutboundTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_open_outbound_task(
    body: OutboundTaskCreate,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.create_task(db, principal, body)


@router.get("/outbound-tasks/{task_id}", response_model=OutboundTaskResponse)
async def get_open_outbound_task(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.get_task(db, principal, task_id)


@router.put("/outbound-tasks/{task_id}", response_model=OutboundTaskResponse)
async def update_open_outbound_task(
    task_id: int,
    body: OutboundTaskUpdate,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.update_task(db, principal, task_id, body)


@router.post("/outbound-tasks/{task_id}/publish", response_model=OutboundTaskResponse)
async def publish_open_outbound_task(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.transition_task(db, principal, task_id, "publish")


@router.post("/outbound-tasks/{task_id}/pause", response_model=OutboundTaskResponse)
async def pause_open_outbound_task(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.transition_task(db, principal, task_id, "pause")


@router.post("/outbound-tasks/{task_id}/resume", response_model=OutboundTaskResponse)
async def resume_open_outbound_task(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.transition_task(db, principal, task_id, "resume")


@router.post("/outbound-tasks/{task_id}/archive", response_model=OutboundTaskResponse)
async def archive_open_outbound_task(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.transition_task(db, principal, task_id, "archive")


@router.get(
    "/outbound-tasks/{task_id}/targets",
    response_model=PaginatedOutboundTargets,
)
async def list_open_outbound_targets(
    task_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    q: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    assignee_id: int | None = None,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.list_targets(
        db, principal, task_id, page, per_page, q, status_filter, assignee_id
    )


@router.post(
    "/outbound-tasks/{task_id}/targets",
    response_model=OutboundTargetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_open_outbound_target(
    task_id: int,
    body: OutboundTargetCreate,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.create_target(db, principal, task_id, body)


@router.post(
    "/outbound-tasks/{task_id}/targets/bulk",
    response_model=OutboundTargetBulkCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_open_outbound_targets_bulk(
    task_id: int,
    body: OutboundTargetBulkCreateRequest,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.create_targets_bulk(
        db, principal, task_id, body
    )


@router.post(
    "/outbound-tasks/{task_id}/targets/import",
    response_model=OutboundTargetImportResponse,
)
async def import_open_outbound_targets(
    task_id: int,
    file: UploadFile = File(...),
    principal: OpenApiTaskPrincipal = Depends(
        get_open_api_task_principal_short_session
    ),
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
async def update_open_outbound_target(
    target_id: int,
    body: OutboundTargetUpdate,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.update_target(db, principal, target_id, body)


@router.post(
    "/outbound-tasks/{task_id}/targets/bulk-assign",
    response_model=BulkAssignResponse,
)
async def bulk_assign_open_outbound_targets(
    task_id: int,
    body: BulkAssignRequest,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.bulk_assign(db, principal, task_id, body)


@router.post(
    "/outbound-tasks/{task_id}/targets/bulk-delete",
    response_model=BulkDeleteResponse,
)
async def bulk_delete_open_outbound_targets(
    task_id: int,
    body: BulkDeleteRequest,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.bulk_delete_targets(db, principal, task_id, body)


@router.get(
    "/outbound-tasks/{task_id}/records",
    response_model=PaginatedOutboundRecords,
)
async def list_open_outbound_records(
    task_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.list_records(
        db, principal, task_id, page, per_page
    )


# Auto outbound task management


@router.get("/auto-outbound-tasks", response_model=PaginatedAutoOutboundTasks)
async def list_open_auto_outbound_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    q: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    mode: str | None = None,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.list_tasks(
        db, principal, page, page_size, q=q, status=status_filter, mode=mode
    )


@router.post(
    "/auto-outbound-tasks",
    response_model=AutoOutboundTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_open_auto_outbound_task(
    body: AutoOutboundTaskCreate,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.create_task(db, principal, body)


@router.get(
    "/auto-outbound-tasks/{task_id}", response_model=AutoOutboundTaskResponse
)
async def get_open_auto_outbound_task(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.get_task(db, principal, task_id)


@router.put(
    "/auto-outbound-tasks/{task_id}", response_model=AutoOutboundTaskResponse
)
async def update_open_auto_outbound_task(
    task_id: int,
    body: AutoOutboundTaskUpdate,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.update_task(db, principal, task_id, body)


@router.post(
    "/auto-outbound-tasks/{task_id}/start",
    response_model=AutoOutboundTaskResponse,
)
async def start_open_auto_outbound_task(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.start_task(db, principal, task_id)


@router.post(
    "/auto-outbound-tasks/{task_id}/pause",
    response_model=AutoOutboundTaskResponse,
)
async def pause_open_auto_outbound_task(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.pause_task(db, principal, task_id)


@router.post(
    "/auto-outbound-tasks/{task_id}/resume",
    response_model=AutoOutboundTaskResponse,
)
async def resume_open_auto_outbound_task(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.resume_task(db, principal, task_id)


@router.post(
    "/auto-outbound-tasks/{task_id}/archive",
    response_model=AutoOutboundTaskResponse,
)
async def archive_open_auto_outbound_task(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.archive_task(db, principal, task_id)


@router.delete("/auto-outbound-tasks/{task_id}")
async def delete_open_auto_outbound_task(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    await AutoOutboundTaskService.delete_task(db, principal, task_id)
    return {"message": "Deleted successfully"}


@router.get(
    "/auto-outbound-tasks/{task_id}/stats",
    response_model=AutoOutboundTaskDetailStats,
)
async def get_open_auto_outbound_task_stats(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.get_stats(db, principal, task_id)


@router.get(
    "/auto-outbound-tasks/{task_id}/monitor",
    response_model=AutoOutboundMonitorResponse,
)
async def get_open_auto_outbound_task_monitor(
    task_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.get_monitor(db, principal, task_id)


@router.get(
    "/auto-outbound-tasks/{task_id}/targets",
    response_model=PaginatedAutoOutboundTargets,
)
async def list_open_auto_outbound_targets(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    q: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.list_targets(
        db, principal, task_id, page, page_size, q=q, status=status_filter
    )


@router.post(
    "/auto-outbound-tasks/{task_id}/targets",
    response_model=AutoOutboundTargetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_open_auto_outbound_target(
    task_id: int,
    body: AutoOutboundTargetCreate,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.create_target(db, principal, task_id, body)


@router.post(
    "/auto-outbound-tasks/{task_id}/targets/bulk",
    response_model=AutoOutboundTargetBulkCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_open_auto_outbound_targets_bulk(
    task_id: int,
    body: AutoOutboundTargetBulkCreateRequest,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.create_targets_bulk(
        db, principal, task_id, body
    )


@router.post(
    "/auto-outbound-tasks/{task_id}/targets/import",
    response_model=AutoOutboundTargetImportResponse,
)
async def import_open_auto_outbound_targets(
    task_id: int,
    file: UploadFile = File(...),
    principal: OpenApiTaskPrincipal = Depends(
        get_open_api_task_principal_short_session
    ),
):
    content = await file.read()
    async with AsyncSessionLocal() as db:
        return await AutoOutboundTaskService.import_targets(
            db,
            principal,
            task_id,
            file.filename or "auto-outbound-targets.xlsx",
            content,
        )


@router.put(
    "/auto-outbound-targets/{target_id}",
    response_model=AutoOutboundTargetResponse,
)
async def update_open_auto_outbound_target(
    target_id: int,
    body: AutoOutboundTargetUpdate,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.update_target(
        db, principal, target_id, body
    )


@router.post(
    "/auto-outbound-targets/{target_id}/mark-invalid",
    response_model=AutoOutboundTargetResponse,
)
async def mark_open_auto_outbound_target_invalid(
    target_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.mark_target_invalid(
        db, principal, target_id
    )


@router.delete("/auto-outbound-targets/{target_id}")
async def delete_open_auto_outbound_target(
    target_id: int,
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    await AutoOutboundTaskService.delete_target(db, principal, target_id)
    return {"message": "Deleted successfully"}


@router.get(
    "/auto-outbound-tasks/{task_id}/records",
    response_model=PaginatedAutoOutboundRecords,
)
async def list_open_auto_outbound_records(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    principal: OpenApiTaskPrincipal = Depends(get_open_api_task_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.list_records(
        db, principal, task_id, page, page_size
    )
