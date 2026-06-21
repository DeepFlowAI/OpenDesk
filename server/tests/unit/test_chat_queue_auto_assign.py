from datetime import datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

from app.core.exceptions import NotFoundError
from app.socketio import chat_handlers


class _SessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _RealtimeHarness:
    def __init__(self, session: dict | None = None):
        self.handlers = {}
        self.session = session or {"user_id": 10, "tenant_id": 1}
        self.join_room = AsyncMock()
        self.leave_room = AsyncMock()
        self.emit = AsyncMock()

    def on(self, event, handler=None, namespace=None):
        if handler is not None:
            self.handlers[(namespace, event)] = handler
            return None

        def decorator(fn):
            self.handlers[(namespace, event)] = fn
            return fn

        return decorator

    async def get_session(self, sid, namespace=None):
        return self.session

    async def save_session(self, sid, session, namespace=None):
        self.session = session


def _conversation():
    visitor = SimpleNamespace(
        id=1,
        public_id="usr_1",
        name="Visitor",
        avatar_color="#2563eb",
    )
    return SimpleNamespace(
        id=100,
        tenant_id=1,
        visitor=visitor,
        channel_id=3,
        public_id="cv_100",
        agent=SimpleNamespace(id=20, display_name="Agent A", name="agent_a", avatar=None),
    )


def _principal(permissions: set[str], data_scopes: dict[str, str] | None = None):
    return SimpleNamespace(
        user_id=10,
        tenant_id=1,
        is_super_admin=False,
        data_scopes=data_scopes or {},
        has_permission=lambda permission: permission in permissions,
    )


@pytest.mark.asyncio
async def test_connect_auto_assign_uses_queue_service(monkeypatch):
    db = SimpleNamespace()
    rt = SimpleNamespace(emit=AsyncMock())
    r = SimpleNamespace()
    conversation = _conversation()
    task = SimpleNamespace(task_ref_id=str(conversation.id))
    enqueue_if_needed = AsyncMock()
    pull_next = AsyncMock(side_effect=[task, NotFoundError("No queue task available")])
    assign_agent = AsyncMock(side_effect=AssertionError("direct conversation assignment is not allowed"))

    monkeypatch.setattr(chat_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        chat_handlers.AgentStatusService,
        "get_status",
        AsyncMock(return_value={"status": "online", "current_count": 0, "max_concurrent": 10}),
    )

    from app.repositories.conversation_repository import ConversationRepository
    from app.repositories.employee_repository import EmployeeRepository
    from app.services.queue_service import QueueTaskService
    from app.services.queue_workspace_service import QueueWorkspaceService

    monkeypatch.setattr(
        EmployeeRepository,
        "get_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                id=20,
                max_concurrent=10,
                display_name="Agent A",
                name="agent_a",
                avatar=None,
            )
        ),
    )
    monkeypatch.setattr(ConversationRepository, "get_queued_by_tenant", AsyncMock(return_value=[conversation]))
    monkeypatch.setattr(ConversationRepository, "get_by_id", AsyncMock(return_value=conversation))
    monkeypatch.setattr(ConversationRepository, "assign_agent", assign_agent)
    monkeypatch.setattr(QueueWorkspaceService, "enqueue_conversation_if_needed", enqueue_if_needed)
    monkeypatch.setattr(QueueTaskService, "pull_next", pull_next)
    emit_assignment_events = AsyncMock()
    monkeypatch.setattr(QueueWorkspaceService, "_emit_assignment_events", emit_assignment_events)

    await chat_handlers._assign_queued_conversations(rt, r, tenant_id=1, agent_id=20)

    enqueue_if_needed.assert_awaited_once_with(
        db,
        1,
        conversation,
        source_type="visitor_waiting",
    )
    assert pull_next.await_count == 2
    assign_agent.assert_not_awaited()
    emit_assignment_events.assert_awaited_once_with(conversation, 20, db=db)


