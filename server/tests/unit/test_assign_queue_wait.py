"""
#3 queue-wait: when no agent is ready, the caller is held in queue and the
pick is retried (agents finishing wrap-up become ready) up to queue_wait_seconds
instead of being dropped immediately.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.call_center import nodes as nodes_module
from app.services.call_center.assign_queue import AssignQueueCandidate, AssignQueueSelection
from app.services.call_center.nodes import (
    AssignQueueExecutor,
    End,
    ExecutionContext,
    WaitForEvent,
)


class _Redis:
    @property
    def client(self):
        return object()


class _Session:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_exc):
        return False


def _candidate():
    return AssignQueueCandidate(
        queue_type="employee_group", queue_id=9, order=0, waiting_count=0,
        tail_wait_seconds=0, available_agent_count=1, gate_passed=True,
    )


@pytest.mark.asyncio
async def test_no_ready_agent_waits_then_times_out(monkeypatch):
    monkeypatch.setattr("app.db.redis.redis_client", _Redis())
    monkeypatch.setattr("app.db.session.AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(
        "app.services.call_center.assign_queue.AssignQueueSelector.select",
        AsyncMock(return_value=AssignQueueSelection(candidate=_candidate(), candidates=[])),
    )
    # Never a ready agent, but someone IS on a call (about to free up) → the wait
    # loop should keep retrying until the cap rather than dropping the caller.
    picker = SimpleNamespace(
        pick_ready_agent_for_queue=AsyncMock(return_value=None),
        has_agent_on_call_for_queue=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(nodes_module, "get_queue_picker", lambda: picker)

    sleeps: list[float] = []

    async def _fast_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(AssignQueueExecutor, "_say", AsyncMock())

    ctx = ExecutionContext(call_id="call-1", tenant_id=7, variables={}, telephony=object())
    step = await AssignQueueExecutor().execute(
        ctx,
        {
            "id": "aq-1",
            "type": "assign_queue",
            "data": {
                "employee_group_id": 9,
                "timeout_seconds": 30,
                "queue_wait_seconds": 20,
                "queue_wait_retry_seconds": 5,
            },
        },
    )

    # Held in queue, retried, then gave up (dangling "timeout" outlet → End).
    assert isinstance(step, End)
    # 20s cap / 5s interval ≈ 4 retries (each retry sleeps once).
    assert len(sleeps) == 4
    # Pick was retried on every wait pass (initial + 4).
    assert picker.pick_ready_agent_for_queue.await_count == 5


@pytest.mark.asyncio
async def test_no_agent_on_call_falls_back_immediately(monkeypatch):
    """No agent is on a call to wait for → don't loop '正在为您转接' for a minute;
    play the fallback prompt and hang up once it finishes."""
    monkeypatch.setattr("app.db.redis.redis_client", _Redis())
    monkeypatch.setattr("app.db.session.AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(
        "app.services.call_center.assign_queue.AssignQueueSelector.select",
        AsyncMock(return_value=AssignQueueSelection(candidate=_candidate(), candidates=[])),
    )
    picker = SimpleNamespace(
        pick_ready_agent_for_queue=AsyncMock(return_value=None),
        has_agent_on_call_for_queue=AsyncMock(return_value=False),  # nobody on a call
    )
    monkeypatch.setattr(nodes_module, "get_queue_picker", lambda: picker)

    sleep_mock = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep_mock)

    say_mock = AsyncMock()
    monkeypatch.setattr(AssignQueueExecutor, "_say", say_mock)

    telephony = SimpleNamespace(call_hangup=AsyncMock())
    ctx = ExecutionContext(call_id="call-1", tenant_id=7, variables={}, telephony=telephony)
    step = await AssignQueueExecutor().execute(
        ctx,
        {
            "id": "aq-1",
            "type": "assign_queue",
            "data": {
                "employee_group_id": 9,
                "timeout_seconds": 30,
                "agent_no_answer_prompt_text": "暂无坐席接听，请稍后再拨。",
            },
        },
    )

    # No waiting — immediate fallback.
    sleep_mock.assert_not_awaited()
    say_mock.assert_awaited_once()
    assert "暂无坐席接听" in say_mock.await_args.args[1]
    assert ctx.variables["sys.assign_queue_status"] == "agent_no_answer"
    # Waits for the prompt to finish, then (no wired outlet) hangs up.
    assert isinstance(step, WaitForEvent)
    assert step.method == "call.play_end"
    result = await step.on_event(ctx, {"id": "aq-1"}, {})
    telephony.call_hangup.assert_awaited_once()
    assert isinstance(result, End)
