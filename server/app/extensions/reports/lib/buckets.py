"""Time bucket generation for session report trends.

A "bucket" is a closed-open interval `[start, end)` with a display label. The
list of buckets is generated from a date range + trend type + tenant tz, and
becomes the X-axis of the trend chart.

Bucket semantics by trend type:
- half_hour / hour: 48 / 24 buckets representing the daily distribution
  across the whole range (e.g. hour=10 aggregates 10:00–10:59 of every
  day in the range). The start/end fields are placeholders at epoch
  with the correct offset-of-day; callers should use ``offset_seconds``
  for SQL grouping instead.
- day / week / month: walking buckets covering [range_start, range_end].
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo


class TrendType(str, Enum):
    HALF_HOUR = "half_hour"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True, slots=True)
class TimeBucket:
    # For day/week/month: real absolute bounds in tenant tz.
    # For half_hour/hour: a representative interval anchored at range_start,
    # only useful for X-axis labels; use offset_seconds for SQL grouping.
    start: datetime
    end: datetime
    label: str
    # Distribution buckets only — seconds-from-day-start for SQL grouping.
    # None for absolute buckets (day/week/month).
    offset_seconds: int | None = None


def generate_buckets(
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    tz: ZoneInfo,
) -> list[TimeBucket]:
    if trend_type is TrendType.HALF_HOUR:
        return _half_hour_buckets(start_date, tz)
    if trend_type is TrendType.HOUR:
        return _hour_buckets(start_date, tz)
    if trend_type is TrendType.DAY:
        return _day_buckets(start_date, end_date, tz)
    if trend_type is TrendType.WEEK:
        return _week_buckets(start_date, end_date, tz)
    if trend_type is TrendType.MONTH:
        return _month_buckets(start_date, end_date, tz)
    raise ValueError(f"Unsupported trend type: {trend_type}")


def _half_hour_buckets(anchor_date: date, tz: ZoneInfo) -> list[TimeBucket]:
    anchor_midnight = datetime.combine(anchor_date, time.min, tzinfo=tz)
    buckets: list[TimeBucket] = []
    for i in range(48):
        offset = i * 30 * 60
        start = anchor_midnight + timedelta(seconds=offset)
        end = start + timedelta(minutes=30)
        buckets.append(
            TimeBucket(
                start=start,
                end=end,
                label=f"{i // 2:02d}:{'30' if i % 2 else '00'}",
                offset_seconds=offset,
            )
        )
    return buckets


def _hour_buckets(anchor_date: date, tz: ZoneInfo) -> list[TimeBucket]:
    anchor_midnight = datetime.combine(anchor_date, time.min, tzinfo=tz)
    buckets: list[TimeBucket] = []
    for h in range(24):
        offset = h * 3600
        start = anchor_midnight + timedelta(seconds=offset)
        end = start + timedelta(hours=1)
        buckets.append(
            TimeBucket(
                start=start,
                end=end,
                label=f"{h:02d}",
                offset_seconds=offset,
            )
        )
    return buckets


def _day_buckets(start_date: date, end_date: date, tz: ZoneInfo) -> list[TimeBucket]:
    buckets: list[TimeBucket] = []
    cursor = start_date
    while cursor <= end_date:
        start = datetime.combine(cursor, time.min, tzinfo=tz)
        end = start + timedelta(days=1)
        buckets.append(TimeBucket(start=start, end=end, label=cursor.isoformat()))
        cursor += timedelta(days=1)
    return buckets


def _week_buckets(start_date: date, end_date: date, tz: ZoneInfo) -> list[TimeBucket]:
    # ISO week: Monday-anchored. Snap the first bucket back to the Monday on
    # or before start_date, otherwise the first week would have <7 days.
    first_monday = start_date - timedelta(days=start_date.weekday())
    buckets: list[TimeBucket] = []
    cursor = first_monday
    while cursor <= end_date:
        start = datetime.combine(cursor, time.min, tzinfo=tz)
        end = start + timedelta(days=7)
        iso_year, iso_week, _ = cursor.isocalendar()
        buckets.append(
            TimeBucket(start=start, end=end, label=f"{iso_year}-W{iso_week:02d}")
        )
        cursor += timedelta(days=7)
    return buckets


def _month_buckets(start_date: date, end_date: date, tz: ZoneInfo) -> list[TimeBucket]:
    buckets: list[TimeBucket] = []
    y, m = start_date.year, start_date.month
    while True:
        start = datetime(y, m, 1, tzinfo=tz)
        if m == 12:
            end = datetime(y + 1, 1, 1, tzinfo=tz)
        else:
            end = datetime(y, m + 1, 1, tzinfo=tz)
        buckets.append(TimeBucket(start=start, end=end, label=f"{y:04d}-{m:02d}"))
        if y > end_date.year or (y == end_date.year and m >= end_date.month):
            break
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return buckets
