"""Helpers for rejected Socket.IO connect attempts.

A single client whose token has expired will, by default, let the Socket.IO
client reconnect forever. Each rejected attempt is individually harmless, so it
used to be logged at WARNING/INFO — which means a stuck tab buries the logs in
routine-looking noise and never trips an error alert.

`ConnectRejectionTracker` turns that volume into a signal: routine rejections
stay quiet (DEBUG at the call site), but once one source crosses a threshold
within a sliding window it is a reconnect storm and gets surfaced as a single,
rate-limited ERROR.
"""
import time
from collections import defaultdict, deque


def _first_client_ip(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    first = value.split(",", 1)[0].strip()
    return first or None


def client_ip_from_environ(environ: dict) -> str | None:
    """Real client IP behind the reverse proxy (falls back to the socket peer).

    Order matters: traffic passes through two nginx layers (gateway → edge), and
    the edge overwrites ``X-Real-IP`` with its own peer (the gateway container).
    The original client therefore only survives as the left-most entry of
    ``X-Forwarded-For``, so that is preferred over ``X-Real-IP`` here.
    """
    for key in ("HTTP_CF_CONNECTING_IP", "HTTP_X_FORWARDED_FOR", "HTTP_X_REAL_IP"):
        ip = _first_client_ip(environ.get(key))
        if ip:
            return ip
    return _first_client_ip(environ.get("REMOTE_ADDR"))


class ConnectRejectionTracker:
    """Per-source sliding-window counter for rejected socket connects.

    `record()` returns ``(count_in_window, should_alert)``:

    - ``count_in_window`` — rejections from this source within the last window.
    - ``should_alert`` — True when the source is storming AND no alert has been
      emitted for it within ``error_cooldown_seconds`` (so a sustained storm
      yields at most one ERROR per cooldown, not one per attempt).
    """

    def __init__(
        self,
        *,
        window_seconds: float = 60.0,
        storm_threshold: int = 20,
        error_cooldown_seconds: float = 60.0,
    ) -> None:
        self._window = window_seconds
        self._threshold = storm_threshold
        self._cooldown = error_cooldown_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_error_at: dict[str, float] = {}

    def record(self, source: str) -> tuple[int, bool]:
        now = time.monotonic()
        hits = self._hits[source]
        hits.append(now)
        cutoff = now - self._window
        while hits and hits[0] < cutoff:
            hits.popleft()
        count = len(hits)

        should_alert = False
        if count >= self._threshold:
            last = self._last_error_at.get(source, 0.0)
            if now - last >= self._cooldown:
                self._last_error_at[source] = now
                should_alert = True

        # Bound memory: drop the bucket once it ages out so a churn of one-shot
        # clients can't accumulate keys forever.
        if not hits:
            self._hits.pop(source, None)
            self._last_error_at.pop(source, None)
        return count, should_alert
