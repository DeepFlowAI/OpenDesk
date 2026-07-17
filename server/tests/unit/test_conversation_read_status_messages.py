"""
Unit tests for conversation message read-status helpers.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.enums import MessageSenderType
from app.schemas.message import MessageResponse
from app.services.conversation_service import ConversationService


def _message(**overrides):
    data = {
        "sender_type": MessageSenderType.AGENT.value,
        "content_type": "text",
        "visitor_online_at_send": None,
        "visitor_delivered_at": None,
        "visitor_read_at": None,
        "agent_read_at": None,
        "metadata_": {},
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_message_read_status_is_side_specific():
    read_at = datetime.now(timezone.utc)

    agent_message = _message(visitor_read_at=read_at)
    visitor_message = _message(
        sender_type=MessageSenderType.VISITOR.value,
        agent_read_at=read_at,
    )

    assert ConversationService._message_read_status(agent_message, visitor_facing=False) == "read"
    assert ConversationService._message_read_status(agent_message, visitor_facing=True) is None
    assert ConversationService._message_read_status(visitor_message, visitor_facing=True) == "read"
    assert ConversationService._message_read_status(visitor_message, visitor_facing=False) is None


def test_message_read_status_skips_open_agent_visitor_messages():
    message = _message(
        sender_type=MessageSenderType.VISITOR.value,
        metadata_={"open_agent": True},
    )

    assert ConversationService._message_read_status(message, visitor_facing=True) is None


def test_message_read_status_skips_non_public_content():
    internal = _message(content_type="internal_note", visitor_read_at=datetime.now(timezone.utc))

    assert ConversationService._message_read_status(internal, visitor_facing=False) is None


@pytest.mark.parametrize("content_type", ["text", "rich_text", "image", "file"])
def test_message_read_status_supports_every_public_content_type(content_type):
    message = _message(
        content_type=content_type,
        visitor_delivered_at=datetime.now(timezone.utc),
    )

    assert ConversationService._message_read_status(message, visitor_facing=False) == "unread"


@pytest.mark.parametrize(
    ("sender_type", "content_type"),
    [
        ("bot", "text"),
        ("system", "system"),
        ("agent", "welcome"),
        ("agent", "bot_welcome"),
        ("agent", "internal_note"),
    ],
)
def test_message_read_status_excludes_non_agent_public_messages(sender_type, content_type):
    message = _message(
        sender_type=sender_type,
        content_type=content_type,
        visitor_online_at_send=True,
        visitor_delivered_at=datetime.now(timezone.utc),
        visitor_read_at=datetime.now(timezone.utc),
    )

    assert ConversationService._message_read_status(message, visitor_facing=False) is None


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"visitor_online_at_send": True}, "sending"),
        ({"visitor_online_at_send": False}, "offline"),
        ({"visitor_online_at_send": False, "visitor_delivered_at": datetime.now(timezone.utc)}, "unread"),
        (
            {
                "visitor_online_at_send": False,
                "visitor_delivered_at": datetime.now(timezone.utc),
                "visitor_read_at": datetime.now(timezone.utc),
            },
            "read",
        ),
        ({"visitor_online_at_send": None}, None),
    ],
)
def test_agent_message_delivery_status_priority(overrides, expected):
    assert ConversationService._message_read_status(_message(**overrides), visitor_facing=False) == expected


@pytest.mark.parametrize("visitor_online_at_send", [True, False, None])
def test_agent_message_read_never_regresses_to_delivery_status(visitor_online_at_send):
    read_at = datetime.now(timezone.utc)
    message = _message(
        visitor_online_at_send=visitor_online_at_send,
        visitor_delivered_at=read_at,
        visitor_read_at=read_at,
    )

    assert ConversationService._message_read_status(message, visitor_facing=False) == "read"


@pytest.mark.parametrize("status", ["sending", "offline", "unread", "read"])
def test_workspace_message_response_accepts_delivery_status(status):
    response = MessageResponse.model_validate({
        "id": 1,
        "conversation_id": 100,
        "sender_type": "agent",
        "sender_id": 9,
        "content_type": "text",
        "content": "hello",
        "created_at": datetime.now(timezone.utc),
        "status": status,
    })

    assert response.status == status


@pytest.mark.asyncio
async def test_mark_read_marks_visitor_messages_with_timezone_aware_timestamp(monkeypatch):
    captured: dict = {}
    conversation = SimpleNamespace(id=100, tenant_id=1)

    async def mark_visitor_messages(_db, *, tenant_id: int, conversation_id: int, read_at: datetime):
        captured["tenant_id"] = tenant_id
        captured["conversation_id"] = conversation_id
        captured["read_at"] = read_at
        return [1, 2]

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.mark_visitor_messages_agent_read",
        mark_visitor_messages,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.reset_unread",
        AsyncMock(),
    )

    result = await ConversationService.mark_read(AsyncMock(), 100)

    assert result == [1, 2]
    assert captured["tenant_id"] == 1
    assert captured["conversation_id"] == 100
    assert captured["read_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_mark_agent_messages_visitor_read_returns_agent_recipients(monkeypatch):
    captured: dict = {}
    conversation = SimpleNamespace(id=100, tenant_id=1, public_id="conv_pub", agent_id=9)

    async def mark_agent_messages(
        _db,
        *,
        tenant_id: int,
        conversation_id: int,
        read_at: datetime,
        before_message_id: int | None = None,
    ):
        captured["tenant_id"] = tenant_id
        captured["conversation_id"] = conversation_id
        captured["read_at"] = read_at
        captured["before_message_id"] = before_message_id
        return [11, 12]

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService.get_conversation_for_visitor_session",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.mark_agent_messages_visitor_read",
        mark_agent_messages,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationCollaborationRepository.get_active_collaborator_agent_ids",
        AsyncMock(return_value=[10, 9]),
    )

    result = await ConversationService.mark_agent_messages_visitor_read_for_session(
        AsyncMock(),
        visitor_context={
            "tenant_id": 1,
            "channel_id": 2,
            "visitor_external_id": "visitor-1",
        },
        conversation_public_id="conv_pub",
    )

    assert result["tenant_id"] == 1
    assert result["conversation_id"] == 100
    assert result["conversation_public_id"] == "conv_pub"
    assert result["message_ids"] == [11, 12]
    assert result["recipient_agent_ids"] == [9, 10]
    assert captured["tenant_id"] == 1
    assert captured["conversation_id"] == 100
    assert captured["read_at"].tzinfo is not None
    assert captured["before_message_id"] is None


@pytest.mark.asyncio
async def test_mark_agent_messages_visitor_read_can_stop_before_new_visitor_message(monkeypatch):
    captured: dict = {}
    conversation = SimpleNamespace(id=100, tenant_id=1, public_id="conv_pub", agent_id=9)

    async def mark_agent_messages(
        _db,
        *,
        tenant_id: int,
        conversation_id: int,
        read_at: datetime,
        before_message_id: int | None = None,
    ):
        captured["tenant_id"] = tenant_id
        captured["conversation_id"] = conversation_id
        captured["read_at"] = read_at
        captured["before_message_id"] = before_message_id
        return [11]

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService.get_conversation_for_visitor_session",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.mark_agent_messages_visitor_read",
        mark_agent_messages,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationCollaborationRepository.get_active_collaborator_agent_ids",
        AsyncMock(return_value=[]),
    )

    result = await ConversationService.mark_agent_messages_visitor_read_for_session(
        AsyncMock(),
        visitor_context={
            "tenant_id": 1,
            "channel_id": 2,
            "visitor_external_id": "visitor-1",
        },
        conversation_public_id="conv_pub",
        before_message_id=301,
    )

    assert result["message_ids"] == [11]
    assert captured["before_message_id"] == 301
    assert captured["read_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_mark_agent_messages_visitor_delivered_returns_changed_ids_and_recipients(monkeypatch):
    conversation = SimpleNamespace(id=100, tenant_id=1, public_id="conv_pub", agent_id=9)
    mark_delivered = AsyncMock(return_value=[11, 12])
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService.get_conversation_for_visitor_session",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.mark_agent_messages_visitor_delivered",
        mark_delivered,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationCollaborationRepository.get_active_collaborator_agent_ids",
        AsyncMock(return_value=[10, 9]),
    )

    result = await ConversationService.mark_agent_messages_visitor_delivered_for_session(
        AsyncMock(),
        visitor_context={"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"},
        conversation_public_id="conv_pub",
        message_ids=[12, 11, 12],
    )

    assert result["message_ids"] == [11, 12]
    assert result["recipient_agent_ids"] == [9, 10]
    assert mark_delivered.await_args.kwargs["message_ids"] == [11, 12]
    assert mark_delivered.await_args.kwargs["delivered_at"].tzinfo is not None
