"""
Logging setup — wires the stdout handler and the observability log handler.

The observability backend (OTLP / GreptimeDB / SigNoz / …) is attached here as
a second handler on the root logger, so every ``logger.info(...)`` the app
emits is shipped to the remote log backend with no business-code changes. When
the backend is ``noop`` this returns None and we keep stdout-only behavior.
"""
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from app.configs.settings import settings
from app.core.trace import TraceFilter
from app.libs.observability import get_provider

# Console shows the full 32-char OTel trace_id so it can be copied directly
# into your log backend queries as an exact match — no LIKE needed. The same
# value is also returned in the X-Trace-Id HTTP response header.
TEXT_FORMAT = (
    "%(asctime)s | %(levelname)-8s | [%(trace_id)s] "
    "%(name)s:%(funcName)s:%(lineno)d - %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class JsonFormatter(logging.Formatter):
    """Single-line JSON formatter. Multi-line messages are preserved as escaped
    \\n inside the JSON string, so every log record is exactly one line."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "Z",
            "level": record.levelname,
            "trace_id": getattr(record, "trace_id", "-"),
            "logger": record.name,
            "func": record.funcName,
            "line": record.lineno,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


class DowngradeCancelledPoolErrorsFilter(logging.Filter):
    """Downgrade SQLAlchemy connection-pool ERRORs caused by request
    cancellation (client disconnect) to WARNING.

    When an ASGI request task is cancelled mid-flight (client closed the
    connection, gateway timeout, …) the cancellation propagates into the async
    DB session teardown, and SQLAlchemy logs ``Exception terminating
    connection ...`` at ERROR with a CancelledError. The connection is simply
    discarded and recreated — benign noise — but it trips the
    ERROR/FATAL/CRITICAL log alert. Record it as WARNING so the alert stays
    quiet while real pool errors (connection refused, network drops) still
    surface at ERROR.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR and record.name.startswith(
            "sqlalchemy.pool"
        ):
            exc = record.exc_info[1] if record.exc_info else None
            if isinstance(exc, asyncio.CancelledError) or (
                exc is not None and "cancel scope" in str(exc)
            ):
                record.levelno = logging.WARNING
                record.levelname = "WARNING"
        return True


def setup_logging() -> None:
    level = logging.DEBUG if settings.DEBUG else logging.INFO

    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        root.handlers.clear()

    downgrade_filter = DowngradeCancelledPoolErrorsFilter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.addFilter(TraceFilter())
    handler.addFilter(downgrade_filter)

    if settings.LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(TEXT_FORMAT, datefmt=DATE_FORMAT))

    root.addHandler(handler)

    # Pipe everything the app writes via stdlib logging into the configured
    # observability backend (OTLP / GreptimeDB / SigNoz / …). When the backend
    # is "noop" this returns None and we keep stdout-only behavior.
    otel_handler = get_provider().get_log_handler()
    if otel_handler is not None:
        otel_handler.setLevel(level)
        otel_handler.addFilter(TraceFilter())
        otel_handler.addFilter(downgrade_filter)
        root.addHandler(otel_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # Per-connection WebSocket lifecycle noise. With socket.io's polling +
    # websocket transports a single client opens/closes many short-lived
    # connections, and a client stuck reconnecting floods these at INFO
    # ("WebSocket ... [accepted]", "connection open", "connection closed").
    # Keep WARNING+ so real protocol errors still surface; reconnect storms are
    # surfaced separately as an ERROR by app.socketio.connect_throttle.
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )
    # OpenTelemetry logs a harmless ERROR ("Failed to detach context") when a
    # span context token is detached in a different asyncio context than the
    # one that attached it — common with streaming responses / async
    # generators. It does not affect tracing or business logic, so silence
    # this specific noise.
    logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)
