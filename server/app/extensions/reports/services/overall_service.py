"""Overall session report service (grouped metric framework).

Composes the registered metric-group providers into the group-first API
responses. Independent of the legacy flat ``sessions_service`` (which still
serves the employee report and the online monitor).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ..lib.buckets import TrendType, generate_buckets
from ..lib.metric_groups import OverallContext, all_groups, get_group
from ..lib.metric_groups.base import MetricGroupProvider
from ..lib.queries import _bucket_python_key
from ..lib.scope import ReportScope
from ..lib.tz import get_tenant_timezone
from ..lib.validators import validate_date_range
from ..schemas import (
    MetricResult,
    OverallSummaryResponse,
    OverallTrendBucket,
    OverallTrendMetricValue,
    OverallTrendResponse,
)


def _resolve_agent_ids(report_scope: ReportScope | None) -> list[int] | None:
    """Map the report scope to the session agent filter.

    None = no restriction (all sessions). A list (possibly empty) restricts to
    the visible agents, mirroring the legacy overall report's scoping.
    """
    if report_scope is None:
        return None
    if report_scope.employee_id is not None:
        return [report_scope.employee_id]
    return report_scope.agent_ids


def _build_context(
    tenant_id: int,
    start_date: date,
    end_date: date,
    report_scope: ReportScope | None,
) -> OverallContext:
    tz = get_tenant_timezone(tenant_id)
    range_start = datetime.combine(start_date, time.min, tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    return OverallContext(
        tenant_id=tenant_id,
        range_start=range_start,
        range_end=range_end,
        tz=tz,
        agent_ids=_resolve_agent_ids(report_scope),
    )


def _group_metrics(group: MetricGroupProvider, values: dict[str, float | None]) -> list[MetricResult]:
    """Flatten one group's descriptors + computed values into metric results,
    tagging each with the group key so the frontend can group by it."""
    return [
        MetricResult(
            key=d.key,
            value=values.get(d.key),
            format=d.format,
            level=d.level,
            group=group.key,
            available=True,
        )
        for d in group.descriptors
        if d.key in values
    ]


async def get_overall_summary(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    *,
    report_scope: ReportScope | None = None,
) -> dict:
    validate_date_range(start_date, end_date)
    ctx = _build_context(tenant_id, start_date, end_date, report_scope)

    metrics: list[MetricResult] = []
    distributions = []
    for group in all_groups():
        values = await group.summary(db, ctx)
        metrics.extend(_group_metrics(group, values))
        distributions.extend(await group.summary_distributions(db, ctx))

    return OverallSummaryResponse(
        metrics=metrics,
        distributions=distributions,
        as_of=datetime.now(ctx.tz).isoformat(),
    ).model_dump()


async def get_overall_trend(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    *,
    group: str | None = None,
    report_scope: ReportScope | None = None,
) -> dict:
    validate_date_range(start_date, end_date)
    ctx = _build_context(tenant_id, start_date, end_date, report_scope)
    provider = get_group(group)

    buckets = generate_buckets(start_date, end_date, trend_type, ctx.tz)
    trend_map = await provider.trend(db, ctx, trend_type, buckets)

    trendable = await provider.visible_trend_descriptors(db, ctx)
    out_buckets: list[OverallTrendBucket] = []
    for b in buckets:
        bkey = _bucket_python_key(b, trend_type)
        values = trend_map.get(bkey, {})
        out_buckets.append(
            OverallTrendBucket(
                label=b.label,
                bucket_start=b.start.isoformat(),
                bucket_end=b.end.isoformat(),
                metrics=[
                    OverallTrendMetricValue(
                        key=d.key,
                        value=values.get(d.key, 0),
                        format=d.format,
                    )
                    for d in trendable
                ],
            )
        )

    return OverallTrendResponse(
        trend=trend_type.value,
        group=provider.key,
        metrics=[
            MetricResult(
                key=d.key,
                value=None,
                format=d.format,
                level=d.level,
                group=provider.key,
            )
            for d in trendable
        ],
        buckets=out_buckets,
        as_of=datetime.now(ctx.tz).isoformat(),
    ).model_dump()
