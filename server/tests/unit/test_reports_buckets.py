"""Unit tests for reports time bucket generation."""
from datetime import date
from zoneinfo import ZoneInfo

import pytest

import sys
import importlib

# The reports extension lives under private/extensions/server/. In a dev checkout
# its package path is mounted by app.extensions._augment_path_with_private_overlay
# at startup. Importing the app package triggers that augmentation.
import app.extensions  # noqa: F401 — triggers private overlay path injection

buckets = importlib.import_module("app.extensions.reports.lib.buckets")
TrendType = buckets.TrendType
generate_buckets = buckets.generate_buckets

TZ = ZoneInfo("Asia/Shanghai")


class TestGenerateBuckets:

    def test_half_hour_returns_48_buckets(self):
        result = generate_buckets(date(2026, 5, 19), date(2026, 5, 19), TrendType.HALF_HOUR, TZ)
        assert len(result) == 48
        assert result[0].label == "00:00"
        assert result[1].label == "00:30"
        assert result[2].label == "01:00"
        assert result[-1].label == "23:30"
        assert result[0].offset_seconds == 0
        assert result[1].offset_seconds == 1800
        assert result[-1].offset_seconds == 23 * 3600 + 1800

    def test_hour_returns_24_buckets(self):
        result = generate_buckets(date(2026, 5, 19), date(2026, 5, 19), TrendType.HOUR, TZ)
        assert len(result) == 24
        assert result[0].label == "00"
        assert result[10].label == "10"
        assert result[23].label == "23"
        assert result[10].offset_seconds == 10 * 3600

    def test_day_walking_range_inclusive(self):
        result = generate_buckets(date(2026, 5, 17), date(2026, 5, 19), TrendType.DAY, TZ)
        assert [b.label for b in result] == ["2026-05-17", "2026-05-18", "2026-05-19"]
        # Each bucket spans exactly one day.
        for b in result:
            assert (b.end - b.start).total_seconds() == 86400

    def test_week_snaps_to_monday(self):
        # 2026-05-19 is Tuesday; 2026-05-24 is Sunday — both within ISO W21.
        # The first bucket should snap back to Monday 2026-05-18.
        result = generate_buckets(date(2026, 5, 19), date(2026, 5, 24), TrendType.WEEK, TZ)
        assert len(result) == 1
        assert result[0].start.weekday() == 0  # Monday
        assert result[0].start.date() == date(2026, 5, 18)
        assert result[0].label == "2026-W21"

    def test_week_spans_iso_boundary(self):
        # 2026-05-19 (Tue, W21) through 2026-05-25 (Mon, W22) => two buckets
        result = generate_buckets(date(2026, 5, 19), date(2026, 5, 25), TrendType.WEEK, TZ)
        assert [b.label for b in result] == ["2026-W21", "2026-W22"]

    def test_month_walks_full_months(self):
        result = generate_buckets(date(2026, 1, 15), date(2026, 3, 10), TrendType.MONTH, TZ)
        labels = [b.label for b in result]
        assert labels == ["2026-01", "2026-02", "2026-03"]

    def test_month_wraps_year(self):
        result = generate_buckets(date(2025, 11, 1), date(2026, 2, 1), TrendType.MONTH, TZ)
        labels = [b.label for b in result]
        assert labels == ["2025-11", "2025-12", "2026-01", "2026-02"]
