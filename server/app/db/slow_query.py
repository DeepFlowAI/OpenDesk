"""Engine-level slow-query interceptor.

Any statement on the DB pool that runs longer than ``DB_SLOW_QUERY_MS``
emits one ERROR, including statements that later succeed. Alerts can match
the stable body phrase ``Slow query``.
"""
import logging
import time

from sqlalchemy import event

from app.configs.settings import settings

logger = logging.getLogger(__name__)

_START_KEY = "slow_query_start"
_SQL_MAX = 300


def _normalize_sql(statement: str) -> str:
    sql = " ".join((statement or "").split())
    if len(sql) > _SQL_MAX:
        return sql[:_SQL_MAX] + "..."
    return sql


def _maybe_log_slow_query(statement: str, duration_ms: int) -> None:
    threshold = settings.DB_SLOW_QUERY_MS
    if threshold <= 0 or duration_ms < threshold:
        return
    logger.error(
        "Slow query — duration_ms=%d, threshold_ms=%d, sql=%s",
        duration_ms,
        threshold,
        _normalize_sql(statement),
        extra={
            "slow_query": "1",
            "duration_ms": str(duration_ms),
            "threshold_ms": str(threshold),
        },
    )


def _before_cursor_execute(conn, _cursor, _statement, _parameters, _context, _executemany):
    conn.info[_START_KEY] = time.monotonic()


def _after_cursor_execute(conn, _cursor, statement, _parameters, _context, _executemany):
    start = conn.info.pop(_START_KEY, None)
    if start is None:
        return
    _maybe_log_slow_query(statement, int((time.monotonic() - start) * 1000))


def _on_cursor_error(context) -> None:
    conn = context.connection
    if conn is None:
        return
    start = conn.info.pop(_START_KEY, None)
    if start is None:
        return
    _maybe_log_slow_query(
        context.statement or "",
        int((time.monotonic() - start) * 1000),
    )


def register_slow_query_listener(async_engine) -> None:
    """Attach once to an AsyncEngine's sync engine."""
    sync_engine = async_engine.sync_engine
    if event.contains(sync_engine, "after_cursor_execute", _after_cursor_execute):
        return
    event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(sync_engine, "after_cursor_execute", _after_cursor_execute)
    event.listen(sync_engine, "handle_error", _on_cursor_error)
