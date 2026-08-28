"""Pin the engine-level slow-query ERROR contract used by log-based alerts."""
import logging
import time
from types import SimpleNamespace

from app.db import slow_query
from app.db.session import engine


def test_slow_query_logs_error_with_stable_fields(caplog, monkeypatch):
    monkeypatch.setattr(slow_query.settings, "DB_SLOW_QUERY_MS", 10_000)

    with caplog.at_level(logging.ERROR, logger=slow_query.logger.name):
        slow_query._maybe_log_slow_query(
            "SELECT id FROM conversations WHERE tenant_id = 1",
            214_597,
        )

    records = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "Slow query" in r.getMessage()
    ]
    assert len(records) == 1
    rec = records[0]
    assert rec.slow_query == "1"
    assert rec.duration_ms == "214597"
    assert rec.threshold_ms == "10000"
    assert "sql=SELECT id FROM conversations" in rec.getMessage()


def test_fast_query_does_not_log_error(caplog, monkeypatch):
    monkeypatch.setattr(slow_query.settings, "DB_SLOW_QUERY_MS", 10_000)

    with caplog.at_level(logging.ERROR, logger=slow_query.logger.name):
        slow_query._maybe_log_slow_query("SELECT 1", 29)

    assert not any("Slow query" in r.getMessage() for r in caplog.records)


def test_slow_query_log_disabled_when_threshold_zero(caplog, monkeypatch):
    monkeypatch.setattr(slow_query.settings, "DB_SLOW_QUERY_MS", 0)

    with caplog.at_level(logging.ERROR, logger=slow_query.logger.name):
        slow_query._maybe_log_slow_query("SELECT 1", 200_000)

    assert not any("Slow query" in r.getMessage() for r in caplog.records)


def test_slow_query_log_truncates_long_sql(caplog, monkeypatch):
    monkeypatch.setattr(slow_query.settings, "DB_SLOW_QUERY_MS", 1)

    with caplog.at_level(logging.ERROR, logger=slow_query.logger.name):
        slow_query._maybe_log_slow_query("SELECT " + "x" * 500, 12_000)

    rec = next(r for r in caplog.records if "Slow query" in r.getMessage())
    assert "..." in rec.getMessage()
    assert len(rec.getMessage()) < 500 + 80


def test_after_cursor_execute_logs_when_over_threshold(caplog, monkeypatch):
    monkeypatch.setattr(slow_query.settings, "DB_SLOW_QUERY_MS", 10_000)
    conn = SimpleNamespace(info={slow_query._START_KEY: time.monotonic() - 12.0})

    with caplog.at_level(logging.ERROR, logger=slow_query.logger.name):
        slow_query._after_cursor_execute(conn, None, "SELECT 1", None, None, False)

    assert any("Slow query" in r.getMessage() for r in caplog.records)
    assert slow_query._START_KEY not in conn.info


def test_on_cursor_error_logs_when_over_threshold(caplog, monkeypatch):
    monkeypatch.setattr(slow_query.settings, "DB_SLOW_QUERY_MS", 10_000)
    conn = SimpleNamespace(info={slow_query._START_KEY: time.monotonic() - 15.0})
    context = SimpleNamespace(connection=conn, statement="SELECT pg_sleep(15)")

    with caplog.at_level(logging.ERROR, logger=slow_query.logger.name):
        slow_query._on_cursor_error(context)

    assert any("Slow query" in r.getMessage() for r in caplog.records)


def test_register_slow_query_listener_is_idempotent():
    slow_query.register_slow_query_listener(engine)
    slow_query.register_slow_query_listener(engine)
    assert slow_query.event.contains(
        engine.sync_engine,
        "after_cursor_execute",
        slow_query._after_cursor_execute,
    )
