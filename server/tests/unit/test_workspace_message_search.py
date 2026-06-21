"""
Unit tests for workspace visitor message search.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_service import ConversationService


def _dt(minute: int = 0):
    return datetime(2026, 6, 20, 9, minute, tzinfo=timezone.utc)


def _principal() -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=30,
        tenant_id=10,
        permissions=["chat.workspace.use"],
        data_scopes={"session_record": "group"},
        group_ids=[7],
    )


def _conversation(conversation_id: int = 4, visitor_id: int | None = 20):
    visitor = SimpleNamespace(id=visitor_id, name="访客") if visitor_id is not None else None
    return SimpleNamespace(
        id=conversation_id,
        public_id=f"cv_{conversation_id}",
        share_code=f"CV-{conversation_id}",
        tenant_id=10,
        visitor=visitor,
        visitor_id=visitor_id,
        agent=SimpleNamespace(id=30, display_name="Alice", name="alice", avatar=None),
        agent_id=30,
        channel=SimpleNamespace(id=2, name="官网", channel_type="web"),
        group=SimpleNamespace(id=7, name="默认组"),
        group_id=7,
        status="active",
        started_at=_dt(0),
        ended_at=None,
        ended_by=None,
        last_message_at=_dt(2),
        last_message_preview="hello",
        unread_count=0,
        created_at=_dt(0),
    )


def _message(message_id: int = 100):
    return SimpleNamespace(
        id=message_id,
        tenant_id=10,
        conversation_id=4,
        sender_type="agent",
        sender_id=30,
        content_type="text",
        content="hello keyword",
        metadata_={},
        created_at=_dt(3),
    )


@pytest.mark.asyncio
async def test_search_workspace_visitor_messages_raises_when_conversation_missing(monkeypatch):
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=None),
    )

    with pytest.raises(NotFoundError):
        await ConversationService.search_workspace_visitor_messages(
            AsyncMock(),
            conversation_id=4,
            tenant_id=10,
            principal=_principal(),
        )


@pytest.mark.asyncio
async def test_search_workspace_visitor_messages_returns_empty_without_visitor(monkeypatch):
    current = _conversation(visitor_id=None)
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=current),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.DataScopeService.assert_conversation_access",
        AsyncMock(return_value=None),
    )

    result = await ConversationService.search_workspace_visitor_messages(
        AsyncMock(),
        conversation_id=current.id,
        tenant_id=10,
        principal=_principal(),
    )

    assert result == {"items": [], "total": 0, "has_more": False}


@pytest.mark.asyncio
async def test_search_workspace_visitor_messages_passes_scope_and_builds_items(monkeypatch):
    current = _conversation()
    message = _message()
    search_repo = AsyncMock(return_value=[(message, current)])
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=current),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.DataScopeService.assert_conversation_access",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.DataScopeService.session_history_filters",
        AsyncMock(return_value=(None, "scope-predicate")),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.search_workspace_visitor_messages",
        search_repo,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.EmployeeRepository.get_by_ids",
        AsyncMock(return_value=[current.agent]),
    )

    result = await ConversationService.search_workspace_visitor_messages(
        AsyncMock(),
        conversation_id=current.id,
        tenant_id=10,
        principal=_principal(),
        q="  keyword  ",
        before_id=200,
        limit=30,
    )

    search_repo.assert_awaited_once()
    assert search_repo.await_args.kwargs["tenant_id"] == 10
    assert search_repo.await_args.kwargs["visitor_id"] == current.visitor_id
    assert search_repo.await_args.kwargs["keyword"] == "keyword"
    assert search_repo.await_args.kwargs["before_id"] == 200
    assert search_repo.await_args.kwargs["scope_predicate"] == "scope-predicate"
    assert search_repo.await_args.kwargs["limit"] == 31
    assert result["total"] == 1
    assert result["has_more"] is False
    item = result["items"][0]
    assert item["id"] == message.id
    assert item["sender_name"] == "Alice"
    assert item["conversation"]["share_code"] == current.share_code
    assert item["conversation"]["channel"]["name"] == "官网"


@pytest.mark.asyncio
async def test_search_workspace_visitor_messages_rejects_long_keyword(monkeypatch):
    current = _conversation()
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=current),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.DataScopeService.assert_conversation_access",
        AsyncMock(return_value=None),
    )

    with pytest.raises(ValidationError):
        await ConversationService.search_workspace_visitor_messages(
            AsyncMock(),
            conversation_id=current.id,
            tenant_id=10,
            principal=_principal(),
            q="x" * 101,
        )
