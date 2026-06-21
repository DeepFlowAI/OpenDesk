"""
Observability Provider — vendor-neutral abstraction for log / trace shipping.

Why an interface:
    The remote system speaks OTLP (e.g. a GreptimeDB-compatible pipeline).
    Tomorrow it might be SigNoz, Honeycomb, Aliyun SLS, or a self-hosted
    Tempo+Loki stack. By funnelling every emit through a single interface,
    switching vendors is a one-line factory change — business code never
    imports OpenTelemetry directly.

Two things this layer models:
    1. Console logs  — captured via a stdlib ``logging`` handler attachment.
                       The provider returns the handler; ``setup_logging()``
                       wires it onto the root logger.
    2. Spans         — opened via ``start_span()`` so individual flows
                       (a queue cycle, a call lifecycle, an IM round …) can be
                       traced when needed. Unused flows stay zero-cost.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Protocol


class ObservabilitySpan(Protocol):
    """Minimal span surface — same shape regardless of underlying SDK."""

    def set_attribute(self, key: str, value: object) -> None: ...
    def set_status_ok(self) -> None: ...
    def set_status_error(self, message: str) -> None: ...
    def add_event(self, name: str, attributes: dict | None = None) -> None: ...


class ObservabilityProvider(Protocol):
    """Facade over the underlying telemetry SDK."""

    name: str

    def init(self) -> None:
        """Initialize exporters / processors. Idempotent."""

    def shutdown(self) -> None:
        """Flush buffers and tear down. Called on app shutdown."""

    def get_log_handler(self) -> logging.Handler | None:
        """Return a stdlib ``logging.Handler`` to attach to the root logger,
        or None if this backend does not capture console logs.
        """

    @contextmanager
    def start_span(
        self, name: str, attributes: dict | None = None
    ) -> Iterator[ObservabilitySpan]:
        """Open a span on the application tracer.

        Use to trace a discrete unit of work (queue assignment cycle, call
        lifecycle, IM message round …). Attach domain ids (``tenant.id``,
        ``ticket.id``, ``call.id`` …) so downstream queries can group by them.
        """
        yield  # type: ignore[misc]

    def get_current_span(self) -> ObservabilitySpan:
        """Return the currently active span (or a no-op span if none).

        Used by deeply nested code that needs to enrich the surrounding
        span — e.g. setting an id that only becomes known after a DB insert.
        Callers never have to know which span is active; they just call
        ``current_span().set_attribute(...)``.
        """
        ...
