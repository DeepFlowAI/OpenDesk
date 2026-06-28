"""
Unit tests for online chat message quote rules.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ValidationError
from app.enums import ConversationStatus, MessageContentType, MessageSenderType
from app.repositories.message_repository import MessageRepository
from app.services.conversation_service import ConversationService


NOW = datetime(2026, 6, 26, 8, 0, tzinfo=timezone.utc)


def _conversation(*, channel_type: str = "web"):
    return SimpleNamespace(
        id=100,
        tenant_id=1,
        status=ConversationStatus.ACTIVE.value,
        channel=SimpleNamespace(channel_type=channel_type),
        visitor=SimpleNamespace(name="访客"),
    )


def _message(
    *,
    message_id: int = 200,
    conversation_id: int = 100,
    sender_type: str = MessageSenderType.VISITOR.value,
    sender_id: int | None = 10,
    content_type: str = MessageContentType.TEXT.value,
    content: str = "hello",
    metadata: dict | None = None,
    is_recalled: bool = False,
):
    return SimpleNamespace(
        id=message_id,
        tenant_id=1,
        conversation_id=conversation_id,
        sender_type=sender_type,
        sender_id=sender_id,
        content_type=content_type,
        content=content,
        metadata_=metadata or {},
        created_at=NOW,
        is_recalled=is_recalled,
    )


@pytest.mark.asyncio
async def test_build_quote_metadata_strips_rich_text(monkeypatch):
    quoted = _message(
        content_type=MessageContentType.RICH_TEXT.value,
        content="<p>Hello <strong>world</strong></p>",
    )
    monkeypatch.setattr(
        MessageRepository,
        "get_by_id_for_conversation",
        AsyncMock(return_value=quoted),
    )

    payload = await ConversationService._build_quote_metadata(
        AsyncMock(),
        _conversation(),
        quoted_message_id=quoted.id,
        visitor_facing=True,
    )

    assert payload["message_id"] == quoted.id
    assert payload["sender_type"] == MessageSenderType.VISITOR.value
    assert payload["sender_name"] == "访客"
    assert payload["content_type"] == MessageContentType.RICH_TEXT.value
    assert payload["summary"] == "Hello world"


@pytest.mark.asyncio
async def test_build_quote_metadata_rejects_recalled_message(monkeypatch):
    monkeypatch.setattr(
        MessageRepository,
        "get_by_id_for_conversation",
        AsyncMock(return_value=_message(is_recalled=True)),
    )

    with pytest.raises(ValidationError):
        await ConversationService._build_quote_metadata(
            AsyncMock(),
            _conversation(),
            quoted_message_id=200,
            visitor_facing=False,
        )


@pytest.mark.asyncio
async def test_build_quote_metadata_rejects_internal_note(monkeypatch):
    monkeypatch.setattr(
        MessageRepository,
        "get_by_id_for_conversation",
        AsyncMock(return_value=_message(content_type=MessageContentType.INTERNAL_NOTE.value)),
    )

    with pytest.raises(ValidationError):
        await ConversationService._build_quote_metadata(
            AsyncMock(),
            _conversation(),
            quoted_message_id=200,
            visitor_facing=False,
        )


@pytest.mark.asyncio
async def test_mark_message_quotes_recalled_removes_snapshot(monkeypatch):
    quoted_message = _message(
        message_id=300,
        metadata={
            "quote": {
                "schema_version": 1,
                "message_id": 200,
                "summary": "secret",
                "file_name": "secret.pdf",
            }
        },
    )
    db = AsyncMock()
    monkeypatch.setattr(
        MessageRepository,
        "get_messages_quoting_message",
        AsyncMock(return_value=[quoted_message]),
    )

    await ConversationService._mark_message_quotes_recalled(
        db,
        _conversation(),
        recalled_message_id=200,
    )

    quote = quoted_message.metadata_["quote"]
    assert quote["is_recalled"] is True
    assert "summary" not in quote
    assert "file_name" not in quote
    db.commit.assert_awaited_once()
