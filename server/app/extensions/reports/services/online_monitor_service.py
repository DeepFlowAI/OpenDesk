"""Online monitor service (SR3) — merges today's overall + per-employee + Redis state."""
from __future__ import annotations

from datetime import datetime, time
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import and_, cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AgentOnlineStatus
from app.models.employee import Employee
from app.models.role import EmployeeRole, Role
from app.services.agent_status_service import AgentStatusService

from ..lib.queries import fetch_employees_overview, fetch_overview
from ..lib.scope import ReportScope
from ..lib.tz import get_tenant_timezone
from ..schemas import EmployeeBrief, OverviewMetrics


_STATUS_PRIORITY = {
    AgentOnlineStatus.ONLINE.value: 0,
    AgentOnlineStatus.BUSY.value: 1,
    AgentOnlineStatus.OFFLINE.value: 2,
    "unknown": 3,
}


async def get_online_monitor(
    db: AsyncSession,
    redis: aioredis.Redis | None,
    tenant_id: int,
    *,
    report_scope: ReportScope | None = None,
) -> dict[str, Any]:
    tz = get_tenant_timezone(tenant_id)
    now = datetime.now(tz)
    range_start = datetime.combine(now.date(), time.min, tzinfo=tz)
    range_end = now

    scope = report_scope or ReportScope(employee_id=None, agent_ids=None, visible_employee_ids=None)
    overall = await fetch_overview(
        db,
        tenant_id,
        range_start,
        range_end,
        employee_id=scope.employee_id,
        agent_ids=scope.agent_ids if scope.employee_id is None else None,
    )
    today_payload = {
        "range_label": f"今日 {range_start:%H:%M} - {now:%H:%M}",
        "session_count": overall.session_count,
        "avg_duration_seconds": overall.avg_duration_seconds,
    }

    employees = await _load_eligible_employees(db, tenant_id, scope.visible_employee_ids)
    metrics_map = await fetch_employees_overview(
        db, tenant_id, range_start, range_end,
        employee_ids=[e.id for e in employees] or None,
    )

    # One Redis round-trip for the whole employee list. Falls back to offline
    # for everyone if the pipeline fails (e.g. Redis transient outage); when
    # ``redis`` itself wasn't injected (e.g. test without redis dep), we mark
    # the rows "unknown" so the UI can surface "data may be outdated" rather
    # than reporting false offline.
    if redis is not None:
        status_map = await AgentStatusService.get_statuses_bulk(
            redis,
            tenant_id,
            [(e.id, e.max_concurrent) for e in employees],
        )
    else:
        status_map = {}

    employee_rows: list[dict[str, Any]] = []
    for e in employees:
        status_data = status_map.get(e.id)
        if status_data is None:
            status_value = "unknown" if redis is None else AgentOnlineStatus.OFFLINE.value
            current_count = 0
        else:
            status_value = status_data["status"]
            current_count = status_data["current_count"]
        m = metrics_map.get(e.id, OverviewMetrics())
        employee_rows.append({
            "employee": EmployeeBrief(
                id=e.id,
                name=e.name or "",
                display_name=e.display_name,
                email=e.email,
                avatar=e.avatar,
                is_active=e.is_active,
            ).model_dump(),
            "status": status_value,
            "current_count": current_count,
            "max_concurrent": e.max_concurrent,
            "session_count": m.session_count,
            "avg_duration_seconds": m.avg_duration_seconds,
        })

    employee_rows.sort(key=_sort_key)

    return {
        "today": today_payload,
        "employees": employee_rows,
        "as_of": now.isoformat(),
    }


async def _load_eligible_employees(
    db: AsyncSession,
    tenant_id: int,
    visible_employee_ids: list[int] | None = None,
) -> list[Employee]:
    permissions_jsonb = cast(Role.permissions, JSONB)
    eligible_ids = (
        select(Employee.id)
        .outerjoin(EmployeeRole, EmployeeRole.employee_id == Employee.id)
        .outerjoin(Role, Role.id == EmployeeRole.role_id)
        .where(
            Employee.tenant_id == tenant_id,
            Employee.is_active == True,  # noqa: E712 — SQL Boolean comparison
            or_(
                Employee.is_super_admin.is_(True),
                and_(
                    Role.tenant_id == tenant_id,
                    Role.is_active.is_(True),
                    permissions_jsonb.contains(["chat.workspace.use"]),
                ),
            ),
        )
        .distinct()
    )
    if visible_employee_ids is not None:
        if not visible_employee_ids:
            return []
        eligible_ids = eligible_ids.where(Employee.id.in_(visible_employee_ids))
    stmt = select(Employee).where(Employee.id.in_(eligible_ids))
    return list((await db.execute(stmt)).scalars().all())


def _sort_key(row: dict[str, Any]):
    status_rank = _STATUS_PRIORITY.get(row["status"], 99)
    name = (row["employee"]["display_name"] or row["employee"]["name"] or "").lower()
    # negative for desc fields so the natural asc sort gives desc effect
    return (
        status_rank,
        -int(row["current_count"] or 0),
        -int(row["session_count"] or 0),
        name,
    )
