"""
Unit tests for workspace conversation pinning.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ValidationError
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_service import ConversationService


def _principal() -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=10,
        tenant_id=1,
        permissions=["chat.workspace.use"],
        data_scopes={},
        group_ids=[],
    )


def _conversation(status: str = "active"):
    now = datetime(2026, 6, 28, 8, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=100,
        public_id="cv_pin",
        share_code="CV-PIN",
        tenant_id=1,
        visitor=SimpleNamespace(id=200, name="Visitor"),
        visitor_id=200,
        agent=None,
        agent_id=10,
        channel=None,
        group=None,
        group_id=None,
        status=status,
        started_at=now,
        ended_at=None,
        ended_by=None,
        last_message_at=now,
        last_message_preview="hello",
        unread_count=0,
        created_at=now,
    )


def test_workspace_conversation_item_includes_pin_fields():
    pinned_at = datetime(2026, 6, 28, 9, 0, tzinfo=timezone.utc)

    pinned = ConversationService._workspace_conversation_item(
        _conversation(),
        viewer_relation="own",
        pinned_at=pinned_at,
    )
    plain = ConversationService._workspace_conversation_item(
        _conversation(),
        viewer_relation="own",
    )

    assert pinned["is_pinned"] is True
    assert pinned["pinned_at"] == pinned_at
    assert plain["is_pinned"] is False
    assert plain["pinned_at"] is None


@pytest.mark.asyncio
async def test_pin_agent_conversation_upserts_current_agent_pin(monkeypatch):
    db = AsyncMock()
    conversation = _conversation()
    principal = _principal()
    returned = {"id": conversation.id, "is_pinned": True}
    upsert = AsyncMock()

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        ConversationService,
        "_assert_conversation_view_access",
        AsyncMock(return_value="own"),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationPinRepository.upsert",
        upsert,
    )
    monkeypatch.setattr(
        ConversationService,
        "get_agent_conversation",
        AsyncMock(return_value=returned),
    )

    result = await ConversationService.pin_agent_conversation(
        db,
        conversation_id=conversation.id,
        principal=principal,
    )

    assert result == returned
    upsert.assert_awaited_once()
    kwargs = upsert.await_args.kwargs
    assert kwargs["tenant_id"] == principal.tenant_id
    assert kwargs["agent_id"] == principal.user_id
    assert kwargs["conversation_id"] == conversation.id
    assert kwargs["pinned_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_unpin_agent_conversation_deletes_current_agent_pin(monkeypatch):
    db = AsyncMock()
    conversation = _conversation()
    principal = _principal()
    returned = {"id": conversation.id, "is_pinned": False}
    delete = AsyncMock(return_value=True)

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        ConversationService,
        "_assert_conversation_view_access",
        AsyncMock(return_value="own"),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationPinRepository.delete",
        delete,
    )
    monkeypatch.setattr(
        ConversationService,
        "get_agent_conversation",
        AsyncMock(return_value=returned),
    )

    result = await ConversationService.unpin_agent_conversation(
        db,
        conversation_id=conversation.id,
        principal=principal,
    )

    assert result == returned
    delete.assert_awaited_once_with(
        db,
        tenant_id=principal.tenant_id,
        agent_id=principal.user_id,
        conversation_id=conversation.id,
    )


@pytest.mark.asyncio
async def test_pin_agent_conversation_rejects_closed_conversation(monkeypatch):
    db = AsyncMock()
    conversation = _conversation(status="closed")
    upsert = AsyncMock()

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        ConversationService,
        "_assert_conversation_view_access",
        AsyncMock(return_value="own"),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationPinRepository.upsert",
        upsert,
    )

    with pytest.raises(ValidationError):
        await ConversationService.pin_agent_conversation(
            db,
            conversation_id=conversation.id,
            principal=_principal(),
        )

    upsert.assert_not_awaited()
