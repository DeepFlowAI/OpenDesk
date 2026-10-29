"""Employee-dimension session report service (SR2)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.employee import Employee
from app.schemas.permission import EffectivePrincipal

from ..lib.queries import fetch_employees_overview
from ..lib.scope import ReportScope
from ..lib.tz import get_tenant_timezone
from ..lib.validators import validate_date_range
from ..schemas import EmployeeBrief, EmployeeOverviewRow, OverviewMetrics
from ..lib.buckets import TrendType
from . import sessions_service


_SORT_FIELDS = {
    "session_count",
    "message_count",
    "user_message_count",
    "agent_message_count",
    "avg_duration_seconds",
    "reception_segment_count",
    "reception_participated_session_count",
    "reception_final_session_count",
    "reception_transfer_in_count",
    "reception_transfer_out_count",
    "name",
}

_BUSINESS_METRIC_FIELDS = {
    "bot_session_count",
    "bot_handoff_count",
    "queued_session_count",
    "avg_queue_duration_seconds",
    "offline_message_count",
    "can_view_offline_messages",
}

_RECEPTION_METRIC_FIELDS = {
    "reception_segment_count",
    "reception_participated_session_count",
    "reception_final_session_count",
    "reception_transfer_in_count",
    "reception_transfer_out_count",
}


async def list_employees_overview(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    *,
    q: str | None = None,
    sort: str = "session_count",
    order: str = "desc",
    page: int = 1,
    per_page: int = 20,
    paginate: bool = True,
    report_scope: ReportScope | None = None,
) -> dict:
    if sort not in _SORT_FIELDS:
        sort = "session_count"
    order = order.lower()
    if order not in ("asc", "desc"):
        order = "desc"
    page = max(1, page)
    if paginate:
        per_page = max(1, min(per_page, 100))

    validate_date_range(start_date, end_date)
    tz = get_tenant_timezone(tenant_id)
    range_start = datetime.combine(start_date, time.min, tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)

    # Load all employees of the tenant (including inactive — see requirement §1.2).
    stmt = select(Employee).where(Employee.tenant_id == tenant_id)
    if report_scope and report_scope.visible_employee_ids is not None:
        if not report_scope.visible_employee_ids:
            return {
                "items": [],
                "total": 0,
                "page": 1,
                "per_page": per_page if paginate else 1,
                "pages": 1,
                "sort": sort,
                "order": order,
                "as_of": datetime.now(tz).isoformat(),
            }
        stmt = stmt.where(Employee.id.in_(report_scope.visible_employee_ids))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Employee.name.ilike(like),
                Employee.display_name.ilike(like),
                Employee.username.ilike(like),
                Employee.email.ilike(like),
            )
        )
    employees = (await db.execute(stmt)).scalars().all()

    metrics_map = await fetch_employees_overview(
        db, tenant_id, range_start, range_end,
        employee_ids=[e.id for e in employees] or None,
    )

    rows: list[EmployeeOverviewRow] = []
    for e in employees:
        metrics = metrics_map.get(e.id, OverviewMetrics())
        rows.append(
            EmployeeOverviewRow(
                employee=EmployeeBrief(
                    id=e.id,
                    name=e.name or "",
                    username=e.username,
                    display_name=e.display_name,
                    email=e.email,
                    avatar=e.avatar,
                    is_active=e.is_active,
                ),
                metrics=metrics,
            )
        )

    rows.sort(key=lambda r: _sort_key(r, sort), reverse=(order == "desc"))
    # Stable secondary tiebreaker on name asc — sorted is stable, so a second pass
    # by name first (asc) then re-sort by main key keeps secondary alpha order.
    # Simpler: rely on Python sort stability + initial pre-sort by name asc.

    total = len(rows)
    if paginate:
        pages = max(1, (total + per_page - 1) // per_page)
        start_idx = (page - 1) * per_page
        items = rows[start_idx:start_idx + per_page]
    else:
        page = 1
        per_page = max(total, 1)
        pages = 1
        items = rows

    return {
        "items": [_employee_row_payload(r) for r in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "sort": sort,
        "order": order,
        "as_of": datetime.now(tz).isoformat(),
    }


async def get_employee_detail(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    employee_id: int,
    *,
    report_scope: ReportScope | None = None,
    principal: EffectivePrincipal | None = None,
) -> dict:
    employee = await _get_visible_employee(db, tenant_id, employee_id, report_scope)
    overview = await sessions_service.get_overview(
        db,
        tenant_id,
        start_date,
        end_date,
        employee_id=employee_id,
        report_scope=report_scope,
        principal=principal,
    )
    return {
        "employee": _employee_brief(employee).model_dump(),
        "metrics": overview_metrics_payload(overview),
        "as_of": overview["as_of"],
    }


async def get_employee_trend(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    employee_id: int,
    trend_type: TrendType,
    *,
    report_scope: ReportScope | None = None,
    principal: EffectivePrincipal | None = None,
) -> dict:
    await _get_visible_employee(db, tenant_id, employee_id, report_scope)
    trend = await sessions_service.get_trend(
        db,
        tenant_id,
        start_date,
        end_date,
        trend_type,
        employee_id=employee_id,
        report_scope=report_scope,
        principal=principal,
    )
    for bucket in trend["buckets"]:
        for field in _RECEPTION_METRIC_FIELDS:
            bucket["metrics"].pop(field, None)
    return trend


async def get_visible_employee(
    db: AsyncSession,
    tenant_id: int,
    employee_id: int,
    report_scope: ReportScope | None = None,
) -> Employee:
    return await _get_visible_employee(db, tenant_id, employee_id, report_scope)


def _employee_row_payload(row: EmployeeOverviewRow) -> dict:
    payload = row.model_dump()
    for field in _BUSINESS_METRIC_FIELDS:
        payload["metrics"].pop(field, None)
    return payload


def overview_metrics_payload(overview: dict) -> dict:
    payload = OverviewMetrics.model_validate(overview).model_dump()
    for field in _BUSINESS_METRIC_FIELDS:
        payload.pop(field, None)
    return payload


async def _get_visible_employee(
    db: AsyncSession,
    tenant_id: int,
    employee_id: int,
    report_scope: ReportScope | None,
) -> Employee:
    if (
        report_scope is not None
        and report_scope.visible_employee_ids is not None
        and employee_id not in set(report_scope.visible_employee_ids)
    ):
        raise NotFoundError("Employee not found or inaccessible")

    stmt = select(Employee).where(Employee.tenant_id == tenant_id, Employee.id == employee_id)
    employee = (await db.execute(stmt)).scalar_one_or_none()
    if employee is None:
        raise NotFoundError("Employee not found or inaccessible")
    return employee


def _employee_brief(employee: Employee) -> EmployeeBrief:
    return EmployeeBrief(
        id=employee.id,
        name=employee.name or "",
        username=employee.username,
        display_name=employee.display_name,
        email=employee.email,
        avatar=employee.avatar,
        is_active=employee.is_active,
    )


def _sort_key(row: EmployeeOverviewRow, field: str):
    if field == "name":
        return (row.employee.display_name or row.employee.name or "").lower()
    if field == "avg_duration_seconds":
        # Null-last regardless of direction — treat None as -inf when desc, +inf when asc.
        # We'll handle this by returning a tuple (has_value, value). For desc, missing
        # should sort to the bottom; sorted(reverse=True) inverts so we need (1, val) for
        # present and (0, 0) for absent so present > absent.
        v = row.metrics.avg_duration_seconds
        return (1 if v is not None else 0, v or 0)
    v = getattr(row.metrics, field, 0)
    return (1, v or 0)
