"""Session reports routes (SR1 + SR2)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_current_principal, get_db, require_permission
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import RESOURCE_SESSION_RECORD

from ..lib.buckets import TrendType
from ..lib.scope import build_report_scope
from ..services import employees_service, export_service, overall_service, queues_service, sessions_service

router = APIRouter(prefix="/reports/sessions", tags=["Reports"])


def _parse_date(s: str, field: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, f"Invalid {field} date format, expected YYYY-MM-DD")


@router.get("/overview")
async def get_overview(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    employee_id: int | None = Query(None, description="Optional: scope to one employee"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.view")),
) -> dict:
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(
        db, principal, RESOURCE_SESSION_RECORD, employee_id
    )
    return await sessions_service.get_overview(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        employee_id=employee_id,
        report_scope=report_scope,
        principal=principal,
    )


@router.get("/export")
async def export_report(
    scope: export_service.ExportScope = Query("overall", description="overall, employees, or employee"),
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR, description="Bucket type"),
    employee_id: int | None = Query(None, description="Required when scope=employee"),
    q: str | None = Query(None, description="Employee list search keyword"),
    sort: str = Query("session_count", description="Employee list sort field"),
    order: str = Query("desc", description="asc or desc"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.export")),
) -> Response:
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(
        db, principal, RESOURCE_SESSION_RECORD, employee_id
    )
    content, filename = await export_service.export_session_report(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        scope=scope,
        trend_type=trend,
        employee_id=employee_id,
        q=q,
        sort=sort,
        order=order,
        report_scope=report_scope,
        principal=principal,
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": export_service.content_disposition(filename),
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/trend")
async def get_trend(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR, description="Bucket type"),
    employee_id: int | None = Query(None, description="Optional: scope to one employee"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.view")),
) -> dict:
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(
        db, principal, RESOURCE_SESSION_RECORD, employee_id
    )
    return await sessions_service.get_trend(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        trend,
        employee_id=employee_id,
        report_scope=report_scope,
        principal=principal,
    )


@router.get("/overall/summary")
async def get_overall_summary(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.view")),
) -> dict:
    """Grouped overall report summary (metric-group framework)."""
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(db, principal, RESOURCE_SESSION_RECORD)
    return await overall_service.get_overall_summary(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        report_scope=report_scope,
    )


@router.get("/overall/trend")
async def get_overall_trend(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR, description="Bucket type"),
    group: str | None = Query(None, description="Metric group key; defaults to the first group"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.view")),
) -> dict:
    """Grouped overall report trend for one metric group."""
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(db, principal, RESOURCE_SESSION_RECORD)
    return await overall_service.get_overall_trend(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        trend,
        group=group,
        report_scope=report_scope,
    )


@router.get("/overall/export")
async def export_overall(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR, description="Bucket type"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.export")),
) -> Response:
    """Grouped overall report export (one overview/trend block per group)."""
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(db, principal, RESOURCE_SESSION_RECORD)
    content, filename = await export_service.export_overall_grouped(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        trend,
        report_scope=report_scope,
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": export_service.content_disposition(filename),
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/queues")
async def list_queues(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    q: str | None = Query(None, description="Queue search keyword"),
    queue_type: str | None = Query(None, description="employee_group"),
    sort: str = Query("queued_session_count", description="Queue list sort field"),
    order: str = Query("desc", description="asc or desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.view")),
) -> dict:
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(db, principal, RESOURCE_SESSION_RECORD)
    return await queues_service.list_queues_overview(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        q=q,
        queue_type=queue_type,
        sort=sort,
        order=order,
        page=page,
        per_page=per_page,
        report_scope=report_scope,
        principal=principal,
    )


@router.get("/queues/export")
async def export_queues(
    scope: export_service.QueueExportScope = Query("list", description="list or detail"),
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR, description="Bucket type"),
    group: str | None = Query(None, description="Metric group for detail export"),
    queue_type: str | None = Query(None, description="employee_group"),
    queue_id: int | None = Query(None, description="Required when scope=detail"),
    q: str | None = Query(None, description="Queue list search keyword"),
    sort: str = Query("queued_session_count", description="Queue list sort field"),
    order: str = Query("desc", description="asc or desc"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.export")),
) -> Response:
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(db, principal, RESOURCE_SESSION_RECORD)
    content, filename = await export_service.export_queue_report(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        scope=scope,
        trend_type=trend,
        group=group,
        queue_type=queue_type,
        queue_id=queue_id,
        q=q,
        sort=sort,
        order=order,
        report_scope=report_scope,
        principal=principal,
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": export_service.content_disposition(filename),
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/queues/{queue_type}/{queue_id}")
async def get_queue_detail(
    queue_type: str,
    queue_id: int,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.view")),
) -> dict:
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(db, principal, RESOURCE_SESSION_RECORD)
    return await queues_service.get_queue_detail(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        queue_type,
        queue_id,
        report_scope=report_scope,
        principal=principal,
    )


@router.get("/queues/{queue_type}/{queue_id}/trend")
async def get_queue_trend(
    queue_type: str,
    queue_id: int,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR, description="Bucket type"),
    group: str | None = Query(None, description="Metric group key"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.view")),
) -> dict:
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(db, principal, RESOURCE_SESSION_RECORD)
    return await queues_service.get_queue_trend(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        trend,
        queue_type,
        queue_id,
        group=group,
        report_scope=report_scope,
        principal=principal,
    )


@router.get("/employees")
async def list_employees(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    q: str | None = Query(None, description="Search keyword"),
    sort: str = Query("session_count", description="Sort field"),
    order: str = Query("desc", description="asc or desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.view")),
) -> dict:
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(db, principal, RESOURCE_SESSION_RECORD)
    return await employees_service.list_employees_overview(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        q=q,
        sort=sort,
        order=order,
        page=page,
        per_page=per_page,
        report_scope=report_scope,
    )


@router.get("/employees/{employee_id}")
async def get_employee_detail(
    employee_id: int,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.view")),
) -> dict:
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(
        db, principal, RESOURCE_SESSION_RECORD, employee_id
    )
    return await employees_service.get_employee_detail(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        employee_id,
        report_scope=report_scope,
        principal=principal,
    )


@router.get("/employees/{employee_id}/trend")
async def get_employee_trend(
    employee_id: int,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    trend: TrendType = Query(TrendType.HOUR, description="Bucket type"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission("chat.session_report.view")),
) -> dict:
    start_d = _parse_date(start, "start")
    end_d = _parse_date(end, "end")
    report_scope = await build_report_scope(
        db, principal, RESOURCE_SESSION_RECORD, employee_id
    )
    return await employees_service.get_employee_trend(
        db,
        principal.tenant_id,
        start_d,
        end_d,
        employee_id,
        trend,
        report_scope=report_scope,
        principal=principal,
    )
