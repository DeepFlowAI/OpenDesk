"""SQL aggregation helpers for persisted employee call facts."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, and_, case, cast, func, literal_column, select, union, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.call_agent_fact import (
    CallAgentAfterCallWork,
    CallAgentOperation,
    CallAgentReceptionSegment,
)
from app.models.call_queue_fact import CallQueueOffer
from app.models.call_record import CallRecord

from .buckets import TrendType


async def fetch_agent_metrics(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    scope_predicate: ColumnElement | None,
    employee_id: int | None = None,
) -> tuple[dict[int, dict], dict[int, str]]:
    """Aggregate all raw employee metric numerators for a date range."""
    output: dict[int, dict] = {}
    snapshots: dict[int, str] = {}
    segment_rows = (
        await db.execute(
            select(
                CallAgentReceptionSegment.agent_id.label("employee_id"),
                *_segment_columns(),
            )
            .join(CallRecord, CallRecord.id == CallAgentReceptionSegment.call_record_id)
            .where(*_segment_filters(tenant_id, range_start, range_end, scope_predicate, employee_id))
            .group_by(CallAgentReceptionSegment.agent_id)
        )
    ).all()
    _merge_rows(output, segment_rows, snapshots)

    outbound_rows = (
        await db.execute(
            select(_outbound_agent().label("employee_id"), *_outbound_columns())
            .where(*_outbound_filters(tenant_id, range_start, range_end, scope_predicate, employee_id))
            .group_by(_outbound_agent())
        )
    ).all()
    _merge_rows(output, outbound_rows, snapshots)

    offer_agent = func.coalesce(CallQueueOffer.agent_ref_id, CallQueueOffer.agent_id)
    offer_rows = (
        await db.execute(
            select(offer_agent.label("employee_id"), *_offer_columns())
            .select_from(CallQueueOffer)
            .join(CallRecord, CallRecord.id == CallQueueOffer.call_record_id)
            .where(*_offer_filters(tenant_id, range_start, range_end, scope_predicate, employee_id))
            .group_by(offer_agent)
        )
    ).all()
    _merge_rows(output, offer_rows, snapshots)

    operation_rows = (
        await db.execute(
            select(CallAgentOperation.actor_agent_id.label("employee_id"), *_operation_columns())
            .join(CallRecord, CallRecord.id == CallAgentOperation.call_record_id)
            .where(*_operation_filters(tenant_id, range_start, range_end, scope_predicate, employee_id))
            .group_by(CallAgentOperation.actor_agent_id)
        )
    ).all()
    _merge_rows(output, operation_rows, snapshots)

    acw_rows = (
        await db.execute(
            select(CallAgentAfterCallWork.agent_id.label("employee_id"), *_acw_columns())
            .join(
                CallAgentReceptionSegment,
                CallAgentReceptionSegment.id == CallAgentAfterCallWork.reception_segment_id,
            )
            .join(CallRecord, CallRecord.id == CallAgentAfterCallWork.call_record_id)
            .where(*_acw_filters(tenant_id, range_start, range_end, scope_predicate, employee_id))
            .group_by(CallAgentAfterCallWork.agent_id)
        )
    ).all()
    _merge_rows(output, acw_rows, snapshots)

    participation_rows = await _participation_rows(
        db, tenant_id, range_start, range_end, scope_predicate, employee_id
    )
    _merge_rows(output, participation_rows, snapshots)
    snapshots.update(
        await _latest_name_snapshots(
            db, tenant_id, range_start, range_end, scope_predicate, employee_id
        )
    )
    return output, snapshots


async def _latest_name_snapshots(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    scope_predicate: ColumnElement | None,
    employee_id: int | None,
) -> dict[int, str]:
    offer_agent = func.coalesce(CallQueueOffer.agent_ref_id, CallQueueOffer.agent_id)
    sources = union_all(
        select(
            CallAgentReceptionSegment.agent_id.label("employee_id"),
            CallAgentReceptionSegment.agent_name_snapshot.label("name_snapshot"),
            CallAgentReceptionSegment.started_at.label("fact_started_at"),
        )
        .join(CallRecord, CallRecord.id == CallAgentReceptionSegment.call_record_id)
        .where(
            *_segment_filters(
                tenant_id, range_start, range_end, scope_predicate, employee_id
            ),
            CallAgentReceptionSegment.agent_name_snapshot.is_not(None),
        ),
        select(
            offer_agent.label("employee_id"),
            CallQueueOffer.agent_name_snapshot.label("name_snapshot"),
            CallQueueOffer.started_at.label("fact_started_at"),
        )
        .join(CallRecord, CallRecord.id == CallQueueOffer.call_record_id)
        .where(
            *_offer_filters(
                tenant_id, range_start, range_end, scope_predicate, employee_id
            ),
            CallQueueOffer.agent_name_snapshot.is_not(None),
        ),
        select(
            CallAgentOperation.actor_agent_id.label("employee_id"),
            CallAgentOperation.actor_name_snapshot.label("name_snapshot"),
            CallAgentOperation.started_at.label("fact_started_at"),
        )
        .join(CallRecord, CallRecord.id == CallAgentOperation.call_record_id)
        .where(
            *_operation_filters(
                tenant_id, range_start, range_end, scope_predicate, employee_id
            ),
            CallAgentOperation.actor_name_snapshot.is_not(None),
        ),
        select(
            _outbound_agent().label("employee_id"),
            CallRecord.initiator_agent_name_snapshot.label("name_snapshot"),
            CallRecord.started_at.label("fact_started_at"),
        ).where(
            *_outbound_filters(
                tenant_id, range_start, range_end, scope_predicate, employee_id
            ),
            CallRecord.initiator_agent_name_snapshot.is_not(None),
        ),
    ).subquery()
    ranked = select(
        sources.c.employee_id,
        sources.c.name_snapshot,
        func.row_number().over(
            partition_by=sources.c.employee_id,
            order_by=sources.c.fact_started_at.desc(),
        ).label("snapshot_rank"),
    ).subquery()
    rows = (
        await db.execute(
            select(ranked.c.employee_id, ranked.c.name_snapshot).where(
                ranked.c.snapshot_rank == 1
            )
        )
    ).all()
    return {
        int(row.employee_id): str(row.name_snapshot)
        for row in rows
        if row.employee_id is not None and row.name_snapshot
    }


async def fetch_agent_trend_metrics(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    trend_type: TrendType,
    tz: ZoneInfo,
    *,
    employee_id: int,
    scope_predicate: ColumnElement | None,
) -> dict[object, dict]:
    """Aggregate all raw metrics for one employee by each fact's start bucket."""
    output: dict[object, dict] = {}
    sources = (
        (
            CallAgentReceptionSegment.started_at,
            select,
            _segment_columns(),
            CallAgentReceptionSegment,
            [CallRecord.id == CallAgentReceptionSegment.call_record_id],
            _segment_filters(tenant_id, range_start, range_end, scope_predicate, employee_id),
        ),
        (
            CallRecord.started_at,
            select,
            _outbound_columns(),
            CallRecord,
            [],
            _outbound_filters(tenant_id, range_start, range_end, scope_predicate, employee_id),
        ),
        (
            CallQueueOffer.started_at,
            select,
            _offer_columns(),
            CallQueueOffer,
            [CallRecord.id == CallQueueOffer.call_record_id],
            _offer_filters(tenant_id, range_start, range_end, scope_predicate, employee_id),
        ),
        (
            CallAgentOperation.started_at,
            select,
            _operation_columns(),
            CallAgentOperation,
            [CallRecord.id == CallAgentOperation.call_record_id],
            _operation_filters(tenant_id, range_start, range_end, scope_predicate, employee_id),
        ),
    )
    for timestamp, _selector, columns, source, joins, filters in sources:
        bucket = _bucket_key_sql(timestamp, trend_type, tz)
        statement = select(bucket.label("bkey"), *columns).select_from(source)
        for condition in joins:
            statement = statement.join(CallRecord, condition)
        rows = (
            await db.execute(statement.where(*filters).group_by(literal_column("bkey")))
        ).all()
        _merge_buckets(output, rows)

    bucket = _bucket_key_sql(CallAgentReceptionSegment.started_at, trend_type, tz)
    acw_rows = (
        await db.execute(
            select(bucket.label("bkey"), *_acw_columns())
            .select_from(CallAgentAfterCallWork)
            .join(
                CallAgentReceptionSegment,
                CallAgentReceptionSegment.id == CallAgentAfterCallWork.reception_segment_id,
            )
            .join(CallRecord, CallRecord.id == CallAgentAfterCallWork.call_record_id)
            .where(*_acw_filters(tenant_id, range_start, range_end, scope_predicate, employee_id))
            .group_by(literal_column("bkey"))
        )
    ).all()
    _merge_buckets(output, acw_rows)
    participation = await _participation_trend_rows(
        db, tenant_id, range_start, range_end, trend_type, tz, scope_predicate, employee_id
    )
    _merge_buckets(output, participation)
    return output


