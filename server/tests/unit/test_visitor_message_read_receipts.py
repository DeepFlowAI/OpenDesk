from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.socketio import visitor_handlers


class _SessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _RealtimeHarness:
    def __init__(self, session: dict):
        self.handlers = {}
        self.session = session
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


@asynccontextmanager
async def _start_lock_stub(*_args, **_kwargs):
    yield


@pytest.mark.asyncio
async def test_visitor_connect_validates_session_and_marks_online(monkeypatch):
    db = SimpleNamespace()
    redis = SimpleNamespace()
    session = {
        "tenant_id": 1,
        "channel_id": 2,
        "visitor_external_id": "visitor-1",
        "visitor_name": "Visitor",
    }
    rt = _RealtimeHarness(session={})
    validate_token = AsyncMock(return_value=session.copy())
    mark_connected = AsyncMock()
    emit_status = AsyncMock()

    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(visitor_handlers, "redis_client", SimpleNamespace(client=redis))
    monkeypatch.setattr(
        visitor_handlers.ChannelService,
        "validate_visitor_session_token",
        validate_token,
    )
    monkeypatch.setattr(
        visitor_handlers.VisitorWebStatusService,
        "mark_connected",
        mark_connected,
    )
    monkeypatch.setattr(
        visitor_handlers.VisitorWebStatusService,
        "emit_status_for_visitor_context",
        emit_status,
    )

    visitor_handlers.register_visitor_handlers(rt)

    await rt.handlers[("/visitor", "connect")](
        "sid-1",
        {"REMOTE_ADDR": "203.0.113.10"},
        {"visitor_session_token": "token"},
    )

    validate_token.assert_awaited_once_with(db, "token")
    assert rt.session["visitor_ip"] == "203.0.113.10"
    rt.join_room.assert_awaited_once_with("sid-1", "visitor:1:visitor-1", namespace="/visitor")
    mark_connected.assert_awaited_once_with(
        redis,
        tenant_id=1,
        channel_id=2,
        visitor_external_id="visitor-1",
        sid="sid-1",
    )
    emit_status.assert_awaited_once_with(
        rt,
        redis,
        db,
        tenant_id=1,
        channel_id=2,
        visitor_external_id="visitor-1",
    )


@pytest.mark.asyncio
async def test_start_conversation_maps_queue_full_response(monkeypatch):
    db = SimpleNamespace()
    session = {
        "tenant_id": 1,
        "channel_id": 2,
        "visitor_external_id": "visitor-1",
        "visitor_name": "Visitor",
    }
    rt = _RealtimeHarness(session=session)
    create_from_visitor = AsyncMock(return_value={
        "queue_full": True,
        "queue_type": "group",
        "queue_id": 8,
        "availability": {
            "reason": "queue_full",
            "queue_full_message": "当前排队人数较多",
            "queue_full_show_leave_message_button": True,
            "queue_full_leave_message_button_label": "留言",
            "leave_message_prompt": "请留言",
        },
    })

    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(visitor_handlers, "redis_client", SimpleNamespace(client=SimpleNamespace()))
    monkeypatch.setattr(visitor_handlers, "_visitor_start_lock", _start_lock_stub)
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "create_from_visitor",
        create_from_visitor,
    )

    visitor_handlers.register_visitor_handlers(rt)

    response = await rt.handlers[("/visitor", "start_conversation")](
        "sid-1",
        {"contextToken": "ctx-1", "metadata": {"source": "unit"}},
    )

    assert response == {
        "ok": False,
        "error": "QUEUE_FULL",
        "reason": "queue_full",
        "queue_type": "group",
        "queue_id": 8,
        "queue_full_message": "当前排队人数较多",
        "queue_full_show_leave_message_button": True,
        "queue_full_leave_message_button_label": "留言",
        "leave_message_prompt": "请留言",
    }
    create_from_visitor.assert_awaited_once()
    assert create_from_visitor.await_args.kwargs["tenant_id"] == 1
    assert create_from_visitor.await_args.kwargs["channel_id"] == 2
    assert create_from_visitor.await_args.kwargs["visitor_external_id"] == "visitor-1"
    assert create_from_visitor.await_args.kwargs["context_token"] == "ctx-1"


