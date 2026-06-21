from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque
from typing import Any

from app.configs.settings import settings
from app.core.trace import _request_id_var, _trace_id_var, set_request_id, set_trace_id
from app.schemas.telemetry import (
    MAX_EVENTS_PER_BATCH,
    MAX_KEY_CHARS,
    MAX_KEYS_PER_DICT,
    MAX_VALUE_CHARS,
    TelemetryBatchRequest,
    TelemetryBatchResponse,
    TelemetryEvent,
    TelemetryLevel,
)


_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_FRONTEND_LOGGER_NAME = "app.frontend.event"
logger = logging.getLogger(_FRONTEND_LOGGER_NAME)

_RESERVED_LOG_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }
)


def _coerce_str(value: Any) -> str:
    out = "true" if value is True else "false" if value is False else str(value)
    if len(out) > MAX_VALUE_CHARS:
        return out[:MAX_VALUE_CHARS] + f"...({len(out) - MAX_VALUE_CHARS} more)"
    return out


# Rate-limit per-event INFO logging so a frontend stuck in a reconnect loop
# (e.g. a tab firing `socket_connect_requested` every few hundred ms) can't
# flood the log backend. warn/error events are never throttled — those are the
# signal we want to keep. Limits are per event name within a sliding window.
_LOG_WINDOW_SECONDS = 10.0
_LOG_MAX_PER_WINDOW = 5
_log_hits: dict[str, deque[float]] = defaultdict(deque)
_log_suppressed: dict[str, int] = defaultdict(int)


def _frontend_log_decision(name: str) -> tuple[bool, int]:
    """Return ``(allow, suppressed_since_last_allow)`` for an INFO event."""
    now = time.monotonic()
    hits = _log_hits[name]
    cutoff = now - _LOG_WINDOW_SECONDS
    while hits and hits[0] < cutoff:
        hits.popleft()
    if len(hits) < _LOG_MAX_PER_WINDOW:
        hits.append(now)
        return True, _log_suppressed.pop(name, 0)
    _log_suppressed[name] += 1
    return False, 0


def _log_frontend_event(event: TelemetryEvent, extra: dict[str, str]) -> None:
    level = _level_to_log(event.level)
    if level >= logging.WARNING:
        logger.log(level, "frontend event: %s", event.name, extra=extra)
        return
    allow, suppressed = _frontend_log_decision(event.name)
    if not allow:
        return
    if suppressed:
        logger.log(
            level,
            "frontend event: %s (+%d suppressed in last %ds)",
            event.name, suppressed, int(_LOG_WINDOW_SECONDS), extra=extra,
        )
    else:
        logger.log(level, "frontend event: %s", event.name, extra=extra)


def _level_to_log(level: TelemetryLevel) -> int:
    if level == "warn":
        return logging.WARNING
    if level == "error":
        return logging.ERROR
    return logging.INFO


def _flatten_dict(target: dict[str, str], prefix: str, source: dict[str, Any] | None) -> None:
    if not source:
        return
    written = 0
    for key, value in source.items():
        if written >= MAX_KEYS_PER_DICT:
            break
        if not isinstance(key, str) or not key or len(key) > MAX_KEY_CHARS:
            continue
        if not _KEY_PATTERN.match(key):
            continue
        attr_name = f"{prefix}{key}"
        if attr_name in _RESERVED_LOG_RECORD_ATTRS:
            continue
        target[attr_name] = _coerce_str(value)
        written += 1


def _common_to_attrs(common) -> dict[str, str]:  # noqa: ANN001
    attrs: dict[str, str] = {
        "session_id": common.session_id,
        "device_id": common.device_id,
    }
    for key in (
        "user_id",
        "release",
        "url",
        "user_agent",
        "network_type",
        "viewport",
        "sdk_name",
        "sdk_version",
    ):
        value = getattr(common, key, None)
        if value is not None:
            attrs[key] = _coerce_str(value)
    if common.ts_offset_ms is not None:
        attrs["ts_offset_ms"] = str(common.ts_offset_ms)
    return attrs


