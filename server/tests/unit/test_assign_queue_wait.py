"""
Queue-wait: when no agent is ready, the caller is held and the pick is retried
(agents finishing wrap-up / on a call become ready) up to queue_wait_seconds
instead of being dropped immediately.

Failure TTS must finish (call.play_end) before hangup / timeout routing so the
busy / no-agent prompt is not cut mid-sentence.
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
from app.services.call_center.queue import QueuePicker


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

    telephony = SimpleNamespace(call_hangup=AsyncMock(), call_stop=AsyncMock())
    ctx = ExecutionContext(call_id="call-1", tenant_id=7, variables={}, telephony=telephony)
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

    # Held in queue, retried, then failure prompt — wait for play_end before End.
    assert len(sleeps) == 4
    assert picker.pick_ready_agent_for_queue.await_count == 5
    assert isinstance(step, WaitForEvent)
    assert step.method == "call.play_end"
    assert ctx.variables["sys.assign_queue_status"] == "agent_no_answer"
    result = await step.on_event(ctx, {"id": "aq-1"}, {})
    telephony.call_hangup.assert_awaited_once()
    assert isinstance(result, End)


@pytest.mark.asyncio
async def test_no_agent_on_call_falls_back_immediately(monkeypatch):
    """No agent worth waiting for → don't loop '正在为您转接' for a minute;
    play the fallback prompt and hang up once it finishes."""
    monkeypatch.setattr("app.db.redis.redis_client", _Redis())
    monkeypatch.setattr("app.db.session.AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(
        "app.services.call_center.assign_queue.AssignQueueSelector.select",
        AsyncMock(return_value=AssignQueueSelection(candidate=_candidate(), candidates=[])),
    )
    picker = SimpleNamespace(
        pick_ready_agent_for_queue=AsyncMock(return_value=None),
        has_agent_on_call_for_queue=AsyncMock(return_value=False),
    )
    monkeypatch.setattr(nodes_module, "get_queue_picker", lambda: picker)

    sleep_mock = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep_mock)

    say_mock = AsyncMock()
    monkeypatch.setattr(AssignQueueExecutor, "_say", say_mock)

    telephony = SimpleNamespace(call_hangup=AsyncMock(), call_stop=AsyncMock())
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


@pytest.mark.asyncio
async def test_after_call_work_counts_as_worth_waiting(monkeypatch):
    """Wrap-up agents are not on a live call but usually return to ready soon."""
    r = object()
    monkeypatch.setattr(
        "app.services.cc_agent_resource_service.CcAgentResourceService.get_snapshot",
        AsyncMock(
            return_value={
                "resource_state": "after_call_work",
                "visible_status": "after_call_work",
            }
        ),
    )

    class _Db:
        async def execute(self, _q):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [42]))

    assert await QueuePicker().has_agent_on_call_for_queue(
        _Db(), tenant_id=7, queue_type="employee", queue_id=42, r=r,
    ) is True


@pytest.mark.asyncio
async def test_busy_does_not_count_as_worth_waiting(monkeypatch):
    r = object()
    monkeypatch.setattr(
        "app.services.cc_agent_resource_service.CcAgentResourceService.get_snapshot",
        AsyncMock(
            return_value={
                "resource_state": "unavailable",
                "visible_status": "busy",
            }
        ),
    )

    class _Db:
        async def execute(self, _q):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [42]))

    assert await QueuePicker().has_agent_on_call_for_queue(
        _Db(), tenant_id=7, queue_type="employee", queue_id=42, r=r,
    ) is False


@pytest.mark.asyncio
async def test_fail_after_prompt_clears_stale_play_ends():
    """Hold-prompt play_ends must not satisfy the failure-prompt wait."""
    from collections import deque

    from app.services.call_center.workflow import VoiceFlowWorkflow

    wf = VoiceFlowWorkflow(
        call_id="c1",
        tenant_id=7,
        graph={"nodes": [{"id": "s", "type": "start"}], "edges": []},
        telephony=SimpleNamespace(
            call_stop=AsyncMock(),
            call_say=AsyncMock(),
            call_hangup=AsyncMock(),
        ),
    )
    wf._pending_events = deque(
        [
            ("call.play_end", {"reason": "completed"}),
            ("call.play_end", {"reason": "completed"}),
            ("call.bridged", {}),
        ]
    )
    ctx = wf.ctx
    step = await AssignQueueExecutor()._fail_after_prompt(
        ctx,
        {"id": "aq-1"},
        {"agent_no_answer_prompt_text": "暂无坐席接听，请稍后再拨。"},
        "agent_no_answer",
    )
    assert isinstance(step, WaitForEvent)
    assert step.method == "call.play_end"
    # Stale play_ends gone; unrelated buffered events kept.
    assert list(wf._pending_events) == [("call.bridged", {})]
    ctx.telephony.call_stop.assert_awaited_once()
    ctx.telephony.call_say.assert_awaited_once()


def test_workflow_clear_buffered_play_end():
    from collections import deque

    from app.services.call_center.workflow import VoiceFlowWorkflow

    wf = VoiceFlowWorkflow(
        call_id="c1",
        tenant_id=7,
        graph={"nodes": [{"id": "s", "type": "start"}], "edges": []},
        telephony=object(),
    )
    wf._pending_events = deque(
        [
            ("call.play_end", {"n": 1}),
            ("call.dtmf", {"digit": "1"}),
            ("call.play_end", {"n": 2}),
        ]
    )
    assert wf.clear_buffered("call.play_end") == 2
    assert list(wf._pending_events) == [("call.dtmf", {"digit": "1"})]


@pytest.mark.asyncio
async def test_hold_loop_silent_when_queue_prompt_text_empty(monkeypatch):
    """queue_prompt_text="" disables the transfer prompt: while holding in
    queue no hold TTS plays; only the final failure prompt is spoken."""
    monkeypatch.setattr("app.db.redis.redis_client", _Redis())
    monkeypatch.setattr("app.db.session.AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(
        "app.services.call_center.assign_queue.AssignQueueSelector.select",
        AsyncMock(return_value=AssignQueueSelection(candidate=_candidate(), candidates=[])),
    )
    picker = SimpleNamespace(
        pick_ready_agent_for_queue=AsyncMock(return_value=None),
        has_agent_on_call_for_queue=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(nodes_module, "get_queue_picker", lambda: picker)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    say = AsyncMock()
    monkeypatch.setattr(AssignQueueExecutor, "_say", say)

    telephony = SimpleNamespace(call_hangup=AsyncMock(), call_stop=AsyncMock())
    ctx = ExecutionContext(call_id="call-1", tenant_id=7, variables={}, telephony=telephony)
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
                "queue_prompt_text": "",
            },
        },
    )

    # Exactly one say: the failure prompt after the wait times out. No hold prompts.
    say.assert_awaited_once()
    assert say.await_args.args[1] == AssignQueueExecutor._failure_prompt({}, "agent_no_answer")
    assert isinstance(step, WaitForEvent)
    assert ctx.variables["sys.assign_queue_status"] == "agent_no_answer"
