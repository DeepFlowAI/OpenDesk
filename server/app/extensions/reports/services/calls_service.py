"""Call reports service."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ..lib.buckets import TrendType
from ..lib.call_queries import fetch_call_overview, fetch_call_trend
from ..lib.scope import ReportScope
from ..lib.tz import get_tenant_timezone
from ..lib.validators import validate_date_range


async def get_overview(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    *,
    employee_id: int | None = None,
    report_scope: ReportScope | None = None,
) -> dict:
    validate_date_range(start_date, end_date)
    tz = get_tenant_timezone(tenant_id)
    # call_records.started_at is timestamptz UTC; bound the tenant calendar day
    # in the report timezone (same contract as session reports).
    range_start = datetime.combine(start_date, time.min, tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)

    scope = report_scope or ReportScope(employee_id=employee_id, agent_ids=None, visible_employee_ids=None)
    resolved_employee_id = employee_id if employee_id is not None else scope.employee_id
    agent_ids = scope.agent_ids if resolved_employee_id is None else None

    metrics = await fetch_call_overview(
        db,
        tenant_id,
        range_start,
        range_end,
        employee_id=resolved_employee_id,
        agent_ids=agent_ids,
    )
    return {
        **metrics.model_dump(),
        "as_of": datetime.now(tz).isoformat(),
    }


async def get_trend(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    *,
    employee_id: int | None = None,
    report_scope: ReportScope | None = None,
) -> dict:
    validate_date_range(start_date, end_date)
    tz = get_tenant_timezone(tenant_id)
    range_start = datetime.combine(start_date, time.min, tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)

    scope = report_scope or ReportScope(employee_id=employee_id, agent_ids=None, visible_employee_ids=None)
    resolved_employee_id = employee_id if employee_id is not None else scope.employee_id
    agent_ids = scope.agent_ids if resolved_employee_id is None else None

    rows = await fetch_call_trend(
        db,
        tenant_id,
        range_start,
        range_end,
        trend_type,
        tz,
        range_start_date=start_date,
        range_end_date=end_date,
        employee_id=resolved_employee_id,
        agent_ids=agent_ids,
    )
    return {
        "trend": trend_type.value,
        "buckets": [r.model_dump() for r in rows],
        "as_of": datetime.now(tz).isoformat(),
    }
