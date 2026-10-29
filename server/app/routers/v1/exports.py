"""Authenticated personal export task endpoints."""
from typing import Annotated, Literal

from pydantic import BeforeValidator
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.db.deps import get_current_principal_short_session, get_current_user
from app.schemas.export_task import (
    ExportNotificationRequest, ExportNotifications, ExportTaskCreate, ExportTaskIDs,
    ExportTaskDownload, ExportTaskList, ExportTaskResponse, ExportTaskStatus,
)
from app.schemas.permission import EffectivePrincipal
from app.services.export_task_service import ExportTaskService

router = APIRouter(prefix="/exports", tags=["Export tasks"])


@router.get("/status", response_model=ExportTaskStatus)
async def status(principal: EffectivePrincipal = Depends(get_current_principal_short_session)) -> dict:
    return await ExportTaskService.status(principal)


@router.get("", response_model=ExportTaskList)
async def list_tasks(page: int = Query(1, ge=1), per_page: Annotated[Literal[20, 50, 100], BeforeValidator(int)] = 20,
                     principal: EffectivePrincipal = Depends(get_current_principal_short_session)) -> dict:
    return await ExportTaskService.list_tasks(principal, page, per_page)


@router.post("", response_model=ExportTaskResponse, status_code=201)
async def create_task(body: ExportTaskCreate,
                      principal: EffectivePrincipal = Depends(get_current_principal_short_session)) -> ExportTaskResponse:
    return await ExportTaskService.create(principal, body)


@router.get("/by-key/{key}", response_model=ExportTaskResponse)
async def by_key(key: UUID,
                 principal: EffectivePrincipal = Depends(get_current_principal_short_session)) -> ExportTaskResponse:
    return await ExportTaskService.by_key(principal, key)


@router.post("/viewed", status_code=204)
async def viewed(body: ExportTaskIDs,
                 principal: EffectivePrincipal = Depends(get_current_principal_short_session)) -> None:
    await ExportTaskService.viewed(principal, body.ids)


@router.post("/notifications", response_model=ExportNotifications)
async def notifications(body: ExportNotificationRequest,
                        principal: EffectivePrincipal = Depends(get_current_principal_short_session)) -> dict:
    return await ExportTaskService.notifications(principal, body.since)


@router.post("/{task_id}/cancel", response_model=ExportTaskResponse)
async def cancel(task_id: UUID,
                 principal: EffectivePrincipal = Depends(get_current_principal_short_session)) -> ExportTaskResponse:
    return await ExportTaskService.cancel(principal, task_id)


@router.get("/{task_id}/download", response_model=ExportTaskDownload)
async def download(task_id: UUID, response: Response,
                   principal: EffectivePrincipal = Depends(get_current_principal_short_session),
                   user_payload: dict = Depends(get_current_user)) -> ExportTaskDownload:
    from app.services.export_task_worker import ExportTaskWorker

    url = await ExportTaskWorker.download(principal, task_id, user_payload)
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return ExportTaskDownload(url=url)
