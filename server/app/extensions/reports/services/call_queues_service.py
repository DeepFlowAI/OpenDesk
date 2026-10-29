"""Call queue report list, detail, and trend orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import cmp_to_key
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.configs.settings import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.call_queue_fact import CallQueueVisit
from app.models.call_record import CallRecord
from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import (
    DataScopeService,
    RESOURCE_CALL_RECORD,
    SCOPE_ALL,
    SCOPE_GROUP,
)

from ..lib.buckets import TrendType, generate_buckets
from ..lib.call_queue_metric_groups import all_groups, get_group
from ..lib.call_queue_metric_groups.base import QueueMetricGroupProvider
from ..lib.call_queue_queries import (
    fetch_queue_distributions,
    fetch_queue_metrics,
    fetch_queue_trend_metrics,
)
from ..lib.call_metric_groups.base import bucket_python_key
from ..lib.tz import get_tenant_timezone
from ..lib.validators import validate_date_range
from ..schemas import (
    CallQueueBrief,
    CallQueueDataQuality,
    CallQueueListResponse,
    CallQueueOverviewMetrics,
    CallQueueOverviewRow,
    CallQueueSummaryResponse,
    CallQueueTrendResponse,
    CallReportCoverage,
    MetricDistribution,
    MetricDistributionSlice,
    MetricResult,
    OverallTrendBucket,
    OverallTrendMetricValue,
)


QUEUE_TYPES = {"employee_group", "employee"}
SORT_FIELDS = {
    "name",
    "queue_type",
    "status",
    *CallQueueOverviewMetrics.model_fields.keys(),
}


@dataclass(frozen=True)
class _QueueInfo:
    brief: CallQueueBrief
    search_text: str


async def list_queues(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    *,
    principal: EffectivePrincipal,
    q: str | None = None,
    queue_type: str | None = "employee_group",
    sort: str = "queue_entry_count",
    order: str = "desc",
    page: int = 1,
    per_page: int = 20,
    paginate: bool = True,
) -> dict:
    """Return current queues plus visible historical queues and core metrics."""
    normalized_type = _normalize_queue_type(queue_type)
    sort = sort if sort in SORT_FIELDS else "queue_entry_count"
    order = order.lower() if order.lower() in {"asc", "desc"} else "desc"
    page = max(1, page)
    per_page = max(1, min(per_page, 100))
    range_start, range_end, tz, coverage = _range_and_coverage(
        tenant_id, start_date, end_date
    )
    if coverage.status == "unavailable":
        return CallQueueListResponse(
            items=[],
            total=0,
            page=1,
            per_page=per_page,
            pages=1,
            sort=sort,
            order=order,
            coverage=coverage,
            as_of=datetime.now(tz).isoformat(),
        ).model_dump()

    current = await _current_queues(db, tenant_id, normalized_type, principal)
    scope_predicate = DataScopeService.build_call_record_predicate(principal)
    raw_map, snapshots = await fetch_queue_metrics(
        db,
        tenant_id,
        range_start,
        range_end,
        scope_predicate=scope_predicate,
        queue_type=normalized_type,
    )
    keys = set(current) | set(raw_map)
    rows = [
        CallQueueOverviewRow(
            queue=_brief_for_key(key, current, snapshots),
            metrics=CallQueueOverviewMetrics(**_all_metric_values(raw_map.get(key, {}))),
        )
        for key in keys
    ]
    if q and q.strip():
        needle = q.strip().lower()
        rows = [
            row
            for row in rows
            if needle
            in current.get(
                (row.queue.queue_type, row.queue.queue_id),
                _QueueInfo(row.queue, row.queue.name.lower()),
            ).search_text
        ]
    rows.sort(key=cmp_to_key(lambda left, right: _compare_rows(left, right, sort, order)))
    total = len(rows)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    start_index = (page - 1) * per_page
    quality = await _data_quality(
        db,
        tenant_id,
        range_start,
        range_end,
        scope_predicate,
        queue_type=normalized_type,
    )
    output_rows = rows[start_index : start_index + per_page] if paginate else rows
    output_per_page = per_page if paginate else max(1, total)
    return CallQueueListResponse(
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


async def get_queue_summary(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    queue_type: str,
    queue_id: int,
    *,
    principal: EffectivePrincipal,
) -> dict:
    """Return all metric groups and distributions for one queue."""
    normalized_type = _normalize_queue_type(queue_type, required=True)
    range_start, range_end, tz, coverage = _range_and_coverage(
        tenant_id, start_date, end_date
    )
    current = await _current_queues(
        db, tenant_id, normalized_type, principal, queue_id=queue_id
    )
    scope_predicate = DataScopeService.build_call_record_predicate(principal)
    raw_map, snapshots = await fetch_queue_metrics(
        db,
        tenant_id,
        range_start,
        range_end,
        scope_predicate=scope_predicate,
        queue_type=normalized_type,
        queue_id=queue_id,
    )
    key = (normalized_type, queue_id)
    if key not in current and key not in raw_map:
        raise NotFoundError("Queue not found or not visible in current data scope")
    brief = _brief_for_key(key, current, snapshots)
    raw = raw_map.get(key, {})
    metrics = _metric_results(raw) if coverage.status != "unavailable" else []
    distributions: list[MetricDistribution] = []
    if coverage.status != "unavailable":
        counts = await fetch_queue_distributions(
            db,
            tenant_id,
            range_start,
            range_end,
            queue_type=normalized_type,
            queue_id=queue_id,
            scope_predicate=scope_predicate,
        )
        distributions = _distributions(counts)
    quality = await _data_quality(
        db,
        tenant_id,
        range_start,
        range_end,
        scope_predicate,
        queue_type=normalized_type,
        queue_id=queue_id,
    )
    return CallQueueSummaryResponse(
        queue=brief,
        metrics=metrics,
        distributions=distributions,
        data_quality=quality,
        coverage=coverage,
        as_of=datetime.now(tz).isoformat(),
    ).model_dump()


async def get_queue_trend(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    queue_type: str,
    queue_id: int,
    trend_type: TrendType,
    *,
    group: str | None,
    principal: EffectivePrincipal,
) -> dict:
    """Return one queue metric group's trend and detail-table buckets."""
    normalized_type = _normalize_queue_type(queue_type, required=True)
    range_start, range_end, tz, coverage = _range_and_coverage(
        tenant_id, start_date, end_date
    )
    try:
        provider = get_group(group)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    current = await _current_queues(
        db, tenant_id, normalized_type, principal, queue_id=queue_id
    )
    scope_predicate = DataScopeService.build_call_record_predicate(principal)
    raw_map, _ = await fetch_queue_metrics(
        db,
        tenant_id,
        range_start,
        range_end,
        scope_predicate=scope_predicate,
        queue_type=normalized_type,
        queue_id=queue_id,
    )
    if (normalized_type, queue_id) not in current and not raw_map:
        raise NotFoundError("Queue not found or not visible in current data scope")
    metric_meta = _provider_metric_results(provider, {})
    if coverage.status == "unavailable":
        return CallQueueTrendResponse(
            trend=trend_type.value,
            group=provider.key,
            metrics=metric_meta,
            buckets=[],
            coverage=coverage,
            as_of=datetime.now(tz).isoformat(),
        ).model_dump()
    raw_trend = await fetch_queue_trend_metrics(
        db,
        tenant_id,
        range_start,
        range_end,
        trend_type,
        tz,
        queue_type=normalized_type,
        queue_id=queue_id,
        scope_predicate=scope_predicate,
    )
    buckets = generate_buckets(start_date, end_date, trend_type, tz)
    output = []
    for bucket in buckets:
        raw = raw_trend.get(bucket_python_key(bucket, trend_type), {})
        values = provider.values(raw)
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
    return CallQueueTrendResponse(
        trend=trend_type.value,
        group=provider.key,
        metrics=metric_meta,
        buckets=output,
        coverage=coverage,
        as_of=datetime.now(tz).isoformat(),
    ).model_dump()