@pytest.mark.asyncio
async def test_join_conversation_validates_visitor_and_joins_realtime_room(monkeypatch):
    db = SimpleNamespace()
    session = {
        "tenant_id": 1,
        "channel_id": 2,
        "visitor_external_id": "visitor-1",
    }
    rt = _RealtimeHarness(session=session)
    conversation = SimpleNamespace(id=100, public_id="cv_100")
    get_conversation = AsyncMock(return_value=conversation)

    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "get_conversation_for_visitor_session",
        get_conversation,
    )

    visitor_handlers.register_visitor_handlers(rt)
    response = await rt.handlers[("/visitor", "join_conversation")](
        "sid-1",
        {"conversation_public_id": "cv_100"},
    )

    assert response == {
        "ok": True,
        "conversation_id": 100,
        "conversation_public_id": "cv_100",
    }
    get_conversation.assert_awaited_once_with(
        db,
        conversation_public_id="cv_100",
        tenant_id=1,
        channel_id=2,
        visitor_external_id="visitor-1",
    )
    rt.join_room.assert_awaited_once_with("sid-1", "conv:100", namespace="/visitor")


@pytest.mark.asyncio
async def test_join_conversation_returns_stable_error_on_internal_failure(monkeypatch):
    db = SimpleNamespace()
    session = {
        "tenant_id": 1,
        "channel_id": 2,
        "visitor_external_id": "visitor-1",
    }
    rt = _RealtimeHarness(session=session)
    get_conversation = AsyncMock(side_effect=RuntimeError("database unavailable"))

    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "get_conversation_for_visitor_session",
        get_conversation,
    )

    visitor_handlers.register_visitor_handlers(rt)
    response = await rt.handlers[("/visitor", "join_conversation")](
        "sid-1",
        {"conversation_public_id": "cv_100"},
    )

    assert response == {"ok": False, "error": "INTERNAL"}
    rt.join_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_visitor_send_message_marks_previous_agent_messages_read(monkeypatch):
    db = SimpleNamespace()
    session = {
        "tenant_id": 1,
        "channel_id": 2,
        "visitor_external_id": "visitor-1",
    }
    rt = _RealtimeHarness(session=session)
    conversation = SimpleNamespace(id=100, public_id="cv_100", unread_count=1)
    message_payload = {
        "id": 301,
        "conversation_public_id": "cv_100",
        "sender_type": "visitor",
        "sender_id": 7,
        "sender_name": "Visitor",
        "sender_avatar": None,
        "content_type": "text",
        "content": "hello",
        "created_at": "2026-06-26T14:00:00+00:00",
        "status": "unread",
    }
    read_result = {
        "tenant_id": 1,
        "conversation_id": 100,
        "conversation_public_id": "cv_100",
        "message_ids": [201],
        "recipient_agent_ids": [9, 10],
    }
    send_visitor_message = AsyncMock(return_value=(message_payload, 9, conversation))
    mark_agent_messages_read = AsyncMock(return_value=read_result)

    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "send_visitor_message_for_session",
        send_visitor_message,
    )
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "mark_agent_messages_visitor_read_for_session",
        mark_agent_messages_read,
    )
    monkeypatch.setattr(
        visitor_handlers.ConversationRealtimeService,
        "emit_conversation_list_updated",
        AsyncMock(),
    )

    visitor_handlers.register_visitor_handlers(rt)

    response = await rt.handlers[("/visitor", "send_message")](
        "sid-1",
        {
            "conversation_public_id": "cv_100",
            "content": "hello",
            "content_type": "text",
        },
    )

    assert response == {"ok": True, "message": message_payload}
    send_visitor_message.assert_awaited_once_with(
        db,
        conversation_public_id="cv_100",
        visitor_context=session,
        content_type="text",
        content="hello",
        quoted_message_id=None,
    )
    mark_agent_messages_read.assert_awaited_once_with(
        db,
        visitor_context=session,
        conversation_public_id="cv_100",
        before_message_id=301,
    )

    read_calls = [
        call for call in rt.emit.await_args_list
        if call.args[0] == "messages_read" and call.kwargs.get("namespace") == "/chat"
    ]
    read_rooms = {call.kwargs.get("room") for call in read_calls}
    assert {"conv:100", "agent:1:9", "agent:1:10"}.issubset(read_rooms)
    assert all(call.args[1]["message_ids"] == [201] for call in read_calls)


