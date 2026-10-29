"""``service_efficiency`` metric group — "how fast and how long human agents
served the session".

Base: human-involved sessions (``had_bot_session = false OR
bot_handoff_succeeded = true``); pure-bot sessions never enter the denominator.
Reads the materialized response/duration columns directly.

- avg first human response = avg(first_human_response_seconds) over rows where
  it is set (NULL rows are excluded by SQL avg).
- avg agent response = weighted by per-session response counts:
  sum(agent_avg_response_seconds * agent_response_count) / sum(agent_response_count).
- avg human session duration = avg(duration_seconds) over rows where it is set.

All three are aggregate averages, so they do not sum across trend buckets.
"""
from __future__ import annotations

from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.conversation import Conversation

from ...schemas import MetricFormat, MetricLevel
from ..buckets import TimeBucket, TrendType
from ..queries import _absolute_bucket_key_sql, _distribution_bucket_key_sql
from .base import MetricDescriptor, MetricGroupProvider, OverallContext

_FIRST = "avg_first_human_response_seconds"
_AGENT = "avg_agent_response_seconds"
_DURATION = "avg_human_session_duration_seconds"


def _value_columns() -> list:
    conv = Conversation
    return [
        func.avg(conv.first_human_response_seconds).label(_FIRST),
        # Weighted average building blocks: numerator and denominator are summed
        # here and divided in _row_to_values (per-session averages can't be
        # re-averaged directly).
        func.sum(conv.agent_avg_response_seconds * conv.agent_response_count).label("agent_resp_num"),
        func.sum(conv.agent_response_count).label("agent_resp_den"),
        func.avg(conv.duration_seconds).label(_DURATION),
    ]


def _row_to_values(row) -> dict[str, float | None]:
    den = row.agent_resp_den
    weighted_agent = (
        float(row.agent_resp_num) / float(den) if row.agent_resp_num is not None and den else None
    )
    return {
        _FIRST: float(row.avg_first_human_response_seconds)
        if row.avg_first_human_response_seconds is not None
        else None,
        _AGENT: weighted_agent,
        _DURATION: float(row.avg_human_session_duration_seconds)
        if row.avg_human_session_duration_seconds is not None
        else None,
    }


class ServiceEfficiencyGroup(MetricGroupProvider):
    key = "service_efficiency"
    descriptors = [
        MetricDescriptor(_FIRST, format=MetricFormat.DURATION_SECONDS, level=MetricLevel.PRIMARY),
        MetricDescriptor(_AGENT, format=MetricFormat.DURATION_SECONDS, level=MetricLevel.PRIMARY),
        MetricDescriptor(_DURATION, format=MetricFormat.DURATION_SECONDS, level=MetricLevel.AUXILIARY),
    ]

    def _session_filter(self, ctx: OverallContext) -> list[ColumnElement]:
        conv = Conversation
        filters: list[ColumnElement] = [
            conv.tenant_id == ctx.tenant_id,
            conv.started_at >= ctx.range_start,
            conv.started_at < ctx.range_end,
            # Human-involved base: pure-bot sessions are excluded entirely.
            or_(conv.had_bot_session.is_(False), conv.bot_handoff_succeeded.is_(True)),
        ]
        if ctx.agent_ids is not None:
            filters.append(conv.agent_id.in_(ctx.agent_ids))
        return filters

    def _empty_values(self) -> dict[str, float | None]:
        return {_FIRST: None, _AGENT: None, _DURATION: None}

    async def summary(self, db: AsyncSession, ctx: OverallContext) -> dict[str, float | None]:
        if ctx.agent_ids is not None and not ctx.agent_ids:
            return self._empty_values()
        stmt = select(*_value_columns()).where(*self._session_filter(ctx))
        row = (await db.execute(stmt)).one()
        return _row_to_values(row)

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
        return {r.bkey: _row_to_values(r) for r in rows}
