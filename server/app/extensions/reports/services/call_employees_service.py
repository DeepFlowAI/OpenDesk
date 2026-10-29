"""Employee call report list, detail, and trend orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import cmp_to_key

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.configs.settings import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.call_agent_fact import CallAgentAfterCallWork, CallAgentReceptionSegment
from app.models.call_queue_fact import CallQueueOffer
from app.models.call_record import CallRecord
from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup, EmployeeGroupMember
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import (
    DataScopeService,
    RESOURCE_CALL_RECORD,
    SCOPE_ALL,
    SCOPE_GROUP,
)

from ..lib.buckets import TrendType, generate_buckets
from ..lib.call_agent_metric_groups import all_groups, get_group
from ..lib.call_agent_metric_groups.base import AgentMetricGroupProvider
from ..lib.call_agent_queries import (
    fetch_agent_distributions,
    fetch_agent_metrics,
    fetch_agent_trend_metrics,
)
from ..lib.call_metric_groups.base import bucket_python_key
from ..lib.tz import get_tenant_timezone
from ..lib.validators import validate_date_range
from ..schemas import (
    CallAgentDataQuality,
    CallAgentOverviewMetrics,
    CallEmployeeOverviewRow,
    CallEmployeesListResponse,
    CallEmployeeSummaryResponse,
    CallEmployeeTrendResponse,
    CallReportCoverage,
    EmployeeBrief,
    MetricDistribution,
    MetricDistributionSlice,
    MetricResult,
    OverallTrendBucket,
    OverallTrendMetricValue,
)


SORT_FIELDS = {"name", "status", *CallAgentOverviewMetrics.model_fields.keys()}
STATUS_FILTERS = {"all", "active", "inactive", "deleted"}


@dataclass(frozen=True)
class _EmployeeInfo:
    brief: EmployeeBrief
    group_ids: frozenset[int]
    group_names: tuple[str, ...]
    search_text: str


async def get_employee_group_name(
    db: AsyncSession,
    tenant_id: int,
    group_id: int,
) -> str | None:
    """Return a tenant-scoped employee group name for export metadata."""
    return await db.scalar(
        select(EmployeeGroup.name).where(
            EmployeeGroup.tenant_id == tenant_id,
            EmployeeGroup.id == group_id,
        )
    )


async def list_employees_overview(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    *,
    principal: EffectivePrincipal,
    q: str | None = None,
    group_id: int | None = None,
    status: str = "all",
    sort: str = "handled_call_count",
    order: str = "desc",
    page: int = 1,
    per_page: int = 20,
    paginate: bool = True,
) -> dict:
    """Return current employees plus scoped historical identities and core metrics."""
    sort = sort if sort in SORT_FIELDS else "handled_call_count"
    order = order.lower() if order.lower() in {"asc", "desc"} else "desc"
    status = status if status in STATUS_FILTERS else "all"
    page = max(1, page)
    per_page = per_page if per_page in {20, 50, 100} else 20
    _, range_end, query_start, tz, coverage = _range_and_coverage(
        tenant_id, start_date, end_date
    )
    current = await _current_employees(db, tenant_id, principal)
    if coverage.status == "unavailable":
        return CallEmployeesListResponse(
            items=[], total=0, page=1, per_page=per_page, pages=1,
            sort=sort, order=order, coverage=coverage,
            as_of=datetime.now(tz).isoformat(),
        ).model_dump()

    scope_predicate = DataScopeService.build_call_record_predicate(principal)
    raw_map, snapshots = await fetch_agent_metrics(
        db, tenant_id, query_start, range_end, scope_predicate=scope_predicate
    )
    keys = set(current)
    if DataScopeService.get_scope(principal, RESOURCE_CALL_RECORD) == SCOPE_ALL:
        keys.update(raw_map)
    rows = [
        CallEmployeeOverviewRow(
            employee=_brief_for_id(employee_id, current, snapshots),
            metrics=CallAgentOverviewMetrics(**_all_metric_values(raw_map.get(employee_id, {}))),
        )
        for employee_id in keys
    ]
    if group_id is not None:
        rows = [
            row for row in rows
            if row.employee.id in current and group_id in current[row.employee.id].group_ids
        ]
    if status != "all":
        rows = [row for row in rows if row.employee.status == status]
    if q and q.strip():
        needle = q.strip().lower()
        rows = [
            row for row in rows
            if needle in current.get(
                row.employee.id,
                _EmployeeInfo(row.employee, frozenset(), (), row.employee.name.lower()),
            ).search_text
        ]
    rows.sort(key=cmp_to_key(lambda left, right: _compare_rows(left, right, sort, order)))
    total = len(rows)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    start_index = (page - 1) * per_page
    quality = await _data_quality(
        db, tenant_id, query_start, range_end, scope_predicate, employee_id=None
    )
    output_rows = rows[start_index : start_index + per_page] if paginate else rows
    output_per_page = per_page if paginate else max(1, total)
    return CallEmployeesListResponse(
        items=output_rows,
        total=total,
        page=page if paginate else 1,
        per_page=output_per_page,
        pages=pages if paginate else 1,
        sort=sort,
        order=order,
        data_quality=quality,
        coverage=coverage,
        as_of=datetime.now(tz).isoformat(),
    ).model_dump()


async def get_employee_summary(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    employee_id: int,
    *,
    principal: EffectivePrincipal,
) -> dict:
    """Return all metric groups and distributions for one scoped employee."""
    _, range_end, query_start, tz, coverage = _range_and_coverage(
        tenant_id, start_date, end_date
    )
    current = await _current_employees(db, tenant_id, principal, employee_id=employee_id)
    scope_predicate = DataScopeService.build_call_record_predicate(principal)
    raw_map: dict[int, dict] = {}
    snapshots: dict[int, str] = {}
    if coverage.status != "unavailable":
        raw_map, snapshots = await fetch_agent_metrics(
            db, tenant_id, query_start, range_end,
            scope_predicate=scope_predicate, employee_id=employee_id,
        )
    if employee_id not in current and employee_id not in raw_map:
        raise NotFoundError("Employee not found or not visible in current data scope")
    raw = raw_map.get(employee_id, {})
    distributions: list[MetricDistribution] = []
    if coverage.status != "unavailable":
        distributions = _distributions(
            await fetch_agent_distributions(
                db, tenant_id, query_start, range_end,
                employee_id=employee_id, scope_predicate=scope_predicate,
            )
        )
    quality = await _data_quality(
        db, tenant_id, query_start, range_end, scope_predicate, employee_id=employee_id
    )
    return CallEmployeeSummaryResponse(
        employee=_brief_for_id(employee_id, current, snapshots),
        group_names=list(current[employee_id].group_names) if employee_id in current else [],
        metrics=_metric_results(raw) if coverage.status != "unavailable" else [],
        distributions=distributions,
        data_quality=quality,
        coverage=coverage,
        as_of=datetime.now(tz).isoformat(),
    ).model_dump()


async def get_employee_trend(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    employee_id: int,
    trend_type: TrendType,
    *,
    group: str | None,
    principal: EffectivePrincipal,
) -> dict:
    """Return one employee metric group's trend and detail-table buckets."""
    _, range_end, query_start, tz, coverage = _range_and_coverage(
        tenant_id, start_date, end_date
    )
    try:
        provider = get_group(group)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    current = await _current_employees(db, tenant_id, principal, employee_id=employee_id)
    scope_predicate = DataScopeService.build_call_record_predicate(principal)
    raw_map: dict[int, dict] = {}
    if coverage.status != "unavailable":
        raw_map, _ = await fetch_agent_metrics(
            db, tenant_id, query_start, range_end,
            scope_predicate=scope_predicate, employee_id=employee_id,
        )
    if employee_id not in current and employee_id not in raw_map:
        raise NotFoundError("Employee not found or not visible in current data scope")
    metadata = _provider_metric_results(provider, {})
    if coverage.status == "unavailable":
        return CallEmployeeTrendResponse(
            trend=trend_type.value, group=provider.key, metrics=metadata, buckets=[],
            coverage=coverage, as_of=datetime.now(tz).isoformat(),
        ).model_dump()
    raw_trend = await fetch_agent_trend_metrics(
        db, tenant_id, query_start, range_end, trend_type, tz,
        employee_id=employee_id, scope_predicate=scope_predicate,
    )
    output = []
    for bucket in generate_buckets(start_date, end_date, trend_type, tz):
        values = provider.values(raw_trend.get(bucket_python_key(bucket, trend_type), {}))
        output.append(
            OverallTrendBucket(
                label=bucket.label,
                bucket_start=bucket.start.isoformat(),
                bucket_end=bucket.end.isoformat(),
                metrics=[
                    OverallTrendMetricValue(
                        key=descriptor.key,
                        value=values.get(descriptor.key),
                        format=descriptor.format,
                    )
                    for descriptor in provider.descriptors
                ],
            )
        )
    return CallEmployeeTrendResponse(
        trend=trend_type.value,
        group=provider.key,
        metrics=metadata,
        buckets=output,
        coverage=coverage,
        as_of=datetime.now(tz).isoformat(),
    ).model_dump()


