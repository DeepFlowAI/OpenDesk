"""
Engagement center APIs.
"""
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import (
    get_db,
    get_current_principal,
    get_current_principal_short_session,
    require_permission,
)
from app.db.session import AsyncSessionLocal
from app.schemas.outbound_task import (
    BulkAssignRequest,
    BulkAssignResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    MyOutboundTargetRecordsResponse,
    MyOutboundTaskListResponse,
    OutboundRecordCreate,
    OutboundRecordResponse,
    OutboundScript,
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
    OutboundTemplateScriptResponse,
    OutboundTemplateScriptUpdate,
    OutboundTemplateUpdate,
    PaginatedOutboundRecords,
    PaginatedOutboundTargets,
    PaginatedOutboundTargetsWithTask,
    PaginatedOutboundTasks,
    PaginatedOutboundTemplates,
)
from app.schemas.auto_outbound import (
    AutoOutboundAgentContextResponse,
    AutoOutboundMonitorResponse,
    AutoOutboundRecordResponse,
    AutoOutboundTargetCreate,
    AutoOutboundTargetImportResponse,
    AutoOutboundTargetResponse,
    AutoOutboundTargetUpdate,
    AutoOutboundTaskCreate,
    AutoOutboundTaskDetailStats,
    AutoOutboundTaskResponse,
    AutoOutboundTaskUpdate,
    AutoOutboundWrapupRequest,
    PaginatedAutoOutboundRecords,
    PaginatedAutoOutboundTargets,
    PaginatedAutoOutboundTasks,
)
from app.schemas.auto_outbound_event import (
    AutoOutboundEventSubscriptionResponse,
    AutoOutboundEventSubscriptionSave,
)
from app.schemas.permission import EffectivePrincipal
from app.services.auto_outbound_task_service import AutoOutboundTaskService
from app.services.auto_outbound_event_service import AutoOutboundEventService
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


