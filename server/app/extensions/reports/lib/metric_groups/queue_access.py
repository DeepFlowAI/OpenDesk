"""``queue_access`` metric group — "how many sessions queued, whether they
connected, and how long they waited".

Source: ``conversations`` session-level queue summary, attributed by
``started_at``. Reads the materialized ``total_queue_duration_seconds`` and
``queue_result`` columns directly (never JOIN ``conversation_queue_summaries``
on the overall report).

- queued     = total_queue_duration_seconds > 0
- assigned   = queued AND queue_result = assigned
- unassigned = queued AND queue_result IN (canceled, timeout)
- avg / max  = over queued sessions only
- assign rate = assigned / queued (None when no queued sessions)
"""
from __future__ import annotations

from sqlalchemy import and_, case, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.conversation import Conversation

from ...schemas import MetricFormat, MetricLevel
from ..buckets import TimeBucket, TrendType
from ..queries import _absolute_bucket_key_sql, _distribution_bucket_key_sql
from .base import MetricDescriptor, MetricGroupProvider, OverallContext

_QUEUED = "queued_session_count"
_ASSIGNED = "assigned_queue_session_count"
_UNASSIGNED = "unassigned_queue_session_count"
_AVG = "avg_queue_duration_seconds"
_MAX = "max_queue_duration_seconds"
_RATE = "queue_assign_rate"


def _is_queued(conv: type[Conversation]) -> ColumnElement:
    return conv.total_queue_duration_seconds > 0


def _value_columns() -> list:
    conv = Conversation
    queued = _is_queued(conv)
    return [
        func.sum(case((queued, 1), else_=0)).label(_QUEUED),
        func.sum(case((and_(queued, conv.queue_result == "assigned"), 1), else_=0)).label(_ASSIGNED),
        func.sum(
            case((and_(queued, conv.queue_result.in_(["canceled", "timeout"])), 1), else_=0)
        ).label(_UNASSIGNED),
        func.avg(case((queued, conv.total_queue_duration_seconds), else_=None)).label(_AVG),
        func.max(case((queued, conv.total_queue_duration_seconds), else_=None)).label(_MAX),
    ]


def _row_to_counts(row) -> dict[str, float | None]:
    return {
        _QUEUED: int(row.queued_session_count or 0),
        _ASSIGNED: int(row.assigned_queue_session_count or 0),
        _UNASSIGNED: int(row.unassigned_queue_session_count or 0),
        _AVG: float(row.avg_queue_duration_seconds) if row.avg_queue_duration_seconds is not None else None,
        _MAX: float(row.max_queue_duration_seconds) if row.max_queue_duration_seconds is not None else None,
    }


def _assign_rate(queued: int, assigned: int) -> float | None:
    """Queue assign rate; no denominator (no queued sessions) renders as ``—``."""
    return assigned / queued if queued else None


class QueueAccessGroup(MetricGroupProvider):
    key = "queue_access"
    descriptors = [
        MetricDescriptor(_QUEUED, level=MetricLevel.PRIMARY),
        MetricDescriptor(_ASSIGNED, level=MetricLevel.PRIMARY),
        MetricDescriptor(_UNASSIGNED, level=MetricLevel.PRIMARY),
        MetricDescriptor(_AVG, format=MetricFormat.DURATION_SECONDS, level=MetricLevel.PRIMARY),
        MetricDescriptor(_MAX, format=MetricFormat.DURATION_SECONDS, level=MetricLevel.AUXILIARY),
        MetricDescriptor(
            _RATE,
            format=MetricFormat.PERCENT,
            level=MetricLevel.AUXILIARY,
            trendable=False,
        ),
    ]

    def _session_filter(self, ctx: OverallContext) -> list[ColumnElement]:
        conv = Conversation
        filters: list[ColumnElement] = [
            conv.tenant_id == ctx.tenant_id,
            conv.started_at >= ctx.range_start,
            conv.started_at < ctx.range_end,
        ]
        if ctx.agent_ids is not None:
            filters.append(conv.agent_id.in_(ctx.agent_ids))
        return filters

    def _empty_values(self) -> dict[str, float | None]:
        return {
            _QUEUED: 0,
            _ASSIGNED: 0,
            _UNASSIGNED: 0,
            _AVG: None,
            _MAX: None,
            _RATE: None,
        }

    async def summary(self, db: AsyncSession, ctx: OverallContext) -> dict[str, float | None]:
        if ctx.agent_ids is not None and not ctx.agent_ids:
            return self._empty_values()
        stmt = select(*_value_columns()).where(*self._session_filter(ctx))
        row = (await db.execute(stmt)).one()
        values = _row_to_counts(row)
        values[_RATE] = _assign_rate(values[_QUEUED], values[_ASSIGNED])
        return values

    async def trend(
        self,
        db: AsyncSession,
        ctx: OverallContext,
        trend_type: TrendType,
        buckets: list[TimeBucket],
    ) -> dict[object, dict[str, float | None]]:
        if ctx.agent_ids is not None and not ctx.agent_ids:
            return {}
        if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR):
            bucket_key_sql = _distribution_bucket_key_sql(trend_type, ctx.tz)
        else:
            bucket_key_sql = _absolute_bucket_key_sql(trend_type, ctx.tz)
        stmt = (
            select(bucket_key_sql.label("bkey"), *_value_columns())
            .where(*self._session_filter(ctx))
            .group_by(literal_column("bkey"))
        )
        rows = (await db.execute(stmt)).all()
        return {r.bkey: _row_to_counts(r) for r in rows}