async def fetch_agent_distributions(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    employee_id: int,
    scope_predicate: ColumnElement | None,
) -> dict[str, dict[str, int]]:
    segment_filters = _segment_filters(
        tenant_id, range_start, range_end, scope_predicate, employee_id
    )
    entry_rows = (
        await db.execute(
            select(CallAgentReceptionSegment.entry_reason, func.count().label("value"))
            .join(CallRecord, CallRecord.id == CallAgentReceptionSegment.call_record_id)
            .where(*segment_filters)
            .group_by(CallAgentReceptionSegment.entry_reason)
        )
    ).all()
    end_rows = (
        await db.execute(
            select(CallAgentReceptionSegment.end_reason, func.count().label("value"))
            .join(CallRecord, CallRecord.id == CallAgentReceptionSegment.call_record_id)
            .where(*segment_filters, CallAgentReceptionSegment.result_reliable.is_(True))
            .group_by(CallAgentReceptionSegment.end_reason)
        )
    ).all()
    offer_rows = (
        await db.execute(
            select(CallQueueOffer.result, func.count().label("value"))
            .join(CallRecord, CallRecord.id == CallQueueOffer.call_record_id)
            .where(
                *_offer_filters(tenant_id, range_start, range_end, scope_predicate, employee_id),
                CallQueueOffer.result_reliable.is_(True),
            )
            .group_by(CallQueueOffer.result)
        )
    ).all()
    handle_ms = CallAgentReceptionSegment.duration_ms + CallAgentAfterCallWork.duration_ms
    handle_bucket = case(
        (handle_ms <= 60_000, "0_1m"),
        (handle_ms <= 180_000, "1_3m"),
        (handle_ms <= 300_000, "3_5m"),
        (handle_ms <= 600_000, "5_10m"),
        else_="over_10m",
    )
    handle_rows = (
        await db.execute(
            select(handle_bucket.label("bucket"), func.count().label("value"))
            .select_from(CallAgentAfterCallWork)
            .join(
                CallAgentReceptionSegment,
                CallAgentReceptionSegment.id == CallAgentAfterCallWork.reception_segment_id,
            )
            .join(CallRecord, CallRecord.id == CallAgentAfterCallWork.call_record_id)
            .where(*_acw_filters(tenant_id, range_start, range_end, scope_predicate, employee_id))
            .group_by(handle_bucket)
        )
    ).all()
    return {
        "reception_entry_reason": _count_map(entry_rows, "entry_reason"),
        "offer_result": _count_map(offer_rows, "result"),
        "handle_duration": _count_map(handle_rows, "bucket"),
        "reception_end_reason": _count_map(end_rows, "end_reason"),
    }


