"""``human_messages`` metric group — "message interaction on human-involved
sessions".

Base: human-involved sessions (``had_bot_session = false OR
bot_handoff_succeeded = true``). Pure-bot sessions never enter the base, so
their messages never inflate the human-side calibers. Reads the materialized
message-count columns directly.
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

_EFFECTIVE = "effective_session_count"
_VISITOR_MSG = "visitor_message_count"
_AGENT_MSG = "agent_message_count"
_UNREPLIED = "unreplied_session_count"
_VISITOR_SILENT = "visitor_silent_session_count"


def _value_columns() -> list:
    conv = Conversation
    return [
        func.sum(
            case((and_(conv.visitor_message_count > 0, conv.agent_message_count > 0), 1), else_=0)
        ).label(_EFFECTIVE),
        func.coalesce(func.sum(conv.visitor_message_count), 0).label(_VISITOR_MSG),
        func.coalesce(func.sum(conv.agent_message_count), 0).label(_AGENT_MSG),
        func.sum(
            case((and_(conv.visitor_message_count > 0, conv.agent_message_count == 0), 1), else_=0)
        ).label(_UNREPLIED),
        func.sum(case((conv.visitor_message_count == 0, 1), else_=0)).label(_VISITOR_SILENT),
    ]


def _row_to_values(row) -> dict[str, float | None]:
    return {
        _EFFECTIVE: int(row.effective_session_count or 0),
        _VISITOR_MSG: int(row.visitor_message_count or 0),
        _AGENT_MSG: int(row.agent_message_count or 0),
        _UNREPLIED: int(row.unreplied_session_count or 0),
        _VISITOR_SILENT: int(row.visitor_silent_session_count or 0),
    }


class HumanMessagesGroup(MetricGroupProvider):
    key = "human_messages"
    descriptors = [
        MetricDescriptor(_EFFECTIVE, level=MetricLevel.PRIMARY),
        MetricDescriptor(_VISITOR_MSG, level=MetricLevel.AUXILIARY),
        MetricDescriptor(_AGENT_MSG, level=MetricLevel.AUXILIARY),
        MetricDescriptor(_UNREPLIED, level=MetricLevel.AUXILIARY),
        MetricDescriptor(_VISITOR_SILENT, level=MetricLevel.AUXILIARY),
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
