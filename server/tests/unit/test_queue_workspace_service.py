from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, ANY

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError
from app.schemas.permission import EffectivePrincipal
from app.schemas.queue_workspace import (
    QueueAssignAndSendRequest,
    QueueAssignRequest,
    QueueAssignSelfRequest,
    QueueAssignmentWorkspaceResponse,
)
from app.services.agent_status_service import AgentStatusService
from app.services.queue_workspace_service import (
    DataScopeService,
    EmployeeRepository,
    QueueTaskRepository,
    QueueTaskService,
    QueueWorkspaceRepository,
    QueueWorkspaceService,
)


def _principal(
    *,
    permissions: list[str],
    data_scope: str = "group",
    user_id: int = 10,
) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=user_id,
        tenant_id=1,
        permissions=permissions,
        data_scopes={"chat.queue.view": data_scope},
        group_ids=[7],
    )


def _visitor(name: str = "访客"):
    return SimpleNamespace(
        id=1,
        public_id="usr_1",
        external_id="ext_1",
        name=name,
        avatar_color="#2563eb",
    )


def _conversation(conversation_id: int, *, preview: str = "hello"):
    now = datetime(2026, 6, 16, 10, 0)
    return SimpleNamespace(
        id=conversation_id,
        public_id=f"cv_{conversation_id}",
        tenant_id=1,
        visitor=_visitor(f"访客{conversation_id}"),
        agent=None,
        agent_id=None,
        channel=SimpleNamespace(id=3, name="Web", channel_type="web"),
        channel_id=3,
        group=SimpleNamespace(id=7, name="售后组"),
        group_id=7,
        status="queued",
        last_message_preview=preview,
        last_message_at=now,
        created_at=now,
    )


def _queue_task(task_id: int, conversation_id: int, *, priority: int = 5, status: str = "queued"):
    return SimpleNamespace(
        id=task_id,
        tenant_id=1,
        channel="online_chat",
        task_type="conversation",
        task_ref_id=str(conversation_id),
        task_ref_public_id=f"cv_{conversation_id}",
        queue_type="employee_group",
        queue_id=7,
        priority=priority,
        status=status,
        source_type="visitor_waiting",
        enqueued_at=datetime(2026, 6, 16, 10, 0),
    )


def _assignment_response(
    *,
    principal: EffectivePrincipal,
    task_id: int = 11,
    conversation_id: int = 100,
) -> QueueAssignmentWorkspaceResponse:
    task = _queue_task(task_id, conversation_id, status="assigned")
    conversation = _conversation(conversation_id)
    return QueueAssignmentWorkspaceResponse(
        task={
            "id": task.id,
            "source": "queue_task",
            "queue_task_id": task.id,
            "conversation_id": conversation.id,
            "conversation_public_id": conversation.public_id,
            "visitor": conversation.visitor,
            "channel": conversation.channel,
            "group": conversation.group,
            "queue": {
                "queue_type": task.queue_type,
                "queue_id": task.queue_id,
                "name": "售后组",
                "waiting_count": 0,
            },
            "priority": task.priority,
            "status": task.status,
            "source_type": task.source_type,
            "last_message_preview": conversation.last_message_preview,
            "last_message_at": conversation.last_message_at,
            "enqueued_at": task.enqueued_at,
            "wait_seconds": 0,
            "position_overall": None,
            "position_in_priority": None,
        },
        conversation_id=conversation.id,
        assigned_agent={
            "id": principal.user_id,
            "display_name": "Alice",
            "name": "alice",
            "avatar": None,
        },
        assigned_to_current_user=True,
    )


@pytest.mark.asyncio
async def test_list_tasks_returns_queue_tasks_only(monkeypatch):
    principal = _principal(permissions=["chat.queue.view"])
    queued_conversation = _conversation(100, preview="排队消息")
    task = _queue_task(11, queued_conversation.id, priority=1)

    monkeypatch.setattr(DataScopeService, "get_group_peer_employee_ids", AsyncMock(return_value=[20]))
    monkeypatch.setattr(DataScopeService, "get_scope", lambda *_args, **_kwargs: "group")
    monkeypatch.setattr(QueueWorkspaceRepository, "list_queued_tasks", AsyncMock(return_value=[task]))
    monkeypatch.setattr(QueueWorkspaceRepository, "count_queued_tasks_by_queue", AsyncMock(return_value=[("employee_group", 7, 1)]))
    monkeypatch.setattr(
        QueueWorkspaceRepository,
        "get_conversations_by_ids",
        AsyncMock(return_value={queued_conversation.id: queued_conversation}),
    )
    monkeypatch.setattr(QueueWorkspaceRepository, "get_group_names", AsyncMock(return_value={7: "售后组"}))
    monkeypatch.setattr(QueueWorkspaceRepository, "get_employee_names", AsyncMock(return_value={}))
    monkeypatch.setattr(QueueTaskRepository, "position_for_task", AsyncMock(return_value=(1, 1)))

    result = await QueueWorkspaceService.list_tasks(object(), principal)

    assert result.total == 1
    assert [item.id for item in result.items] == [11]
    assert result.items[0].source == "queue_task"
    assert result.items[0].queue_task_id == 11
    assert result.items[0].conversation_id == queued_conversation.id
    assert result.visible_queues[0].name == "售后组"
    assert result.visible_queues[0].waiting_count == 1


