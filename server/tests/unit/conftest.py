"""Unit-test-only fixtures.

Kept under ``tests/unit/`` so these guards never apply to ``tests/integration/``,
which legitimately opens a real Postgres connection.
"""

from __future__ import annotations

import asyncpg
import pytest


_GUARD_MESSAGE = (
    "Unit test opened a real database connection via asyncpg.connect. "
    "tests/unit must stay hermetic — stub the service call that reaches the DB "
    "(see monkeypatch.setattr patterns in neighboring unit tests) instead of "
    "hitting DATABASE_URL."
)


@pytest.fixture(autouse=True)
def _block_real_asyncpg_connect(monkeypatch):
    """Fail loudly if any unit test opens a real Postgres connection."""

    async def _forbidden(*_args, **_kwargs):
        raise RuntimeError(_GUARD_MESSAGE)

    monkeypatch.setattr(asyncpg, "connect", _forbidden)
