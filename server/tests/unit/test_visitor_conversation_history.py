"""
Unit tests for visitor conversation history.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.conversation_service import ConversationService
from app.core.exceptions import ForbiddenError


def _dt(day: int) -> datetime:
    return datetime(2026, 5, day, 8, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_has_visitor_history_returns_false_without_visitor_external_id():
    result = await ConversationService.has_visitor_history(
        AsyncMock(),
        channel_id=1,
        visitor_external_id=None,
    )

    assert result is False


@pytest.mark.asyncio
async def test_get_visitor_history_returns_empty_when_visitor_missing(monkeypatch):
    monkeypatch.setattr(
        "app.services.conversation_service.ChannelRepository.get_by_id",
        AsyncMock(return_value=SimpleNamespace(id=1, tenant_id=10)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.UserRepository.get_by_external_id",
        AsyncMock(return_value=None),
    )

    result = await ConversationService.get_visitor_history(
        AsyncMock(),
        channel_id=1,
        visitor_external_id="visitor-1",
    )

    assert result == {"items": [], "has_more": False}


@pytest.mark.asyncio
async def test_create_from_visitor_resumes_only_same_channel_active_conversation(monkeypatch):
    visitor = SimpleNamespace(id=20, name="访客", external_id="visitor-1")
    existing = SimpleNamespace(
        id=30,
        tenant_id=10,
        channel_id=5,
        visitor=visitor,
        status="active",
        agent_id=99,
    )
    get_active = AsyncMock(return_value=existing)
    monkeypatch.setattr(
        "app.services.conversation_service.UserRepository.get_or_create",
        AsyncMock(return_value=(visitor, False)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_active_visitor_conversation",
        get_active,
    )

    result = await ConversationService.create_from_visitor(
        AsyncMock(),
        AsyncMock(),
        tenant_id=10,
        channel_id=5,
        visitor_external_id="visitor-1",
    )

    assert result["conversation"] is existing
    get_active.assert_awaited_once()
    assert get_active.await_args.kwargs["tenant_id"] == 10
    assert get_active.await_args.kwargs["visitor_id"] == 20
    assert get_active.await_args.kwargs["channel_id"] == 5


@pytest.mark.asyncio
async def test_create_from_visitor_persists_matched_welcome_message(monkeypatch):
    visitor = SimpleNamespace(id=20, name="访客", external_id="visitor-1")
    channel = SimpleNamespace(id=5, tenant_id=10, channel_type="web")
    conversation = SimpleNamespace(
        id=30,
        tenant_id=10,
        channel_id=5,
        visitor=visitor,
        channel=channel,
        status="queued",
        agent_id=None,
    )
    system_msg = SimpleNamespace(
        id=100,
        content_type="system",
        content="等待客服接入...",
        created_at=_dt(1),
    )
    welcome_msg = SimpleNamespace(
        id=101,
        content_type="welcome",
        content="<p>Hello&nbsp;<strong>there</strong></p>",
        created_at=_dt(1),
    )
    create_message = AsyncMock(side_effect=[system_msg, welcome_msg])
    update_last = AsyncMock()

    monkeypatch.setattr(
        "app.services.conversation_service.UserRepository.get_or_create",
        AsyncMock(return_value=(visitor, True)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_active_visitor_conversation",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.check_channel_availability",
        AsyncMock(return_value={"can_start_conversation": True}),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.RoutingService.route_conversation",
        AsyncMock(return_value=(None, [], {})),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.generate_unique_public_id",
        AsyncMock(return_value="cv_test"),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.generate_unique_share_code",
        AsyncMock(return_value="CV-TEST123"),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.create",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.WelcomeMessageRuleService.match_public_welcome_message",
        AsyncMock(return_value={"id": 1, "name": "Welcome", "content": welcome_msg.content}),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.create",
        create_message,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.update_last_message",
        update_last,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )

    result = await ConversationService.create_from_visitor(
        AsyncMock(),
        AsyncMock(),
        tenant_id=10,
        channel_id=5,
        visitor_external_id="visitor-1",
    )

    assert result["is_new"] is True
    assert create_message.await_count == 2
    welcome_data = create_message.await_args_list[1].args[1]
    assert welcome_data["sender_type"] == "system"
    assert welcome_data["content_type"] == "welcome"
    assert welcome_data["content"] == welcome_msg.content
    update_last.assert_awaited_once()
    assert update_last.await_args.args[2] == "Hello there"


@pytest.mark.asyncio
async def test_get_visitor_history_assembles_messages_and_has_more(monkeypatch):
    visitor = SimpleNamespace(id=20, name="访客")
    agent = SimpleNamespace(id=30, display_name="Alice", name="alice", avatar="avatar.png")
    conversations = [
        SimpleNamespace(
            id=3,
            status="closed",
            started_at=_dt(3),
            ended_at=_dt(3),
            last_message_at=_dt(3),
            created_at=_dt(3),
            agent=agent,
        ),
        SimpleNamespace(
            id=2,
            status="closed",
            started_at=_dt(2),
            ended_at=_dt(2),
            last_message_at=_dt(2),
            created_at=_dt(2),
            agent=None,
        ),
        SimpleNamespace(
            id=1,
            status="closed",
            started_at=_dt(1),
            ended_at=_dt(1),
            last_message_at=_dt(1),
            created_at=_dt(1),
            agent=None,
        ),
    ]
    messages_by_conversation = {
        3: [
            SimpleNamespace(
                id=101,
                conversation_id=3,
                sender_type="agent",
                sender_id=30,
                content_type="text",
                content="hello",
                created_at=_dt(3),
            )
        ],
        2: [
            SimpleNamespace(
                id=99,
                conversation_id=2,
                sender_type="visitor",
                sender_id=20,
                content_type="text",
                content="question",
                created_at=_dt(2),
            )
        ],
    }

    get_history = AsyncMock(return_value=conversations)
    get_messages = AsyncMock(return_value=messages_by_conversation)
    get_agents = AsyncMock(return_value=[agent])
    monkeypatch.setattr(
        "app.services.conversation_service.ChannelRepository.get_by_id",
        AsyncMock(return_value=SimpleNamespace(id=1, tenant_id=10)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.UserRepository.get_by_external_id",
        AsyncMock(return_value=visitor),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_visitor_history",
        get_history,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.get_recent_by_conversations",
        get_messages,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.EmployeeRepository.get_by_ids",
        get_agents,
    )

    result = await ConversationService.get_visitor_history(
        AsyncMock(),
        channel_id=1,
        visitor_external_id="visitor-1",
        current_conversation_id=4,
        before_id=3,
        limit=2,
    )

    assert result["has_more"] is True
    assert [item["id"] for item in result["items"]] == [3, 2]
    assert result["items"][0]["agent_name"] == "Alice"
    assert result["items"][0]["messages"][0]["sender_name"] == "Alice"
    assert result["items"][1]["messages"][0]["sender_name"] == "访客"
    get_history.assert_awaited_once()
    assert get_history.await_args.kwargs["current_conversation_id"] == 4
    assert get_history.await_args.kwargs["before_id"] == 3


@pytest.mark.asyncio
async def test_get_workspace_visitor_history_rejects_other_agent(monkeypatch):
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=SimpleNamespace(id=1, tenant_id=10, agent_id=99, visitor=SimpleNamespace(id=20))),
    )

    with pytest.raises(ForbiddenError):
        await ConversationService.get_workspace_visitor_history(
            AsyncMock(),
            conversation_id=1,
            tenant_id=10,
            agent_id=30,
            roles=["agent"],
        )


@pytest.mark.asyncio
async def test_get_workspace_visitor_history_assembles_channel_and_agent(monkeypatch):
    visitor = SimpleNamespace(id=20, name="访客")
    channel = SimpleNamespace(id=5, name="官网", channel_type="web")
    agent = SimpleNamespace(id=30, display_name="Alice", name="alice", avatar="avatar.png")
    current = SimpleNamespace(id=4, tenant_id=10, agent_id=30, visitor=visitor)
    history_conversations = [
        SimpleNamespace(
            id=3,
            status="closed",
            started_at=_dt(3),
            ended_at=_dt(3),
            last_message_at=_dt(3),
            created_at=_dt(3),
            channel=channel,
            agent=agent,
        )
    ]
    messages_by_conversation = {
        3: [
            SimpleNamespace(
                id=101,
                conversation_id=3,
                sender_type="visitor",
                sender_id=20,
                content_type="text",
                content="question",
                created_at=_dt(3),
            )
        ]
    }

    get_history = AsyncMock(return_value=history_conversations)
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=current),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_visitor_history",
        get_history,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.get_recent_by_conversations",
        AsyncMock(return_value=messages_by_conversation),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.EmployeeRepository.get_by_ids",
        AsyncMock(return_value=[]),
    )

    result = await ConversationService.get_workspace_visitor_history(
        AsyncMock(),
        conversation_id=4,
        tenant_id=10,
        agent_id=30,
        roles=["agent"],
    )

    assert result["has_more"] is False
    assert result["items"][0]["channel"]["name"] == "官网"
    assert result["items"][0]["agent"]["display_name"] == "Alice"
    assert result["items"][0]["messages"][0]["sender_name"] == "访客"
    get_history.assert_awaited_once()
    assert get_history.await_args.kwargs["channel_id"] is None
    assert get_history.await_args.kwargs["agent_id"] == 30
