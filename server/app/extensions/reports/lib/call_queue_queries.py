"""SQL aggregation helpers for persisted call queue facts."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, and_, case, cast, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.call_queue_fact import CallQueueOffer, CallQueueVisit
from app.models.call_record import CallRecord

from .buckets import TrendType


QueueKey = tuple[str, int]
VALID_RESULTS = ("answered", "abandoned", "timeout", "transfer_out", "canceled")


async def fetch_queue_metrics(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    scope_predicate: ColumnElement | None,
    queue_type: str | None = None,
    queue_id: int | None = None,
) -> tuple[dict[QueueKey, dict], dict[QueueKey, str]]:
    """Aggregate raw visit and offer counters by queue."""
    visit_rows = (
        await db.execute(
            select(
                CallQueueVisit.queue_type,
                CallQueueVisit.queue_id,
                func.max(CallQueueVisit.queue_name_snapshot).label("queue_name_snapshot"),
                *_visit_columns(),
            )
            .join(CallRecord, CallRecord.id == CallQueueVisit.call_record_id)
            .where(
                *_filters(
                    tenant_id,
                    range_start,
                    range_end,
                    scope_predicate,
                    queue_type,
                    queue_id,
                )
            )
            .group_by(CallQueueVisit.queue_type, CallQueueVisit.queue_id)
        )
    ).all()
    offer_rows = (
        await db.execute(
            select(
                CallQueueVisit.queue_type,
                CallQueueVisit.queue_id,
                *_offer_columns(),
            )
            .select_from(CallQueueOffer)
            .join(CallQueueVisit, CallQueueVisit.id == CallQueueOffer.queue_visit_id)
            .join(CallRecord, CallRecord.id == CallQueueVisit.call_record_id)
            .where(
                *_filters(
                    tenant_id,
                    range_start,
                    range_end,
                    scope_predicate,
                    queue_type,
                    queue_id,
                )
            )
            .group_by(CallQueueVisit.queue_type, CallQueueVisit.queue_id)
        )
    ).all()
    metrics: dict[QueueKey, dict] = {}
    snapshots: dict[QueueKey, str] = {}
    for row in visit_rows:
        key = (str(row.queue_type), int(row.queue_id))
        metrics[key] = _row_dict(row)
        if row.queue_name_snapshot:
            snapshots[key] = str(row.queue_name_snapshot)
    for row in offer_rows:
        key = (str(row.queue_type), int(row.queue_id))
        metrics.setdefault(key, {}).update(_row_dict(row))
    return metrics, snapshots


async def fetch_queue_trend_metrics(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    trend_type: TrendType,
    tz: ZoneInfo,
    *,
    queue_type: str,
    queue_id: int,
    scope_predicate: ColumnElement | None,
) -> dict[object, dict]:
    """Aggregate raw counters by one queue's entry-time buckets."""
    bucket = _bucket_key_sql(trend_type, tz)
    filters = _filters(
        tenant_id,
        range_start,
        range_end,
        scope_predicate,
        queue_type,
        queue_id,
    )
    visit_rows = (
        await db.execute(
            select(bucket.label("bkey"), *_visit_columns())
            .join(CallRecord, CallRecord.id == CallQueueVisit.call_record_id)
            .where(*filters)
            .group_by(literal_column("bkey"))
        )
    ).all()
    offer_rows = (
        await db.execute(
            select(bucket.label("bkey"), *_offer_columns())
            .select_from(CallQueueOffer)
            .join(CallQueueVisit, CallQueueVisit.id == CallQueueOffer.queue_visit_id)
            .join(CallRecord, CallRecord.id == CallQueueVisit.call_record_id)
            .where(*filters)
            .group_by(literal_column("bkey"))
        )
    ).all()
    output = {row.bkey: _row_dict(row) for row in visit_rows}
    for row in offer_rows:
        output.setdefault(row.bkey, {}).update(_row_dict(row))
    return output


async def fetch_queue_distributions(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    queue_type: str,
    queue_id: int,
    scope_predicate: ColumnElement | None,
) -> dict[str, dict[str, int]]:
    """Return fixed-enum distribution counts for one queue."""
    filters = _filters(
        tenant_id,
        range_start,
        range_end,
        scope_predicate,
        queue_type,
        queue_id,
    )
    exit_rows = (
        await db.execute(
            select(CallQueueVisit.result, func.count(CallQueueVisit.id).label("value"))
            .join(CallRecord, CallRecord.id == CallQueueVisit.call_record_id)
            .where(*filters, CallQueueVisit.result_reliable.is_(True))
            .group_by(CallQueueVisit.result)
        )
    ).all()
    wait_bucket = _wait_bucket()
    wait_rows = (
        await db.execute(
            select(wait_bucket.label("bucket"), func.count(CallQueueVisit.id).label("value"))
            .join(CallRecord, CallRecord.id == CallQueueVisit.call_record_id)
            .where(
                *filters,
                CallQueueVisit.result_reliable.is_(True),
                CallQueueVisit.wait_duration_ms.is_not(None),
            )
            .group_by(wait_bucket)
        )
    ).all()
    offer_rows = (
        await db.execute(
            select(CallQueueOffer.result, func.count(CallQueueOffer.id).label("value"))
            .select_from(CallQueueOffer)
            .join(CallQueueVisit, CallQueueVisit.id == CallQueueOffer.queue_visit_id)
            .join(CallRecord, CallRecord.id == CallQueueVisit.call_record_id)
            .where(*filters, CallQueueOffer.result_reliable.is_(True))
            .group_by(CallQueueOffer.result)
        )
    ).all()
    return {
        "queue_exit_result": {str(row.result): int(row.value or 0) for row in exit_rows},
        "queue_wait_duration": {str(row.bucket): int(row.value or 0) for row in wait_rows},
        "offer_result": {str(row.result): int(row.value or 0) for row in offer_rows},
    }


