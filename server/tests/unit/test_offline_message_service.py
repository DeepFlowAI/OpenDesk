from datetime import datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock

import pytest

from app.core.exceptions import BusinessError
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.offline_message import OfflineMessage, OfflineMessageEntry
from app.schemas.permission import EffectivePrincipal
from app.services.offline_message_service import (
    DataScopeService,
    OFFLINE_MESSAGE_CONVERSATION_CREATED_EVENT,
    OFFLINE_MESSAGE_CONVERSATION_CREATED_TEXT,
    OFFLINE_MESSAGE_PROMPT_EVENT,
    OfflineMessageRepository,
    OfflineMessageService,
)
from app.services.offline_message_realtime_service import OfflineMessageRealtimeService


def _principal() -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=10,
        tenant_id=1,
        permissions=["chat.offline_message.view", "chat.queue.assign_self"],
        data_scopes={"offline_message": "group"},
        group_ids=[7],
    )


@pytest.mark.asyncio
async def test_count_for_agent_uses_scope_predicate(monkeypatch):
    db = object()
    principal = _principal()
    predicate = object()
    count_by_tenant = AsyncMock(return_value=3)

    monkeypatch.setattr(DataScopeService, "get_group_peer_employee_ids", AsyncMock(return_value=[20]))
    monkeypatch.setattr(DataScopeService, "build_offline_message_predicate", lambda *_args: predicate)
    monkeypatch.setattr(OfflineMessageRepository, "count_by_tenant", count_by_tenant)

    result = await OfflineMessageService.count_for_agent(db, principal, status="pending")

    assert result == {"total": 3}
    count_by_tenant.assert_awaited_once_with(
        db,
        tenant_id=1,
        status="pending",
        scope_predicate=predicate,
    )


@pytest.mark.asyncio
async def test_offline_message_realtime_message_updates_list_room(monkeypatch):
    emit = AsyncMock()
    row = SimpleNamespace(
        id=12,
        public_id="om_test",
        tenant_id=1,
        status="pending",
        target_group_id=7,
        last_message_at=datetime(2026, 6, 17, 10, 30),
        message_count=2,
    )

    monkeypatch.setattr(
        "app.services.offline_message_realtime_service.get_realtime_transport",
        lambda: SimpleNamespace(emit=emit),
    )

    await OfflineMessageRealtimeService.emit_updated(row, action="message")

    emit.assert_awaited_once_with(
        "offline_list_updated",
        {
            "action": "message",
            "offline_message_id": 12,
            "offline_message_public_id": "om_test",
            "status": "pending",
            "target_group_id": 7,
            "last_message_at": "2026-06-17T10:30:00",
            "message_count": 2,
            "updated_at": ANY,
        },
        room="workspace:1:offline:list",
        namespace="/chat",
    )


@pytest.mark.asyncio
async def test_offline_message_realtime_created_updates_count_and_list_rooms(monkeypatch):
    emit = AsyncMock()
    row = SimpleNamespace(
        id=12,
        public_id="om_test",
        tenant_id=1,
        status="pending",
        target_group_id=7,
        last_message_at=datetime(2026, 6, 17, 10, 30),
        message_count=1,
    )

    monkeypatch.setattr(
        "app.services.offline_message_realtime_service.get_realtime_transport",
        lambda: SimpleNamespace(emit=emit),
    )

    await OfflineMessageRealtimeService.emit_updated(row, action="created")

    assert emit.await_count == 2
    list_call, count_call = emit.await_args_list
    assert list_call.args[0] == "offline_list_updated"
    assert count_call.args[0] == "offline_count_updated"
    assert list_call.args[1]["action"] == "created"
    assert count_call.args[1] == list_call.args[1]
    assert list_call.kwargs == {
        "room": "workspace:1:offline:list",
        "namespace": "/chat",
    }
    assert count_call.kwargs == {
        "room": "workspace:1:offline:count",
        "namespace": "/chat",
    }


