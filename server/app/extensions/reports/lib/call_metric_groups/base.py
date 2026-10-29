"""Shared framework for grouped call-report metric providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, cast, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.call_record import CallRecord

from ...schemas import MetricDistribution, MetricDistributionSlice, MetricFormat, MetricLevel
from ..buckets import TimeBucket, TrendType


@dataclass(frozen=True)
class CallMetricDescriptor:
    """Stable metadata for one call-report metric."""

    key: str
    format: MetricFormat = MetricFormat.INTEGER
    level: MetricLevel = MetricLevel.PRIMARY
    trendable: bool = True
    projection_required: bool = False


@dataclass(frozen=True)
class CallOverallContext:
    """Tenant, date, and row-level scope shared by all call providers."""

    tenant_id: int
    range_start: datetime
    range_end: datetime
    tz: ZoneInfo
    scope_predicate: ColumnElement | None = None

    def filters(self) -> list[ColumnElement]:
        filters: list[ColumnElement] = [
            CallRecord.tenant_id == self.tenant_id,
            CallRecord.started_at >= self.range_start,
            CallRecord.started_at < self.range_end,
            CallRecord.direction.in_(("inbound", "outbound")),
        ]
        if self.scope_predicate is not None:
            filters.append(self.scope_predicate)
        return filters


class CallMetricGroupProvider(ABC):
    """Contract for one independently maintained call metric group."""

    key: str = ""
    descriptors: list[CallMetricDescriptor] = field(default_factory=list)

    @abstractmethod
    def metric_columns(self) -> tuple:
        """Return aggregate SQL expressions used for summary and trend."""

    @abstractmethod
    def values_from_row(self, row) -> dict[str, float | None]:
        """Convert one aggregate row into public metric values."""

    async def summary(
        self,
        db: AsyncSession,
        ctx: CallOverallContext,
    ) -> dict[str, float | None]:
        row = (await db.execute(select(*self.metric_columns()).where(*ctx.filters()))).one()
        return self.values_from_row(row)

    async def trend(
        self,
        db: AsyncSession,
        ctx: CallOverallContext,
        trend_type: TrendType,
        buckets: list[TimeBucket],
    ) -> dict[object, dict[str, float | None]]:
        del buckets
        bucket_key = _bucket_key_sql(trend_type, ctx.tz)
        rows = (
            await db.execute(
                select(bucket_key.label("bkey"), *self.metric_columns())
                .where(*ctx.filters())
                .group_by(literal_column("bkey"))
            )
        ).all()
        return {row.bkey: self.values_from_row(row) for row in rows}

    async def summary_distributions(
        self,
        db: AsyncSession,
        ctx: CallOverallContext,
    ) -> list[MetricDistribution]:
        del db, ctx
        return []

    def trendable_descriptors(self) -> list[CallMetricDescriptor]:
        return [descriptor for descriptor in self.descriptors if descriptor.trendable]

    def empty_values(self) -> dict[str, float | None]:
        return {
            descriptor.key: 0 if descriptor.format is MetricFormat.INTEGER else None
            for descriptor in self.descriptors
        }


async def enum_distribution(
    db: AsyncSession,
    ctx: CallOverallContext,
    *,
    distribution_key: str,
    group: str,
    value_column,
    extra_filters: tuple[ColumnElement, ...] = (),
    null_key: str | None = None,
    label_column=None,
) -> MetricDistribution:
    """Aggregate a stable enum or snapshot-label distribution."""

    key_expr = value_column
    if null_key is not None:
        key_expr = func.coalesce(value_column, null_key)
    filters = [*ctx.filters(), *extra_filters]
    if null_key is None:
        filters.append(value_column.is_not(None))
    label_expr = label_column if label_column is not None else key_expr
    rows = (
        await db.execute(
            select(
                key_expr.label("slice_key"),
                label_expr.label("slice_label"),
                func.count(CallRecord.id).label("slice_value"),
            )
            .where(*filters)
            .group_by(key_expr, label_expr)
            .order_by(func.count(CallRecord.id).desc(), key_expr.asc())
        )
    ).all()
    slices = [
        MetricDistributionSlice(
            key=str(row.slice_key),
            label=str(row.slice_label or row.slice_key),
            value=int(row.slice_value or 0),
        )
        for row in rows
    ]
    return MetricDistribution(
        key=distribution_key,
        group=group,
        total=sum(item.value for item in slices),
        slices=slices,
    )


def count_when(condition, label: str):
    return func.count(CallRecord.id).filter(condition).label(label)


def ratio(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if not denominator:
        return None
    return float(numerator or 0) / float(denominator)


def average_milliseconds(
    total: int | float | None,
    count: int | float | None,
) -> float | None:
    if not count:
        return None
    return float(total or 0) / float(count) / 1000.0


def _bucket_key_sql(trend_type: TrendType, tz: ZoneInfo):
    local_ts = func.timezone(str(tz), CallRecord.started_at)
    if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR):
        hour = func.extract("hour", local_ts)
        minute = func.extract("minute", local_ts)
        if trend_type is TrendType.HALF_HOUR:
            return cast(hour * 3600 + func.floor(minute / 30) * 1800, Integer)
        return cast(hour * 3600, Integer)
    if trend_type is TrendType.DAY:
        return func.to_char(func.date_trunc("day", local_ts), "YYYY-MM-DD")
    if trend_type is TrendType.WEEK:
        return func.to_char(func.date_trunc("week", local_ts), 'IYYY"-W"IW')
    if trend_type is TrendType.MONTH:
        return func.to_char(func.date_trunc("month", local_ts), "YYYY-MM")
    raise ValueError(trend_type)


def bucket_python_key(bucket: TimeBucket, trend_type: TrendType):
    if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR):
        return bucket.offset_seconds
    return bucket.label