def _build_extra(
    event: TelemetryEvent,
    common_attrs: dict[str, str],
    channel_attrs: dict[str, str],
) -> dict[str, str]:
    extra: dict[str, str] = {}
    extra.update(channel_attrs)
    extra.update(common_attrs)
    extra["event"] = event.name
    extra["event_ts_ms"] = str(event.ts)
    extra["event_level"] = event.level

    if event.trace_id:
        extra["trace_id"] = event.trace_id
    if event.conversation_external_id:
        extra["conversation_external_id"] = event.conversation_external_id
    if event.request_id:
        extra["request_id"] = event.request_id
    if event.client_message_id:
        extra["client_message_id"] = event.client_message_id

    _flatten_dict(extra, "props_", event.props)
    _flatten_dict(extra, "metrics_", event.metrics)
    return extra


class TelemetryService:
    @staticmethod
    async def ingest(*, channel, body: TelemetryBatchRequest) -> TelemetryBatchResponse:  # noqa: ANN001
        incoming = list(body.events)
        accepted_events = incoming[:MAX_EVENTS_PER_BATCH]
        dropped = len(incoming) - len(accepted_events)

        if not settings.TELEMETRY_ENABLED:
            return TelemetryBatchResponse(accepted=0, dropped=len(incoming))
        if not accepted_events:
            return TelemetryBatchResponse(accepted=0, dropped=dropped)

        common_attrs = _common_to_attrs(body.common)
        channel_attrs: dict[str, str] = {
            "channel_key": channel.channel_key,
            "channel_id": str(channel.id),
            "tenant_id": str(channel.tenant_id),
        }

        prev_trace = _trace_id_var.get()
        prev_req = _request_id_var.get()

        try:
            for event in accepted_events:
                if event.trace_id:
                    set_trace_id(event.trace_id)
                else:
                    _trace_id_var.set("-")
                if event.request_id:
                    set_request_id(event.request_id)
                else:
                    _request_id_var.set("-")

                extra = _build_extra(event, common_attrs, channel_attrs)
                _log_frontend_event(event, extra)
        finally:
            _trace_id_var.set(prev_trace)
            _request_id_var.set(prev_req)

        return TelemetryBatchResponse(accepted=len(accepted_events), dropped=dropped)

    @staticmethod
    async def ingest_app(
        *,
        body: TelemetryBatchRequest,
        user_payload: dict | None = None,
    ) -> TelemetryBatchResponse:
        incoming = list(body.events)
        accepted_events = incoming[:MAX_EVENTS_PER_BATCH]
        dropped = len(incoming) - len(accepted_events)

        if not settings.TELEMETRY_ENABLED:
            return TelemetryBatchResponse(accepted=0, dropped=len(incoming))
        if not accepted_events:
            return TelemetryBatchResponse(accepted=0, dropped=dropped)

        common_attrs = _common_to_attrs(body.common)
        app_attrs: dict[str, str] = {"source": "opendesk-web"}
        if user_payload:
            tenant_id = user_payload.get("tenant_id")
            user_id = user_payload.get("user_id") or user_payload.get("sub")
            if tenant_id is not None:
                app_attrs["tenant_id"] = str(tenant_id)
            if user_id is not None:
                app_attrs["user_id"] = str(user_id)

        prev_trace = _trace_id_var.get()
        prev_req = _request_id_var.get()

        try:
            for event in accepted_events:
                if event.trace_id:
                    set_trace_id(event.trace_id)
                else:
                    _trace_id_var.set("-")
                if event.request_id:
                    set_request_id(event.request_id)
                else:
                    _request_id_var.set("-")

                extra = _build_extra(event, common_attrs, app_attrs)
                _log_frontend_event(event, extra)
        finally:
            _trace_id_var.set(prev_trace)
            _request_id_var.set(prev_req)

        return TelemetryBatchResponse(accepted=len(accepted_events), dropped=dropped)