@pytest.mark.asyncio
async def test_count_tasks_returns_queue_task_count(monkeypatch):
    principal = _principal(permissions=["chat.queue.view"])
    count_tasks = AsyncMock(return_value=4)

    monkeypatch.setattr(DataScopeService, "get_group_peer_employee_ids", AsyncMock(return_value=[20]))
    monkeypatch.setattr(DataScopeService, "get_scope", lambda *_args, **_kwargs: "group")
    monkeypatch.setattr(QueueWorkspaceRepository, "count_queued_tasks", count_tasks)

    result = await QueueWorkspaceService.count_tasks(object(), principal)

    assert result.total == 4
    count_tasks.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_visible_task_rejects_legacy_negative_id(monkeypatch):
    principal = _principal(permissions=["chat.queue.view"])

    monkeypatch.setattr(DataScopeService, "get_group_peer_employee_ids", AsyncMock(return_value=[20]))
    monkeypatch.setattr(DataScopeService, "get_scope", lambda *_args, **_kwargs: "group")
    monkeypatch.setattr(QueueWorkspaceRepository, "get_queued_task", AsyncMock(return_value=None))

    with pytest.raises(NotFoundError):
        await QueueWorkspaceService._get_visible_task(object(), principal, -200)


@pytest.mark.asyncio
async def test_list_assignable_agents_excludes_current_user(monkeypatch):
    principal = _principal(permissions=["chat.queue.assign_other"], user_id=10)
    teammate = SimpleNamespace(
        id=20,
        name="teammate",
        username="teammate",
        display_name="Teammate",
        job_number="A20",
        avatar=None,
        max_concurrent=4,
    )

    async def get_candidates(_db, tenant_id, exclude_user_ids, keyword, limit):
        assert tenant_id == principal.tenant_id
        assert exclude_user_ids == [principal.user_id]
        assert keyword == "team"
        assert limit == 200
        return [teammate]

    monkeypatch.setattr(DataScopeService, "get_scope", lambda *_args, **_kwargs: "group")
    monkeypatch.setattr(DataScopeService, "get_group_peer_employee_ids", AsyncMock(return_value=[20]))
    monkeypatch.setattr(EmployeeRepository, "get_transfer_candidates", AsyncMock(side_effect=get_candidates))
    monkeypatch.setattr(
        QueueWorkspaceRepository,
        "get_agent_group_names",
        AsyncMock(return_value={20: [(7, "默认组")]}),
    )
    monkeypatch.setattr(
        AgentStatusService,
        "get_statuses_bulk",
        AsyncMock(return_value={20: {"status": "online", "current_count": 1, "max_concurrent": 4}}),
    )

    result = await QueueWorkspaceService.list_assignable_agents(object(), object(), principal, q="team")

    assert result.total == 1
    assert [item.id for item in result.items] == [20]
    assert all(item.id != principal.user_id for item in result.items)


@pytest.mark.asyncio
async def test_assign_to_agent_rejects_target_outside_group_scope(monkeypatch):
    principal = _principal(
        permissions=["chat.queue.assign_other"],
        data_scope="group",
    )

    monkeypatch.setattr(DataScopeService, "get_scope", lambda *_args, **_kwargs: "group")
    monkeypatch.setattr(DataScopeService, "get_group_peer_employee_ids", AsyncMock(return_value=[20, 21]))
    monkeypatch.setattr(
        QueueWorkspaceService,
        "_assign_to_agent",
        AsyncMock(side_effect=AssertionError("assignment should not be attempted")),
    )

    with pytest.raises(ForbiddenError):
        await QueueWorkspaceService.assign_to_agent(
            object(),
            object(),
            principal,
            11,
            QueueAssignRequest(agent_id=99, reason="转给其他人"),
        )


