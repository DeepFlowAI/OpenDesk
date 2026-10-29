"""``bot_handoff`` metric group — "how far does the bot reach and does handoff
succeed".

Source: ``conversations``, attributed by ``started_at``. Reads the materialized
bot columns directly (never the API-derived ``bot_handoff_status``):

- bot session       = had_bot_session
- handoff triggered = bot_handoff_triggered (any handoff attempt)
- handoff succeeded = bot_handoff_succeeded (success only)
- success rate      = succeeded / triggered (None when no triggers)
"""
from __future__ import annotations

from sqlalchemy import case, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.conversation import Conversation

from ...schemas import MetricFormat, MetricLevel
from ..buckets import TimeBucket, TrendType
from ..queries import _absolute_bucket_key_sql, _distribution_bucket_key_sql
from .base import MetricDescriptor, MetricGroupProvider, OverallContext

_BOT_SESSION = "bot_session_count"
_BOT_PHASE_VISITOR_MSG = "bot_phase_visitor_message_count"
_HANDOFF_TRIGGERED = "bot_handoff_triggered_count"
_HANDOFF_SUCCEEDED = "bot_handoff_succeeded_count"
_HANDOFF_SUCCESS_RATE = "bot_handoff_success_rate"


def _value_columns() -> list:
    conv = Conversation
    return [
        func.sum(case((conv.had_bot_session.is_(True), 1), else_=0)).label(_BOT_SESSION),
        func.coalesce(func.sum(conv.bot_phase_visitor_message_count), 0).label(_BOT_PHASE_VISITOR_MSG),
        func.sum(case((conv.bot_handoff_triggered.is_(True), 1), else_=0)).label(_HANDOFF_TRIGGERED),
        func.sum(case((conv.bot_handoff_succeeded.is_(True), 1), else_=0)).label(_HANDOFF_SUCCEEDED),
    ]


def _row_to_counts(row) -> dict[str, float | None]:
    return {
        _BOT_SESSION: int(row.bot_session_count or 0),
        _BOT_PHASE_VISITOR_MSG: int(row.bot_phase_visitor_message_count or 0),
        _HANDOFF_TRIGGERED: int(row.bot_handoff_triggered_count or 0),
        _HANDOFF_SUCCEEDED: int(row.bot_handoff_succeeded_count or 0),
    }


def _success_rate(triggered: int, succeeded: int) -> float | None:
    """Handoff success rate; no denominator (no triggers) renders as ``—``."""
    return succeeded / triggered if triggered else None


class BotHandoffGroup(MetricGroupProvider):
    key = "bot_handoff"
    descriptors = [
        MetricDescriptor(_BOT_SESSION, level=MetricLevel.PRIMARY),
        MetricDescriptor(_BOT_PHASE_VISITOR_MSG, level=MetricLevel.AUXILIARY),
        MetricDescriptor(_HANDOFF_TRIGGERED, level=MetricLevel.PRIMARY),
        MetricDescriptor(_HANDOFF_SUCCEEDED, level=MetricLevel.PRIMARY),
        # Derived ratio: surfaces in the overview but stays out of the trend —
        # a rate has no meaningful per-bucket sum.
        MetricDescriptor(
            _HANDOFF_SUCCESS_RATE,
            format=MetricFormat.PERCENT,
            level=MetricLevel.PRIMARY,
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
        return {d.key: (None if d.key == _HANDOFF_SUCCESS_RATE else 0) for d in self.descriptors}

    async def summary(self, db: AsyncSession, ctx: OverallContext) -> dict[str, float | None]:
        if ctx.agent_ids is not None and not ctx.agent_ids:
            return self._empty_values()
        stmt = select(*_value_columns()).where(*self._session_filter(ctx))
        row = (await db.execute(stmt)).one()
        values = _row_to_counts(row)
        values[_HANDOFF_SUCCESS_RATE] = _success_rate(values[_HANDOFF_TRIGGERED], values[_HANDOFF_SUCCEEDED])
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