async def _participation_rows(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    scope_predicate: ColumnElement | None,
    employee_id: int | None,
) -> list:
    segment_pairs = (
        select(
            CallAgentReceptionSegment.agent_id.label("employee_id"),
            CallAgentReceptionSegment.call_record_id.label("call_record_id"),
        )
        .join(CallRecord, CallRecord.id == CallAgentReceptionSegment.call_record_id)
        .where(*_segment_filters(tenant_id, range_start, range_end, scope_predicate, employee_id))
    )
    outbound_pairs = select(
        _outbound_agent().label("employee_id"), CallRecord.id.label("call_record_id")
    ).where(*_outbound_filters(tenant_id, range_start, range_end, scope_predicate, employee_id))
    pairs = union(segment_pairs, outbound_pairs).subquery()
    return (
        await db.execute(
            select(
                pairs.c.employee_id,
                func.count(pairs.c.call_record_id).label("participated_call_count"),
            ).group_by(pairs.c.employee_id)
        )
    ).all()


async def _participation_trend_rows(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    trend_type: TrendType,
    tz: ZoneInfo,
    scope_predicate: ColumnElement | None,
    employee_id: int,
) -> list:
    segment_bucket = _bucket_key_sql(CallAgentReceptionSegment.started_at, trend_type, tz)
    outbound_bucket = _bucket_key_sql(CallRecord.started_at, trend_type, tz)
    segment_pairs = (
        select(
            segment_bucket.label("bkey"),
            CallAgentReceptionSegment.call_record_id.label("call_record_id"),
        )
        .join(CallRecord, CallRecord.id == CallAgentReceptionSegment.call_record_id)
        .where(*_segment_filters(tenant_id, range_start, range_end, scope_predicate, employee_id))
    )
    outbound_pairs = select(
        outbound_bucket.label("bkey"), CallRecord.id.label("call_record_id")
    ).where(*_outbound_filters(tenant_id, range_start, range_end, scope_predicate, employee_id))
    pairs = union(segment_pairs, outbound_pairs).subquery()
    return (
        await db.execute(
            select(
                pairs.c.bkey,
                func.count(pairs.c.call_record_id).label("participated_call_count"),
            ).group_by(pairs.c.bkey)
        )
    ).all()