@pytest.mark.asyncio
async def test_assign_self_uses_unified_queue_assignment(monkeypatch):
    principal = _principal(permissions=["chat.queue.assign_self"])
    task = _queue_task(11, 100)
    assigned_task = _queue_task(11, 100, status="assigned")
    assigned_conversation = _conversation(100)
    assigned_conversation.agent = SimpleNamespace(
        id=principal.user_id,
        display_name="Alice",
        name="alice",
        avatar=None,
    )
    assigned_conversation.agent_id = principal.user_id

    admin_assign = AsyncMock(return_value=assigned_task)
    emit_events = AsyncMock()
    create_note = AsyncMock(return_value=SimpleNamespace(id=901, content_type="internal_note", content="我来处理"))
    monkeypatch.setattr(
        QueueWorkspaceService,
        "_get_visible_task",
        AsyncMock(return_value=(task, assigned_conversation)),
    )
    monkeypatch.setattr(EmployeeRepository, "has_effective_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(QueueTaskService, "admin_assign", admin_assign)
    monkeypatch.setattr(
        "app.services.queue_workspace_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=assigned_conversation),
    )
    monkeypatch.setattr(QueueWorkspaceService, "_create_assignment_internal_note", create_note)
    monkeypatch.setattr(QueueWorkspaceService, "_emit_assignment_events", emit_events)
    monkeypatch.setattr(
        QueueWorkspaceService,
        "_queue_names",
        AsyncMock(return_value={("employee_group", 7): "售后组"}),
    )
    monkeypatch.setattr(QueueTaskRepository, "position_for_task", AsyncMock(return_value=(None, None)))

    result = await QueueWorkspaceService.assign_self(
        object(),
        object(),
        principal,
        11,
        QueueAssignSelfRequest(reason="我来处理"),
    )

    admin_assign.assert_awaited_once()
    create_note.assert_awaited_once()
    emit_events.assert_awaited_once_with(
        assigned_conversation,
        principal.user_id,
        db=ANY,
        operator_id=principal.user_id,
        assignment_note=create_note.return_value,
    )
    assert result.assigned_to_current_user is True
    assert result.conversation_id == assigned_conversation.id
    assert result.assigned_agent.name == "alice"


@pytest.mark.asyncio
async def test_assign_self_and_send_assigns_then_sends_text(monkeypatch):
    principal = _principal(permissions=["chat.queue.assign_self"])
    assignment = _assignment_response(principal=principal)
    assigned_conversation = _conversation(100)
    assigned_conversation.agent = SimpleNamespace(
        id=principal.user_id,
        display_name="Alice",
        name="alice",
        avatar=None,
    )
    assigned_conversation.agent_id = principal.user_id
    message = SimpleNamespace(
        id=901,
        conversation_id=assigned_conversation.id,
        sender_type="agent",
        sender_id=principal.user_id,
        content_type="text",
        content="您好，我来处理",
        metadata_=None,
        created_at=datetime(2026, 6, 16, 10, 5),
    )
    assign_to_agent = AsyncMock(return_value=assignment)
    send_message = AsyncMock(return_value=message)
    emit_message = AsyncMock()
    monkeypatch.setattr(QueueWorkspaceService, "_assign_to_agent", assign_to_agent)
    monkeypatch.setattr(
        "app.services.queue_workspace_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=assigned_conversation),
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.ConversationService.send_message",
        send_message,
    )
    monkeypatch.setattr(QueueWorkspaceService, "_emit_sent_message_events", emit_message)
    db = object()
    redis = object()

    result = await QueueWorkspaceService.assign_self_and_send(
        db,
        redis,
        principal,
        11,
        QueueAssignAndSendRequest(content="  您好，我来处理  "),
    )

    assign_to_agent.assert_awaited_once_with(
        db,
        redis,
        principal,
        11,
        principal.user_id,
    )
    send_message.assert_awaited_once()
    kwargs = send_message.await_args.kwargs
    assert kwargs["conversation_id"] == assigned_conversation.id
    assert kwargs["sender_type"] == "agent"
    assert kwargs["sender_id"] == principal.user_id
    assert kwargs["content_type"] == "text"
    assert kwargs["content"] == "您好，我来处理"
    assert kwargs["principal"] is principal
    emit_message.assert_awaited_once_with(assigned_conversation, message, principal.user_id)
    assert result.message_sent is True
    assert result.message.content == "您好，我来处理"
    assert result.message.sender_name == "Alice"


@pytest.mark.asyncio
async def test_assign_self_and_send_requires_assign_self_permission(monkeypatch):
    principal = _principal(permissions=[])
    monkeypatch.setattr(
        QueueWorkspaceService,
        "_assign_to_agent",
        AsyncMock(side_effect=AssertionError("assignment should not be attempted")),
    )

    with pytest.raises(ForbiddenError):
        await QueueWorkspaceService.assign_self_and_send(
            object(),
            object(),
            principal,
            11,
            QueueAssignAndSendRequest(content="hello"),
        )


@pytest.mark.asyncio
async def test_assign_self_and_send_keeps_assignment_when_message_fails(monkeypatch):
    principal = _principal(permissions=["chat.queue.assign_self"])
    assignment = _assignment_response(principal=principal)
    assigned_conversation = _conversation(100)
    assigned_conversation.agent_id = principal.user_id
    assign_to_agent = AsyncMock(return_value=assignment)
    send_message = AsyncMock(side_effect=ForbiddenError("Permission denied"))
    emit_message = AsyncMock()
    monkeypatch.setattr(QueueWorkspaceService, "_assign_to_agent", assign_to_agent)
    monkeypatch.setattr(
        "app.services.queue_workspace_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=assigned_conversation),
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.ConversationService.send_message",
        send_message,
    )
    monkeypatch.setattr(QueueWorkspaceService, "_emit_sent_message_events", emit_message)

    result = await QueueWorkspaceService.assign_self_and_send(
        object(),
        object(),
        principal,
        11,
        QueueAssignAndSendRequest(content="hello"),
    )

    assign_to_agent.assert_awaited_once()
    send_message.assert_awaited_once()
    emit_message.assert_not_awaited()
    assert result.assigned_to_current_user is True
    assert result.conversation_id == assigned_conversation.id
    assert result.message is None
    assert result.message_sent is False


@pytest.mark.asyncio
async def test_enqueue_conversation_emits_queue_update(monkeypatch):
    db = SimpleNamespace()
    conversation = _conversation(100)
    task = _queue_task(11, conversation.id)
    enqueue_task = AsyncMock(return_value=SimpleNamespace(task=task, position=SimpleNamespace(position_overall=1)))

    monkeypatch.setattr(QueueTaskRepository, "get_active_task_by_ref", AsyncMock(return_value=None))
    monkeypatch.setattr(QueueTaskService, "enqueue_task", enqueue_task)

    result = await QueueWorkspaceService.enqueue_conversation_if_needed(db, 1, conversation)

    enqueue_task.assert_awaited_once()
    request = enqueue_task.await_args.args[2]
    assert request.channel.value == "online_chat"
    assert request.task_type.value == "conversation"
    assert request.task_ref_id == str(conversation.id)
    assert request.queue_type.value == "employee_group"
    assert request.queue_id == 7
    assert result.position.position_overall == 1


@pytest.mark.asyncio
async def test_emit_assignment_events_sends_welcome_message_to_visitor(monkeypatch):
    db = SimpleNamespace()
    conversation = _conversation(100)
    conversation.agent = SimpleNamespace(id=20, display_name="Agent A", name="agent_a", avatar=None)
    conversation.agent_id = 20
    conversation.unread_count = 0
    welcome_msg = SimpleNamespace(
        id=501,
        sender_type="system",
        sender_id=None,
        content_type="welcome",
        content="<p>Hello</p>",
        metadata_=None,
        created_at=datetime(2026, 6, 16, 10, 1),
    )
    rt = SimpleNamespace(emit=AsyncMock())
    emit_list_updated = AsyncMock()

    monkeypatch.setattr(
        "app.services.queue_workspace_service.get_realtime_transport",
        lambda: rt,
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.MessageRepository.get_event_message",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.MessageRepository.get_welcome_message",
        AsyncMock(return_value=welcome_msg),
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.ConversationRealtimeService.emit_conversation_list_updated",
        emit_list_updated,
    )

    await QueueWorkspaceService._emit_assignment_events(conversation, 20, db=db)

    emitted_events = [call.args[0] for call in rt.emit.await_args_list]
    assert "conversation_assigned" in emitted_events
    assert emitted_events.count("new_message") == 2
    visitor_new_message = rt.emit.await_args_list[emitted_events.index("new_message")]
    assert visitor_new_message.kwargs["namespace"] == "/visitor"
    assert visitor_new_message.args[1]["content_type"] == "welcome"


@pytest.mark.asyncio
async def test_emit_assignment_events_sends_agent_assigned_event_to_visitor(monkeypatch):
    db = SimpleNamespace()
    conversation = _conversation(100)
    conversation.agent = SimpleNamespace(id=20, display_name="Agent A", name="agent_a", avatar=None)
    conversation.agent_id = 20
    conversation.unread_count = 0
    assigned_msg = SimpleNamespace(
        id=601,
        sender_type="system",
        sender_id=None,
        content_type="system",
        content="客服已接入会话",
        metadata_={"event_type": "agent_assigned", "agent_id": 20},
        created_at=datetime(2026, 6, 16, 10, 2),
    )
    rt = SimpleNamespace(emit=AsyncMock())

    monkeypatch.setattr(
        "app.services.queue_workspace_service.get_realtime_transport",
        lambda: rt,
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.MessageRepository.get_event_message",
        AsyncMock(return_value=assigned_msg),
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.MessageRepository.get_welcome_message",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.ConversationRealtimeService.emit_conversation_list_updated",
        AsyncMock(),
    )

    await QueueWorkspaceService._emit_assignment_events(conversation, 20, db=db)

    emitted_events = [call.args[0] for call in rt.emit.await_args_list]
    assert emitted_events.count("new_message") == 2
    visitor_new_message = rt.emit.await_args_list[emitted_events.index("new_message")]
    assert visitor_new_message.kwargs["namespace"] == "/visitor"
    assert visitor_new_message.args[1]["content"] == "客服已接入会话"
    assert visitor_new_message.args[1]["event_type"] == "agent_assigned"


@pytest.mark.asyncio
async def test_create_assignment_internal_note_skips_blank_reason():
    principal = _principal(permissions=["chat.queue.assign_other"])
    conversation = _conversation(100)

    result = await QueueWorkspaceService._create_assignment_internal_note(
        object(),
        principal,
        conversation,
        "   ",
    )

    assert result is None


@pytest.mark.asyncio
async def test_create_assignment_internal_note_persists_internal_message(monkeypatch):
    principal = _principal(permissions=["chat.queue.assign_other"])
    conversation = _conversation(100)
    internal_msg = SimpleNamespace(id=901, content_type="internal_note", content="请先安抚客户")
    send_message = AsyncMock(return_value=internal_msg)
    monkeypatch.setattr(
        "app.services.queue_workspace_service.ConversationService.send_message",
        send_message,
    )

    result = await QueueWorkspaceService._create_assignment_internal_note(
        object(),
        principal,
        conversation,
        "请先安抚客户",
    )

    assert result is internal_msg
    send_message.assert_awaited_once()
    kwargs = send_message.await_args.kwargs
    assert kwargs["conversation_id"] == conversation.id
    assert kwargs["sender_type"] == "agent"
    assert kwargs["sender_id"] == principal.user_id
    assert kwargs["content_type"] == "internal_note"
    assert kwargs["content"] == "请先安抚客户"


@pytest.mark.asyncio
async def test_emit_assignment_events_emits_internal_note_to_agents_only(monkeypatch):
    db = SimpleNamespace()
    conversation = _conversation(100)
    conversation.agent = SimpleNamespace(id=20, display_name="Agent A", name="agent_a", avatar=None)
    conversation.agent_id = 20
    conversation.unread_count = 0
    internal_note = SimpleNamespace(
        id=701,
        sender_type="agent",
        sender_id=10,
        content_type="internal_note",
        content="请先安抚客户",
        metadata_={"visibility": "internal"},
        created_at=datetime(2026, 6, 16, 10, 3),
    )
    rt = SimpleNamespace(emit=AsyncMock())

    monkeypatch.setattr(
        "app.services.queue_workspace_service.get_realtime_transport",
        lambda: rt,
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.MessageRepository.get_event_message",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.MessageRepository.get_welcome_message",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.ConversationRealtimeService.emit_conversation_list_updated",
        AsyncMock(),
    )

    await QueueWorkspaceService._emit_assignment_events(
        conversation,
        20,
        db=db,
        operator_id=10,
        assignment_note=internal_note,
    )

    emitted_events = [call.args[0] for call in rt.emit.await_args_list]
    assert emitted_events.count("new_message") == 3
    assert all(call.kwargs["namespace"] != "/visitor" for call in rt.emit.await_args_list if call.args[0] == "new_message")
    internal_payloads = [
        call.args[1]
        for call in rt.emit.await_args_list
        if call.args[0] == "new_message"
    ]
    assert all(payload["content_type"] == "internal_note" for payload in internal_payloads)