@pytest.mark.asyncio
async def test_visitor_recall_message_broadcasts_to_visitor_and_agents(monkeypatch):
    db = SimpleNamespace()
    session = {
        "tenant_id": 1,
        "channel_id": 2,
        "visitor_external_id": "visitor-1",
    }
    rt = _RealtimeHarness(session=session)
    message = SimpleNamespace(
        id=301,
        conversation_id=100,
        sender_type="visitor",
        sender_id=7,
        content_type="text",
        content="hello",
        created_at=datetime(2026, 6, 26, 14, 0, 0),
        metadata_={},
        is_recalled=True,
        recalled_at=datetime(2026, 6, 26, 14, 1, 0),
        recalled_by_type="visitor",
        recalled_by_id=7,
        recalled_by_name="Visitor",
        visitor_read_at=None,
        agent_read_at=None,
    )
    conversation = SimpleNamespace(
        id=100,
        public_id="cv_100",
        agent_id=9,
        unread_count=3,
        visitor=SimpleNamespace(name="Visitor"),
    )
    conversation_update = {"last_message_preview": "访客撤回了一条消息"}
    recall_message = AsyncMock(return_value=(message, conversation, conversation_update))

    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "recall_visitor_message_for_session",
        recall_message,
    )
    monkeypatch.setattr(
        visitor_handlers.ConversationRealtimeService,
        "emit_conversation_list_updated",
        AsyncMock(),
    )

    from app.repositories.conversation_collaboration_repository import ConversationCollaborationRepository

    monkeypatch.setattr(
        ConversationCollaborationRepository,
        "get_active_collaborator_agent_ids",
        AsyncMock(return_value=[10]),
    )

    visitor_handlers.register_visitor_handlers(rt)

    response = await rt.handlers[("/visitor", "recall_message")](
        "sid-1",
        {"conversation_public_id": "cv_100", "message_id": "301"},
    )

    assert response["ok"] is True
    recall_message.assert_awaited_once_with(
        db,
        conversation_public_id="cv_100",
        visitor_context=session,
        message_id=301,
    )
    recall_calls = [
        call for call in rt.emit.await_args_list
        if call.args[0] == "message_recalled"
    ]
    recall_targets = {(call.kwargs.get("namespace"), call.kwargs.get("room")) for call in recall_calls}
    assert recall_targets == {
        ("/visitor", "conv:100"),
        ("/chat", "agent:1:9"),
        ("/chat", "agent:1:10"),
    }
    visitor_handlers.ConversationRealtimeService.emit_conversation_list_updated.assert_awaited_once_with(
        1,
        action="message",
        conversation_id=100,
        rt=rt,
    )


@pytest.mark.asyncio
async def test_visitor_mark_read_notifies_conversation_and_agent_rooms(monkeypatch):
    db = SimpleNamespace()
    session = {
        "tenant_id": 1,
        "channel_id": 2,
        "visitor_external_id": "visitor-1",
    }
    rt = _RealtimeHarness(session=session)
    read_result = {
        "tenant_id": 1,
        "conversation_id": 100,
        "conversation_public_id": "cv_100",
        "message_ids": [201, 202],
        "recipient_agent_ids": [9, 10],
    }
    mark_read = AsyncMock(return_value=read_result)

    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "mark_agent_messages_visitor_read_for_session",
        mark_read,
    )

    visitor_handlers.register_visitor_handlers(rt)

    response = await rt.handlers[("/visitor", "mark_read")](
        "sid-1",
        {"conversation_public_id": "cv_100"},
    )

    assert response == {"ok": True, "message_ids": [201, 202]}
    mark_read.assert_awaited_once_with(
        db,
        visitor_context=session,
        conversation_public_id="cv_100",
    )
    read_calls = [
        call for call in rt.emit.await_args_list
        if call.args[0] == "messages_read"
    ]
    read_targets = {call.kwargs.get("room") for call in read_calls}
    assert read_targets == {"conv:100", "agent:1:9", "agent:1:10"}
    assert all(call.kwargs.get("namespace") == "/chat" for call in read_calls)


