from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.configs.settings import settings
from app.enums import ConversationStatus
from app.services.open_agent_bot_timeout_service import (
    OPEN_AGENT_BOT_TIMEOUT_ENDED_BY,
    OpenAgentBotTimeoutService,
)


def _conversation(**overrides):
    data = {
        "id": 100,
        "public_id": "cv_bot",
        "tenant_id": 10,
        "visitor_id": 20,
        "status": ConversationStatus.BOT.value,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _message(**overrides):
    data = {
        "id": 200,
        "created_at": datetime(2026, 6, 23, 8, 0, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_close_if_stale_closes_bot_conversation(monkeypatch):
    monkeypatch.setattr(settings, "OPEN_AGENT_BOT_TIMEOUT_SECONDS", 3600)
    now = datetime(2026, 6, 23, 9, 1, tzinfo=timezone.utc)
    conversation = _conversation()
    latest_bot_activity = _message(created_at=now - timedelta(minutes=61))
    end_conversation = AsyncMock(return_value=_conversation(status=ConversationStatus.CLOSED.value))
    emit_ended = AsyncMock()

    monkeypatch.setattr(
        "app.services.open_agent_bot_timeout_service.MessageRepository.get_latest_open_agent_bot_activity",
        AsyncMock(return_value=latest_bot_activity),
    )
    monkeypatch.setattr(
        "app.services.open_agent_bot_timeout_service.MessageRepository.has_visitor_message_after",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "app.services.open_agent_bot_timeout_service.ConversationRepository.end_conversation",
        end_conversation,
    )
    monkeypatch.setattr(
        OpenAgentBotTimeoutService,
        "_emit_conversation_ended",
        emit_ended,
    )

    result = await OpenAgentBotTimeoutService.close_if_stale(AsyncMock(), conversation, now=now)

    assert result is True
    end_conversation.assert_awaited_once()
    assert end_conversation.await_args.args[2] == OPEN_AGENT_BOT_TIMEOUT_ENDED_BY
    emit_ended.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_if_stale_keeps_conversation_when_visitor_replied(monkeypatch):
    monkeypatch.setattr(settings, "OPEN_AGENT_BOT_TIMEOUT_SECONDS", 3600)
    now = datetime(2026, 6, 23, 9, 1, tzinfo=timezone.utc)
    conversation = _conversation()
    latest_bot_activity = _message(created_at=now - timedelta(minutes=61))
    end_conversation = AsyncMock()

    monkeypatch.setattr(
        "app.services.open_agent_bot_timeout_service.MessageRepository.get_latest_open_agent_bot_activity",
        AsyncMock(return_value=latest_bot_activity),
    )
    monkeypatch.setattr(
        "app.services.open_agent_bot_timeout_service.MessageRepository.has_visitor_message_after",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "app.services.open_agent_bot_timeout_service.ConversationRepository.end_conversation",
        end_conversation,
    )

    result = await OpenAgentBotTimeoutService.close_if_stale(AsyncMock(), conversation, now=now)

    assert result is False
    end_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_expired_conversations_counts_revalidated_skip(monkeypatch):
    now = datetime(2026, 6, 23, 9, 1, tzinfo=timezone.utc)
    conversations = [_conversation(id=1), _conversation(id=2)]

    monkeypatch.setattr(settings, "OPEN_AGENT_BOT_TIMEOUT_SECONDS", 3600)
    monkeypatch.setattr(
        "app.services.open_agent_bot_timeout_service.ConversationRepository.list_stale_open_agent_bot_conversations",
        AsyncMock(return_value=conversations),
    )
    close_if_stale = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(OpenAgentBotTimeoutService, "close_if_stale", close_if_stale)

    result = await OpenAgentBotTimeoutService.process_expired_conversations(
        AsyncMock(),
        now=now,
        limit=10,
    )

    assert result == {"checked": 2, "closed": 1, "skipped": 1}
    assert close_if_stale.await_count == 2