@pytest.mark.asyncio
async def test_send_public_message_emits_offline_message_update(monkeypatch):
    def add_message(message):
        message.id = 101

    db = SimpleNamespace(
        add=Mock(side_effect=add_message),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    row = SimpleNamespace(
        id=12,
        public_id="om_test",
        tenant_id=1,
        channel_id=2,
        visitor_external_id="visitor-1",
        status="pending",
        visitor_id=20,
        visitor=SimpleNamespace(name="Visitor"),
        visitor_name="Visitor",
        message_count=1,
    )
    refreshed = SimpleNamespace(
        **{key: value for key, value in row.__dict__.items() if key != "message_count"},
        target_group_id=7,
        last_message_at=datetime(2026, 6, 17, 10, 31),
        message_count=2,
    )
    emit_updated = AsyncMock()

    monkeypatch.setattr(OfflineMessageService, "_get_for_session_for_update", AsyncMock(return_value=row))
    monkeypatch.setattr(
        "app.services.offline_message_service.ConversationService.validate_message_content",
        lambda _content_type, content: content,
    )
    monkeypatch.setattr(OfflineMessageRepository, "get_by_id", AsyncMock(return_value=refreshed))
    monkeypatch.setattr(OfflineMessageRealtimeService, "emit_updated", emit_updated)

    result = await OfflineMessageService.send_public_message(
        db,
        "om_test",
        {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"},
        content_type="text",
        content="hello",
    )

    assert result["id"] == 101
    assert row.last_message_preview == "hello"
    assert row.message_count == 2
    db.add.assert_called_once()
    db.flush.assert_awaited_once()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()
    emit_updated.assert_awaited_once_with(refreshed, action="message")


@pytest.mark.asyncio
async def test_send_public_message_rolls_back_when_locked_message_is_converted(monkeypatch):
    db = SimpleNamespace(
        add=Mock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    row = SimpleNamespace(
        id=12,
        public_id="om_test",
        tenant_id=1,
        channel_id=2,
        visitor_external_id="visitor-1",
        status="converted",
        visitor_id=20,
    )
    emit_updated = AsyncMock()

    monkeypatch.setattr(OfflineMessageService, "_get_for_session_for_update", AsyncMock(return_value=row))
    monkeypatch.setattr(
        "app.services.offline_message_service.ConversationService.validate_message_content",
        lambda _content_type, content: content,
    )
    monkeypatch.setattr(OfflineMessageRealtimeService, "emit_updated", emit_updated)

    with pytest.raises(BusinessError):
        await OfflineMessageService.send_public_message(
            db,
            "om_test",
            {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"},
            content_type="text",
            content="hello",
        )

    db.add.assert_not_called()
    db.flush.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()
    emit_updated.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_or_continue_and_send_for_session_creates_leave_prompt_system_message(monkeypatch):
    created_row = None
    added_entries = []

    def add_object(obj):
        nonlocal created_row
        if isinstance(obj, OfflineMessage):
            obj.id = 12
            created_row = obj
        elif isinstance(obj, OfflineMessageEntry):
            obj.id = 101 + len(added_entries)
            added_entries.append(obj)

    db = SimpleNamespace(
        add=Mock(side_effect=add_object),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    visitor = SimpleNamespace(id=20, name="Visitor")
    emit_updated = AsyncMock()

    monkeypatch.setattr(
        OfflineMessageService,
        "_prepare_leave_message_session",
        AsyncMock(return_value=(1, 2, "visitor-1", visitor, 7, {}, "<p>请留言&nbsp;联系方式</p>")),
    )
    monkeypatch.setattr(OfflineMessageRepository, "get_pending_by_visitor_for_update", AsyncMock(return_value=None))
    monkeypatch.setattr(OfflineMessageRepository, "generate_unique_public_id", AsyncMock(return_value="om_test"))
    monkeypatch.setattr(
        "app.services.offline_message_service.ConversationService.validate_message_content",
        lambda _content_type, content: content,
    )
    monkeypatch.setattr(
        "app.services.offline_message_service.ConversationService.build_message_preview",
        lambda _content_type, content: content,
    )
    monkeypatch.setattr(OfflineMessageRepository, "get_by_id", AsyncMock(side_effect=lambda _db, _id: created_row))
    monkeypatch.setattr(OfflineMessageRealtimeService, "emit_updated", emit_updated)

    result = await OfflineMessageService.create_or_continue_and_send_for_session(
        db,
        object(),
        {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"},
        content_type="text",
        content="hello",
    )

    assert len(added_entries) == 2
    prompt, visitor_message = added_entries
    assert prompt.sender_type == "system"
    assert prompt.content_type == "system"
    assert prompt.content == "请留言 联系方式"
    assert prompt.metadata_["offline_message_event"] == OFFLINE_MESSAGE_PROMPT_EVENT
    assert visitor_message.sender_type == "visitor"
    assert visitor_message.content == "hello"
    assert created_row.message_count == 2
    assert created_row.last_message_preview == "hello"
    assert result["message"]["id"] == visitor_message.id
    assert [message["id"] for message in result["messages"]] == [prompt.id, visitor_message.id]
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()
    emit_updated.assert_awaited_once_with(created_row, action="created")


@pytest.mark.asyncio
async def test_create_conversation_appends_created_event_after_offline_messages(monkeypatch):
    created_conversation = None
    added_messages = []

    def add_object(obj):
        nonlocal created_conversation
        if isinstance(obj, Conversation):
            obj.id = 21
            obj.agent = None
            created_conversation = obj
        elif isinstance(obj, Message):
            obj.id = 1001 + len(added_messages)
            added_messages.append(obj)

    db = SimpleNamespace(
        add=Mock(side_effect=add_object),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    entry_prompt = SimpleNamespace(
        id=1,
        sender_type="system",
        sender_id=None,
        content_type="system",
        content="请留言",
        metadata_={"offline_message_event": OFFLINE_MESSAGE_PROMPT_EVENT},
        created_at=datetime(2026, 6, 18, 22, 0),
    )
    entry_visitor = SimpleNamespace(
        id=2,
        sender_type="visitor",
        sender_id=20,
        content_type="text",
        content="34324",
        metadata_={"offline_message_public_id": "om_test"},
        created_at=datetime(2026, 6, 18, 22, 7),
    )
    row = SimpleNamespace(
        id=12,
        public_id="om_test",
        tenant_id=1,
        status="pending",
        visitor=SimpleNamespace(name="Visitor"),
        channel=SimpleNamespace(id=2),
        target_group=SimpleNamespace(id=7),
        conversation=None,
        visitor_id=20,
        visitor_external_id="visitor-1",
        visitor_name="Visitor",
        channel_id=2,
        target_group_id=7,
        handled_by_id=None,
        handled_at=None,
        last_message_at=entry_visitor.created_at,
        last_message_preview="34324",
        message_count=2,
        metadata_={},
        created_at=datetime(2026, 6, 18, 22, 0),
        updated_at=datetime(2026, 6, 18, 22, 7),
        messages=[entry_prompt, entry_visitor],
    )
    principal = _principal()

    async def refresh_row(_db, _offline_message_id):
        row.conversation = created_conversation
        return row

    monkeypatch.setattr(OfflineMessageService, "_assert_view_access", AsyncMock())
    monkeypatch.setattr(OfflineMessageRepository, "get_by_id_for_update", AsyncMock(return_value=row))
    monkeypatch.setattr(OfflineMessageRepository, "get_by_id", AsyncMock(side_effect=refresh_row))
    monkeypatch.setattr(
        "app.services.offline_message_service.ConversationRepository.generate_unique_public_id",
        AsyncMock(return_value="conv_test"),
    )
    monkeypatch.setattr(
        "app.services.offline_message_service.ConversationRepository.generate_unique_share_code",
        AsyncMock(return_value="share_test"),
    )
    monkeypatch.setattr(
        "app.services.offline_message_service.ConversationRepository.get_by_id",
        AsyncMock(side_effect=lambda _db, _conversation_id: created_conversation),
    )
    monkeypatch.setattr(
        "app.services.offline_message_service.AgentStatusService.increment_count",
        AsyncMock(),
    )
    monkeypatch.setattr(OfflineMessageRealtimeService, "emit_updated", AsyncMock())
    monkeypatch.setattr(
        "app.services.offline_message_service.EmployeeRepository.get_by_id",
        AsyncMock(return_value=None),
    )

    result = await OfflineMessageService.create_conversation(db, object(), principal, row.id)

    assert [message.content for message in added_messages] == [
        "请留言",
        "34324",
        OFFLINE_MESSAGE_CONVERSATION_CREATED_TEXT,
    ]
    assert added_messages[0].metadata_["offline_message_entry_id"] == entry_prompt.id
    assert added_messages[1].metadata_["offline_message_entry_id"] == entry_visitor.id
    assert added_messages[2].metadata_ == {
        "event_type": OFFLINE_MESSAGE_CONVERSATION_CREATED_EVENT,
        "offline_message_public_id": row.public_id,
        "offline_message_id": row.id,
    }
    assert [message["content"] for message in result["messages"]] == [
        "请留言",
        "34324",
        OFFLINE_MESSAGE_CONVERSATION_CREATED_TEXT,
    ]
    assert result["messages"][0]["metadata"]["offline_message_entry_id"] == entry_prompt.id
    assert result["messages"][1]["metadata"]["offline_message_entry_id"] == entry_visitor.id
    assert result["messages"][2]["event_type"] == OFFLINE_MESSAGE_CONVERSATION_CREATED_EVENT
    assert created_conversation.last_message_preview == OFFLINE_MESSAGE_CONVERSATION_CREATED_TEXT
    assert created_conversation.last_message_at == added_messages[-1].created_at
    assert row.status == "converted"
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_or_continue_and_send_file_for_session_locks_existing_pending_message(monkeypatch):
    def add_message(message):
        message.id = 102

    db = SimpleNamespace(
        add=Mock(side_effect=add_message),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    visitor = SimpleNamespace(id=20, name="Visitor")
    row = SimpleNamespace(
        id=12,
        public_id="om_test",
        tenant_id=1,
        channel_id=2,
        visitor_external_id="visitor-1",
        status="pending",
        visitor_id=visitor.id,
        visitor=visitor,
        visitor_name=visitor.name,
        message_count=1,
    )
    refreshed = SimpleNamespace(
        **{key: value for key, value in row.__dict__.items() if key != "message_count"},
        target_group_id=7,
        last_message_at=datetime(2026, 6, 17, 10, 32),
        message_count=2,
    )
    locked_lookup = AsyncMock(return_value=row)
    unlocked_lookup = AsyncMock(return_value=None)
    emit_updated = AsyncMock()

    monkeypatch.setattr(
        OfflineMessageService,
        "_prepare_leave_message_session",
        AsyncMock(return_value=(1, 2, "visitor-1", visitor, 7, {}, "请留言")),
    )
    monkeypatch.setattr(OfflineMessageRepository, "get_pending_by_visitor_for_update", locked_lookup)
    monkeypatch.setattr(OfflineMessageRepository, "get_pending_by_visitor", unlocked_lookup)
    monkeypatch.setattr(
        OfflineMessageService,
        "_upload_file",
        AsyncMock(return_value={
            "schema_version": 1,
            "file_id": "file_test",
            "name": "a.pdf",
            "size": 12,
            "mime_type": "application/pdf",
        }),
    )
    monkeypatch.setattr(
        "app.services.offline_message_service.ConversationService.validate_message_content",
        lambda _content_type, content: content,
    )
    monkeypatch.setattr(OfflineMessageRepository, "get_by_id", AsyncMock(return_value=refreshed))
    monkeypatch.setattr(OfflineMessageRealtimeService, "emit_updated", emit_updated)

    result = await OfflineMessageService.create_or_continue_and_send_file_for_session(
        db,
        object(),
        {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"},
        object(),
    )

    assert result["message"]["id"] == 102
    locked_lookup.assert_awaited_once_with(
        db,
        tenant_id=1,
        channel_id=2,
        visitor_external_id="visitor-1",
    )
    unlocked_lookup.assert_not_awaited()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()
    emit_updated.assert_awaited_once_with(refreshed, action="message")
