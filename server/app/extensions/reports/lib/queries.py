"""Shared aggregation queries against conversations + messages.

This module is the *only* place that hits the DB for session metrics. SR1, SR2,
SR3 routers/services compose results from these functions; they never write raw
SQL of their own.

All times passed in MUST be tz-aware (in tenant timezone). All times in the
return values are tz-aware in UTC unless otherwise stated.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, case, cast, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.libs.reception_segments import END_TRANSFER_OUT, ENTRY_TRANSFER_IN
from app.models.conversation import Conversation
from app.models.conversation_reception_segment import ConversationReceptionSegment
from app.models.offline_message import OfflineMessage

from ..schemas import OverviewMetrics, TrendBucketResult
from .buckets import TimeBucket, TrendType, generate_buckets


# ──────────────────────────────────────────────────────────────────────────
# Overview (single scope: overall OR one employee)
# ──────────────────────────────────────────────────────────────────────────

async def fetch_overview(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    employee_id: int | None = None,
    agent_ids: list[int] | None = None,
    include_business_metrics: bool = False,
    include_offline_messages: bool = False,
    offline_message_scope_predicate: ColumnElement | None = None,
) -> OverviewMetrics:
    """All five metrics for one scope.

    Sessions are attributed by ``conversations.started_at``. Message counts read
    the materialized per-conversation columns (visitor/agent), so a message
    sent on the day after a session started still counts toward that session's
    day — same caliber as the old messages JOIN, without the join.
    """
    conv = Conversation

    session_filter = [
        conv.tenant_id == tenant_id,
        conv.started_at >= range_start,
        conv.started_at < range_end,
    ]
    if employee_id is not None:
        session_filter.append(conv.agent_id == employee_id)
    elif agent_ids is not None:
        if not agent_ids:
            return OverviewMetrics()
        session_filter.append(conv.agent_id.in_(agent_ids))

    # Per-conversation aggregation in one round-trip: session count, average
    # duration and the materialized message counts.
    user_count_expr, agent_count_expr = _message_count_exprs()
    base = select(
        func.count(conv.id).label("session_count"),
        _avg_duration_expr().label("avg_duration_seconds"),
        user_count_expr,
        agent_count_expr,
    ).where(*session_filter)
    row = (await db.execute(base)).one()

    metrics = OverviewMetrics(
        session_count=int(row.session_count or 0),
        message_count=int(row.user_count or 0) + int(row.agent_count or 0),
        user_message_count=int(row.user_count or 0),
        agent_message_count=int(row.agent_count or 0),
        avg_duration_seconds=(
            float(row.avg_duration_seconds) if row.avg_duration_seconds is not None else None
        ),
    )

    # Reception-segment calibers are shown by both the overall and the
    # per-employee detail views, so they are merged regardless of the business
    # metric flag.
    reception_metrics = await _fetch_reception_overview(
        db,
        tenant_id,
        range_start,
        range_end,
        employee_id=employee_id,
        agent_ids=agent_ids,
    )
    metrics = metrics.model_copy(update=reception_metrics)

    if not include_business_metrics:
        return metrics

    business_metrics = await _fetch_business_overview(
        db,
        tenant_id,
        range_start,
        range_end,
        session_filter,
        include_offline_messages=include_offline_messages,
        offline_message_scope_predicate=offline_message_scope_predicate,
    )
    return metrics.model_copy(update=business_metrics)


# ──────────────────────────────────────────────────────────────────────────
# Trend (one scope, all 5 metrics per bucket)
# ──────────────────────────────────────────────────────────────────────────

async def fetch_trend(
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
    include_business_metrics: bool = False,
    include_offline_messages: bool = False,
    offline_message_scope_predicate: ColumnElement | None = None,
) -> list[TrendBucketResult]:
    """Per-bucket metrics.

    Strategy: generate the buckets in Python (deterministic order, fills empty
    buckets with zeros), then run one SQL query that groups by the same bucket
    key. Merge results in Python.
    """
    buckets = generate_buckets(range_start_date, range_end_date, trend_type, tz)

    if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR):
        bucket_key_sql = _distribution_bucket_key_sql(trend_type, tz)
    else:
        bucket_key_sql = _absolute_bucket_key_sql(trend_type, tz)

    conv = Conversation

    session_filter = [
        conv.tenant_id == tenant_id,
        conv.started_at >= range_start,
        conv.started_at < range_end,
    ]
    if employee_id is not None:
        session_filter.append(conv.agent_id == employee_id)
    elif agent_ids is not None:
        if not agent_ids:
            buckets = generate_buckets(range_start_date, range_end_date, trend_type, tz)
            return [
                TrendBucketResult(
                    label=b.label,
                    bucket_start=b.start.isoformat(),
                    bucket_end=b.end.isoformat(),
                    metrics=OverviewMetrics(
                        can_view_offline_messages=include_offline_messages
                    ),
                )
                for b in buckets
            ]
        session_filter.append(conv.agent_id.in_(agent_ids))

    # Session counts + avg duration + materialized message counts per bucket.
    user_count_expr, agent_count_expr = _message_count_exprs()
    s_stmt = (
        select(
            bucket_key_sql.label("bkey"),
            func.count(conv.id).label("session_count"),
            _avg_duration_expr().label("avg_duration_seconds"),
            user_count_expr,
            agent_count_expr,
        )
        .where(*session_filter)
        .group_by(literal_column("bkey"))
    )
    s_rows = (await db.execute(s_stmt)).all()
    s_map = {r.bkey: r for r in s_rows}

    business_maps = {}
    if include_business_metrics:
        business_maps = await _fetch_business_trend_maps(
            db,
            tenant_id,
            range_start,
            range_end,
            trend_type,
            tz,
            session_filter,
            include_offline_messages=include_offline_messages,
            offline_message_scope_predicate=offline_message_scope_predicate,
        )

    out: list[TrendBucketResult] = []
    for b in buckets:
        bkey = _bucket_python_key(b, trend_type)
        s = s_map.get(bkey)
        user_count = int(s.user_count or 0) if s else 0
        agent_count = int(s.agent_count or 0) if s else 0
        metrics = OverviewMetrics(
            session_count=int(s.session_count) if s else 0,
            message_count=user_count + agent_count,
            user_message_count=user_count,
            agent_message_count=agent_count,
            avg_duration_seconds=float(s.avg_duration_seconds) if s and s.avg_duration_seconds is not None else None,
        )
        if include_business_metrics:
            bot = business_maps.get("bot", {}).get(bkey)
            queue = business_maps.get("queue", {}).get(bkey)
            offline = business_maps.get("offline", {}).get(bkey)
            metrics = metrics.model_copy(update={
                "bot_session_count": int(bot.bot_session_count or 0) if bot else 0,
                "bot_handoff_count": int(bot.bot_handoff_count or 0) if bot else 0,
                "queued_session_count": int(queue.queued_session_count or 0) if queue else 0,
                "avg_queue_duration_seconds": (
                    float(queue.avg_queue_duration_seconds)
                    if queue and queue.avg_queue_duration_seconds is not None
                    else None
                ),
                "offline_message_count": (
                    int(offline.offline_message_count or 0)
                    if include_offline_messages and offline
                    else (0 if include_offline_messages else None)
                ),
                "can_view_offline_messages": include_offline_messages,
            })
        out.append(
            TrendBucketResult(
                label=b.label,
                bucket_start=b.start.isoformat(),
                bucket_end=b.end.isoformat(),
                metrics=metrics,
            )
        )
    return out


# ──────────────────────────────────────────────────────────────────────────
# Business supplement metrics (overall report only)
# ──────────────────────────────────────────────────────────────────────────

async def _fetch_business_overview(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    session_filter: list[ColumnElement],
    *,
    include_offline_messages: bool,
    offline_message_scope_predicate: ColumnElement | None,
) -> dict:
    conv = Conversation

    bot_condition = _bot_session_condition()
    bot_stmt = select(
        func.sum(case((bot_condition, 1), else_=0)).label("bot_session_count"),
        func.sum(
            case((conv.bot_handoff_succeeded.is_(True), 1), else_=0)
        ).label("bot_handoff_count"),
    ).where(*session_filter)
    bot_row = (await db.execute(bot_stmt)).one()

    queue_row = await _fetch_queue_overview(db, session_filter)
    offline_count = None
    if include_offline_messages:
        offline_count = await _fetch_offline_message_count(
            db,
            tenant_id,
            range_start,
            range_end,
            offline_message_scope_predicate,
        )

    return {
        "bot_session_count": int(bot_row.bot_session_count or 0),
        "bot_handoff_count": int(bot_row.bot_handoff_count or 0),
        "queued_session_count": int(queue_row.queued_session_count or 0),
        "avg_queue_duration_seconds": (
            float(queue_row.avg_queue_duration_seconds)
            if queue_row.avg_queue_duration_seconds is not None
            else None
        ),
        "offline_message_count": offline_count,
        "can_view_offline_messages": include_offline_messages,
    }


async def _fetch_reception_overview(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    employee_id: int | None,
    agent_ids: list[int] | None,
) -> dict:
    """Reception-segment calibers for one scope (overall or one employee).

    Segments are attributed by ``conversation_started_at`` (same as the
    conversation start day) and scoped by the segment's owning agent. The
    "final agent" count reads the materialized ``conversations`` aggregate.
    """
    seg = ConversationReceptionSegment
    seg_filter: list[ColumnElement] = [
        seg.tenant_id == tenant_id,
        seg.conversation_started_at >= range_start,
        seg.conversation_started_at < range_end,
    ]
    if employee_id is not None:
        seg_filter.append(seg.agent_id == employee_id)
    elif agent_ids is not None:
        seg_filter.append(seg.agent_id.in_(agent_ids))

    seg_stmt = select(
        func.count(seg.id).label("segment_count"),
        func.count(func.distinct(seg.conversation_id)).label("participated"),
        func.sum(case((seg.entry_reason == ENTRY_TRANSFER_IN, 1), else_=0)).label("transfer_in"),
        func.sum(case((seg.end_reason == END_TRANSFER_OUT, 1), else_=0)).label("transfer_out"),
    ).where(*seg_filter)
    seg_row = (await db.execute(seg_stmt)).one()

    conv = Conversation
    final_filter: list[ColumnElement] = [
        conv.tenant_id == tenant_id,
        conv.started_at >= range_start,
        conv.started_at < range_end,
        conv.reception_final_agent_id.is_not(None),
    ]
    if employee_id is not None:
        final_filter.append(conv.reception_final_agent_id == employee_id)
    elif agent_ids is not None:
        final_filter.append(conv.reception_final_agent_id.in_(agent_ids))
    final_count = (
        await db.execute(select(func.count(conv.id)).where(*final_filter))
    ).scalar_one()

    return {
        "reception_segment_count": int(seg_row.segment_count or 0),
        "reception_participated_session_count": int(seg_row.participated or 0),
        "reception_final_session_count": int(final_count or 0),
        "reception_transfer_in_count": int(seg_row.transfer_in or 0),
        "reception_transfer_out_count": int(seg_row.transfer_out or 0),
    }


async def _fetch_queue_overview(db: AsyncSession, session_filter: list[ColumnElement]):
    # Reads the materialized per-conversation queue duration (NULL when there was
    # no substantial queue), so the caliber matches session records exactly and
    # we avoid re-aggregating queue_tasks at query time.
    conv = Conversation
    stmt = select(
        func.count(conv.id).label("queued_session_count"),
        func.avg(conv.total_queue_duration_seconds).label("avg_queue_duration_seconds"),
    ).where(*session_filter, conv.total_queue_duration_seconds > 0)
    return (await db.execute(stmt)).one()


async def _fetch_offline_message_count(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    scope_predicate: ColumnElement | None,
) -> int:
    offline = OfflineMessage
    filters: list[ColumnElement] = [
        offline.tenant_id == tenant_id,
        offline.created_at >= range_start,
        offline.created_at < range_end,
    ]
    if scope_predicate is not None:
        filters.append(scope_predicate)
    row = (await db.execute(select(func.count(offline.id)).where(*filters))).scalar_one()
    return int(row or 0)


async def _fetch_business_trend_maps(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    trend_type: TrendType,
    tz: ZoneInfo,
    session_filter: list[ColumnElement],
    *,
    include_offline_messages: bool,
    offline_message_scope_predicate: ColumnElement | None,
) -> dict[str, dict]:
    bot_map = await _fetch_bot_trend_map(db, trend_type, tz, session_filter)
    queue_map = await _fetch_queue_trend_map(db, trend_type, tz, session_filter)
    offline_map = {}
    if include_offline_messages:
        offline_map = await _fetch_offline_message_trend_map(
            db,
            tenant_id,
            range_start,
            range_end,
            trend_type,
            tz,
            offline_message_scope_predicate,
        )
    return {
        "bot": bot_map,
        "queue": queue_map,
        "offline": offline_map,
    }


async def _fetch_bot_trend_map(
    db: AsyncSession,
    trend_type: TrendType,
    tz: ZoneInfo,
    session_filter: list[ColumnElement],
) -> dict:
    conv = Conversation
    bucket_key_sql = (
        _distribution_bucket_key_sql(trend_type, tz)
        if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR)
        else _absolute_bucket_key_sql(trend_type, tz)
    )
    stmt = (
        select(
            bucket_key_sql.label("bkey"),
            func.sum(case((_bot_session_condition(), 1), else_=0)).label("bot_session_count"),
            func.sum(case((conv.bot_handoff_succeeded.is_(True), 1), else_=0)).label("bot_handoff_count"),
        )
        .where(*session_filter)
        .group_by(literal_column("bkey"))
    )
    rows = (await db.execute(stmt)).all()
    return {r.bkey: r for r in rows}


async def _fetch_queue_trend_map(
    db: AsyncSession,
    trend_type: TrendType,
    tz: ZoneInfo,
    session_filter: list[ColumnElement],
) -> dict:
    conv = Conversation
    bucket_key_sql = (
        _distribution_bucket_key_sql(trend_type, tz)
        if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR)
        else _absolute_bucket_key_sql(trend_type, tz)
    )
    stmt = (
        select(
            bucket_key_sql.label("bkey"),
            func.count(conv.id).label("queued_session_count"),
            func.avg(conv.total_queue_duration_seconds).label("avg_queue_duration_seconds"),
        )
        .where(*session_filter, conv.total_queue_duration_seconds > 0)
        .group_by(literal_column("bkey"))
    )
    rows = (await db.execute(stmt)).all()
    return {r.bkey: r for r in rows}


async def _fetch_offline_message_trend_map(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    trend_type: TrendType,
    tz: ZoneInfo,
    scope_predicate: ColumnElement | None,
) -> dict:
    offline = OfflineMessage
    bucket_key_sql = (
        _distribution_bucket_key_sql(trend_type, tz, offline.created_at)
        if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR)
        else _absolute_bucket_key_sql(trend_type, tz, offline.created_at)
    )
    filters: list[ColumnElement] = [
        offline.tenant_id == tenant_id,
        offline.created_at >= range_start,
        offline.created_at < range_end,
    ]
    if scope_predicate is not None:
        filters.append(scope_predicate)
    stmt = (
        select(
            bucket_key_sql.label("bkey"),
            func.count(offline.id).label("offline_message_count"),
        )
        .where(*filters)
        .group_by(literal_column("bkey"))
    )
    rows = (await db.execute(stmt)).all()
    return {r.bkey: r for r in rows}


def _message_count_exprs():
    """Materialized per-conversation message-count sums (visitor + agent).

    Reads the redundant columns written at message send and reconciled at
    conversation end, instead of joining/counting the ``messages`` table. Same
    caliber as before: only visitor/agent feed the report totals.
    """
    conv = Conversation
    return (
        func.coalesce(func.sum(conv.visitor_message_count), 0).label("user_count"),
        func.coalesce(func.sum(conv.agent_message_count), 0).label("agent_count"),
    )


def _bot_session_condition():
    # Reads the materialized bot marker instead of OR-ing the three OpenAgent
    # identity fields; same caliber, index-friendly.
    return Conversation.had_bot_session.is_(True)


def _avg_duration_expr():
    """Average session duration in seconds.

    Prefers the materialized ``duration_seconds`` (written when a session ends);
    falls back to the live ``coalesce(ended_at, now()) - started_at`` expression
    so in-progress sessions still use ``now()`` and un-backfilled rows stay
    correct. Same caliber as before for both states.
    """
    conv = Conversation
    return func.avg(
        func.coalesce(
            conv.duration_seconds,
            func.extract(
                "epoch",
                func.coalesce(conv.ended_at, func.now()) - conv.started_at,
            ),
        )
    )


# ──────────────────────────────────────────────────────────────────────────
# Per-employee overview (used by SR2 list + SR3 online monitor)
# ──────────────────────────────────────────────────────────────────────────

async def fetch_employees_overview(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    employee_ids: list[int] | None = None,
) -> dict[int, OverviewMetrics]:
    """All 5 metrics grouped by agent_id.

    Returns a dict keyed by employee_id. Employees with no sessions in range are
    NOT present in the result — callers (SR2 / SR3) join against the employee
    table and fill zeros for missing entries.
    """
    conv = Conversation

    session_filter = [
        conv.tenant_id == tenant_id,
        conv.agent_id.is_not(None),
        conv.started_at >= range_start,
        conv.started_at < range_end,
    ]
    if employee_ids is not None:
        if not employee_ids:
            return {}
        session_filter.append(conv.agent_id.in_(employee_ids))

    user_count_expr, agent_count_expr = _message_count_exprs()
    s_stmt = (
        select(
            conv.agent_id.label("agent_id"),
            func.count(conv.id).label("session_count"),
            _avg_duration_expr().label("avg_duration_seconds"),
            user_count_expr,
            agent_count_expr,
        )
        .where(*session_filter)
        .group_by(conv.agent_id)
    )
    s_rows = (await db.execute(s_stmt)).all()

    reception_map = await _fetch_reception_employees(
        db, tenant_id, range_start, range_end, employee_ids=employee_ids
    )

    out: dict[int, OverviewMetrics] = {}
    for s in s_rows:
        user_count = int(s.user_count or 0)
        agent_count = int(s.agent_count or 0)
        out[s.agent_id] = OverviewMetrics(
            session_count=int(s.session_count or 0),
            message_count=user_count + agent_count,
            user_message_count=user_count,
            agent_message_count=agent_count,
            avg_duration_seconds=(
                float(s.avg_duration_seconds) if s.avg_duration_seconds is not None else None
            ),
        )

    # Merge reception metrics; a transferred-out agent may have reception
    # segments without owning the conversation (no agent_id session row), so
    # union both keysets instead of only iterating the session rows.
    for agent_id, reception in reception_map.items():
        metrics = out.get(agent_id, OverviewMetrics())
        out[agent_id] = metrics.model_copy(update=reception)
    return out


async def _fetch_reception_employees(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    employee_ids: list[int] | None,
) -> dict[int, dict]:
    """Per-agent reception-segment calibers keyed by agent_id."""
    seg = ConversationReceptionSegment
    seg_filter: list[ColumnElement] = [
        seg.tenant_id == tenant_id,
        seg.agent_id.is_not(None),
        seg.conversation_started_at >= range_start,
        seg.conversation_started_at < range_end,
    ]
    if employee_ids is not None:
        seg_filter.append(seg.agent_id.in_(employee_ids))
    seg_stmt = (
        select(
            seg.agent_id.label("agent_id"),
            func.count(seg.id).label("segment_count"),
            func.count(func.distinct(seg.conversation_id)).label("participated"),
            func.sum(case((seg.entry_reason == ENTRY_TRANSFER_IN, 1), else_=0)).label("transfer_in"),
            func.sum(case((seg.end_reason == END_TRANSFER_OUT, 1), else_=0)).label("transfer_out"),
        )
        .where(*seg_filter)
        .group_by(seg.agent_id)
    )
    seg_rows = (await db.execute(seg_stmt)).all()

    conv = Conversation
    final_filter: list[ColumnElement] = [
        conv.tenant_id == tenant_id,
        conv.started_at >= range_start,
        conv.started_at < range_end,
        conv.reception_final_agent_id.is_not(None),
    ]
    if employee_ids is not None:
        final_filter.append(conv.reception_final_agent_id.in_(employee_ids))
    final_stmt = (
        select(
            conv.reception_final_agent_id.label("agent_id"),
            func.count(conv.id).label("final_count"),
        )
        .where(*final_filter)
        .group_by(conv.reception_final_agent_id)
    )
    final_rows = (await db.execute(final_stmt)).all()
    final_by_agent = {r.agent_id: int(r.final_count or 0) for r in final_rows}

    out: dict[int, dict] = {}
    for r in seg_rows:
        out[r.agent_id] = {
            "reception_segment_count": int(r.segment_count or 0),
            "reception_participated_session_count": int(r.participated or 0),
            "reception_transfer_in_count": int(r.transfer_in or 0),
            "reception_transfer_out_count": int(r.transfer_out or 0),
            "reception_final_session_count": final_by_agent.get(r.agent_id, 0),
        }
    for agent_id, final_count in final_by_agent.items():
        if agent_id not in out:
            out[agent_id] = {"reception_final_session_count": final_count}
    return out


# ──────────────────────────────────────────────────────────────────────────
# Internal: per-bucket SQL key expressions
# ──────────────────────────────────────────────────────────────────────────

def _distribution_bucket_key_sql(trend_type: TrendType, tz: ZoneInfo, timestamp_column=None):
    """SQL key for distribution-style buckets (half_hour / hour).

    The key is "seconds-from-midnight in tenant tz" so it lines up with
    TimeBucket.offset_seconds generated in Python.
    """
    tz_name = str(tz)
    # started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Shanghai' converts the
    # stored UTC timestamptz into a local naive timestamp, then EXTRACT(hour /
    # minute) reads off it.
    source_column = timestamp_column if timestamp_column is not None else Conversation.started_at
    local_ts = func.timezone(tz_name, source_column)
    hour = func.extract("hour", local_ts)
    minute = func.extract("minute", local_ts)
    if trend_type is TrendType.HALF_HOUR:
        # floor(minute/30) * 30 + hour*3600
        return cast(hour * 3600 + (func.floor(minute / 30) * 1800), Integer)
    # HOUR
    return cast(hour * 3600, Integer)


def _absolute_bucket_key_sql(trend_type: TrendType, tz: ZoneInfo, timestamp_column=None):
    """SQL key for absolute buckets (day / week / month).

    Returns a date_trunc'd timestamp in the tenant tz, formatted as ISO string
    so it matches TimeBucket label format.
    """
    tz_name = str(tz)
    source_column = timestamp_column if timestamp_column is not None else Conversation.started_at
    local_ts = func.timezone(tz_name, source_column)
    if trend_type is TrendType.DAY:
        return func.to_char(func.date_trunc("day", local_ts), "YYYY-MM-DD")
    if trend_type is TrendType.WEEK:
        # IYYY = ISO year, IW = ISO week number
        return func.to_char(func.date_trunc("week", local_ts), 'IYYY"-W"IW')
    if trend_type is TrendType.MONTH:
        return func.to_char(func.date_trunc("month", local_ts), "YYYY-MM")
    raise ValueError(trend_type)


def _bucket_python_key(b: TimeBucket, trend_type: TrendType):
    """Python-side key matching the SQL bucket key, used to merge results."""
    if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR):
        return b.offset_seconds
    return b.label