@pytest.mark.asyncio
async def test_join_conversation_validates_access_and_joins_room(monkeypatch):
    db = SimpleNamespace()
    rt = _RealtimeHarness()
    principal = SimpleNamespace(user_id=10, tenant_id=1)

    monkeypatch.setattr(chat_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        chat_handlers.PermissionService,
        "get_current_principal",
        AsyncMock(return_value=principal),
    )
    monkeypatch.setattr(
        chat_handlers.ConversationService,
        "get_agent_conversation",
        AsyncMock(return_value={"id": 100, "viewer_relation": "peer"}),
    )

    chat_handlers.register_chat_handlers(rt)

    response = await rt.handlers[("/chat", "join_conversation")](
        "sid-1",
        {"conversation_id": 100},
    )

    assert response == {"ok": True}
    chat_handlers.PermissionService.get_current_principal.assert_awaited_once_with(
        db,
        {"user_id": 10, "tenant_id": 1},
    )
    chat_handlers.ConversationService.get_agent_conversation.assert_awaited_once_with(
        db,
        conversation_id=100,
        tenant_id=1,
        agent_id=10,
        principal=principal,
    )
    rt.join_room.assert_awaited_once_with("sid-1", "conv:100", namespace="/chat")


@pytest.mark.asyncio
async def test_leave_conversation_leaves_room():
    rt = _RealtimeHarness()
    chat_handlers.register_chat_handlers(rt)

    response = await rt.handlers[("/chat", "leave_conversation")](
        "sid-1",
        {"conversation_id": 100},
    )

    assert response == {"ok": True}
    rt.leave_room.assert_awaited_once_with("sid-1", "conv:100", namespace="/chat")


