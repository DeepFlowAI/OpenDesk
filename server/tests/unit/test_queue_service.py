from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.queue import QueueAdminAssignRequest, QueueDispatchRequest
from app.services import queue_service as qs
from app.services.queue_service import QueueTaskService
from app.services.queue_strategy import QueueCandidate


def _task(
    status: str = "queued",
    *,
    task_id: int = 11,
    task_ref_id: str = "100",
    task_type: str = "conversation",
    channel: str = "online_chat",
    priority: int = 5,
    assignment_strategy: str | None = None,
    policy_snapshot: dict | None = None,
    source_context: dict | None = None,
):
    return SimpleNamespace(
        id=task_id,
        tenant_id=1,
        channel=channel,
        task_type=task_type,
        task_ref_id=task_ref_id,
        task_ref_public_id=f"cv_{task_ref_id}",
        queue_type="employee_group",
        queue_id=7,
        priority=priority,
        status=status,
        source_type="visitor_waiting",
        source_context=source_context or {},
        policy_snapshot=policy_snapshot or {},
        assignment_strategy=assignment_strategy,
        assigned_agent_id=None,
        assigned_by=None,
        attempts=0,
        last_error=None,
        enqueued_at=datetime(2026, 6, 16, 10, 0),
        assigning_at=None,
        assigned_at=None,
        canceled_at=None,
        timeout_at=None,
        deadline_at=None,
        created_at=None,
        updated_at=None,
    )


class _OnlineProvider:
    def __init__(self, loads: dict[int, int], capacities: dict[int, int]):
        self.loads = loads
        self.capacities = capacities

    async def list_candidates(self, _db, _r, _tenant_id, _queue_type, _queue_id, _task_context=None):
        return [
            QueueCandidate(
                employee_id=employee_id,
                available=self.loads[employee_id] < self.capacities[employee_id],
                current_load=self.loads[employee_id],
                max_capacity=self.capacities[employee_id],
                metrics={"status": "online"},
            )
            for employee_id in sorted(self.loads)
        ]

    async def try_reserve(self, _db, _r, _tenant_id, employee_id, _task, *, bypass_capacity=False):
        before = {
            "status": "online",
            "current_load": self.loads[employee_id],
            "max_capacity": self.capacities[employee_id],
        }
        if not bypass_capacity and self.loads[employee_id] >= self.capacities[employee_id]:
            return SimpleNamespace(success=False, before_load=before, after_load=None, reason="capacity_full")
        self.loads[employee_id] += 1
        return SimpleNamespace(
            success=True,
            before_load=before,
            after_load=before | {"current_load": self.loads[employee_id]},
            reason=None,
        )

    async def release(self, _r, _tenant_id, employee_id, _task, _reason):
        self.loads[employee_id] = max(0, self.loads[employee_id] - 1)