def _range_and_coverage(tenant_id: int, start_date: date, end_date: date):
    validate_date_range(start_date, end_date)
    tz = get_tenant_timezone(tenant_id)
    range_start = datetime.combine(start_date, time.min, tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    effective_at = settings.CALL_AGENT_REPORT_DATA_EFFECTIVE_AT
    if effective_at.tzinfo is None or effective_at.utcoffset() is None:
        raise RuntimeError("CALL_AGENT_REPORT_DATA_EFFECTIVE_AT must include a timezone")
    effective_at = effective_at.astimezone(timezone.utc)
    status = "available"
    if range_end <= effective_at:
        status = "unavailable"
    elif range_start < effective_at:
        status = "partial"
    query_start = max(range_start, effective_at.astimezone(tz))
    coverage = CallReportCoverage(
        effective_at=effective_at.isoformat(),
        requested_start=range_start.isoformat(),
        requested_end=range_end.isoformat(),
        actual_start=query_start.isoformat() if status != "unavailable" else None,
        actual_end=range_end.isoformat() if status != "unavailable" else None,
        truncated=status == "partial",
        status=status,
    )
    return range_start, range_end, query_start, tz, coverage


async def _current_employees(
    db: AsyncSession,
    tenant_id: int,
    principal: EffectivePrincipal,
    *,
    employee_id: int | None = None,
) -> dict[int, _EmployeeInfo]:
    scope = DataScopeService.get_scope(principal, RESOURCE_CALL_RECORD)
    stmt = select(Employee).where(Employee.tenant_id == tenant_id)
    if employee_id is not None:
        stmt = stmt.where(Employee.id == employee_id)
    if scope == SCOPE_GROUP:
        peers = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        stmt = stmt.where(Employee.id.in_(sorted(set(peers) | {principal.user_id})))
    elif scope != SCOPE_ALL:
        stmt = stmt.where(Employee.id == principal.user_id)
    employees = list((await db.execute(stmt)).scalars().all())
    ids = [item.id for item in employees]
    group_map: dict[int, list[tuple[int, str]]] = {}
    if ids:
        rows = (
            await db.execute(
                select(EmployeeGroupMember.employee_id, EmployeeGroup.id, EmployeeGroup.name)
                .join(EmployeeGroup, EmployeeGroup.id == EmployeeGroupMember.group_id)
                .where(
                    EmployeeGroup.tenant_id == tenant_id,
                    EmployeeGroupMember.employee_id.in_(ids),
                )
            )
        ).all()
        for emp_id, group_id, group_name in rows:
            group_map.setdefault(int(emp_id), []).append((int(group_id), str(group_name)))
    output = {}
    for item in employees:
        groups = sorted(group_map.get(item.id, []), key=lambda value: value[1].lower())
        name = item.display_name or item.name or item.username or f"Employee #{item.id}"
        brief = EmployeeBrief(
            id=item.id,
            name=name,
            username=item.username,
            display_name=item.display_name,
            email=item.email,
            avatar=item.avatar,
            is_active=item.is_active,
            status="active" if item.is_active else "inactive",
        )
        output[item.id] = _EmployeeInfo(
            brief=brief,
            group_ids=frozenset(value[0] for value in groups),
            group_names=tuple(value[1] for value in groups),
            search_text=" ".join(
                filter(None, [name, item.name, item.display_name, item.username, item.email])
            ).lower(),
        )
    return output


async def _data_quality(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    scope_predicate: ColumnElement | None,
    *,
    employee_id: int | None,
) -> CallAgentDataQuality:
    segment_filters: list[ColumnElement] = [
        CallAgentReceptionSegment.tenant_id == tenant_id,
        CallAgentReceptionSegment.started_at >= range_start,
        CallAgentReceptionSegment.started_at < range_end,
    ]
    if employee_id is not None:
        segment_filters.append(CallAgentReceptionSegment.agent_id == employee_id)
    if scope_predicate is not None:
        segment_filters.append(scope_predicate)
    row = (
        await db.execute(
            select(
                func.count(func.distinct(CallRecord.id))
                .filter(CallRecord.finalization_status == "pending")
                .label("processing"),
                func.count(func.distinct(CallRecord.id))
                .filter(and_(
                    CallRecord.lifecycle_status == "ended",
                    CallAgentReceptionSegment.result_reliable.is_(False),
                ))
                .label("reception_incomplete"),
                func.count(func.distinct(CallRecord.id))
                .filter(CallRecord.finalization_status == "failed")
                .label("failed"),
            )
            .select_from(CallAgentReceptionSegment)
            .join(CallRecord, CallRecord.id == CallAgentReceptionSegment.call_record_id)
            .where(*segment_filters)
        )
    ).one()
    offer_agent = func.coalesce(CallQueueOffer.agent_ref_id, CallQueueOffer.agent_id)
    offer_filters: list[ColumnElement] = [
        CallQueueOffer.tenant_id == tenant_id,
        CallQueueOffer.started_at >= range_start,
        CallQueueOffer.started_at < range_end,
        CallRecord.lifecycle_status == "ended",
        CallQueueOffer.result_reliable.is_(False),
    ]
    if employee_id is not None:
        offer_filters.append(offer_agent == employee_id)
    if scope_predicate is not None:
        offer_filters.append(scope_predicate)
    offer_incomplete = int(await db.scalar(
        select(func.count(CallQueueOffer.id))
        .join(CallRecord, CallRecord.id == CallQueueOffer.call_record_id)
        .where(*offer_filters)
    ) or 0)
    acw_filters: list[ColumnElement] = [
        CallAgentAfterCallWork.tenant_id == tenant_id,
        CallAgentReceptionSegment.started_at >= range_start,
        CallAgentReceptionSegment.started_at < range_end,
        CallAgentAfterCallWork.result_reliable.is_(False),
    ]
    if employee_id is not None:
        acw_filters.append(CallAgentAfterCallWork.agent_id == employee_id)
    if scope_predicate is not None:
        acw_filters.append(scope_predicate)
    acw_incomplete = int(await db.scalar(
        select(func.count(CallAgentAfterCallWork.id))
        .join(
            CallAgentReceptionSegment,
            CallAgentReceptionSegment.id == CallAgentAfterCallWork.reception_segment_id,
        )
        .join(CallRecord, CallRecord.id == CallAgentAfterCallWork.call_record_id)
        .where(*acw_filters)
    ) or 0)
    return CallAgentDataQuality(
        processing=int(row.processing or 0),
        reception_incomplete=int(row.reception_incomplete or 0),
        offer_incomplete=offer_incomplete,
        after_call_work_incomplete=acw_incomplete,
        failed=int(row.failed or 0),
    )


def _brief_for_id(
    employee_id: int,
    current: dict[int, _EmployeeInfo],
    snapshots: dict[int, str],
) -> EmployeeBrief:
    if employee_id in current:
        return current[employee_id].brief
    return EmployeeBrief(
        id=employee_id,
        name=snapshots.get(employee_id) or f"Deleted employee #{employee_id}",
        is_active=False,
        status="deleted",
    )


def _all_metric_values(raw: dict[str, float | int | None]) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for provider in all_groups():
        values.update(provider.values(raw))
    return values


def _metric_results(raw: dict[str, float | int | None]) -> list[MetricResult]:
    output: list[MetricResult] = []
    for provider in all_groups():
        output.extend(_provider_metric_results(provider, raw))
    return output


def _provider_metric_results(
    provider: AgentMetricGroupProvider,
    raw: dict[str, float | int | None],
) -> list[MetricResult]:
    values = provider.values(raw)
    return [
        MetricResult(
            key=descriptor.key,
            value=values.get(descriptor.key),
            format=descriptor.format,
            level=descriptor.level,
            group=provider.key,
        )
        for descriptor in provider.descriptors
    ]


def _distributions(counts: dict[str, dict[str, int]]) -> list[MetricDistribution]:
    definitions = (
        ("reception_entry_reason", "workload", (
            "initial", "agent_transfer", "queue_transfer", "outbound",
            "supervisor_takeover", "other", "unknown",
        )),
        ("offer_result", "offer_response", (
            "accepted", "rejected", "timeout", "canceled", "bridge_failed",
        )),
        ("handle_duration", "efficiency", (
            "0_1m", "1_3m", "3_5m", "5_10m", "over_10m",
        )),
        ("reception_end_reason", "collaboration", (
            "call_ended", "transfer_completed", "agent_exit", "supervisor_takeover",
            "system_error", "other", "unknown",
        )),
    )
    output = []
    for key, group, slice_keys in definitions:
        values = counts.get(key, {})
        slices = [
            MetricDistributionSlice(key=item, label=item, value=values.get(item, 0))
            for item in slice_keys
        ]
        output.append(MetricDistribution(
            key=key, group=group, total=sum(item.value for item in slices), slices=slices
        ))
    return output


def _compare_rows(
    left: CallEmployeeOverviewRow,
    right: CallEmployeeOverviewRow,
    sort: str,
    order: str,
) -> int:
    if sort == "name":
        result = _compare_values(left.employee.name.lower(), right.employee.name.lower())
    elif sort == "status":
        result = _compare_values(left.employee.status, right.employee.status)
    else:
        left_value = getattr(left.metrics, sort)
        right_value = getattr(right.metrics, sort)
        if left_value is None or right_value is None:
            return _compare_nullable(left_value, right_value)
        result = _compare_values(left_value, right_value)
    if result == 0 and sort == "handled_call_count" and order == "desc":
        secondary = _compare_values(
            left.metrics.participated_call_count, right.metrics.participated_call_count
        )
        if secondary != 0:
            return -secondary
    if result == 0:
        return _compare_values(left.employee.name.lower(), right.employee.name.lower())
    return result if order == "asc" else -result


def _compare_values(left: object, right: object) -> int:
    if left is None and right is None:
        return 0
    if left is None:
        return 1
    if right is None:
        return -1
    if left == right:
        return 0
    return -1 if left < right else 1


def _compare_nullable(left: object, right: object) -> int:
    if left is None and right is None:
        return 0
    if left is None:
        return 1
    if right is None:
        return -1
    return _compare_values(left, right)
