"""Call report routes."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_current_principal, get_db, require_permission
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import RESOURCE_CALL_RECORD

from ..lib.buckets import TrendType
from ..lib.scope import build_report_scope
from ..schemas import (
    CallEmployeesListResponse,
    CallEmployeeSummaryResponse,
    CallEmployeeTrendResponse,
    CallQueueListResponse,
    CallQueueSummaryResponse,
    CallQueueTrendResponse,
    CallOverallSummaryResponse,
    CallOverallTrendResponse,
    CallOverviewResponse,
    CallTrendResponse,
)
from ..services import (
    call_employees_service,
    call_export_service,
    call_overall_service,
    call_queues_service,
    calls_service,
)

router = APIRouter(prefix="/reports/calls", tags=["Reports"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, f"Invalid {field} date format, expected YYYY-MM-DD")


@router.get("/overview", response_model=CallOverviewResponse)
async def get_overview(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    employee_id: int | None = Query(None, description="Optional: scope to one employee"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.view")),
) -> dict:
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(
        db, principal, RESOURCE_CALL_RECORD, employee_id
    )
    return await calls_service.get_overview(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        employee_id=employee_id,
        report_scope=report_scope,
    )


@router.get("/trend", response_model=CallTrendResponse)
async def get_trend(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR, description="Bucket type"),
    employee_id: int | None = Query(None, description="Optional: scope to one employee"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.view")),
) -> dict:
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(
        db, principal, RESOURCE_CALL_RECORD, employee_id
    )
    return await calls_service.get_trend(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        trend,
        employee_id=employee_id,
        report_scope=report_scope,
    )


@router.get("/overall/summary", response_model=CallOverallSummaryResponse)
async def get_overall_summary(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.view")),
) -> dict:
    """Return all grouped call-report metrics and distributions."""

    return await call_overall_service.get_overall_summary(
        db,
        principal.tenant_id,
        _parse_date(start, "start"),
        _parse_date(end, "end"),
        principal=principal,
    )


@router.get("/overall/trend", response_model=CallOverallTrendResponse)
async def get_overall_trend(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR, description="Bucket type"),
    group: str | None = Query(None, description="Metric group key"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.view")),
) -> dict:
    """Return all trendable metrics for one call-report group."""

    return await call_overall_service.get_overall_trend(
        db,
        principal.tenant_id,
        _parse_date(start, "start"),
        _parse_date(end, "end"),
        trend,
        group=group,
        principal=principal,
    )


@router.get("/overall/export")
async def export_call_overall(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR, description="Bucket type"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.export")),
) -> Response:
    content, filename = await call_export_service.export_overall(
        db, principal.tenant_id, _parse_date(start, "start"), _parse_date(end, "end"), trend, principal
    )
    return _xlsx_response(content, filename)


@router.get("/employees", response_model=CallEmployeesListResponse)
async def list_employees(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    q: str | None = Query(None, description="Search keyword"),
    group_id: int | None = Query(None, description="Current employee group"),
    status: str = Query("all", description="all, active, inactive, or deleted"),
    sort: str = Query("handled_call_count", description="Sort field"),
    order: str = Query("desc", description="asc or desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.view")),
) -> dict:
    return await call_employees_service.list_employees_overview(
        db,
        principal.tenant_id,
        _parse_date(start, "start"),
        _parse_date(end, "end"),
        principal=principal,
        q=q,
        group_id=group_id,
        status=status,
        sort=sort,
        order=order,
        page=page,
        per_page=per_page,
    )


@router.get("/employees/export")
async def export_call_employees(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    q: str | None = Query(None),
    group_id: int | None = Query(None),
    status: str = Query("all"),
    sort: str = Query("handled_call_count"),
    order: str = Query("desc"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.export")),
) -> Response:
    content, filename = await call_export_service.export_employee_list(
        db, principal.tenant_id, _parse_date(start, "start"), _parse_date(end, "end"),
        q=q, group_id=group_id, status=status, sort=sort, order=order, principal=principal,
    )
    return _xlsx_response(content, filename)


@router.get("/employees/{employee_id}/export")
async def export_call_employee_detail(
    employee_id: int,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.export")),
) -> Response:
    content, filename = await call_export_service.export_employee_detail(
        db, principal.tenant_id, _parse_date(start, "start"), _parse_date(end, "end"), trend,
        employee_id, principal,
    )
    return _xlsx_response(content, filename)


@router.get(
    "/employees/{employee_id}/summary",
    response_model=CallEmployeeSummaryResponse,
)
async def get_call_employee_summary(
    employee_id: int,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.view")),
) -> dict:
    """Return all summary groups for one independently scoped employee."""
    return await call_employees_service.get_employee_summary(
        db,
        principal.tenant_id,
        _parse_date(start, "start"),
        _parse_date(end, "end"),
        employee_id,
        principal=principal,
    )


@router.get(
    "/employees/{employee_id}/trend",
    response_model=CallEmployeeTrendResponse,
)
async def get_call_employee_trend(
    employee_id: int,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR),
    group: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.view")),
) -> dict:
    """Return one employee metric group's trend buckets."""
    return await call_employees_service.get_employee_trend(
        db,
        principal.tenant_id,
        _parse_date(start, "start"),
        _parse_date(end, "end"),
        employee_id,
        trend,
        group=group,
        principal=principal,
    )


