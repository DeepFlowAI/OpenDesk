"""
Observability — vendor-neutral telemetry layer.

Public API:
    init_observability() / shutdown_observability()
        Lifecycle hooks (call once at app startup / shutdown).

    get_provider()
        Read the active provider, e.g. to attach its log handler to the
        stdlib root logger inside ``setup_logging()``.

    span(name, attributes)
        Span context manager on the application tracer. Use to trace a
        discrete unit of work (queue cycle, call lifecycle, IM round …).

    current_span()
        Returns the currently active span (or a no-op span if none). Use this
        to enrich the surrounding span when an attribute only becomes known
        after the span has already been opened.
"""
from app.libs.observability.factory import (
    get_provider,
    init_observability,
    shutdown_observability,
)
from app.libs.observability.helpers import current_span, span

__all__ = [
    "init_observability",
    "shutdown_observability",
    "get_provider",
    "span",
    "current_span",
]
