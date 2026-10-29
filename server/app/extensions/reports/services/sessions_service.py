"""Session reports service — composes SR0 query primitives into API responses.

Shared between SR1 (overall) and SR2 (per-employee): the same service handles
both by passing/omitting ``employee_id``.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import DataScopeService, RESOURCE_OFFLINE_MESSAGE

from ..lib.buckets import TrendType
from ..lib.queries import fetch_overview, fetch_trend
from ..lib.scope import ReportScope
from ..lib.tz import get_tenant_timezone
from ..lib.validators import validate_date_range

_BUSINESS_METRIC_FIELDS = {
    "bot_session_count",
    "bot_handoff_count",
    "queued_session_count",
    "avg_queue_duration_seconds",
    "offline_message_count",
    "can_view_offline_messages",
}


async def get_overview(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    *,
    employee_id: int | None = None,
    report_scope: ReportScope | None = None,
    principal: EffectivePrincipal | None = None,
) -> dict:
    validate_date_range(start_date, end_date)
    tz = get_tenant_timezone(tenant_id)
    range_start = datetime.combine(start_date, time.min, tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)

    scope = report_scope or ReportScope(employee_id=employee_id, agent_ids=None, visible_employee_ids=None)
    employee_denied = (
        employee_id is not None
        and scope.visible_employee_ids is not None
        and employee_id not in set(scope.visible_employee_ids)
    )
    resolved_employee_id = None if employee_denied else (
        employee_id if employee_id is not None else scope.employee_id
    )
    agent_ids = [] if employee_denied else (
        scope.agent_ids if resolved_employee_id is None else None
    )
    include_business_metrics = employee_id is None
    include_offline_messages, offline_predicate = await _offline_message_scope(
        db,
        principal,
        include_business_metrics,
    )

    metrics = await fetch_overview(
        db,
        tenant_id,
        range_start,
        range_end,
        employee_id=resolved_employee_id,
        agent_ids=agent_ids,
        include_business_metrics=include_business_metrics,
        include_offline_messages=include_offline_messages,
        offline_message_scope_predicate=offline_predicate,
    )
    payload = metrics.model_dump()
    if not include_business_metrics:
        _strip_business_metrics(payload)
    return {
        **payload,
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
    principal: EffectivePrincipal | None = None,
) -> dict:
    validate_date_range(start_date, end_date)
    tz = get_tenant_timezone(tenant_id)
    range_start = datetime.combine(start_date, time.min, tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)

    scope = report_scope or ReportScope(employee_id=employee_id, agent_ids=None, visible_employee_ids=None)
    employee_denied = (
        employee_id is not None
        and scope.visible_employee_ids is not None
        and employee_id not in set(scope.visible_employee_ids)
    )
    resolved_employee_id = None if employee_denied else (
        employee_id if employee_id is not None else scope.employee_id
    )
    agent_ids = [] if employee_denied else (
        scope.agent_ids if resolved_employee_id is None else None
    )
    include_business_metrics = employee_id is None
    include_offline_messages, offline_predicate = await _offline_message_scope(
        db,
        principal,
        include_business_metrics,
    )

    rows = await fetch_trend(
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
        include_business_metrics=include_business_metrics,
        include_offline_messages=include_offline_messages,
        offline_message_scope_predicate=offline_predicate,
    )
    buckets = [r.model_dump() for r in rows]
    if not include_business_metrics:
        for bucket in buckets:
            _strip_business_metrics(bucket["metrics"])
    return {
        "trend": trend_type.value,
        "buckets": buckets,
        "as_of": datetime.now(tz).isoformat(),
    }


async def _offline_message_scope(
    db: AsyncSession,
    principal: EffectivePrincipal | None,
    enabled: bool,
) -> tuple[bool, object | None]:
    if not enabled or principal is None or not principal.has_permission("chat.offline_message.view"):
        return False, None
    peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
    return True, DataScopeService.build_offline_message_predicate(
        principal,
        peer_ids,
    )


def _strip_business_metrics(metrics: dict) -> None:
    for field in _BUSINESS_METRIC_FIELDS:
        metrics.pop(field, None)
