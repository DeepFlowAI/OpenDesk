"""Unit tests for session RoutingService condition matching."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.channel_service import ChannelService
from app.services.routing_service import RoutingService


def _channel(cid: int, tenant_id: int = 7, access_mode: str = "url") -> SimpleNamespace:
    return SimpleNamespace(id=cid, tenant_id=tenant_id, access_mode=access_mode)


def _service_hours(**overrides):
    data = {
        "id": 1,
        "tenant_id": 7,
        "weekly_schedules": [
            {"day_of_week": 1, "slots": [{"start": "09:00", "end": "18:00"}]},
        ],
        "holidays": [],
        "makeup_days": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_rule_matches_channel_eq_web_sdk():
    ch = _channel(3, access_mode="url")
    ok = await RoutingService._rule_matches(
        AsyncMock(),
        7,
        ch,
        [{"condition_type": "channel", "operator": "eq", "value": "websdk"}],
    )
    assert ok is True


@pytest.mark.asyncio
async def test_rule_matches_channel_eq_sdk_legacy_alias():
    ch = _channel(3, access_mode="embed")
    ok = await RoutingService._rule_matches(
        AsyncMock(),
        7,
        ch,
        [{"condition_type": "channel", "operator": "eq", "value": "sdk"}],
    )
    assert ok is True


@pytest.mark.asyncio
async def test_rule_matches_web_sdk_eq_by_channel_id():
    ch = _channel(42)
    ok = await RoutingService._rule_matches(
        AsyncMock(),
        7,
        ch,
        [{"condition_type": "web_sdk", "operator": "eq", "value": "42"}],
    )
    assert ok is True


@pytest.mark.asyncio
async def test_rule_matches_web_sdk_ne():
    ch = _channel(42)
    ok = await RoutingService._rule_matches(
        AsyncMock(),
        7,
        ch,
        [{"condition_type": "web_sdk", "operator": "ne", "value": "99"}],
    )
    assert ok is True


@pytest.mark.asyncio
async def test_rule_matches_web_sdk_any_eq():
    ch = _channel(5)
    ok = await RoutingService._rule_matches(
        AsyncMock(),
        7,
        ch,
        [{"condition_type": "web_sdk", "operator": "any_eq", "value": ["1", "5", "9"]}],
    )
    assert ok is True


@pytest.mark.asyncio
async def test_rule_matches_web_sdk_requires_channel():
    ok = await RoutingService._rule_matches(
        AsyncMock(),
        7,
        None,
        [{"condition_type": "web_sdk", "operator": "eq", "value": "5"}],
    )
    assert ok is False


@pytest.mark.asyncio
async def test_rule_matches_current_time_in_schedule(monkeypatch):
    db = AsyncMock()
    db.get = AsyncMock(return_value=_service_hours())

    monkeypatch.setattr(ChannelService, "is_within_service_hours", lambda sh, now=None: True)

    ok = await RoutingService._rule_matches(
        db,
        7,
        _channel(1),
        [{"condition_type": "current_time", "operator": "in_schedule", "value": "1"}],
    )
    assert ok is True
    db.get.assert_awaited()


@pytest.mark.asyncio
async def test_rule_matches_combined_and_semantics():
    ch = _channel(10, access_mode="url")
    ok = await RoutingService._rule_matches(
        AsyncMock(),
        7,
        ch,
        [
            {"condition_type": "channel", "operator": "eq", "value": "sdk"},
            {"condition_type": "web_sdk", "operator": "eq", "value": "10"},
        ],
    )
    assert ok is True