async def _invoke_update_status(monkeypatch, status: str, backfill: AsyncMock):
    db = SimpleNamespace()
    rt = _RealtimeHarness(session={"user_id": 10, "tenant_id": 1})
    redis_stub = SimpleNamespace(client=SimpleNamespace())

    monkeypatch.setattr(chat_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(chat_handlers, "redis_client", redis_stub)
    monkeypatch.setattr(chat_handlers.AgentStatusService, "set_status", AsyncMock())
    monkeypatch.setattr(
        chat_handlers.AgentStatusService,
        "get_status",
        AsyncMock(return_value={"status": status, "current_count": 1, "max_concurrent": 4}),
    )
    monkeypatch.setattr(chat_handlers, "_assign_queued_conversations", backfill)

    from app.repositories.employee_repository import EmployeeRepository

    monkeypatch.setattr(
        EmployeeRepository,
        "get_by_id",
        AsyncMock(return_value=SimpleNamespace(max_concurrent=4)),
    )

    chat_handlers.register_chat_handlers(rt)
    response = await rt.handlers[("/chat", "update_status")]("sid-1", {"status": status})
    return response, rt, redis_stub


@pytest.mark.asyncio
async def test_update_status_online_triggers_backfill(monkeypatch):
    backfill = AsyncMock()
    response, rt, redis_stub = await _invoke_update_status(monkeypatch, "online", backfill)

    assert response["ok"] is True
    backfill.assert_awaited_once_with(rt, redis_stub.client, 1, 10)


@pytest.mark.asyncio
async def test_update_status_busy_does_not_trigger_backfill(monkeypatch):
    backfill = AsyncMock()
    response, _rt, _redis_stub = await _invoke_update_status(monkeypatch, "busy", backfill)

    assert response["ok"] is True
    backfill.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscribe_workspace_counters_joins_authorized_rooms(monkeypatch):
    db = SimpleNamespace()
    rt = _RealtimeHarness()
    principal = _principal({"chat.queue.view", "chat.offline_message.view"})

    monkeypatch.setattr(chat_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        chat_handlers.PermissionService,
        "get_current_principal",
        AsyncMock(return_value=principal),
    )

    chat_handlers.register_chat_handlers(rt)

    response = await rt.handlers[("/chat", "subscribe_workspace_counters")](
        "sid-1",
        {"resources": ["queue", "offline"]},
    )

    assert response == {"ok": True, "subscribed": ["queue", "offline"]}
    assert [call.args[1] for call in rt.join_room.await_args_list] == [
        "workspace:1:queue:count",
        "workspace:1:offline:count",
    ]


@pytest.mark.asyncio
async def test_subscribe_workspace_tab_joins_peer_list_room(monkeypatch):
    db = SimpleNamespace()
    rt = _RealtimeHarness()
    principal = _principal(
        {"chat.conversation.peer.view"},
        {"chat.conversation.peer.view": "group"},
    )

    monkeypatch.setattr(chat_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        chat_handlers.PermissionService,
        "get_current_principal",
        AsyncMock(return_value=principal),
    )

    chat_handlers.register_chat_handlers(rt)

    response = await rt.handlers[("/chat", "subscribe_workspace_tab")](
        "sid-1",
        {"tab": "peers"},
    )

    assert response == {"ok": True, "subscribed": "peers"}
    rt.join_room.assert_awaited_once_with(
        "sid-1",
        "workspace:1:conversation:peers:list",
        namespace="/chat",
    )


@pytest.mark.asyncio
async def test_send_message_broadcasts_normalized_payload_to_agent_message_stream(monkeypatch):
    db = SimpleNamespace()
    rt = _RealtimeHarness(session={"user_id": "10", "tenant_id": "1"})
    principal = SimpleNamespace(user_id=10, tenant_id=1)
    created_at = datetime(2026, 6, 19, 10, 30, 0)
    message = SimpleNamespace(
        id=501,
        conversation_id=100,
        sender_type="agent",
        sender_id=10,
        content_type="text",
        content="hello",
        created_at=created_at,
        metadata_={},
    )
    conversation = SimpleNamespace(id=100, agent_id=20)
    employee = SimpleNamespace(
        id=10,
        display_name="Agent",
        name="agent",
        avatar=None,
    )

    monkeypatch.setattr(chat_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        chat_handlers.PermissionService,
        "get_current_principal",
        AsyncMock(return_value=principal),
    )
    monkeypatch.setattr(
        chat_handlers.ConversationService,
        "send_message",
        AsyncMock(return_value=message),
    )
    monkeypatch.setattr(
        chat_handlers.ConversationRealtimeService,
        "emit_conversation_list_updated",
        AsyncMock(),
    )

    from app.repositories.conversation_repository import ConversationRepository
    from app.repositories.employee_repository import EmployeeRepository

    monkeypatch.setattr(EmployeeRepository, "get_by_id", AsyncMock(return_value=employee))
    monkeypatch.setattr(ConversationRepository, "get_by_id", AsyncMock(return_value=conversation))

    chat_handlers.register_chat_handlers(rt)

    response = await rt.handlers[("/chat", "send_message")](
        "sid-1",
        {"conversation_id": "100", "content": "hello", "content_type": "text"},
    )

    assert response["ok"] is True
    assert response["message"]["conversation_id"] == 100
    assert response["message"]["sender_id"] == 10
    chat_handlers.ConversationService.send_message.assert_awaited_once_with(
        db,
        conversation_id=100,
        sender_type="agent",
        sender_id=10,
        content_type="text",
        content="hello",
        tenant_id=1,
        principal=principal,
    )
    chat_handlers.ConversationRealtimeService.emit_conversation_list_updated.assert_awaited_once_with(
        1,
        action="message",
        conversation_id=100,
        rt=rt,
        message_flow_id=ANY,
    )
    new_message_calls = [
        call for call in rt.emit.await_args_list
        if call.args[0] == "new_message" and call.kwargs.get("namespace") == "/chat"
    ]
    new_message_rooms = {call.kwargs.get("room") for call in new_message_calls}
    assert {"agent:1:10", "agent:1:20", "conv:100"}.issubset(new_message_rooms)
    for call in new_message_calls:
        payload = call.args[1]
        assert payload["conversation_id"] == 100
        assert payload["sender_id"] == 10
