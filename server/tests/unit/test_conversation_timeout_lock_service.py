from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ForbiddenError, ValidationError
from app.enums import ConversationStatus
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_service import ConversationService


def _principal(**overrides) -> EffectivePrincipal:
    data = {
        "user_id": 20,
        "tenant_id": 1,
        "permissions": ["chat.workspace.use", "chat.conversation.lock"],
    }
    data.update(overrides)
    return EffectivePrincipal(**data)


def _conversation(**overrides):
    data = {
        "id": 100,
        "tenant_id": 1,
        "agent_id": 20,
        "status": ConversationStatus.ACTIVE.value,
        "started_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_lock_agent_conversation_timeout_requires_permission(monkeypatch):
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=_conversation()),
    )

    with pytest.raises(ForbiddenError):
        await ConversationService.lock_agent_conversation_timeout(
            AsyncMock(),
            conversation_id=100,
            principal=_principal(permissions=["chat.workspace.use"]),
        )


@pytest.mark.asyncio
async def test_lock_agent_conversation_timeout_requires_owner(monkeypatch):
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=_conversation(agent_id=21)),
    )

    with pytest.raises(ForbiddenError):
        await ConversationService.lock_agent_conversation_timeout(
            AsyncMock(),
            conversation_id=100,
            principal=_principal(),
        )


@pytest.mark.asyncio
async def test_lock_agent_conversation_timeout_rejects_closed_conversation(monkeypatch):
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=_conversation(status=ConversationStatus.CLOSED.value)),
    )

    with pytest.raises(ValidationError, match="Conversation ended"):
        await ConversationService.lock_agent_conversation_timeout(
            AsyncMock(),
            conversation_id=100,
            principal=_principal(),
        )


@pytest.mark.asyncio
async def test_lock_agent_conversation_timeout_returns_updated_conversation(monkeypatch):
    conversation = _conversation()
    state = SimpleNamespace(
        timeout_locked_at=datetime.now(timezone.utc),
        timeout_locked_by_id=20,
    )
    expected = {
        "id": conversation.id,
        "is_timeout_locked": True,
        "timeout_locked_at": state.timeout_locked_at,
        "timeout_locked_by_id": 20,
    }
    lock_timeout = AsyncMock(return_value=state)

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.visitor_timeout_close_service.VisitorTimeoutCloseService.lock_conversation_timeout",
        lock_timeout,
    )
    monkeypatch.setattr(
        ConversationService,
        "get_agent_conversation",
        AsyncMock(return_value=expected),
    )
    monkeypatch.setattr(
        ConversationService,
        "_emit_timeout_lock_updated",
        AsyncMock(),
    )

    result = await ConversationService.lock_agent_conversation_timeout(
        AsyncMock(),
        conversation_id=100,
        principal=_principal(),
    )

    assert result == expected
    lock_timeout.assert_awaited_once()
