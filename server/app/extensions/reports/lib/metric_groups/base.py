"""Metric-group framework for the overall session report.

The overall report is modeled as an ordered list of *metric groups*; each group
answers one business question and owns an ordered list of *metrics*. A metric is
self-describing: a stable key plus a format and a display level. The backend
never sends display text — the frontend localizes by key and formats by format.

Adding a metric later means: add a descriptor + its computation to a group.
Adding a group means: implement one provider and register it. Neither touches
existing groups (open-closed).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from ...schemas import MetricDistribution, MetricFormat, MetricLevel
from ..buckets import TimeBucket, TrendType


@dataclass(frozen=True)
class MetricDescriptor:
    """Static description of one metric inside a group."""
    key: str
    format: MetricFormat = MetricFormat.INTEGER
    level: MetricLevel = MetricLevel.PRIMARY
    # Whether this metric can be plotted on the trend chart / detail table.
    trendable: bool = True


@dataclass(frozen=True)
class OverallContext:
    """Shared inputs for an overall-report aggregation.

    ``agent_ids`` is None when the principal sees all sessions; when the data
    scope is restricted it carries the visible agent ids and providers must
    filter sessions by them.
    """
    tenant_id: int
    range_start: datetime
    range_end: datetime
    tz: ZoneInfo
    agent_ids: list[int] | None = None


class MetricGroupProvider(ABC):
    """Contract every metric group implements.

    ``summary`` returns one value per metric key for the whole range.
    ``trend`` returns a per-bucket map: ``{bucket_python_key: {metric_key: value}}``,
    keyed the same way the caller keys the generated buckets, so missing buckets
    fall back to zero.
    """

    key: str = ""
    descriptors: list[MetricDescriptor] = field(default_factory=list)

    @abstractmethod
    async def summary(self, db: AsyncSession, ctx: OverallContext) -> dict[str, float | None]:
        ...

    @abstractmethod
    async def trend(
        self,
        db: AsyncSession,
        ctx: OverallContext,
        trend_type: TrendType,
        buckets: list[TimeBucket],
    ) -> dict[object, dict[str, float | None]]:
        ...

    def trendable_descriptors(self) -> list[MetricDescriptor]:
        return [d for d in self.descriptors if d.trendable]

    async def visible_trend_descriptors(
        self,
        db: AsyncSession,
        ctx: OverallContext,
    ) -> list[MetricDescriptor]:
        """Trend descriptors visible for the current config/scope.

        Most groups are static and can use all trendable descriptors. Config-
        gated groups override this to hide disabled metrics before the frontend
        or export builds columns.
        """
        return self.trendable_descriptors()

    async def summary_distributions(
        self,
        db: AsyncSession,
        ctx: OverallContext,
    ) -> list[MetricDistribution]:
        """Optional distribution charts displayed below a group's summary cards."""
        return []