@router.get("/queues", response_model=CallQueueListResponse)
async def list_call_queues(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    q: str | None = Query(None, description="Queue-name search"),
    queue_type: str = Query("employee_group"),
    sort: str = Query("queue_entry_count"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.view")),
) -> dict:
    """Return the scoped queue comparison list."""
    return await call_queues_service.list_queues(
        db,
        principal.tenant_id,
        _parse_date(start, "start"),
        _parse_date(end, "end"),
        principal=principal,
        q=q,
        queue_type=queue_type,
        sort=sort,
        order=order,
        page=page,
        per_page=per_page,
    )


@router.get("/queues/export")
async def export_call_queues(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    q: str | None = Query(None),
    queue_type: str = Query("employee_group"),
    sort: str = Query("queue_entry_count"),
    order: str = Query("desc"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.export")),
) -> Response:
    content, filename = await call_export_service.export_queue_list(
        db, principal.tenant_id, _parse_date(start, "start"), _parse_date(end, "end"),
        q=q, queue_type=queue_type, sort=sort, order=order, principal=principal,
    )
    return _xlsx_response(content, filename)


@router.get("/queues/{queue_type}/{queue_id}/export")
async def export_call_queue_detail(
    queue_type: str,
    queue_id: int,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.export")),
) -> Response:
    content, filename = await call_export_service.export_queue_detail(
        db, principal.tenant_id, _parse_date(start, "start"), _parse_date(end, "end"), trend,
        queue_type, queue_id, principal,
    )
    return _xlsx_response(content, filename)


@router.get(
    "/queues/{queue_type}/{queue_id}/summary",
    response_model=CallQueueSummaryResponse,
)
async def get_call_queue_summary(
    queue_type: str,
    queue_id: int,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.view")),
) -> dict:
    """Return all summary groups for one scoped queue."""
    return await call_queues_service.get_queue_summary(
        db,
        principal.tenant_id,
        _parse_date(start, "start"),
        _parse_date(end, "end"),
        queue_type,
        queue_id,
        principal=principal,
    )


@router.get(
    "/queues/{queue_type}/{queue_id}/trend",
    response_model=CallQueueTrendResponse,
)
async def get_call_queue_trend(
    queue_type: str,
    queue_id: int,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR),
    group: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("call.report.view")),
) -> dict:
    """Return one queue metric group's trend buckets."""
    return await call_queues_service.get_queue_trend(
        db,
        principal.tenant_id,
        _parse_date(start, "start"),
        _parse_date(end, "end"),
        queue_type,
        queue_id,
        trend,
        group=group,
        principal=principal,
    )


def _xlsx_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": call_export_service.content_disposition(filename),
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
