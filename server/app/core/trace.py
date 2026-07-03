"""
Request trace context — provides a unique trace_id per request via contextvars.

Two correlation IDs are exposed:

* ``trace_id``    — full 128-bit hex (32 chars), one per HTTP request, also
                    used as the OpenTelemetry trace_id. Console shows the full
                    value, and it is returned in the ``X-Trace-Id`` response
                    header. Use to grep ONE request end-to-end.
* ``request_id``  — optional client-supplied correlation id carried in the
                    ``X-Request-Id`` request header. Useful when a caller wants
                    to correlate its own logs / error reports with a backend
                    trace.

Both are injected into every log record by ``TraceFilter`` so they:
  - show up in the console line prefix (trace_id only — request_id would be too
    verbose), and
  - get exported as searchable log attributes by the OTel LoggingHandler
    (i.e. you can query
    ``WHERE json_get_string(log_attributes, 'request_id') = '...'`` in your
    log backend).
"""
import logging
import uuid
from contextvars import ContextVar

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_call_id_var: ContextVar[str] = ContextVar("call_id", default="-")


def set_trace_id(trace_id: str | None = None) -> str:
    """Set trace_id for the current async context.

    Auto-generates a full 128-bit hex (32 chars) so the same value can be
    used as the OpenTelemetry trace_id (which is 128-bit by spec). The full
    value is what gets shipped to OTel / your log backend and returned in the
    ``X-Trace-Id`` response header, so clients and backend queries match
    byte-for-byte.
    """
    tid = trace_id or uuid.uuid4().hex
    _trace_id_var.set(tid)
    return tid


def get_trace_id() -> str:
    """Get trace_id from the current async context."""
    return _trace_id_var.get()


def parse_traceparent(traceparent: str | None) -> str | None:
    """Extract the 32-hex trace_id from a W3C ``traceparent`` header.

    Format: ``<version>-<trace_id>-<parent_id>-<flags>``. Returns ``None`` when
    the header is missing or malformed so callers can fall back to generating a
    fresh trace_id.
    """
    if not traceparent:
        return None
    parts = traceparent.split("-")
    if len(parts) < 4:
        return None
    trace_id = parts[1]
    if len(trace_id) != 32 or trace_id == "0" * 32:
        return None
    try:
        int(trace_id, 16)
    except ValueError:
        return None
    return trace_id


def build_traceparent(trace_id: str, *, sampled: bool = True) -> str:
    """Build a W3C ``traceparent`` header carrying ``trace_id``.

    Used when an inbound call arrives without a (valid) ``traceparent`` so we
    can still propagate our freshly-minted trace_id to downstream services
    (telephony kernel RPCs, the VoiceSpeed realtime mint) and keep one trace_id
    across the whole call.
    """
    span_id = uuid.uuid4().hex[:16]
    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{span_id}-{flags}"


def set_call_id(call_id: str | None) -> str:
    """Bind a call-center ``call_id`` to the current async context.

    Injected into every log record by ``TraceFilter`` (as the ``call_id`` log
    attribute) so all logs for one phone call can be queried by business key in
    addition to ``trace_id``.
    """
    cid = "-" if not call_id else str(call_id)
    _call_id_var.set(cid)
    return cid


def get_call_id() -> str:
    """Get the call-center call_id from the current async context."""
    return _call_id_var.get()


def get_trace_id_int() -> int | None:
    """Return the current trace_id as an int (128-bit), or None if unset/invalid.

    Used by the OpenTelemetry IdGenerator to align OTel's trace_id with the
    application's trace_id so the same value appears in the console log prefix,
    the X-Trace-Id response header, and the tracing backend's trace tree.
    """
    tid = _trace_id_var.get()
    if not tid or tid == "-":
        return None
    try:
        return int(tid, 16)
    except ValueError:
        return None


def set_request_id(request_id: str | None) -> str:
    """Set the client-supplied per-request correlation id.

    Clients can pass their own ``request_id`` (via the ``X-Request-Id`` header)
    so the same id appears in their logs and in the backend log backend, which
    makes cross-stack debugging trivial. If the caller does not pass one we
    leave the context var unset (``-``) — we already have ``trace_id`` serving
    as the canonical per-request id.
    """
    rid = "-" if not request_id else str(request_id)
    _request_id_var.set(rid)
    return rid


def get_request_id() -> str:
    """Get the client-supplied request_id from the current async context."""
    return _request_id_var.get()


class TraceFilter(logging.Filter):
    """Logging filter that injects ``trace_id`` and ``request_id`` into every
    log record.

    Both fields are added as record attributes — the stdout formatter uses
    ``%(trace_id)s`` directly, and the OTel ``LoggingHandler`` automatically
    forwards every non-standard record attribute as an OTLP log attribute.
    Net result: queries like
    ``WHERE json_get_string(log_attributes, 'request_id') = '...'`` work in
    your log backend without any further code changes.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_var.get()  # type: ignore[attr-defined]
        record.request_id = _request_id_var.get()  # type: ignore[attr-defined]
        record.call_id = _call_id_var.get()  # type: ignore[attr-defined]
        return True