@router.get(
    "/outbound-task-templates/{template_id}/script",
    response_model=OutboundTemplateScriptResponse,
)
async def get_outbound_task_template_script(
    template_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.get_template_script(db, principal, template_id)


@router.put(
    "/outbound-task-templates/{template_id}/script",
    response_model=OutboundTemplateScriptResponse,
)
async def update_outbound_task_template_script(
    template_id: int,
    body: OutboundTemplateScriptUpdate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.update_template_script(db, principal, template_id, body)


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


@router.get("/my-outbound-tasks", response_model=MyOutboundTaskListResponse)
async def list_my_outbound_tasks(
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.list_my_tasks(db, principal)


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


@router.get("/my-outbound-targets/{target_id}/records", response_model=MyOutboundTargetRecordsResponse)
async def list_my_outbound_target_records(
    target_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.list_my_target_records(db, principal, target_id)


@router.get("/my-outbound-targets/{target_id}/script", response_model=OutboundScript)
async def get_my_outbound_target_script(
    target_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundTaskService.get_my_target_script(db, principal, target_id)


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


# ── Auto outbound tasks ──────────────────────────────────────────────


@router.get("/auto-outbound-tasks", response_model=PaginatedAutoOutboundTasks)
async def list_auto_outbound_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    q: str | None = None,
    status: str | None = None,
    mode: str | None = None,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.list_tasks(
        db, principal, page, page_size, q=q, status=status, mode=mode
    )


@router.post(
    "/auto-outbound-tasks",
    response_model=AutoOutboundTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_auto_outbound_task(
    body: AutoOutboundTaskCreate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.create_task(db, principal, body)


@router.get("/auto-outbound-tasks/{task_id}", response_model=AutoOutboundTaskResponse)
async def get_auto_outbound_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.get_task(db, principal, task_id)


@router.get(
    "/auto-outbound-tasks/{task_id}/event-subscription",
    response_model=AutoOutboundEventSubscriptionResponse,
)
async def get_auto_outbound_event_subscription(
    task_id: int,
    principal: EffectivePrincipal = Depends(
        require_permission("engagement.auto_outbound_task.subscription.manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundEventService.get_configuration(db, principal, task_id)


@router.put(
    "/auto-outbound-tasks/{task_id}/event-subscription",
    response_model=AutoOutboundEventSubscriptionResponse,
)
async def save_auto_outbound_event_subscription(
    task_id: int,
    body: AutoOutboundEventSubscriptionSave,
    principal: EffectivePrincipal = Depends(
        require_permission("engagement.auto_outbound_task.subscription.manage")
    ),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundEventService.save_configuration(
        db, principal, task_id, body
    )


@router.put("/auto-outbound-tasks/{task_id}", response_model=AutoOutboundTaskResponse)
async def update_auto_outbound_task(
    task_id: int,
    body: AutoOutboundTaskUpdate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.update_task(db, principal, task_id, body)


@router.post("/auto-outbound-tasks/{task_id}/start", response_model=AutoOutboundTaskResponse)
async def start_auto_outbound_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.start_task(db, principal, task_id)


@router.post("/auto-outbound-tasks/{task_id}/pause", response_model=AutoOutboundTaskResponse)
async def pause_auto_outbound_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.pause_task(db, principal, task_id)


@router.post("/auto-outbound-tasks/{task_id}/resume", response_model=AutoOutboundTaskResponse)
async def resume_auto_outbound_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.resume_task(db, principal, task_id)


@router.post("/auto-outbound-tasks/{task_id}/archive", response_model=AutoOutboundTaskResponse)
async def archive_auto_outbound_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.archive_task(db, principal, task_id)


@router.delete("/auto-outbound-tasks/{task_id}")
async def delete_auto_outbound_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    await AutoOutboundTaskService.delete_task(db, principal, task_id)
    return {"message": "Deleted successfully"}


@router.get("/auto-outbound-tasks/{task_id}/stats", response_model=AutoOutboundTaskDetailStats)
async def get_auto_outbound_task_stats(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.get_stats(db, principal, task_id)


@router.get("/auto-outbound-tasks/{task_id}/monitor", response_model=AutoOutboundMonitorResponse)
async def get_auto_outbound_task_monitor(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.get_monitor(db, principal, task_id)


@router.get("/auto-outbound-tasks/{task_id}/targets", response_model=PaginatedAutoOutboundTargets)
async def list_auto_outbound_targets(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    q: str | None = None,
    status: str | None = None,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.list_targets(
        db, principal, task_id, page, page_size, q=q, status=status
    )


@router.post(
    "/auto-outbound-tasks/{task_id}/targets",
    response_model=AutoOutboundTargetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_auto_outbound_target(
    task_id: int,
    body: AutoOutboundTargetCreate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.create_target(db, principal, task_id, body)


@router.post(
    "/auto-outbound-tasks/{task_id}/targets/import",
    response_model=AutoOutboundTargetImportResponse,
)
async def import_auto_outbound_targets(
    task_id: int,
    file: UploadFile = File(...),
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
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


@router.put("/auto-outbound-targets/{target_id}", response_model=AutoOutboundTargetResponse)
async def update_auto_outbound_target(
    target_id: int,
    body: AutoOutboundTargetUpdate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.update_target(db, principal, target_id, body)


@router.post(
    "/auto-outbound-targets/{target_id}/mark-invalid",
    response_model=AutoOutboundTargetResponse,
)
async def mark_auto_outbound_target_invalid(
    target_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.mark_target_invalid(db, principal, target_id)


@router.delete("/auto-outbound-targets/{target_id}")
async def delete_auto_outbound_target(
    target_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    await AutoOutboundTaskService.delete_target(db, principal, target_id)
    return {"message": "Deleted successfully"}


@router.get("/auto-outbound-tasks/{task_id}/records", response_model=PaginatedAutoOutboundRecords)
async def list_auto_outbound_records(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.list_records(db, principal, task_id, page, page_size)


@router.get(
    "/auto-outbound-tasks/{task_id}/agent-context",
    response_model=AutoOutboundAgentContextResponse,
)
async def get_auto_outbound_agent_context(
    task_id: int,
    call_record_id: int | None = None,
    phone_number: str | None = None,
    principal: EffectivePrincipal = Depends(require_permission("call.workspace.use")),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.get_agent_context(
        db,
        principal,
        task_id,
        call_record_id=call_record_id,
        phone_number=phone_number,
    )


@router.post(
    "/auto-outbound-tasks/{task_id}/records/{record_id}/wrapup",
    response_model=AutoOutboundRecordResponse,
)
async def submit_auto_outbound_wrapup(
    task_id: int,
    record_id: int,
    body: AutoOutboundWrapupRequest,
    principal: EffectivePrincipal = Depends(require_permission("call.workspace.use")),
    db: AsyncSession = Depends(get_db),
):
    return await AutoOutboundTaskService.submit_wrapup(
        db, principal, task_id, record_id, body
    )
