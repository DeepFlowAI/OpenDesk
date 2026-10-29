"""Grouped overall call-report service."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.models.call_record import CallRecord
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import DataScopeService

from ..lib.buckets import TrendType, generate_buckets
from ..lib.call_metric_groups import CallOverallContext, all_groups, get_group
from ..lib.call_metric_groups.base import (
    CallMetricDescriptor,
    CallMetricGroupProvider,
    bucket_python_key,
)
from ..lib.tz import get_tenant_timezone
from ..lib.validators import validate_date_range
from ..schemas import (
    CallOverallSummaryResponse,
    CallOverallTrendResponse,
    CallReportCoverage,
    CallReportDataQuality,
    MetricResult,
    OverallTrendBucket,
    OverallTrendMetricValue,
)


def _effective_at() -> datetime:
    value = settings.CALL_REPORT_DATA_EFFECTIVE_AT
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError("CALL_REPORT_DATA_EFFECTIVE_AT must include a timezone")
    return value.astimezone(timezone.utc)


def _build_context_and_coverage(
    tenant_id: int,
    start_date: date,
    end_date: date,
    principal: EffectivePrincipal,
) -> tuple[CallOverallContext, CallReportCoverage]:
    tz = get_tenant_timezone(tenant_id)
    requested_start = datetime.combine(start_date, time.min, tzinfo=tz)
    requested_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    effective_at = _effective_at()
    coverage = CallReportCoverage(
        effective_at=effective_at.isoformat(),
        requested_start=requested_start.isoformat(),
        requested_end=requested_end.isoformat(),
        actual_start=requested_start.isoformat(),
        actual_end=requested_end.isoformat(),
        truncated=False,
        status="partial" if requested_start < effective_at else "available",
    )
    return (
        CallOverallContext(
            tenant_id=tenant_id,
            range_start=requested_start,
            range_end=requested_end,
            tz=tz,
            scope_predicate=DataScopeService.build_call_record_predicate(principal),
        ),
        coverage,
    )


def _metric_value(
    descriptor: CallMetricDescriptor,
    value: float | None,
    *,
    interval_end: datetime,
) -> float | None:
    if descriptor.projection_required and interval_end <= _effective_at():
        return None
    return value


def _metric_results(
    provider: CallMetricGroupProvider,
    values: dict[str, float | None],
    *,
    interval_end: datetime,
) -> list[MetricResult]:
    return [
        MetricResult(
            key=descriptor.key,
            value=_metric_value(
                descriptor,
                values.get(descriptor.key),
                interval_end=interval_end,
            ),
            format=descriptor.format,
            level=descriptor.level,
            group=provider.key,
            available=True,
        )
        for descriptor in provider.descriptors
    ]


async def _data_quality(
    db: AsyncSession,
    ctx: CallOverallContext,
) -> CallReportDataQuality:
    cr = CallRecord
    ended = cr.lifecycle_status == "ended"
    row = (
        await db.execute(
            select(
                func.count(cr.id).filter(
                    and_(ended, cr.finalization_status == "pending")
                ).label("pending"),
                func.count(cr.id).filter(
                    and_(ended, cr.finalization_status == "incomplete")
                ).label("incomplete"),
                func.count(cr.id).filter(
                    and_(ended, cr.finalization_status == "failed")
                ).label("failed"),
                func.count(cr.id).filter(
                    and_(ended, cr.satisfaction_result.is_(None))
                ).label("satisfaction_pending"),
            ).where(*ctx.filters())
        )
    ).one()
    return CallReportDataQuality(
        pending=int(row.pending or 0),
        incomplete=int(row.incomplete or 0),
        failed=int(row.failed or 0),
        satisfaction_pending=int(row.satisfaction_pending or 0),
    )


async def get_overall_summary(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    *,
    principal: EffectivePrincipal,
) -> dict:
    validate_date_range(start_date, end_date)
    ctx, coverage = _build_context_and_coverage(
        tenant_id,
        start_date,
        end_date,
        principal,
    )
    tz = get_tenant_timezone(tenant_id)
    metrics: list[MetricResult] = []
    distributions = []
    for provider in all_groups():
        values = await provider.summary(db, ctx)
        metrics.extend(_metric_results(provider, values, interval_end=ctx.range_end))
        distributions.extend(await provider.summary_distributions(db, ctx))
    if ctx.range_end <= _effective_at():
        distributions = [
            item
            for item in distributions
            if item.key not in {"inbound_human_funnel", "hangup_stage"}
        ]
    quality = await _data_quality(db, ctx)
    return CallOverallSummaryResponse(
        metrics=metrics,
        distributions=distributions,
        data_quality=quality,
        coverage=coverage,
        as_of=datetime.now(tz).isoformat(),
    ).model_dump()


async def get_overall_trend(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    *,
    group: str | None,
    principal: EffectivePrincipal,
) -> dict:
    validate_date_range(start_date, end_date)
    ctx, coverage = _build_context_and_coverage(
        tenant_id,
        start_date,
        end_date,
        principal,
    )
    tz = get_tenant_timezone(tenant_id)
    provider = get_group(group)
    descriptors = provider.trendable_descriptors()
    buckets = generate_buckets(start_date, end_date, trend_type, tz)
    trend_map = await provider.trend(db, ctx, trend_type, buckets)
    empty_values = provider.empty_values()
    output_buckets: list[OverallTrendBucket] = []
    for bucket in buckets:
        values = trend_map.get(bucket_python_key(bucket, trend_type), empty_values)
        interval_end = (
            ctx.range_end
            if bucket.offset_seconds is not None
            else min(bucket.end, ctx.range_end)
        )
        output_buckets.append(
            OverallTrendBucket(
                label=bucket.label,
                bucket_start=bucket.start.isoformat(),
                bucket_end=bucket.end.isoformat(),
                metrics=[
                    OverallTrendMetricValue(
                        key=descriptor.key,
                        value=_metric_value(
                            descriptor,
                            values.get(descriptor.key),
                            interval_end=interval_end,
                        ),
                        format=descriptor.format,
                    )
                    for descriptor in descriptors
                ],
            )
        )
    return CallOverallTrendResponse(
        trend=trend_type.value,
        group=provider.key,
        metrics=[
            MetricResult(
                key=descriptor.key,
                value=None,
                format=descriptor.format,
                level=descriptor.level,
                group=provider.key,
            )
            for descriptor in descriptors
        ],
        buckets=output_buckets,
        coverage=coverage,
        as_of=datetime.now(tz).isoformat(),
    ).model_dump()
