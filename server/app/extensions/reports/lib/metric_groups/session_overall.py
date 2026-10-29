"""``session_overall`` metric group — "how many sessions and what mix".

Source: ``conversations``, attributed by ``started_at``. Bases read the
materialized ``had_bot_session`` / ``bot_handoff_succeeded`` columns directly
(never the API-derived ``session_type``):

- pure bot      = had_bot_session AND NOT bot_handoff_succeeded
- pure human    = NOT had_bot_session
- bot + human   = had_bot_session AND bot_handoff_succeeded
- human involved = NOT had_bot_session OR bot_handoff_succeeded
"""
from __future__ import annotations

from sqlalchemy import and_, case, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.conversation import Conversation

from ...schemas import MetricLevel
from ..buckets import TimeBucket, TrendType
from ..queries import _absolute_bucket_key_sql, _distribution_bucket_key_sql
from .base import MetricDescriptor, MetricGroupProvider, OverallContext

_TOTAL = "total_session_count"
_PURE_BOT = "pure_bot_session_count"
_PURE_HUMAN = "pure_human_session_count"
_BOT_HUMAN = "bot_human_session_count"
_HUMAN_INVOLVED = "human_involved_session_count"


def _conditions() -> dict[str, ColumnElement]:
    conv = Conversation
    return {
        _PURE_BOT: and_(conv.had_bot_session.is_(True), conv.bot_handoff_succeeded.is_(False)),
        _PURE_HUMAN: conv.had_bot_session.is_(False),
        _BOT_HUMAN: and_(conv.had_bot_session.is_(True), conv.bot_handoff_succeeded.is_(True)),
        _HUMAN_INVOLVED: or_(conv.had_bot_session.is_(False), conv.bot_handoff_succeeded.is_(True)),
    }


def _value_columns() -> list:
    conv = Conversation
    conds = _conditions()
    return [
        func.count(conv.id).label(_TOTAL),
        func.sum(case((conds[_PURE_BOT], 1), else_=0)).label(_PURE_BOT),
        func.sum(case((conds[_PURE_HUMAN], 1), else_=0)).label(_PURE_HUMAN),
        func.sum(case((conds[_BOT_HUMAN], 1), else_=0)).label(_BOT_HUMAN),
        func.sum(case((conds[_HUMAN_INVOLVED], 1), else_=0)).label(_HUMAN_INVOLVED),
    ]


def _row_to_values(row) -> dict[str, float | None]:
    return {
        _TOTAL: int(row.total_session_count or 0),
        _PURE_BOT: int(row.pure_bot_session_count or 0),
        _PURE_HUMAN: int(row.pure_human_session_count or 0),
        _BOT_HUMAN: int(row.bot_human_session_count or 0),
        _HUMAN_INVOLVED: int(row.human_involved_session_count or 0),
    }


class SessionOverallGroup(MetricGroupProvider):
    key = "session_overall"
    descriptors = [
        MetricDescriptor(_TOTAL, level=MetricLevel.PRIMARY),
        MetricDescriptor(_PURE_BOT, level=MetricLevel.PRIMARY),
        MetricDescriptor(_PURE_HUMAN, level=MetricLevel.PRIMARY),
        MetricDescriptor(_BOT_HUMAN, level=MetricLevel.PRIMARY),
        MetricDescriptor(_HUMAN_INVOLVED, level=MetricLevel.PRIMARY),
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

    async def summary(self, db: AsyncSession, ctx: OverallContext) -> dict[str, float | None]:
        if ctx.agent_ids is not None and not ctx.agent_ids:
            return {d.key: 0 for d in self.descriptors}
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
