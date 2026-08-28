"""Unit tests for call report query helpers."""
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import importlib

from sqlalchemy.dialects import postgresql

import app.extensions  # noqa: F401 - triggers private overlay path injection

call_queries = importlib.import_module("app.extensions.reports.lib.call_queries")
TrendType = importlib.import_module("app.extensions.reports.lib.buckets").TrendType


def test_metrics_from_empty_row_returns_zero_metrics():
    metrics = call_queries._metrics_from_row(None)

    assert metrics.total_calls == 0
    assert metrics.inbound_calls == 0
    assert metrics.answered_inbound_calls == 0
    assert metrics.outbound_calls == 0
    assert metrics.answered_outbound_calls == 0
    assert metrics.avg_inbound_talk_seconds is None
    assert metrics.avg_outbound_talk_seconds is None


def test_metrics_from_row_casts_numeric_values():
    row = SimpleNamespace(
        total_calls=4,
        inbound_calls=2,
        answered_inbound_calls=1,
        outbound_calls=2,
        answered_outbound_calls=1,
        avg_inbound_talk_seconds=180,
        avg_outbound_talk_seconds=300.5,
    )

    metrics = call_queries._metrics_from_row(row)

    assert metrics.total_calls == 4
    assert metrics.inbound_calls == 2
    assert metrics.answered_inbound_calls == 1
    assert metrics.outbound_calls == 2
    assert metrics.answered_outbound_calls == 1
    assert metrics.avg_inbound_talk_seconds == 180.0
    assert metrics.avg_outbound_talk_seconds == 300.5


def test_bucket_key_sql_converts_started_at_to_tenant_timezone():
    tz = ZoneInfo("Asia/Shanghai")
    compiled = call_queries._distribution_bucket_key_sql(TrendType.HOUR, tz).compile(
        dialect=postgresql.dialect()
    )
    sql = str(compiled).lower()
    assert "timezone(" in sql
    assert "started_at" in sql
    assert "asia/shanghai" in {
        str(value).lower() for value in compiled.params.values()
    }