def _install_dispatch_mocks(monkeypatch, tasks: list, provider: _OnlineProvider) -> dict[str, int | None]:
    pending = list(tasks)
    round_robin_state = {"last_agent_id": None}

    async def lock_next(_db, _tenant_id, _channel, _queue_type, _queue_id):
        return pending.pop(0) if pending else None

    async def mark_assigning(_db, task, now):
        task.status = "assigning"
        task.assigning_at = now
        task.attempts += 1
        return task

    async def mark_assigned(_db, task, *, agent_id, assigned_by, now):
        task.status = "assigned"
        task.assigned_agent_id = agent_id
        task.assigned_by = assigned_by
        task.assigned_at = now
        return task

    async def restore_queued(_db, task, reason=None):
        task.status = "queued"
        task.last_error = reason
        return task

    async def get_state(_db, _tenant_id, _channel, _queue_type, _queue_id):
        return SimpleNamespace(last_agent_id=round_robin_state["last_agent_id"])

    async def set_last_agent(_db, _tenant_id, _channel, _queue_type, _queue_id, agent_id):
        round_robin_state["last_agent_id"] = agent_id
        return SimpleNamespace(last_agent_id=agent_id)

    monkeypatch.setattr(qs.QueueTaskRepository, "lock_next_queued_task", AsyncMock(side_effect=lock_next))
    monkeypatch.setattr(qs.QueueTaskRepository, "mark_assigning", AsyncMock(side_effect=mark_assigning))
    monkeypatch.setattr(qs.QueueTaskRepository, "mark_assigned", AsyncMock(side_effect=mark_assigned))
    monkeypatch.setattr(qs.QueueTaskRepository, "restore_queued", AsyncMock(side_effect=restore_queued))
    monkeypatch.setattr(qs.QueueRoundRobinRepository, "get_state", AsyncMock(side_effect=get_state))
    monkeypatch.setattr(qs.QueueRoundRobinRepository, "set_last_agent", AsyncMock(side_effect=set_last_agent))
    monkeypatch.setattr(qs.QueueResourceProviderFactory, "create", lambda _channel: provider)
    monkeypatch.setattr(QueueTaskService, "_assign_business_object", AsyncMock())
    monkeypatch.setattr(QueueTaskService, "_record_event", AsyncMock())
    monkeypatch.setattr(QueueTaskService, "_materialize_conversation_summary", AsyncMock())
    monkeypatch.setattr(qs.QueueRealtimeService, "emit_queue_updated", AsyncMock())
    return round_robin_state


def _dispatch_request(channel: str = "online_chat") -> QueueDispatchRequest:
    return QueueDispatchRequest(channel=channel, queue_type="employee_group", queue_id=7)


@pytest.mark.asyncio
async def test_admin_assign_locks_task_and_emits_queue_update(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    task = _task()
    provider = SimpleNamespace(
        try_reserve=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                before_load={"current_load": 0},
                after_load={"current_load": 1},
            )
        )
    )
    emit_queue_updated = AsyncMock()

    monkeypatch.setattr(
        qs.QueueTaskRepository,
        "get_task_for_update",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        qs.QueueTaskRepository,
        "get_task",
        AsyncMock(side_effect=AssertionError("admin_assign should lock the task row")),
    )
    monkeypatch.setattr(
        qs.QueueCandidateRepository,
        "list_candidate_employees",
        AsyncMock(return_value=[SimpleNamespace(id=20)]),
    )
    monkeypatch.setattr(qs.QueueTaskRepository, "mark_assigning", AsyncMock(return_value=task))
    monkeypatch.setattr(qs.QueueTaskRepository, "mark_assigned", AsyncMock(return_value=task))
    monkeypatch.setattr(qs.QueueResourceProviderFactory, "create", lambda _channel: provider)
    monkeypatch.setattr(QueueTaskService, "_assign_business_object", AsyncMock())
    monkeypatch.setattr(QueueTaskService, "_record_event", AsyncMock())
    monkeypatch.setattr(QueueTaskService, "_materialize_conversation_summary", AsyncMock())
    monkeypatch.setattr(qs.QueueRealtimeService, "emit_queue_updated", emit_queue_updated)

    result = await QueueTaskService.admin_assign(
        db,
        SimpleNamespace(),
        tenant_id=1,
        operator_id=10,
        task_id=task.id,
        data=QueueAdminAssignRequest(agent_id=20, reason="assign"),
    )

    assert result is task
    qs.QueueTaskRepository.get_task_for_update.assert_awaited_once_with(db, 1, 11)
    emit_queue_updated.assert_awaited_once_with(
        1,
        action="assigned",
        task_id=11,
        queue_type="employee_group",
        queue_id=7,
    )


