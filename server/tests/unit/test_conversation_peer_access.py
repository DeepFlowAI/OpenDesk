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


def _conversation_with_time(conversation_id: int, agent_id: int, last_message_at: datetime):
    conversation = _conversation(agent_id=agent_id)
    conversation.id = conversation_id
    conversation.public_id = f"cv_{conversation_id}"
    conversation.last_message_at = last_message_at
    conversation.created_at = last_message_at
    conversation.started_at = last_message_at
    return conversation


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
async def test_conversation_view_access_relation_matrix(monkeypatch):
    db = AsyncMock()
    principal = _principal(
        permissions=["chat.conversation.peer.view"],
        data_scope="all",
        user_id=10,
    )
    owner = _conversation(agent_id=10)
    collaborator = _conversation(agent_id=20)
    collaborator.id = 101
    closed_participated = _conversation(agent_id=20)
    closed_participated.id = 102
    closed_participated.status = "closed"
    peer = _conversation(agent_id=30)
    peer.id = 103
    forbidden = _conversation(agent_id=40)
    forbidden.id = 104
    collaborator_ids = {collaborator.id}
    participated_ids = {closed_participated.id}

    async def is_collaborator(_db, *, conversation_id: int, **_kwargs):
        return conversation_id in collaborator_ids

    async def has_participated(_db, *, conversation_id: int, **_kwargs):
        return conversation_id in participated_ids

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationCollaborationRepository.is_active_collaborator",
        AsyncMock(side_effect=is_collaborator),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.has_agent_participated",
        AsyncMock(side_effect=has_participated),
    )
    monkeypatch.setattr(
        "app.services.data_scope_service.EmployeeRepository.get_employee_ids_in_groups",
        AsyncMock(return_value=[30]),
    )

    assert await ConversationService._assert_conversation_view_access(db, principal, owner) == "own"
    assert await ConversationService._assert_conversation_view_access(db, principal, collaborator) == "collaborator"
    assert await ConversationService._assert_conversation_view_access(db, principal, closed_participated) == "own"
    assert await ConversationService._assert_conversation_view_access(db, principal, peer) == "peer"

    no_peer_permission = _principal(permissions=[], data_scope="all", user_id=10)
    with pytest.raises(ForbiddenError):
        await ConversationService._assert_conversation_view_access(db, no_peer_permission, forbidden)


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
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationPinRepository.get_by_conversation_ids",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationCollaborationRepository.get_active_collaborator_agents_by_conversation_ids",
        AsyncMock(return_value={conversation.id: []}),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.VisitorTimeoutCloseStateRepository.get_by_conversation_ids",
        AsyncMock(return_value={}),
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
async def test_my_conversation_list_merges_collaborator_conversations(monkeypatch):
    newer = datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc)
    older = datetime(2026, 6, 16, 8, 0, tzinfo=timezone.utc)
    own = _conversation_with_time(100, 10, older)
    duplicate_own = _conversation_with_time(100, 10, older)
    collaborator = _conversation_with_time(101, 20, newer)
    principal = _principal(permissions=[], user_id=10)

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_active_by_agent",
        AsyncMock(return_value=[own]),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationCollaborationRepository.get_active_conversations_by_agent",
        AsyncMock(return_value=[duplicate_own, collaborator]),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.DataScopeService.session_history_filters",
        AsyncMock(return_value=(None, None)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.get_agent_message_conversation_ids",
        AsyncMock(return_value={collaborator.id}),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationCollaborationRepository.get_active_collaborator_agents_by_conversation_ids",
        AsyncMock(return_value={own.id: [], collaborator.id: []}),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationPinRepository.get_by_conversation_ids",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.VisitorTimeoutCloseStateRepository.get_by_conversation_ids",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_visitor_history",
        AsyncMock(side_effect=[[], [SimpleNamespace(id=1)]]),
    )

    result = await ConversationService.get_agent_conversations(
        AsyncMock(),
        tenant_id=1,
        agent_id=10,
        principal=principal,
        scope="my",
    )

    assert [item["id"] for item in result] == [101, 100]
    assert result[0]["viewer_relation"] == "collaborator"
    assert result[0]["collaborated_by_current_user"] is True
    assert result[1]["viewer_relation"] == "own"
    assert result[1]["has_history_conversations"] is True


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
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationCollaborationRepository.is_active_collaborator",
        AsyncMock(return_value=False),
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
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationCollaborationRepository.is_active_collaborator",
        AsyncMock(return_value=False),
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
