"""
Engagement center bulk SMS task APIs.
"""
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_current_principal, get_current_principal_short_session, get_db, get_redis
from app.db.session import AsyncSessionLocal
from app.schemas.permission import EffectivePrincipal
from app.schemas.sms_bulk_task import (
    PaginatedSmsBulkTargets,
    PaginatedSmsBulkTasks,
    SmsBulkImportExecuteResponse,
    SmsBulkImportMapping,
    SmsBulkImportParseResponse,
    SmsBulkImportValidateResponse,
    SmsBulkTargetBulkDeleteRequest,
    SmsBulkTargetBulkDeleteResponse,
    SmsBulkTargetCreate,
    SmsBulkTargetDetail,
    SmsBulkTargetResendResponse,
    SmsBulkTargetResponse,
    SmsBulkTaskCreate,
    SmsBulkTaskDetail,
    SmsBulkTaskResponse,
    SmsBulkTaskUpdate,
    SmsBulkTemplateListResponse,
)
from app.services.sms_bulk_import_service import SmsBulkImportService
from app.services.sms_bulk_task_service import SmsBulkTaskService

router = APIRouter(prefix="/engagement/sms-tasks", tags=["Engagement"])


@router.get("/available-templates", response_model=SmsBulkTemplateListResponse)
async def list_available_templates(
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.list_available_templates(db, principal)


@router.get("", response_model=PaginatedSmsBulkTasks)
async def list_sms_bulk_tasks(
    page: int = 1,
    per_page: int = Query(default=20, le=100),
    q: str | None = None,
    status: str | None = None,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.list_tasks(db, principal, page=page, per_page=per_page, q=q, status=status)


@router.post("", response_model=SmsBulkTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_sms_bulk_task(
    body: SmsBulkTaskCreate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.create_task(db, principal, body)


@router.get("/{task_id}", response_model=SmsBulkTaskDetail)
async def get_sms_bulk_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.get_task(db, principal, task_id)


@router.put("/{task_id}", response_model=SmsBulkTaskResponse)
async def update_sms_bulk_task(
    task_id: int,
    body: SmsBulkTaskUpdate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.update_task(db, principal, task_id, body)


@router.delete("/{task_id}")
async def delete_sms_bulk_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    await SmsBulkTaskService.delete_task(db, principal, task_id)
    return {"message": "Deleted successfully"}


@router.post("/{task_id}/publish", response_model=SmsBulkTaskResponse)
async def publish_sms_bulk_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.publish_task(db, principal, task_id)


@router.post("/{task_id}/pause", response_model=SmsBulkTaskResponse)
async def pause_sms_bulk_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.pause_task(db, principal, task_id)


@router.post("/{task_id}/resume", response_model=SmsBulkTaskResponse)
async def resume_sms_bulk_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.resume_task(db, principal, task_id)


@router.post("/{task_id}/archive", response_model=SmsBulkTaskResponse)
async def archive_sms_bulk_task(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.archive_task(db, principal, task_id)


@router.get("/{task_id}/targets", response_model=PaginatedSmsBulkTargets)
async def list_sms_bulk_targets(
    task_id: int,
    page: int = 1,
    per_page: int = Query(default=20, le=100),
    q: str | None = None,
    status: str | None = None,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.list_targets(
        db, principal, task_id, page=page, per_page=per_page, q=q, status=status
    )


@router.post(
    "/{task_id}/targets",
    response_model=SmsBulkTargetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sms_bulk_target(
    task_id: int,
    body: SmsBulkTargetCreate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.create_target(db, principal, task_id, body)


@router.post("/{task_id}/targets/import/parse", response_model=SmsBulkImportParseResponse)
async def parse_sms_bulk_target_import(
    task_id: int,
    file: UploadFile = File(...),
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    content = await file.read()
    async with AsyncSessionLocal() as db:
        return await SmsBulkImportService.parse(
            db, redis, principal, task_id, file.filename or "targets.xlsx", content
        )


@router.post("/{task_id}/targets/import/validate", response_model=SmsBulkImportValidateResponse)
async def validate_sms_bulk_target_import(
    task_id: int,
    body: SmsBulkImportMapping,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    return await SmsBulkImportService.validate(db, redis, principal, task_id, body)


@router.post("/{task_id}/targets/import", response_model=SmsBulkImportExecuteResponse)
async def execute_sms_bulk_target_import(
    task_id: int,
    body: SmsBulkImportMapping,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    return await SmsBulkImportService.execute(db, redis, principal, task_id, body)


@router.get("/{task_id}/targets/{target_id}", response_model=SmsBulkTargetDetail)
async def get_sms_bulk_target(
    task_id: int,
    target_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.get_target(db, principal, task_id, target_id)


@router.post("/{task_id}/targets/bulk-delete", response_model=SmsBulkTargetBulkDeleteResponse)
async def bulk_delete_sms_bulk_targets(
    task_id: int,
    body: SmsBulkTargetBulkDeleteRequest,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.bulk_delete_targets(db, principal, task_id, body.target_ids)


@router.post("/{task_id}/targets/resend-failed", response_model=SmsBulkTargetResendResponse)
async def resend_failed_sms_bulk_targets(
    task_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    return await SmsBulkTaskService.resend_failed_targets(db, principal, task_id)
