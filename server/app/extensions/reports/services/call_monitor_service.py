"""Call monitor service — today's tenant-wide and per-employee call counters."""
from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_status import AgentStatus
from app.models.employee import Employee

from ..lib.call_queries import fetch_call_employees_overview, fetch_call_overview
from ..lib.scope import ReportScope
from ..lib.tz import get_tenant_timezone
from ..schemas import (
    CallMonitorEmployeeRow,
    CallMonitorToday,
    CallOverviewMetrics,
    EmployeeBrief,
)


async def get_call_monitor(
    db: AsyncSession,
    tenant_id: int,
    *,
    report_scope: ReportScope | None = None,
) -> dict:
    tz = get_tenant_timezone(tenant_id)
    now = datetime.now(tz)
    range_start = datetime.combine(now.date(), time.min, tzinfo=tz)
    range_end = now

    scope = report_scope or ReportScope(employee_id=None, agent_ids=None, visible_employee_ids=None)
    overall = await fetch_call_overview(
        db,
        tenant_id,
        range_start,
        range_end,
        employee_id=scope.employee_id,
        agent_ids=scope.agent_ids if scope.employee_id is None else None,
    )
    employees, metrics_map = await _load_monitored_employees(
        db,
        tenant_id,
        range_start,
        range_end,
        visible_employee_ids=scope.visible_employee_ids,
    )
    status_map = await _load_call_center_statuses(
        db,
        tenant_id,
        [employee.id for employee in employees],
    )

    rows: list[CallMonitorEmployeeRow] = []
    for employee in employees:
        metrics = metrics_map.get(employee.id)
        rows.append(
            CallMonitorEmployeeRow(
                employee=EmployeeBrief(
                    id=employee.id,
                    name=employee.name or "",
                    username=employee.username,
                    display_name=employee.display_name,
                    email=employee.email,
                    avatar=employee.avatar,
                    is_active=employee.is_active,
                ),
                call_center_status=status_map.get(employee.id, "offline"),
                answered_inbound_calls=(
                    metrics.answered_inbound_calls if metrics is not None else 0
                ),
                outbound_calls=metrics.outbound_calls if metrics is not None else 0,
                answered_outbound_calls=(
                    metrics.answered_outbound_calls if metrics is not None else 0
                ),
            )
        )

    rows.sort(key=_sort_key)
    return {
        "today": CallMonitorToday(
            range_label=f"今日 {range_start:%H:%M} - {now:%H:%M}",
            total_calls=overall.total_calls,
            inbound_calls=overall.inbound_calls,
            answered_inbound_calls=overall.answered_inbound_calls,
            outbound_calls=overall.outbound_calls,
            answered_outbound_calls=overall.answered_outbound_calls,
        ).model_dump(),
        "employees": [row.model_dump() for row in rows],
        "as_of": now.isoformat(),
    }


async def _load_monitored_employees(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    visible_employee_ids: list[int] | None = None,
) -> tuple[list[Employee], dict[int, CallOverviewMetrics]]:
    active_stmt = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.is_active.is_(True),
    )
    if visible_employee_ids is not None:
        if not visible_employee_ids:
            return [], {}
        active_stmt = active_stmt.where(Employee.id.in_(visible_employee_ids))
    active_result = await db.execute(active_stmt)
    active_employees = list(active_result.scalars().all())

    metrics_map = await fetch_call_employees_overview(
        db,
        tenant_id,
        range_start,
        range_end,
        employee_ids=visible_employee_ids,
    )

    employee_by_id = {employee.id: employee for employee in active_employees}
    missing_ids = sorted(set(metrics_map) - set(employee_by_id))
    if missing_ids:
        missing_result = await db.execute(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.id.in_(missing_ids),
            )
        )
        for employee in missing_result.scalars().all():
            employee_by_id[employee.id] = employee

    return list(employee_by_id.values()), metrics_map


async def _load_call_center_statuses(
    db: AsyncSession,
    tenant_id: int,
    employee_ids: list[int],
) -> dict[int, str]:
    if not employee_ids:
        return {}

    result = await db.execute(
        select(AgentStatus).where(
            AgentStatus.tenant_id == tenant_id,
            AgentStatus.employee_id.in_(employee_ids),
        )
    )
    return {row.employee_id: row.status for row in result.scalars().all()}


def _sort_key(row: CallMonitorEmployeeRow) -> tuple[int, int, int, str]:
    name = (
        row.employee.display_name
        or row.employee.name
        or row.employee.username
        or ""
    ).lower()
    return (
        -row.answered_inbound_calls,
        -row.outbound_calls,
        -row.answered_outbound_calls,
        name,
    )
