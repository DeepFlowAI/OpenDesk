"""
Session discipline on the inbound assign_queue failure path (CLAUDE.md §8).

When queue selection fails immediately, ``_fail_after_prompt`` must not run
telephony RPCs while a managed DB session is still open.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.call_center import nodes as nodes_module
from app.services.call_center.assign_queue import AssignQueueSelection
from app.services.call_center.nodes import (
    AssignQueueExecutor,
    ExecutionContext,
    WaitForEvent,
)


class SessionTracker:
    active = False
    opens = 0
    closes = 0


class FakeSessionContext:
    async def __aenter__(self):
        assert SessionTracker.active is False
        SessionTracker.active = True
        SessionTracker.opens += 1
        return SimpleNamespace()

    async def __aexit__(self, *_exc_info):
        SessionTracker.active = False
        SessionTracker.closes += 1


class _Redis:
    @property
    def client(self):
        return object()


def _reset_tracker() -> None:
    SessionTracker.active = False
    SessionTracker.opens = 0
    SessionTracker.closes = 0


@pytest.mark.asyncio
async def test_fail_after_prompt_closes_db_before_telephony(monkeypatch):
    """No DB session may be active while call_stop / call_say run."""
    _reset_tracker()
    telephony_active_states: list[tuple[str, bool]] = []

    class _Tel:
        async def call_stop(self, call_id: str, target: str | None = None) -> None:
            telephony_active_states.append(("call_stop", SessionTracker.active))
            assert call_id == "call-fail-1"
            assert target == "play"

        async def call_say(self, call_id: str, text: str) -> None:
            telephony_active_states.append(("call_say", SessionTracker.active))
            assert call_id == "call-fail-1"
            assert text == "当前坐席繁忙，请稍后再拨。"

        async def call_hangup(self, call_id: str, reason: str | None = None) -> None:
            raise AssertionError("hangup must wait for call.play_end")

    monkeypatch.setattr("app.db.redis.redis_client", _Redis())
    monkeypatch.setattr("app.db.session.AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        "app.services.call_center.assign_queue.AssignQueueSelector.select",
        AsyncMock(
            return_value=AssignQueueSelection(
                candidate=None,
                candidates=[],
                failure_status="no_available_queue",
            )
        ),
    )
    monkeypatch.setattr(
        nodes_module,
        "get_queue_picker",
        lambda: SimpleNamespace(pick_ready_agent_for_queue=AsyncMock()),
    )

    ctx = ExecutionContext(
        call_id="call-fail-1",
        tenant_id=7,
        variables={},
        telephony=_Tel(),
    )
    step = await AssignQueueExecutor().execute(
        ctx,
        {
            "id": "aq-1",
            "type": "assign_queue",
            "data": {"employee_group_id": 9, "timeout_seconds": 30},
        },
    )

    assert isinstance(step, WaitForEvent)
    assert step.method == "call.play_end"
    assert ctx.variables["sys.assign_queue_status"] == "no_available_queue"
    assert telephony_active_states == [
        ("call_stop", False),
        ("call_say", False),
    ]
    assert SessionTracker.opens == 1
    assert SessionTracker.opens == SessionTracker.closes
    assert SessionTracker.active is False


@pytest.mark.asyncio
async def test_fail_after_prompt_swallows_telephony_errors(monkeypatch):
    """Telephony failure on the immediate no-queue path must not abandon the call."""
    _reset_tracker()
    order: list[str] = []

    class _Tel:
        async def call_stop(self, call_id: str, target: str | None = None) -> None:
            order.append("call_stop")
            assert SessionTracker.active is False
            raise RuntimeError("kernel unavailable")

        async def call_say(self, call_id: str, text: str) -> None:
            order.append("call_say")
            assert SessionTracker.active is False
            raise RuntimeError("kernel unavailable")

        async def call_hangup(self, call_id: str, reason: str | None = None) -> None:
            raise AssertionError("hangup must wait for call.play_end")

    monkeypatch.setattr("app.db.redis.redis_client", _Redis())
    monkeypatch.setattr("app.db.session.AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        "app.services.call_center.assign_queue.AssignQueueSelector.select",
        AsyncMock(
            return_value=AssignQueueSelection(
                candidate=None,
                candidates=[],
                failure_status="queue_limit_reached",
                limit_reason="max_waiting",
            )
        ),
    )
    monkeypatch.setattr(
        nodes_module,
        "get_queue_picker",
        lambda: SimpleNamespace(pick_ready_agent_for_queue=AsyncMock()),
    )

    ctx = ExecutionContext(
        call_id="call-fail-2",
        tenant_id=7,
        variables={},
        telephony=_Tel(),
    )
    step = await AssignQueueExecutor().execute(
        ctx,
        {
            "id": "aq-1",
            "type": "assign_queue",
            "data": {
                "employee_group_id": 9,
                "timeout_seconds": 30,
                "queue_limit_reached_prompt_text": "当前排队人数较多，请稍后再拨。",
            },
        },
    )

    assert isinstance(step, WaitForEvent)
    assert step.method == "call.play_end"
    assert order == ["call_stop", "call_say"]
    assert ctx.variables["sys.assign_queue_status"] == "queue_limit_reached"
    assert ctx.variables["sys.assign_queue_limit_reason"] == "max_waiting"
    assert SessionTracker.opens == SessionTracker.closes
    assert SessionTracker.active is False
