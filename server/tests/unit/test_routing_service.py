"""Unit tests for session RoutingService condition matching."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.channel_service import ChannelService
from app.services.routing_service import RouteQueueCandidate, RoutingService


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


def _candidate(
    queue_id: int,
    *,
    waiting: int,
    tail: int,
    available: bool,
    gate: bool = True,
    order: int = 0,
) -> RouteQueueCandidate:
    return RouteQueueCandidate(
        queue_type="employee_group",
        queue_id=queue_id,
        group_id=queue_id,
        member_ids=[queue_id * 10],
        max_concurrent_map={queue_id * 10: 10},
        waiting_count=waiting,
        tail_wait_seconds=tail,
        gate_passed=gate,
        has_available_agent=available,
        order=order,
    )


def _rule(strategy: str) -> SimpleNamespace:
    return SimpleNamespace(id=1, target_strategy=strategy)


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


@pytest.mark.asyncio
async def test_sequential_overflow_requires_immediate_available_candidate(monkeypatch):
    rule = _rule("sequential_overflow")

    async def fake_resolve(*args, **kwargs):
        return [
            _candidate(1, waiting=0, tail=0, available=False, order=0),
            _candidate(2, waiting=4, tail=30, available=True, order=1),
        ]

    monkeypatch.setattr(RoutingService, "_resolve_candidates_for_rule", fake_resolve)

    selected, block_reason = await RoutingService._select_candidate_for_rule(AsyncMock(), None, 7, rule)

    assert selected is not None
    assert selected.queue_id == 2
    assert block_reason is None


@pytest.mark.asyncio
async def test_sequential_overflow_falls_back_to_last_enqueueable_candidate(monkeypatch):
    rule = _rule("sequential_overflow")

    async def fake_resolve(*args, **kwargs):
        return [
            _candidate(1, waiting=0, tail=0, available=False, gate=False, order=0),
            _candidate(2, waiting=2, tail=20, available=False, order=1),
            _candidate(3, waiting=0, tail=0, available=False, order=2),
        ]

    monkeypatch.setattr(RoutingService, "_resolve_candidates_for_rule", fake_resolve)

    selected, block_reason = await RoutingService._select_candidate_for_rule(AsyncMock(), None, 7, rule)

    assert selected is not None
    assert selected.queue_id == 3
    assert block_reason is None


@pytest.mark.asyncio
async def test_sequential_overflow_returns_none_when_no_candidate_can_enqueue(monkeypatch):
    rule = _rule("sequential_overflow")

    async def fake_resolve(*args, **kwargs):
        return [
            _candidate(1, waiting=0, tail=0, available=False, gate=False, order=0),
            _candidate(2, waiting=2, tail=20, available=False, gate=False, order=1),
        ]

    monkeypatch.setattr(RoutingService, "_resolve_candidates_for_rule", fake_resolve)

    selected, block_reason = await RoutingService._select_candidate_for_rule(AsyncMock(), None, 7, rule)

    assert selected is None
    assert block_reason == "queue_limit"


@pytest.mark.asyncio
async def test_least_waiting_strategy_uses_tail_time_as_tiebreaker(monkeypatch):
    rule = _rule("least_waiting_count")

    async def fake_resolve(*args, **kwargs):
        return [
            _candidate(1, waiting=3, tail=20, available=False, order=0),
            _candidate(2, waiting=1, tail=50, available=False, order=1),
            _candidate(3, waiting=1, tail=10, available=False, order=2),
        ]

    monkeypatch.setattr(RoutingService, "_resolve_candidates_for_rule", fake_resolve)

    selected, block_reason = await RoutingService._select_candidate_for_rule(AsyncMock(), None, 7, rule)

    assert selected is not None
    assert selected.queue_id == 3
    assert block_reason is None


@pytest.mark.asyncio
async def test_shortest_tail_wait_strategy_uses_waiting_count_as_tiebreaker(monkeypatch):
    rule = _rule("shortest_tail_wait")

    async def fake_resolve(*args, **kwargs):
        return [
            _candidate(1, waiting=5, tail=10, available=False, order=0),
            _candidate(2, waiting=2, tail=10, available=False, order=1),
            _candidate(3, waiting=1, tail=40, available=False, order=2),
        ]

    monkeypatch.setattr(RoutingService, "_resolve_candidates_for_rule", fake_resolve)

    selected, block_reason = await RoutingService._select_candidate_for_rule(AsyncMock(), None, 7, rule)

    assert selected is not None
    assert selected.queue_id == 2
    assert block_reason is None