@pytest.mark.asyncio
async def test_assign_business_object_anchors_timeout_at_assignment_time(monkeypatch):
    db = SimpleNamespace()
    assigned_at = datetime(2026, 6, 22, 12, 24, tzinfo=timezone.utc)
    captured: dict = {}
    conversation = SimpleNamespace(
        id=100,
        started_at=datetime(2026, 6, 22, 12, 21, tzinfo=timezone.utc),
    )

    async def assign_conversation(_db, tenant_id, conversation_id, employee_id, now):
        captured["assign_conversation"] = (tenant_id, conversation_id, employee_id, now)
        return True

    async def initialize_for_conversation(_db, conversation_arg, *, anchor_at=None, commit=True):
        captured["initialize"] = (conversation_arg, anchor_at, commit)
        return None

    monkeypatch.setattr(qs, "_now", lambda: assigned_at)
    monkeypatch.setattr(QueueTaskService, "_record_reception_assignment", AsyncMock())
    monkeypatch.setattr(qs.QueueBusinessRepository, "assign_conversation", assign_conversation)
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService.create_agent_assigned_system_message",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService.create_welcome_message_on_agent_assignment",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.repositories.conversation_repository.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.visitor_timeout_close_service.VisitorTimeoutCloseService.initialize_for_conversation",
        initialize_for_conversation,
    )

    await QueueTaskService._assign_business_object(db, 1, _task(task_ref_id="100"), 20)

    assert captured["assign_conversation"] == (1, 100, 20, assigned_at)
    assert captured["initialize"] == (conversation, assigned_at, False)


