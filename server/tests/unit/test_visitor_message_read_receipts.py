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
