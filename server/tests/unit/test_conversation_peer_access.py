"""
Unit tests for peer conversation access and internal notes.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ForbiddenError
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_service import ConversationService


def _conversation(agent_id: int = 20):
    now = datetime(2026, 6, 16, 8, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=100,
        public_id="cv_peer",
        share_code="CV-PEER",
        tenant_id=1,
        visitor=SimpleNamespace(id=200, name="访客"),
        visitor_id=200,
        agent=SimpleNamespace(id=agent_id, display_name="Alice", name="alice", avatar=None),
        agent_id=agent_id,
        channel=None,
        group=None,
        group_id=7,
        status="active",
        started_at=now,
        ended_at=None,
        ended_by=None,
        last_message_at=now,
        last_message_preview="hello",
        unread_count=0,
        created_at=now,
    )


def _principal(
    *,
    permissions: list[str],
    data_scope: str = "group",
    user_id: int = 10,
) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=user_id,
        tenant_id=1,
        permissions=permissions,
        data_scopes={"chat.conversation.peer.view": data_scope},
        group_ids=[7],
    )


@pytest.mark.asyncio
async def test_peer_list_requires_peer_view_permission():
    principal = _principal(permissions=[], data_scope="all")

    with pytest.raises(ForbiddenError):
        await ConversationService.get_agent_conversations(
            AsyncMock(),
            tenant_id=1,
            agent_id=10,
            principal=principal,
            scope="peers",
        )


@pytest.mark.asyncio
async def test_peer_list_rejects_self_data_scope():
    principal = _principal(
        permissions=["chat.conversation.peer.view"],
        data_scope="self",
    )

    with pytest.raises(ForbiddenError):
        await ConversationService.get_agent_conversations(
            AsyncMock(),
            tenant_id=1,
            agent_id=10,
            principal=principal,
            scope="peers",
        )


@pytest.mark.asyncio
async def test_peer_list_returns_collaboration_marker(monkeypatch):
    conversation = _conversation()
    principal = _principal(
        permissions=["chat.conversation.peer.view"],
        data_scope="all",
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_active_peer_conversations",
        AsyncMock(return_value=[conversation]),
    )
    monkeypatch.setattr(
        "app.services.data_scope_service.EmployeeRepository.get_employee_ids_in_groups",
        AsyncMock(return_value=[20]),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.get_agent_message_conversation_ids",
        AsyncMock(return_value={conversation.id}),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_visitor_history",
        AsyncMock(return_value=[]),
    )

    result = await ConversationService.get_agent_conversations(
        AsyncMock(),
        tenant_id=1,
        agent_id=10,
        principal=principal,
        scope="peers",
    )

    assert result[0]["viewer_relation"] == "peer"
    assert result[0]["collaborated_by_current_user"] is True


@pytest.mark.asyncio
async def test_peer_public_message_requires_send_permission(monkeypatch):
    principal = _principal(
        permissions=["chat.conversation.peer.view"],
        data_scope="all",
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=_conversation()),
    )

    with pytest.raises(ForbiddenError):
        await ConversationService.send_message(
            AsyncMock(),
            conversation_id=100,
            sender_type="agent",
            sender_id=10,
            content_type="text",
            content="hello",
            tenant_id=1,
            principal=principal,
        )


@pytest.mark.asyncio
async def test_internal_note_requires_internal_permission(monkeypatch):
    principal = _principal(
        permissions=["chat.conversation.peer.view"],
        data_scope="all",
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=_conversation()),
    )

    with pytest.raises(ForbiddenError):
        await ConversationService.send_message(
            AsyncMock(),
            conversation_id=100,
            sender_type="agent",
            sender_id=10,
            content_type="internal_note",
            content="note",
            tenant_id=1,
            principal=principal,
        )