@pytest.mark.asyncio
async def test_dispatch_realistic_online_sessions_prioritizes_and_round_robins(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    tasks = [
        _task(task_id=101, task_ref_id="vip", priority=1, assignment_strategy="round_robin"),
        _task(task_id=102, task_ref_id="urgent", priority=2, assignment_strategy="round_robin"),
        _task(task_id=103, task_ref_id="normal-early", priority=5, assignment_strategy="round_robin"),
        _task(task_id=104, task_ref_id="normal-late", priority=5, assignment_strategy="round_robin"),
    ]
    provider = _OnlineProvider(
        loads={1: 0, 2: 0, 3: 0},
        capacities={1: 3, 2: 3, 3: 3},
    )
    round_robin_state = _install_dispatch_mocks(monkeypatch, tasks, provider)

    responses = [
        await QueueTaskService.dispatch(db, SimpleNamespace(), 1, _dispatch_request())
        for _ in tasks
    ]

    assert [response.dispatched for response in responses] == [True, True, True, True]
    assert [response.task.task_ref_id for response in responses] == [
        "vip",
        "urgent",
        "normal-early",
        "normal-late",
    ]
    assert [response.agent_id for response in responses] == [1, 2, 3, 1]
    assert provider.loads == {1: 2, 2: 1, 3: 1}
    assert round_robin_state["last_agent_id"] == 1


@pytest.mark.asyncio
async def test_dispatch_skips_full_agents_and_recovers_after_capacity_release(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    first = _task(task_id=201, task_ref_id="first", assignment_strategy="round_robin")
    second = _task(task_id=202, task_ref_id="second", assignment_strategy="round_robin")
    third = _task(task_id=203, task_ref_id="third", assignment_strategy="round_robin")
    provider = _OnlineProvider(
        loads={1: 0, 2: 0},
        capacities={1: 1, 2: 1},
    )
    _install_dispatch_mocks(monkeypatch, [first, second, third, third], provider)

    first_response = await QueueTaskService.dispatch(db, SimpleNamespace(), 1, _dispatch_request())
    second_response = await QueueTaskService.dispatch(db, SimpleNamespace(), 1, _dispatch_request())
    blocked_response = await QueueTaskService.dispatch(db, SimpleNamespace(), 1, _dispatch_request())

    assert first_response.dispatched is True
    assert first_response.agent_id == 1
    assert second_response.dispatched is True
    assert second_response.agent_id == 2
    assert blocked_response.dispatched is False
    assert blocked_response.reason == "no_available_agent"
    assert blocked_response.task.task_ref_id == "third"
    assert third.status == "queued"
    assert third.last_error == "no_available_agent"

    provider.loads[1] = 0
    recovered_response = await QueueTaskService.dispatch(db, SimpleNamespace(), 1, _dispatch_request())

    assert recovered_response.dispatched is True
    assert recovered_response.agent_id == 1
    assert recovered_response.task.task_ref_id == "third"
    assert provider.loads == {1: 1, 2: 1}


@pytest.mark.asyncio
async def test_dispatch_prioritizes_returning_online_chat_agent(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    task = _task(
        task_id=301,
        task_ref_id="900",
        assignment_strategy="round_robin",
        policy_snapshot={
            "config": {
                "returning_agent_priority_enabled": True,
                "returning_agent_window_hours": 24,
            }
        },
    )
    provider = _OnlineProvider(
        loads={1: 0, 2: 0, 3: 0},
        capacities={1: 3, 2: 3, 3: 3},
    )
    round_robin_state = _install_dispatch_mocks(monkeypatch, [task], provider)
    monkeypatch.setattr(
        qs.QueueReturningAgentRepository,
        "find_recent_online_chat_agent",
        AsyncMock(return_value=3),
    )

    response = await QueueTaskService.dispatch(db, SimpleNamespace(), 1, _dispatch_request())

    assert response.dispatched is True
    assert response.agent_id == 3
    assert provider.loads == {1: 0, 2: 0, 3: 1}
    assert round_robin_state["last_agent_id"] is None
    QueueTaskService._record_event.assert_awaited_once()
    args, kwargs = QueueTaskService._record_event.await_args
    assert args[2] == "returning_agent_assigned"
    assert kwargs["reason"] == "returning_agent_priority"


@pytest.mark.asyncio
async def test_dispatch_falls_back_when_returning_agent_is_not_available(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    task = _task(
        task_id=302,
        task_ref_id="901",
        assignment_strategy="round_robin",
        policy_snapshot={
            "config": {
                "returning_agent_priority_enabled": True,
                "returning_agent_window_hours": 24,
            }
        },
    )
    provider = _OnlineProvider(
        loads={1: 0, 2: 0, 3: 1},
        capacities={1: 3, 2: 3, 3: 1},
    )
    round_robin_state = _install_dispatch_mocks(monkeypatch, [task], provider)
    monkeypatch.setattr(
        qs.QueueReturningAgentRepository,
        "find_recent_online_chat_agent",
        AsyncMock(return_value=3),
    )

    response = await QueueTaskService.dispatch(db, SimpleNamespace(), 1, _dispatch_request())

    assert response.dispatched is True
    assert response.agent_id == 1
    assert provider.loads == {1: 1, 2: 0, 3: 1}
    assert round_robin_state["last_agent_id"] == 1
    args, kwargs = QueueTaskService._record_event.await_args
    assert args[2] == "auto_assigned"
    assert kwargs.get("reason") is None


@pytest.mark.asyncio
async def test_dispatch_prioritizes_returning_call_center_agent(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    task = _task(
        task_id=303,
        task_ref_id="call-current",
        task_type="call",
        channel="call_center",
        assignment_strategy="round_robin",
        policy_snapshot={
            "config": {
                "returning_agent_priority_enabled": True,
                "returning_agent_window_hours": 12,
            }
        },
        source_context={"call_id": "call-current"},
    )
    provider = _OnlineProvider(
        loads={1: 0, 2: 0},
        capacities={1: 1, 2: 1},
    )
    _install_dispatch_mocks(monkeypatch, [task], provider)
    monkeypatch.setattr(
        qs.QueueReturningAgentRepository,
        "find_recent_call_center_agent",
        AsyncMock(return_value=2),
    )

    response = await QueueTaskService.dispatch(db, SimpleNamespace(), 1, _dispatch_request("call_center"))

    assert response.dispatched is True
    assert response.agent_id == 2
    QueueTaskService._record_event.assert_awaited_once()
    args, kwargs = QueueTaskService._record_event.await_args
    assert args[2] == "returning_agent_assigned"
    assert kwargs["reason"] == "returning_agent_priority"