def _range_and_coverage(
    tenant_id: int,
    start_date: date,
    end_date: date,
) -> tuple[datetime, datetime, ZoneInfo, CallReportCoverage]:
    validate_date_range(start_date, end_date)
    tz = get_tenant_timezone(tenant_id)
    range_start = datetime.combine(start_date, time.min, tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    effective_at = settings.CALL_QUEUE_REPORT_DATA_EFFECTIVE_AT
    if effective_at.tzinfo is None or effective_at.utcoffset() is None:
        raise RuntimeError("CALL_QUEUE_REPORT_DATA_EFFECTIVE_AT must include a timezone")
    effective_at = effective_at.astimezone(timezone.utc)
    status = "available"
    if range_end <= effective_at:
        status = "unavailable"
    elif range_start < effective_at:
        status = "partial"
    coverage = CallReportCoverage(
        effective_at=effective_at.isoformat(),
        requested_start=range_start.isoformat(),
        requested_end=range_end.isoformat(),
        actual_start=range_start.isoformat(),
        actual_end=range_end.isoformat(),
        truncated=False,
        status=status,
    )
    return range_start, range_end, tz, coverage


async def _current_queues(
    db: AsyncSession,
    tenant_id: int,
    queue_type: str | None,
    principal: EffectivePrincipal,
    *,
    queue_id: int | None = None,
) -> dict[tuple[str, int], _QueueInfo]:
    scope = DataScopeService.get_scope(principal, RESOURCE_CALL_RECORD)
    output: dict[tuple[str, int], _QueueInfo] = {}
    if queue_type in {None, "employee_group"}:
        stmt = select(EmployeeGroup).where(EmployeeGroup.tenant_id == tenant_id)
        if queue_id is not None and queue_type == "employee_group":
            stmt = stmt.where(EmployeeGroup.id == queue_id)
        elif scope != SCOPE_ALL:
            if not principal.group_ids:
                stmt = None
            else:
                stmt = stmt.where(EmployeeGroup.id.in_(principal.group_ids))
        if stmt is not None:
            for row in (await db.execute(stmt)).scalars().all():
                brief = CallQueueBrief(
                    queue_type="employee_group",
                    queue_id=row.id,
                    name=row.name or "Unknown queue",
                )
                output[(brief.queue_type, brief.queue_id)] = _QueueInfo(
                    brief, brief.name.lower()
                )
    if queue_type in {None, "employee"}:
        stmt = select(Employee).where(Employee.tenant_id == tenant_id)
        if queue_id is not None and queue_type == "employee":
            stmt = stmt.where(Employee.id == queue_id)
        elif scope == SCOPE_GROUP:
            visible = await DataScopeService.get_group_peer_employee_ids(
                db, principal.group_ids
            )
            visible = sorted(set(visible) | {principal.user_id})
            stmt = stmt.where(Employee.id.in_(visible))
        elif scope != SCOPE_ALL:
            stmt = stmt.where(Employee.id == principal.user_id)
        for row in (await db.execute(stmt)).scalars().all():
            name = row.display_name or row.name or row.username or "Unknown queue"
            brief = CallQueueBrief(
                queue_type="employee",
                queue_id=row.id,
                name=name,
                status="active" if row.is_active else "inactive",
            )
            output[(brief.queue_type, brief.queue_id)] = _QueueInfo(
                brief,
                " ".join(filter(None, [name, row.name, row.username, row.email])).lower(),
            )
    return output


async def _data_quality(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    scope_predicate: ColumnElement | None,
    *,
    queue_type: str | None = None,
    queue_id: int | None = None,
) -> CallQueueDataQuality:
    filters = [
        CallQueueVisit.tenant_id == tenant_id,
        CallQueueVisit.entered_at >= range_start,
        CallQueueVisit.entered_at < range_end,
    ]
    if scope_predicate is not None:
        filters.append(scope_predicate)
    if queue_type is not None:
        filters.append(CallQueueVisit.queue_type == queue_type)
    if queue_id is not None:
        filters.append(CallQueueVisit.queue_id == queue_id)
    ended = CallRecord.lifecycle_status == "ended"
    row = (
        await db.execute(
            select(
                func.count(func.distinct(CallRecord.id)).filter(
                    and_(ended, CallRecord.finalization_status == "pending")
                ).label("pending"),
                func.count(func.distinct(CallRecord.id)).filter(
                    and_(ended, CallRecord.finalization_status == "incomplete")
                ).label("incomplete"),
                func.count(func.distinct(CallRecord.id)).filter(
                    and_(ended, CallRecord.finalization_status == "failed")
                ).label("failed"),
            )
            .select_from(CallQueueVisit)
            .join(CallRecord, CallRecord.id == CallQueueVisit.call_record_id)
            .where(*filters)
        )
    ).one()
    return CallQueueDataQuality(
        pending=int(row.pending or 0),
        incomplete=int(row.incomplete or 0),
        failed=int(row.failed or 0),
    )


def _all_metric_values(
    raw: dict[str, float | int | None],
) -> dict[str, float | None]:
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
    provider: QueueMetricGroupProvider,
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


def _brief_for_key(
    key: tuple[str, int],
    current: dict[tuple[str, int], _QueueInfo],
    snapshots: dict[tuple[str, int], str],
) -> CallQueueBrief:
    if key in current:
        return current[key].brief
    return CallQueueBrief(
        queue_type=key[0],
        queue_id=key[1],
        name=snapshots.get(key) or f"Deleted queue #{key[1]}",
        status="deleted",
    )


def _distributions(counts: dict[str, dict[str, int]]) -> list[MetricDistribution]:
    definitions = (
        (
            "queue_exit_result",
            "queue_outcomes",
            ("answered", "abandoned", "timeout", "transfer_out", "canceled", "failed"),
        ),
        (
            "queue_wait_duration",
            "queue_waiting",
            ("0_5s", "5_20s", "20_60s", "60_180s", "over_180s"),
        ),
        (
            "offer_result",
            "agent_response",
            ("accepted", "rejected", "timeout", "canceled", "bridge_failed"),
        ),
    )
    output = []
    for key, group, slices in definitions:
        values = counts.get(key, {})
        items = [
            MetricDistributionSlice(key=slice_key, label=slice_key, value=values.get(slice_key, 0))
            for slice_key in slices
        ]
        output.append(
            MetricDistribution(
                key=key,
                group=group,
                total=sum(item.value for item in items),
                slices=items,
            )
        )
    return output


def _normalize_queue_type(value: str | None, *, required: bool = False) -> str | None:
    if value in {None, "", "all"}:
        if required:
            raise ValidationError("Queue type is required")
        return None
    if value not in QUEUE_TYPES:
        raise ValidationError("Unsupported queue type")
    return value


def _compare_rows(
    left: CallQueueOverviewRow,
    right: CallQueueOverviewRow,
    sort: str,
    order: str,
) -> int:
    if sort in {"name", "queue_type", "status"}:
        left_value = left.queue.name if sort == "name" else getattr(left.queue, sort)
        right_value = right.queue.name if sort == "name" else getattr(right.queue, sort)
    else:
        left_value = getattr(left.metrics, sort)
        right_value = getattr(right.metrics, sort)
    if left_value is None or right_value is None:
        return _compare_values(left_value, right_value)
    result = _compare_values(left_value, right_value)
    if result == 0:
        result = _compare_values(left.queue.name.lower(), right.queue.name.lower())
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