@pytest.mark.asyncio
async def test_visitor_messages_delivered_notifies_conversation_and_agent_rooms(monkeypatch):
    db = SimpleNamespace()
    session = {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"}
    rt = _RealtimeHarness(session=session)
    delivery_result = {
        "tenant_id": 1,
        "conversation_id": 100,
        "conversation_public_id": "cv_100",
        "message_ids": [201, 202],
        "recipient_agent_ids": [9, 10],
    }
    mark_delivered = AsyncMock(return_value=delivery_result)
    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "mark_agent_messages_visitor_delivered_for_session",
        mark_delivered,
    )

    visitor_handlers.register_visitor_handlers(rt)
    response = await rt.handlers[("/visitor", "messages_delivered")](
        "sid-1",
        {"conversation_public_id": "cv_100", "message_ids": [201, 202]},
    )

    assert response == {"ok": True, "message_ids": [201, 202]}
    delivery_calls = [call for call in rt.emit.await_args_list if call.args[0] == "messages_delivered"]
    assert {call.kwargs.get("room") for call in delivery_calls} == {
        "conv:100",
        "agent:1:9",
        "agent:1:10",
    }
    assert all(call.kwargs.get("namespace") == "/chat" for call in delivery_calls)


@pytest.mark.asyncio
async def test_visitor_messages_delivered_duplicate_ack_has_no_realtime_side_effect(monkeypatch):
    db = SimpleNamespace()
    session = {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"}
    rt = _RealtimeHarness(session=session)
    mark_delivered = AsyncMock(return_value={
        "tenant_id": 1,
        "conversation_id": 100,
        "conversation_public_id": "cv_100",
        "message_ids": [],
        "recipient_agent_ids": [9, 10],
    })
    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "mark_agent_messages_visitor_delivered_for_session",
        mark_delivered,
    )

    visitor_handlers.register_visitor_handlers(rt)
    response = await rt.handlers[("/visitor", "messages_delivered")](
        "sid-1",
        {"conversation_public_id": "cv_100", "message_ids": [201, 202]},
    )

    assert response == {"ok": True, "message_ids": []}
    rt.emit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"conversation_public_id": "cv_100", "message_ids": ["bad"]}, "Invalid message_ids"),
        (
            {"conversation_public_id": "cv_100", "message_ids": list(range(501))},
            "Too many message_ids",
        ),
        ({"conversation_public_id": "cv_100"}, "conversation_public_id and message_ids required"),
    ],
)
async def test_visitor_messages_delivered_rejects_invalid_batches(payload, error):
    rt = _RealtimeHarness(session={
        "tenant_id": 1,
        "channel_id": 2,
        "visitor_external_id": "visitor-1",
    })
    visitor_handlers.register_visitor_handlers(rt)

    response = await rt.handlers[("/visitor", "messages_delivered")]("sid-1", payload)

    assert response == {"ok": False, "error": error}
    rt.emit.assert_not_awaited()


class _DeadlockDetectedError(Exception):
    sqlstate = "40P01"


@pytest.mark.asyncio
async def test_visitor_messages_delivered_retries_deadlock_then_succeeds(monkeypatch):
    db = SimpleNamespace()
    session = {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"}
    rt = _RealtimeHarness(session=session)
    delivery_result = {
        "tenant_id": 1,
        "conversation_id": 100,
        "conversation_public_id": "cv_100",
        "message_ids": [201],
        "recipient_agent_ids": [9],
    }
    mark_delivered = AsyncMock(
        side_effect=[_DeadlockDetectedError("deadlock detected"), delivery_result],
    )
    monkeypatch.setattr("app.db.retry.asyncio.sleep", AsyncMock())
    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "mark_agent_messages_visitor_delivered_for_session",
        mark_delivered,
    )

    visitor_handlers.register_visitor_handlers(rt)
    response = await rt.handlers[("/visitor", "messages_delivered")](
        "sid-1",
        {"conversation_public_id": "cv_100", "message_ids": [201]},
    )

    assert response == {"ok": True, "message_ids": [201]}
    assert mark_delivered.await_count == 2
    assert rt.emit.await_count == 2


