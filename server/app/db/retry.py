"""Retry short database operations after PostgreSQL deadlocks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEADLOCK_SQLSTATE = "40P01"
DEFAULT_DEADLOCK_ATTEMPTS = 3


def is_deadlock_error(exc: BaseException) -> bool:
    """True when PostgreSQL aborted the transaction with 40P01."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "sqlstate", None) == DEADLOCK_SQLSTATE:
            return True
        if type(current).__name__ == "DeadlockDetectedError":
            return True
        orig = getattr(current, "orig", None)
        if isinstance(orig, BaseException):
            current = orig
            continue
        current = current.__cause__
    return "deadlock detected" in str(exc).lower()


async def run_db_op_with_deadlock_retry(
    op: Callable[[], Awaitable[T]],
    *,
    attempts: int = DEFAULT_DEADLOCK_ATTEMPTS,
    log_label: str = "db_op",
) -> T:
    """Re-run ``op`` after a deadlock. ``op`` must open a fresh session each time."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await op()
        except Exception as exc:
            last_exc = exc
            if not is_deadlock_error(exc) or attempt >= attempts:
                raise
            logger.warning(
                "%s deadlock retry attempt=%s/%s",
                log_label,
                attempt,
                attempts,
            )
            await asyncio.sleep(0.05 * attempt)
    assert last_exc is not None
    raise last_exc