def _segment_columns() -> tuple:
    segment = CallAgentReceptionSegment
    reliable = and_(segment.result_reliable.is_(True), segment.duration_ms.is_not(None))
    talk_valid = and_(reliable, segment.talk_duration_ms.is_not(None))
    hold_valid = and_(reliable, segment.held.is_(True), segment.hold_duration_ms.is_not(None))
    return (
        func.count(func.distinct(segment.call_record_id)).label("handled_call_count"),
        func.count(segment.id).label("reception_segment_count"),
        func.count(func.distinct(segment.call_record_id))
        .filter(CallRecord.direction == "inbound")
        .label("inbound_handled_call_count"),
        func.count(func.distinct(segment.call_record_id))
        .filter(CallRecord.direction == "outbound")
        .label("outbound_handled_call_count"),
        func.count(segment.id)
        .filter(segment.entry_reason.in_(("agent_transfer", "queue_transfer")))
        .label("transfer_in_segment_count"),
        func.sum(segment.talk_duration_ms).filter(talk_valid).label("talk_total_ms"),
        func.count(segment.id).filter(talk_valid).label("talk_count"),
        func.count(segment.id).filter(and_(reliable, segment.held.is_(True))).label("held_segment_count"),
        func.sum(segment.hold_duration_ms).filter(hold_valid).label("hold_total_ms"),
        func.count(segment.id).filter(hold_valid).label("hold_count"),
    )


def _outbound_columns() -> tuple:
    return (
        func.count(CallRecord.id).label("outbound_attempt_count"),
        func.count(CallRecord.id)
        .filter(CallRecord.customer_connected_at.is_not(None))
        .label("outbound_customer_answered_count"),
    )


def _offer_columns() -> tuple:
    offer = CallQueueOffer
    terminal = and_(
        offer.result_reliable.is_(True), offer.result.in_(("accepted", "rejected", "timeout"))
    )
    response = and_(
        offer.result_reliable.is_(True),
        offer.result.in_(("accepted", "rejected")),
        offer.duration_ms.is_not(None),
    )
    return (
        func.count(func.distinct(offer.call_record_id)).label("offered_call_count"),
        func.count(offer.id).label("offer_attempt_count"),
        func.count(offer.id).filter(offer.result == "accepted").label("offer_accepted_count"),
        func.count(offer.id).filter(offer.result == "rejected").label("offer_rejected_count"),
        func.count(offer.id).filter(offer.result == "timeout").label("offer_timeout_count"),
        func.count(offer.id).filter(terminal).label("offer_rate_denominator"),
        func.sum(offer.duration_ms).filter(response).label("offer_response_total_ms"),
        func.count(offer.id).filter(response).label("offer_response_count"),
    )


def _operation_columns() -> tuple:
    operation = CallAgentOperation
    transfer = operation.operation_type == "transfer"
    consult = operation.operation_type == "consult"
    return (
        func.count(operation.id).filter(transfer).label("transfer_attempt_count"),
        func.count(operation.id)
        .filter(and_(transfer, operation.result == "completed"))
        .label("transfer_completed_count"),
        func.count(operation.id)
        .filter(and_(transfer, operation.result == "failed"))
        .label("transfer_failed_count"),
        func.count(operation.id)
        .filter(and_(transfer, operation.result_reliable.is_(True)))
        .label("transfer_terminal_count"),
        func.count(operation.id).filter(consult).label("consult_attempt_count"),
        func.count(operation.id)
        .filter(and_(consult, operation.result == "connected"))
        .label("consult_connected_count"),
        func.count(operation.id)
        .filter(
            and_(
                consult,
                operation.result_reliable.is_(True),
                operation.result.in_(("connected", "failed", "canceled")),
            )
        )
        .label("consult_terminal_count"),
        func.count(operation.id)
        .filter(and_(operation.operation_type == "conference", operation.result == "joined"))
        .label("conference_join_count"),
    )