@pytest.mark.asyncio
async def test_visitor_messages_delivered_returns_internal_instead_of_raising(monkeypatch):
    db = SimpleNamespace()
    session = {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"}
    rt = _RealtimeHarness(session=session)
    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "mark_agent_messages_visitor_delivered_for_session",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    visitor_handlers.register_visitor_handlers(rt)
    response = await rt.handlers[("/visitor", "messages_delivered")](
        "sid-1",
        {"conversation_public_id": "cv_100", "message_ids": [201]},
    )

    assert response == {"ok": False, "error": "INTERNAL"}
    rt.emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_visitor_mark_read_returns_internal_instead_of_raising(monkeypatch):
    db = SimpleNamespace()
    session = {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"}
    rt = _RealtimeHarness(session=session)
    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "mark_agent_messages_visitor_read_for_session",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    visitor_handlers.register_visitor_handlers(rt)
    response = await rt.handlers[("/visitor", "mark_read")](
        "sid-1",
        {"conversation_public_id": "cv_100"},
    )

    assert response == {"ok": False, "error": "INTERNAL"}
    rt.emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_visitor_handoff_success_notifies_visitor_and_assigned_agent(monkeypatch):
    db = SimpleNamespace()
    redis = SimpleNamespace()
    session = {
        "tenant_id": 1,
        "channel_id": 2,
        "visitor_external_id": "visitor-1",
    }
    rt = _RealtimeHarness(session=session)
    visitor = SimpleNamespace(id=7, public_id="usr_7", name="Visitor", avatar_color="#123456")
    agent = SimpleNamespace(id=9, display_name="Agent", name="agent", avatar="avatar.png")
    conversation = SimpleNamespace(
        id=100,
        public_id="cv_100",
        tenant_id=1,
        channel_id=2,
        visitor=visitor,
        agent=agent,
        agent_id=9,
        status="active",
        unread_count=0,
    )
    message_payload = {
        "id": 301,
        "conversation_public_id": "cv_100",
        "sender_type": "system",
        "content_type": "system",
        "content": "已为您转接人工客服",
        "created_at": "2026-06-26T14:00:00+00:00",
    }
    request_handoff = AsyncMock(return_value={
        "ok": True,
        "reason": "assigned",
        "conversation": conversation,
        "messages": [message_payload],
    })
    emit_list_updated = AsyncMock()

    monkeypatch.setattr(visitor_handlers, "AsyncSessionLocal", lambda: _SessionContext(db))
    monkeypatch.setattr(visitor_handlers, "redis_client", SimpleNamespace(client=redis))
    monkeypatch.setattr(
        visitor_handlers.ConversationService,
        "request_human_handoff_for_session",
        request_handoff,
    )
    monkeypatch.setattr(
        visitor_handlers.ConversationAgentDisplaySettingService,
        "get_display_mode",
        AsyncMock(return_value="name"),
    )
    monkeypatch.setattr(
        visitor_handlers.ConversationRepository,
        "increment_unread",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        visitor_handlers.ConversationRealtimeService,
        "emit_conversation_list_updated",
        emit_list_updated,
    )

    visitor_handlers.register_visitor_handlers(rt)

    response = await rt.handlers[("/visitor", "request_human_handoff")](
        "sid-1",
        {"conversation_public_id": "cv_100", "handoff_trigger": "visitor"},
    )

    assert response["ok"] is True
    assert response["status"] == "active"
    assert response["agent"]["name"] == "Agent"
    request_handoff.assert_awaited_once_with(
        db,
        redis,
        conversation_public_id="cv_100",
        visitor_context=session,
        handoff_payload=None,
        handoff_trigger="visitor",
        tool_call_id=None,
    )
    visitor_handlers.ConversationRepository.increment_unread.assert_awaited_once_with(db, 100)
    rt.emit.assert_any_await(
        "conversation_assigned",
        {
            "conversation_id": 100,
            "conversation_public_id": "cv_100",
            "agent": {"id": 9, "name": "Agent", "avatar": "avatar.png"},
        },
        room="conv:100",
        namespace="/visitor",
    )
    rt.emit.assert_any_await(
        "new_conversation",
        {
            "conversation_id": 100,
            "visitor": {
                "id": 7,
                "public_id": "usr_7",
                "name": "Visitor",
                "avatar_color": "#123456",
            },
            "channel": {"id": 2},
        },
        room="agent:1:9",
        namespace="/chat",
    )
    emit_list_updated.assert_awaited_once_with(1, action="assigned", conversation_id=100, rt=rt)
