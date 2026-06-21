from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.enums import MessageContentType, MessageSenderType
from app.services.conversation_service import ConversationService


def _message(message_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=message_id,
        conversation_id=100,
        sender_type=MessageSenderType.SYSTEM.value,
        sender_id=None,
        content_type=MessageContentType.SYSTEM.value,
        content=f"message-{message_id}",
        created_at=datetime.now(timezone.utc),
        metadata_={"visible_to": ["visitor"]},
    )


@pytest.mark.asyncio
async def test_get_messages_filters_visibility_before_pagination(monkeypatch):
    captured: dict = {}

    async def get_by_conversation(_db, conversation_id, **kwargs):
        captured["conversation_id"] = conversation_id
        captured.update(kwargs)
        return [_message(1), _message(2), _message(3)]

    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.get_by_conversation",
        get_by_conversation,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.EmployeeRepository.get_by_ids",
        AsyncMock(return_value=[]),
    )

    result = await ConversationService.get_messages(
        AsyncMock(),
        conversation_id=100,
        limit=2,
        visitor_facing=True,
    )

    assert captured["visibility_target"] == "visitor"
    assert captured["limit"] == 3
    assert result["has_more"] is True
    assert [item["id"] for item in result["items"]] == [2, 3]