def _filters(
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    scope_predicate: ColumnElement | None,
    queue_type: str | None,
    queue_id: int | None,
) -> list[ColumnElement]:
    filters: list[ColumnElement] = [
        CallQueueVisit.tenant_id == tenant_id,
        CallRecord.tenant_id == tenant_id,
        CallQueueVisit.entered_at >= range_start,
        CallQueueVisit.entered_at < range_end,
    ]
    if scope_predicate is not None:
        filters.append(scope_predicate)
    if queue_type is not None:
        filters.append(CallQueueVisit.queue_type == queue_type)
    if queue_id is not None:
        filters.append(CallQueueVisit.queue_id == queue_id)
    return filters


def _visit_columns() -> tuple:
    visit = CallQueueVisit
    valid = and_(visit.result_reliable.is_(True), visit.result.in_(VALID_RESULTS))
    answered = and_(valid, visit.result == "answered")
    abandoned = and_(valid, visit.result == "abandoned")
    wait_valid = and_(valid, visit.wait_duration_ms.is_not(None))
    service_valid = and_(valid, visit.is_short_abandon.is_(False))
    return (
        func.count(func.distinct(visit.call_record_id)).label("queue_call_count"),
        func.count(visit.id).label("queue_entry_count"),
        func.count(visit.id).filter(visit.entry_kind == "first").label("first_queue_entry_count"),
        func.count(visit.id)
        .filter(visit.entry_kind == "transfer_in")
        .label("transfer_in_entry_count"),
        func.count(visit.id).filter(valid).label("valid_result_count"),
        func.count(visit.id).filter(answered).label("queue_answered_count"),
        func.count(visit.id).filter(abandoned).label("queue_abandoned_count"),
        func.count(visit.id)
        .filter(and_(abandoned, visit.is_short_abandon.is_(True)))
        .label("queue_short_abandon_count"),
        func.count(visit.id)
        .filter(and_(valid, visit.result == "timeout"))
        .label("queue_timeout_count"),
        func.count(visit.id)
        .filter(and_(valid, visit.result == "transfer_out"))
        .label("queue_transfer_out_count"),
        func.sum(visit.wait_duration_ms)
        .filter(and_(answered, visit.wait_duration_ms.is_not(None)))
        .label("answer_wait_total_ms"),
        func.count(visit.id)
        .filter(and_(answered, visit.wait_duration_ms.is_not(None)))
        .label("answer_wait_count"),
        func.sum(visit.wait_duration_ms)
        .filter(and_(abandoned, visit.wait_duration_ms.is_not(None)))
        .label("abandon_wait_total_ms"),
        func.count(visit.id)
        .filter(and_(abandoned, visit.wait_duration_ms.is_not(None)))
        .label("abandon_wait_count"),
        func.sum(visit.wait_duration_ms).filter(wait_valid).label("queue_wait_total_ms"),
        func.count(visit.id).filter(wait_valid).label("queue_wait_count"),
        func.max(visit.wait_duration_ms).filter(wait_valid).label("max_queue_wait_ms"),
        func.count(visit.id).filter(service_valid).label("service_level_count"),
        func.count(visit.id).filter(
            and_(service_valid, visit.result == "answered", visit.wait_duration_ms <= 20_000)
        ).label("service_level_answered_count"),
    )


def _offer_columns() -> tuple:
    offer = CallQueueOffer
    rate_valid = and_(
        offer.result_reliable.is_(True),
        offer.result.in_(("accepted", "rejected", "timeout")),
    )
    return (
        func.count(func.distinct(offer.call_record_id)).label("offered_call_count"),
        func.count(offer.id).label("offer_attempt_count"),
        func.count(offer.id).filter(offer.result == "accepted").label("offer_accepted_count"),
        func.count(offer.id).filter(offer.result == "rejected").label("offer_rejected_count"),
        func.count(offer.id).filter(offer.result == "timeout").label("offer_timeout_count"),
        func.count(offer.id).filter(rate_valid).label("offer_rate_denominator"),
    )


def _bucket_key_sql(trend_type: TrendType, tz: ZoneInfo):
    local_ts = func.timezone(str(tz), CallQueueVisit.entered_at)
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


def _wait_bucket():
    wait = CallQueueVisit.wait_duration_ms
    return case(
        (wait <= 5_000, "0_5s"),
        (wait <= 20_000, "5_20s"),
        (wait <= 60_000, "20_60s"),
        (wait <= 180_000, "60_180s"),
        else_="over_180s",
    )


def _row_dict(row) -> dict:
    return {
        key: value
        for key, value in row._mapping.items()
        if key not in {"queue_type", "queue_id", "queue_name_snapshot", "bkey"}
    }
