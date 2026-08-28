"""Realtime delivery tests for visitor language detection updates."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.repositories.conversation_collaboration_repository import (
    ConversationCollaborationRepository,
)
from app.schemas.conversation_translation import ConversationTranslationSettingsResponse
from app.services.conversation_translation_service import VisitorMessageTranslationResult
from app.socketio import visitor_handlers


class _SessionContext:
    def __init__(self, db: object):
        self.db = db

    async def __aenter__(self) -> object:
        return self.db

    async def __aexit__(self, *_exc_info: object) -> bool:
        return False


@pytest.mark.asyncio
async def test_detected_language_update_is_emitted_without_message_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation = SimpleNamespace(id=12, agent_id=9)
    settings_update = ConversationTranslationSettingsResponse(
        global_enabled=True,
        visitor_language="en",
        visitor_language_source="detected",
        visitor_translation_enabled=False,
        agent_translation_enabled=True,
        agent_language="zh",
    )
    process = AsyncMock(
        return_value=VisitorMessageTranslationResult(
            conversation=conversation,
            settings_update=settings_update,
        )
    )
    collaborators = AsyncMock(return_value=[10])
    realtime = SimpleNamespace(emit=AsyncMock())

    monkeypatch.setattr(
        visitor_handlers,
        "AsyncSessionLocal",
        lambda: _SessionContext(SimpleNamespace()),
    )
    monkeypatch.setattr(
        visitor_handlers.ConversationTranslationService,
        "process_visitor_message_managed",
        process,
    )
    monkeypatch.setattr(
        ConversationCollaborationRepository,
        "get_active_collaborator_agent_ids",
        collaborators,
    )

    await visitor_handlers._process_visitor_translation(
        realtime,
        tenant_id=3,
        message_id=44,
    )

    expected_payload = {
        "conversation_id": 12,
        "settings": settings_update.model_dump(mode="json"),
    }
    assert realtime.emit.await_count == 3
    realtime.emit.assert_any_await(
        "translation_settings_updated",
        expected_payload,
        room="agent:3:9",
        namespace="/chat",
    )
    realtime.emit.assert_any_await(
        "translation_settings_updated",
        expected_payload,
        room="agent:3:10",
        namespace="/chat",
    )
    realtime.emit.assert_any_await(
        "translation_settings_updated",
        expected_payload,
        room="conv:12",
        namespace="/chat",
    )


@pytest.mark.asyncio
async def test_pending_message_update_is_emitted_before_translation_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation = SimpleNamespace(id=12, agent_id=9)
    pending_payload = {
        "id": 44,
        "metadata": {"translation": {"status": "pending"}},
    }
    translated_payload = {
        "id": 44,
        "metadata": {"translation": {"status": "translated"}},
    }

    async def process(**kwargs):
        await kwargs["on_pending"](
            VisitorMessageTranslationResult(
                conversation=conversation,
                message_payload=pending_payload,
            )
        )
        return VisitorMessageTranslationResult(
            conversation=conversation,
            message_payload=translated_payload,
        )

    realtime = SimpleNamespace(emit=AsyncMock())
    monkeypatch.setattr(
        visitor_handlers,
        "AsyncSessionLocal",
        lambda: _SessionContext(SimpleNamespace()),
    )
    monkeypatch.setattr(
        visitor_handlers.ConversationTranslationService,
        "process_visitor_message_managed",
        process,
    )
    monkeypatch.setattr(
        ConversationCollaborationRepository,
        "get_active_collaborator_agent_ids",
        AsyncMock(return_value=[]),
    )

    await visitor_handlers._process_visitor_translation(
        realtime,
        tenant_id=3,
        message_id=44,
    )

    statuses = [
        call.args[1]["metadata"]["translation"]["status"]
        for call in realtime.emit.await_args_list
        if call.args[0] == "message_updated"
    ]
    assert statuses == ["pending", "pending", "translated", "translated"]
