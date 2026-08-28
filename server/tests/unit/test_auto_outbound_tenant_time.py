"""Unit tests for tenant timezone resolution."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.services.auto_outbound.tenant_time import (
    clear_tenant_timezone_cache,
    resolve_tenant_timezone,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_tenant_timezone_cache()
    yield
    clear_tenant_timezone_cache()


@pytest.mark.asyncio
async def test_resolve_tenant_timezone_from_settings():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "America/New_York"
    db.execute = AsyncMock(return_value=result)

    tz = await resolve_tenant_timezone(db, 42)
    assert tz == ZoneInfo("America/New_York")
    # Cached — second call does not hit DB.
    tz2 = await resolve_tenant_timezone(db, 42)
    assert tz2 is tz
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_resolve_tenant_timezone_invalid_falls_back():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "Not/A_Real_Zone"
    db.execute = AsyncMock(return_value=result)

    tz = await resolve_tenant_timezone(db, 7)
    assert tz == ZoneInfo("Asia/Shanghai")


@pytest.mark.asyncio
async def test_resolve_tenant_timezone_missing_row():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    tz = await resolve_tenant_timezone(db, 9)
    assert tz == ZoneInfo("Asia/Shanghai")