def _acw_columns() -> tuple:
    acw = CallAgentAfterCallWork
    valid = and_(
        acw.result_reliable.is_(True),
        acw.duration_ms.is_not(None),
        CallAgentReceptionSegment.result_reliable.is_(True),
        CallAgentReceptionSegment.duration_ms.is_not(None),
    )
    return (
        func.sum(acw.duration_ms).filter(valid).label("acw_total_ms"),
        func.count(acw.id).filter(valid).label("acw_count"),
        func.sum(CallAgentReceptionSegment.duration_ms + acw.duration_ms)
        .filter(valid)
        .label("handle_total_ms"),
        func.count(acw.id).filter(valid).label("handle_count"),
    )


def _segment_filters(tenant_id, start, end, scope, employee_id) -> list[ColumnElement]:
    filters: list[ColumnElement] = [
        CallAgentReceptionSegment.tenant_id == tenant_id,
        CallRecord.tenant_id == tenant_id,
        CallAgentReceptionSegment.agent_id.is_not(None),
        CallAgentReceptionSegment.started_at >= start,
        CallAgentReceptionSegment.started_at < end,
    ]
    return _finish_filters(filters, scope, CallAgentReceptionSegment.agent_id, employee_id)


def _outbound_filters(tenant_id, start, end, scope, employee_id) -> list[ColumnElement]:
    agent = _outbound_agent()
    filters: list[ColumnElement] = [
        CallRecord.tenant_id == tenant_id,
        CallRecord.direction == "outbound",
        agent.is_not(None),
        CallRecord.started_at >= start,
        CallRecord.started_at < end,
    ]
    return _finish_filters(filters, scope, agent, employee_id)


def _outbound_agent():
    return func.coalesce(CallRecord.initiator_agent_ref_id, CallRecord.initiator_agent_id)


def _offer_filters(tenant_id, start, end, scope, employee_id) -> list[ColumnElement]:
    agent = func.coalesce(CallQueueOffer.agent_ref_id, CallQueueOffer.agent_id)
    filters: list[ColumnElement] = [
        CallQueueOffer.tenant_id == tenant_id,
        CallRecord.tenant_id == tenant_id,
        agent.is_not(None),
        CallQueueOffer.started_at >= start,
        CallQueueOffer.started_at < end,
    ]
    return _finish_filters(filters, scope, agent, employee_id)


def _operation_filters(tenant_id, start, end, scope, employee_id) -> list[ColumnElement]:
    filters: list[ColumnElement] = [
        CallAgentOperation.tenant_id == tenant_id,
        CallRecord.tenant_id == tenant_id,
        CallAgentOperation.actor_agent_id.is_not(None),
        CallAgentOperation.started_at >= start,
        CallAgentOperation.started_at < end,
    ]
    return _finish_filters(filters, scope, CallAgentOperation.actor_agent_id, employee_id)


def _acw_filters(tenant_id, start, end, scope, employee_id) -> list[ColumnElement]:
    filters: list[ColumnElement] = [
        CallAgentAfterCallWork.tenant_id == tenant_id,
        CallRecord.tenant_id == tenant_id,
        CallAgentAfterCallWork.agent_id.is_not(None),
        CallAgentReceptionSegment.started_at >= start,
        CallAgentReceptionSegment.started_at < end,
    ]
    return _finish_filters(filters, scope, CallAgentAfterCallWork.agent_id, employee_id)


def _finish_filters(filters, scope, agent_column, employee_id) -> list[ColumnElement]:
    if scope is not None:
        filters.append(scope)
    if employee_id is not None:
        filters.append(agent_column == employee_id)
    return filters


def _bucket_key_sql(column, trend_type: TrendType, tz: ZoneInfo):
    local_ts = func.timezone(str(tz), column)
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


def _merge_rows(output: dict[int, dict], rows, snapshots: dict[int, str]) -> None:
    for row in rows:
        if row.employee_id is None:
            continue
        employee_id = int(row.employee_id)
        output.setdefault(employee_id, {}).update(
            {
                key: value
                for key, value in row._mapping.items()
                if key not in {"employee_id", "name_snapshot"}
            }
        )
        if getattr(row, "name_snapshot", None):
            snapshots[employee_id] = str(row.name_snapshot)


def _merge_buckets(output: dict[object, dict], rows) -> None:
    for row in rows:
        output.setdefault(row.bkey, {}).update(
            {key: value for key, value in row._mapping.items() if key != "bkey"}
        )


def _count_map(rows, key: str) -> dict[str, int]:
    return {str(getattr(row, key) or "unknown"): int(row.value or 0) for row in rows}
