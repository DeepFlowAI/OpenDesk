"""Aggregation queries for call reports.

This module is the only DB-facing layer for call-report metrics. Calls are
attributed by ``call_records.started_at`` and scoped to a tenant.

All times passed in MUST be tz-aware (tenant timezone day bounds). Stored CDR
timestamps are UTC timestamptz; trend buckets convert via ``AT TIME ZONE``.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Float, Integer, case, cast, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_record import CallRecord

from ..schemas import CallOverviewMetrics, CallTrendBucketResult
from .buckets import TimeBucket, TrendType, generate_buckets


def _attributed_agent_id():
    """Prefer the last serving agent; fall back to the outbound initiator."""

    cr = CallRecord
    return func.coalesce(cr.last_serving_agent_id, cr.initiator_agent_id)


def _answered_predicate():
    """Direction-aware answer signal on the rebuilt CDR model."""

    cr = CallRecord
    return or_(
        (cr.direction == "inbound") & cr.first_agent_connected_at.is_not(None),
        (cr.direction == "outbound") & cr.customer_connected_at.is_not(None),
    )


async def fetch_call_overview(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    employee_id: int | None = None,
    agent_ids: list[int] | None = None,
) -> CallOverviewMetrics:
    """All seven metrics for the whole tenant or one employee in one date range."""

    if employee_id is not None:
        filters = _employee_filter(tenant_id, range_start, range_end, employee_id=employee_id)
    elif agent_ids is not None:
        if not agent_ids:
            return CallOverviewMetrics()
        filters = _employee_filter(tenant_id, range_start, range_end, employee_ids=agent_ids)
    else:
        filters = _base_filter(tenant_id, range_start, range_end)
    stmt = (
        select(*_metric_columns())
        .where(*filters)
    )
    row = (await db.execute(stmt)).one()
    return _metrics_from_row(row)


async def fetch_call_trend(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    trend_type: TrendType,
    tz: ZoneInfo,
    *,
    range_start_date,
    range_end_date,
    employee_id: int | None = None,
    agent_ids: list[int] | None = None,
) -> list[CallTrendBucketResult]:
    """Per-bucket call metrics with deterministic empty buckets."""

    buckets = generate_buckets(range_start_date, range_end_date, trend_type, tz)
    if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR):
        bucket_key_sql = _distribution_bucket_key_sql(trend_type, tz)
    else:
        bucket_key_sql = _absolute_bucket_key_sql(trend_type, tz)

    if employee_id is not None:
        filters = _employee_filter(tenant_id, range_start, range_end, employee_id=employee_id)
    elif agent_ids is not None:
        if not agent_ids:
            return [
                CallTrendBucketResult(
                    label=bucket.label,
                    bucket_start=bucket.start.isoformat(),
                    bucket_end=bucket.end.isoformat(),
                    metrics=CallOverviewMetrics(),
                )
                for bucket in buckets
            ]
        filters = _employee_filter(tenant_id, range_start, range_end, employee_ids=agent_ids)
    else:
        filters = _base_filter(tenant_id, range_start, range_end)
    stmt = (
        select(bucket_key_sql.label("bkey"), *_metric_columns())
        .where(*filters)
        .group_by(literal_column("bkey"))
    )
    rows = (await db.execute(stmt)).all()
    row_map = {r.bkey: r for r in rows}

    out: list[CallTrendBucketResult] = []
    for bucket in buckets:
        metrics = _metrics_from_row(row_map.get(_bucket_python_key(bucket, trend_type)))
        out.append(
            CallTrendBucketResult(
                label=bucket.label,
                bucket_start=bucket.start.isoformat(),
                bucket_end=bucket.end.isoformat(),
                metrics=metrics,
            )
        )
    return out


async def fetch_call_employees_overview(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    employee_ids: list[int] | None = None,
) -> dict[int, CallOverviewMetrics]:
    """All seven call metrics grouped by attributed employee."""

    if employee_ids is not None and not employee_ids:
        return {}

    agent_id = _attributed_agent_id()
    filters = _employee_filter(
        tenant_id,
        range_start,
        range_end,
        employee_ids=employee_ids,
    )
    stmt = (
        select(agent_id.label("agent_id"), *_metric_columns())
        .where(*filters)
        .group_by(agent_id)
    )
    rows = (await db.execute(stmt)).all()
    return {int(row.agent_id): _metrics_from_row(row) for row in rows if row.agent_id is not None}


def _base_filter(tenant_id: int, range_start: datetime, range_end: datetime) -> list:
    cr = CallRecord
    return [
        cr.tenant_id == tenant_id,
        cr.started_at >= range_start,
        cr.started_at < range_end,
        cr.direction.in_(("inbound", "outbound")),
    ]


def _employee_filter(
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    employee_id: int | None = None,
    employee_ids: list[int] | None = None,
) -> list:
    cr = CallRecord
    agent_id = _attributed_agent_id()
    filters = [
        cr.tenant_id == tenant_id,
        cr.started_at >= range_start,
        cr.started_at < range_end,
        agent_id.is_not(None),
        cr.direction.in_(("inbound", "outbound")),
        or_(
            cr.direction == "outbound",
            (cr.direction == "inbound") & cr.first_agent_connected_at.is_not(None),
        ),
    ]
    if employee_id is not None:
        filters.append(agent_id == employee_id)
    if employee_ids is not None:
        filters.append(agent_id.in_(employee_ids))
    return filters


def _metric_columns() -> tuple:
    cr = CallRecord
    inbound = cr.direction == "inbound"
    outbound = cr.direction == "outbound"
    answered = _answered_predicate()
    inbound_answered = inbound & answered
    outbound_answered = outbound & answered
    talk_seconds = _talk_seconds_expr()

    return (
        func.count(cr.id).label("total_calls"),
        func.sum(case((inbound, 1), else_=0)).label("inbound_calls"),
        func.sum(case((inbound_answered, 1), else_=0)).label("answered_inbound_calls"),
        func.sum(case((outbound, 1), else_=0)).label("outbound_calls"),
        func.sum(case((outbound_answered, 1), else_=0)).label("answered_outbound_calls"),
        func.avg(case((inbound_answered, talk_seconds), else_=None)).label(
            "avg_inbound_talk_seconds"
        ),
        func.avg(case((outbound_answered, talk_seconds), else_=None)).label(
            "avg_outbound_talk_seconds"
        ),
    )


def _talk_seconds_expr():
    cr = CallRecord
    answered_at = func.coalesce(cr.first_agent_connected_at, cr.customer_connected_at)
    return func.coalesce(
        cast(cr.customer_agent_talk_duration_ms, Float) / 1000.0,
        func.extract("epoch", func.now() - answered_at),
    )


def _metrics_from_row(row) -> CallOverviewMetrics:
    if row is None:
        return CallOverviewMetrics()
    return CallOverviewMetrics(
        total_calls=int(row.total_calls or 0),
        inbound_calls=int(row.inbound_calls or 0),
        answered_inbound_calls=int(row.answered_inbound_calls or 0),
        outbound_calls=int(row.outbound_calls or 0),
        answered_outbound_calls=int(row.answered_outbound_calls or 0),
        avg_inbound_talk_seconds=(
            float(row.avg_inbound_talk_seconds)
            if row.avg_inbound_talk_seconds is not None
            else None
        ),
        avg_outbound_talk_seconds=(
            float(row.avg_outbound_talk_seconds)
            if row.avg_outbound_talk_seconds is not None
            else None
        ),
    )


def _distribution_bucket_key_sql(trend_type: TrendType, tz: ZoneInfo):
    # Convert UTC timestamptz into tenant-local wall time before EXTRACT.
    local_ts = func.timezone(str(tz), CallRecord.started_at)
    hour = func.extract("hour", local_ts)
    minute = func.extract("minute", local_ts)
    if trend_type is TrendType.HALF_HOUR:
        return cast(hour * 3600 + (func.floor(minute / 30) * 1800), Integer)
    return cast(hour * 3600, Integer)


def _absolute_bucket_key_sql(trend_type: TrendType, tz: ZoneInfo):
    local_ts = func.timezone(str(tz), CallRecord.started_at)
    if trend_type is TrendType.DAY:
        return func.to_char(func.date_trunc("day", local_ts), "YYYY-MM-DD")
    if trend_type is TrendType.WEEK:
        return func.to_char(func.date_trunc("week", local_ts), 'IYYY"-W"IW')
    if trend_type is TrendType.MONTH:
        return func.to_char(func.date_trunc("month", local_ts), "YYYY-MM")
    raise ValueError(trend_type)


def _bucket_python_key(bucket: TimeBucket, trend_type: TrendType):
    if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR):
        return bucket.offset_seconds
    return bucket.label
