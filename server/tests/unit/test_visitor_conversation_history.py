"""
Unit tests for visitor conversation history.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, ANY

import pytest

from app.services.conversation_service import ConversationService
from app.core.exceptions import BusinessError, ForbiddenError, ValidationError
from app.schemas.open_agent_settings import OpenAgentWelcomeMessage
from app.schemas.permission import EffectivePrincipal


def _dt(day: int) -> datetime:
    return datetime(2026, 5, day, 8, 0, tzinfo=timezone.utc)


def _workspace_conversation(
    *,
    conversation_id: int = 3,
    agent_id: int = 30,
    status: str = "closed",
):
    channel = SimpleNamespace(id=5, tenant_id=10, name="官网", channel_type="web")
    visitor = SimpleNamespace(
        id=20,
        public_id="usr_20",
        external_id="visitor-1",
        name="访客",
        avatar_color="#4A8C5C",
    )
    agent = SimpleNamespace(id=agent_id, display_name="Alice", name="alice", avatar="avatar.png")
    return SimpleNamespace(
        id=conversation_id,
        public_id=f"cv_{conversation_id}",
        share_code=f"CV-{conversation_id}",
        tenant_id=10,
        visitor=visitor,
        visitor_id=visitor.id,
        agent=agent,
        agent_id=agent_id,
        channel=channel,
        channel_id=channel.id,
        group=SimpleNamespace(id=8, name="Support"),
        group_id=8,
        status=status,
        started_at=_dt(3),
        ended_at=_dt(3) if status == "closed" else None,
        ended_by="agent" if status == "closed" else None,
        last_message_at=_dt(3),
        last_message_preview="hello",
        unread_count=0,
        created_at=_dt(3),
    )


def _principal() -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=30,
        tenant_id=10,
        permissions=["chat.workspace.use"],
        data_scopes={"session_record": "self"},
        group_ids=[8],
    )


def test_visitor_agent_display_name_prefers_nickname():
    agent = SimpleNamespace(nickname="小艾", name="张三")
    assert ConversationService.visitor_agent_display_name(agent) == "小艾"


def test_visitor_agent_display_name_falls_back_to_name():
    agent = SimpleNamespace(nickname=None, name="张三")
    assert ConversationService.visitor_agent_display_name(agent) == "张三"


def test_visitor_visible_messages_hides_agent_only_timeout_events():
    visible_default = SimpleNamespace(id=1, metadata_=None)
    visible_visitor = SimpleNamespace(id=2, metadata_={"visible_to": ["visitor"]})
    hidden_agent = SimpleNamespace(id=3, metadata_={"visible_to": ["agent"]})

    result = ConversationService._visitor_visible_messages([
        visible_default,
        visible_visitor,
        hidden_agent,
    ])

    assert [message.id for message in result] == [1, 2]


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
        channel=SimpleNamespace(channel_type="web"),
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
async def test_create_from_visitor_persists_routed_group_before_reenqueue(monkeypatch):
    db = AsyncMock()
    r = AsyncMock()
    visitor = SimpleNamespace(id=20, name="访客", external_id="visitor-1")
    existing = SimpleNamespace(
        id=30,
        tenant_id=10,
        channel_id=5,
        channel=SimpleNamespace(channel_type="web"),
        visitor=visitor,
        visitor_id=visitor.id,
        status="queued",
        agent_id=None,
        group_id=None,
    )
    enqueue_result = SimpleNamespace(position=SimpleNamespace(position_overall=1))

    async def persist_group(_db, conversation, group_id):
        conversation.group_id = group_id
        return conversation

    update_group = AsyncMock(side_effect=persist_group)
    enqueue = AsyncMock(return_value=enqueue_result)

    monkeypatch.setattr(
        "app.services.conversation_service.UserRepository.get_or_create",
        AsyncMock(return_value=(visitor, False)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_active_visitor_conversation",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.RoutingService.route_conversation_with_meta",
        AsyncMock(return_value=(13, [21, 22], {21: 10, 22: 10}, None)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.AgentStatusService.find_available_agent",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.update_group",
        update_group,
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.QueueWorkspaceService.enqueue_conversation_if_needed",
        enqueue,
    )
    monkeypatch.setattr(
        ConversationService,
        "_sync_web_sdk_context_if_present",
        AsyncMock(return_value=None),
    )

    result = await ConversationService.create_from_visitor(
        db,
        r,
        tenant_id=10,
        channel_id=5,
        visitor_external_id="visitor-1",
    )

    update_group.assert_awaited_once_with(db, existing, 13)
    enqueue.assert_awaited_once_with(
        db,
        10,
        existing,
        source_type="visitor_waiting",
    )
    assert existing.group_id == 13
    assert result["conversation"] is existing
    assert result["queue_position"] == 1


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
        status="active",
        agent_id=11,
        group_id=None,
    )
    system_msg = SimpleNamespace(
        id=100,
        content_type="system",
        content="用户发起了新会话",
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
        "app.services.conversation_service.RoutingService.route_conversation_with_meta",
        AsyncMock(return_value=(None, [11], {11: 5}, None)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.AgentStatusService.find_available_agent",
        AsyncMock(return_value=11),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.AgentStatusService.increment_count",
        AsyncMock(),
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
        "app.services.conversation_service.MessageRepository.has_welcome_message",
        AsyncMock(return_value=False),
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
    assert update_last.await_count == 2
    assert update_last.await_args.args[2] == "Hello there"


@pytest.mark.asyncio
async def test_create_from_visitor_returns_queue_full_when_routing_blocked_by_queue_limit(monkeypatch):
    visitor = SimpleNamespace(id=20, name="访客", external_id="visitor-1")
    channel = SimpleNamespace(
        id=5,
        tenant_id=10,
        channel_type="web",
        config={
            "queue_full_message": "<p>Queue is full</p>",
            "queue_full_show_leave_message_button": True,
            "queue_full_leave_message_button_label": "留言",
        },
    )

    monkeypatch.setattr(
        "app.services.conversation_service.UserRepository.get_or_create",
        AsyncMock(return_value=(visitor, True)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_active_visitor_conversation",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ChannelRepository.get_by_id",
        AsyncMock(return_value=channel),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.check_human_service_gate",
        AsyncMock(return_value={"can_start_conversation": True, "reason": "available"}),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.RoutingService.route_conversation_with_meta",
        AsyncMock(return_value=(None, [], {}, "queue_limit")),
    )
    create_conversation = AsyncMock()

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.create",
        create_conversation,
    )

    result = await ConversationService.create_from_visitor(
        AsyncMock(),
        AsyncMock(),
        tenant_id=10,
        channel_id=5,
        visitor_external_id="visitor-1",
    )

    assert result["queue_full"] is True
    assert result["conversation"] is None
    assert result["availability"]["reason"] == "queue_full"
    assert result["availability"]["queue_full_message"] == "<p>Queue is full</p>"
    create_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_from_visitor_returns_no_assignable_queue_when_routing_has_no_target(monkeypatch):
    visitor = SimpleNamespace(id=20, name="访客", external_id="visitor-1")
    channel = SimpleNamespace(
        id=5,
        tenant_id=10,
        channel_type="web",
        config={},
    )

    monkeypatch.setattr(
        "app.services.conversation_service.UserRepository.get_or_create",
        AsyncMock(return_value=(visitor, True)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_active_visitor_conversation",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ChannelRepository.get_by_id",
        AsyncMock(return_value=channel),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.check_human_service_gate",
        AsyncMock(return_value={"can_start_conversation": True, "reason": "available"}),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.RoutingService.route_conversation_with_meta",
        AsyncMock(return_value=(None, [], {}, "no_candidate")),
    )
    create_conversation = AsyncMock()

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.create",
        create_conversation,
    )

    result = await ConversationService.create_from_visitor(
        AsyncMock(),
        AsyncMock(),
        tenant_id=10,
        channel_id=5,
        visitor_external_id="visitor-1",
    )

    assert result["no_assignable_queue"] is True
    assert result["conversation"] is None
    create_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_from_visitor_returns_no_assignable_queue_when_reenqueue_has_no_group(monkeypatch):
    db = AsyncMock()
    r = AsyncMock()
    visitor = SimpleNamespace(id=20, name="访客", external_id="visitor-1")
    existing = SimpleNamespace(
        id=30,
        tenant_id=10,
        channel_id=5,
        channel=SimpleNamespace(channel_type="web"),
        visitor=visitor,
        visitor_id=visitor.id,
        status="queued",
        agent_id=None,
        group_id=None,
    )
    channel = SimpleNamespace(
        id=5,
        tenant_id=10,
        channel_type="web",
        config={
            "queue_full_message": "<p>Queue is full</p>",
            "queue_full_show_leave_message_button": True,
            "queue_full_leave_message_button_label": "留言",
        },
    )

    monkeypatch.setattr(
        "app.services.conversation_service.UserRepository.get_or_create",
        AsyncMock(return_value=(visitor, False)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_active_visitor_conversation",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.RoutingService.route_conversation_with_meta",
        AsyncMock(return_value=(None, [], {}, "no_candidate")),
    )
    monkeypatch.setattr(
        "app.services.queue_workspace_service.QueueWorkspaceService.enqueue_conversation_if_needed",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        ConversationService,
        "_sync_web_sdk_context_if_present",
        AsyncMock(return_value=None),
    )

    result = await ConversationService.create_from_visitor(
        db,
        r,
        tenant_id=10,
        channel_id=5,
        visitor_external_id="visitor-1",
    )

    assert result["no_assignable_queue"] is True
    assert result["conversation"] is None


@pytest.mark.asyncio
async def test_create_welcome_message_on_agent_assignment_persists_matched_welcome(monkeypatch):
    channel = SimpleNamespace(id=5, tenant_id=10, channel_type="web")
    conversation = SimpleNamespace(
        id=30,
        tenant_id=10,
        channel_id=5,
        channel=channel,
        agent_id=11,
    )
    welcome_msg = SimpleNamespace(
        id=101,
        content_type="welcome",
        content="<p>Hello&nbsp;<strong>there</strong></p>",
        created_at=_dt(2),
    )
    has_welcome = AsyncMock(return_value=False)
    get_by_id = AsyncMock(return_value=conversation)
    create_welcome = AsyncMock(return_value=welcome_msg)
    update_last = AsyncMock()

    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.has_welcome_message",
        has_welcome,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        get_by_id,
    )
    monkeypatch.setattr(
        ConversationService,
        "_create_matched_welcome_message",
        create_welcome,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.update_last_message",
        update_last,
    )

    result = await ConversationService.create_welcome_message_on_agent_assignment(
        AsyncMock(),
        tenant_id=10,
        conversation_id=30,
    )

    assert result is welcome_msg
    has_welcome.assert_awaited_once()
    create_welcome.assert_awaited_once_with(ANY, conversation)
    update_last.assert_awaited_once()
    assert update_last.await_args.args[2] == "Hello there"


@pytest.mark.asyncio
async def test_create_welcome_message_on_agent_assignment_skips_when_welcome_exists(monkeypatch):
    has_welcome = AsyncMock(return_value=True)
    create_welcome = AsyncMock()

    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.has_welcome_message",
        has_welcome,
    )
    monkeypatch.setattr(
        ConversationService,
        "_create_matched_welcome_message",
        create_welcome,
    )

    result = await ConversationService.create_welcome_message_on_agent_assignment(
        AsyncMock(),
        tenant_id=10,
        conversation_id=30,
    )

    assert result is None
    create_welcome.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_from_visitor_persists_open_agent_welcome_after_bot_started(monkeypatch):
    visitor = SimpleNamespace(id=20, name="访客", external_id="visitor-1")
    channel = SimpleNamespace(
        id=5,
        tenant_id=10,
        channel_type="web",
        config={
            "open_agent_enabled": True,
            "open_agent_agent_id": 7,
            "open_agent_agent_name": "小云智能机器人",
        },
    )
    conversation = SimpleNamespace(
        id=30,
        public_id="cv_test",
        tenant_id=10,
        channel_id=5,
        visitor=visitor,
        channel=channel,
        status="bot",
        agent_id=None,
        group_id=None,
    )
    system_msg = SimpleNamespace(
        id=100,
        content_type="system",
        content="智能助手开始接待",
        created_at=_dt(1),
    )
    welcome_msg = SimpleNamespace(
        id=101,
        content_type="bot_welcome",
        content="Hi **there**\n\n[嵌入内容]",
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
        "app.services.conversation_service.ChannelRepository.get_by_id",
        AsyncMock(return_value=channel),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.check_open_agent_bot_availability",
        AsyncMock(return_value={"can_start_conversation": True}),
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
        "app.services.open_agent_settings_service.OpenAgentSettingsService.get_agent_welcome_message",
        AsyncMock(return_value=OpenAgentWelcomeMessage.model_validate({
            "enabled": True,
            "blocks": [
                {"type": "markdown", "content": "Hi **there**"},
                {"type": "embed", "embed_code": "<div>Card</div>", "height": 240},
            ],
        })),
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
    monkeypatch.setattr(
        ConversationService,
        "_sync_web_sdk_context_if_present",
        AsyncMock(return_value=None),
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

    bot_started_data = create_message.await_args_list[0].args[1]
    assert bot_started_data["content_type"] == "system"
    assert bot_started_data["content"] == "智能助手开始接待"

    welcome_data = create_message.await_args_list[1].args[1]
    assert welcome_data["sender_type"] == "system"
    assert welcome_data["content_type"] == "bot_welcome"
    assert welcome_data["content"] == "Hi **there**\n\n[嵌入内容]"
    assert welcome_data["metadata_"]["event_type"] == "open_agent_welcome_message"
    assert welcome_data["metadata_"]["open_agent_agent_name"] == "小云智能机器人"
    assert welcome_data["metadata_"]["open_agent_welcome_blocks"] == [
        {"type": "markdown", "content": "Hi **there**", "embed_code": None, "height": None},
        {"type": "embed", "content": None, "embed_code": "<div>Card</div>", "height": 240},
    ]
    update_last.assert_awaited_once()
    assert update_last.await_args.args[2] == "Hi **there** [嵌入内容]"


@pytest.mark.asyncio
async def test_get_visitor_history_assembles_messages_and_has_more(monkeypatch):
    visitor = SimpleNamespace(id=20, name="访客")
    agent = SimpleNamespace(id=30, display_name="Alice", nickname="小艾", name="alice", avatar="avatar.png")
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
            ),
            SimpleNamespace(
                id=102,
                conversation_id=3,
                sender_type="system",
                sender_id=None,
                content_type="system",
                content="仅坐席可见的超时提醒",
                created_at=_dt(3),
                metadata_={"visible_to": ["agent"]},
            ),
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
    assert result["items"][0]["agent_name"] == "小艾"
    assert result["items"][0]["messages"][0]["sender_name"] == "小艾"
    assert [message["content"] for message in result["items"][0]["messages"]] == ["hello"]
    assert result["items"][1]["messages"][0]["sender_name"] == "访客"
    get_history.assert_awaited_once()
    assert get_history.await_args.kwargs["current_conversation_id"] == 4
    assert get_history.await_args.kwargs["before_id"] == 3
    assert get_messages.await_args.kwargs["include_internal"] is False


@pytest.mark.asyncio
async def test_get_unread_offline_replies_for_session_assembles_customer_unread_items(monkeypatch):
    visitor = SimpleNamespace(id=20, name="访客")
    agent = SimpleNamespace(id=30, display_name="Alice", nickname="小艾", name="alice", avatar="avatar.png")
    older_conversation = SimpleNamespace(
        id=2,
        public_id="cv_2",
        status="closed",
        started_at=_dt(2),
        ended_at=_dt(2),
        last_message_at=_dt(2),
        created_at=_dt(2),
        agent=agent,
        visitor=visitor,
    )
    newer_conversation = SimpleNamespace(
        id=3,
        public_id="cv_3",
        status="active",
        started_at=_dt(3),
        ended_at=None,
        last_message_at=_dt(3),
        created_at=_dt(3),
        agent=agent,
        visitor=visitor,
    )
    newer_row = SimpleNamespace(
        public_id="om_3",
        conversation=newer_conversation,
        visitor=visitor,
        customer_unread_at=_dt(3),
        customer_unread_first_message_id=301,
    )
    older_row = SimpleNamespace(
        public_id="om_2",
        conversation=older_conversation,
        visitor=visitor,
        customer_unread_at=_dt(2),
        customer_unread_first_message_id=201,
    )
    messages_by_conversation = {
        2: [
            SimpleNamespace(
                id=201,
                conversation_id=2,
                sender_type="agent",
                sender_id=30,
                content_type="text",
                content="older reply",
                created_at=_dt(2),
            )
        ],
        3: [
            SimpleNamespace(
                id=301,
                conversation_id=3,
                sender_type="agent",
                sender_id=30,
                content_type="text",
                content="newer reply",
                created_at=_dt(3),
            )
        ],
    }

    list_unread = AsyncMock(return_value=([newer_row, older_row], True))
    monkeypatch.setattr(
        "app.services.conversation_service.OfflineMessageRepository.list_customer_unread_replies",
        list_unread,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.get_recent_by_conversations",
        AsyncMock(return_value=messages_by_conversation),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.EmployeeRepository.get_by_ids",
        AsyncMock(return_value=[agent]),
    )

    result = await ConversationService.get_unread_offline_replies_for_session(
        AsyncMock(),
        visitor_context={
            "tenant_id": 10,
            "channel_id": 5,
            "visitor_external_id": "visitor-1",
        },
    )

    assert result["has_more"] is True
    assert [item["conversation_public_id"] for item in result["items"]] == ["cv_2", "cv_3"]
    assert result["items"][0]["offline_message_public_id"] == "om_2"
    assert result["items"][1]["customer_unread_message_id"] == 301
    assert result["items"][1]["messages"][0]["sender_name"] == "小艾"
    list_unread.assert_awaited_once()
    assert list_unread.await_args.kwargs["tenant_id"] == 10
    assert list_unread.await_args.kwargs["limit"] == 3


@pytest.mark.asyncio
async def test_mark_customer_read_for_session_clears_offline_reply_unread(monkeypatch):
    conversation = SimpleNamespace(id=3, public_id="cv_3")
    get_conversation = AsyncMock(return_value=conversation)
    mark_read = AsyncMock()
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService.get_conversation_for_visitor_session",
        get_conversation,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.OfflineMessageRepository.mark_customer_read_by_conversation",
        mark_read,
    )

    result = await ConversationService.mark_customer_read_for_session(
        AsyncMock(),
        visitor_context={
            "tenant_id": 10,
            "channel_id": 5,
            "visitor_external_id": "visitor-1",
        },
        conversation_public_id="cv_3",
    )

    assert result == {"ok": True}
    get_conversation.assert_awaited_once()
    mark_read.assert_awaited_once()
    assert mark_read.await_args.kwargs["conversation_id"] == 3
    assert mark_read.await_args.kwargs["visitor_external_id"] == "visitor-1"


@pytest.mark.asyncio
async def test_agent_message_marks_offline_reply_customer_unread(monkeypatch):
    conversation = SimpleNamespace(id=3, tenant_id=10, status="active", agent_id=30)
    message = SimpleNamespace(
        id=301,
        conversation_id=3,
        sender_type="agent",
        sender_id=30,
        content_type="text",
        content="reply",
        created_at=_dt(3),
        metadata_={},
    )
    mark_unread = AsyncMock()
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.create",
        AsyncMock(return_value=message),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.update_last_message",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.OfflineMessageRepository.mark_customer_unread_by_conversation",
        mark_unread,
    )

    result = await ConversationService.send_message(
        AsyncMock(),
        conversation_id=3,
        sender_type="agent",
        sender_id=30,
        content_type="text",
        content="reply",
        tenant_id=10,
    )

    assert result is message
    mark_unread.assert_awaited_once()
    assert mark_unread.await_args.kwargs["conversation_id"] == 3
    assert mark_unread.await_args.kwargs["message_id"] == 301


@pytest.mark.asyncio
async def test_send_message_updates_last_message_with_aware_timestamp(monkeypatch):
    conversation = _workspace_conversation(status="active")
    message = SimpleNamespace(
        id=301,
        tenant_id=10,
        conversation_id=3,
        sender_type="agent",
        sender_id=30,
        content_type="text",
        content="reply",
        created_at=_dt(3),
        metadata_={},
    )
    update_last_message = AsyncMock()
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.create",
        AsyncMock(return_value=message),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.update_last_message",
        update_last_message,
    )
    mark_unread = AsyncMock()
    monkeypatch.setattr(
        "app.services.conversation_service.OfflineMessageRepository.mark_customer_unread_by_conversation",
        mark_unread,
    )

    await ConversationService.send_message(
        AsyncMock(),
        conversation_id=3,
        sender_type="agent",
        sender_id=30,
        content_type="text",
        content="reply",
        tenant_id=10,
    )

    timestamp = update_last_message.await_args.args[3]
    assert timestamp.tzinfo is timezone.utc
    assert mark_unread.await_args.kwargs["unread_at"] is timestamp


@pytest.mark.asyncio
async def test_get_public_messages_filters_internal_notes(monkeypatch):
    conversation = SimpleNamespace(id=3, public_id="cv_3")
    get_messages = AsyncMock(return_value={"items": [], "has_more": False})
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService.get_conversation_for_visitor_session",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService.get_messages",
        get_messages,
    )

    await ConversationService.get_public_messages_for_session(
        AsyncMock(),
        conversation_public_id="cv_3",
        visitor_context={
            "tenant_id": 10,
            "channel_id": 5,
            "visitor_external_id": "visitor-1",
        },
    )

    assert get_messages.await_args.kwargs["include_internal"] is False
    assert get_messages.await_args.kwargs["visitor_facing"] is True


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
        q="  question  ",
    )

    assert result["has_more"] is False
    assert result["items"][0]["channel"]["name"] == "官网"
    assert result["items"][0]["agent"]["display_name"] == "Alice"
    assert result["items"][0]["messages"][0]["sender_name"] == "访客"
    get_history.assert_awaited_once()
    assert get_history.await_args.kwargs["channel_id"] is None
    assert get_history.await_args.kwargs["agent_id"] == 30
    assert get_history.await_args.kwargs["keyword"] == "question"


@pytest.mark.asyncio
async def test_get_workspace_visitor_history_rejects_long_keyword(monkeypatch):
    current = _workspace_conversation(conversation_id=4, agent_id=30)
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=current),
    )

    with pytest.raises(ValidationError):
        await ConversationService.get_workspace_visitor_history(
            AsyncMock(),
            conversation_id=4,
            tenant_id=10,
            agent_id=30,
            roles=["agent"],
            q="x" * 101,
        )


@pytest.mark.asyncio
async def test_get_agent_history_conversations_limits_to_recent_closed_items(monkeypatch):
    conversation = _workspace_conversation()
    get_history = AsyncMock(return_value=[conversation])
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_recent_closed_by_agent",
        get_history,
    )

    result = await ConversationService.get_agent_history_conversations(
        AsyncMock(),
        tenant_id=10,
        agent_id=30,
        limit=20,
    )

    assert result["total"] == 1
    assert result["has_more"] is False
    assert result["items"][0]["id"] == conversation.id
    get_history.assert_awaited_once()
    assert get_history.await_args.kwargs["tenant_id"] == 10
    assert get_history.await_args.kwargs["agent_id"] == 30
    assert get_history.await_args.kwargs["limit"] == 21


@pytest.mark.asyncio
async def test_get_agent_history_conversation_rejects_unhandled_conversation(monkeypatch):
    conversation = _workspace_conversation(agent_id=99)
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.has_agent_participated",
        AsyncMock(return_value=False),
    )

    with pytest.raises(ForbiddenError):
        await ConversationService.get_agent_history_conversation(
            AsyncMock(),
            conversation_id=conversation.id,
            tenant_id=10,
            agent_id=30,
        )


@pytest.mark.asyncio
async def test_start_new_from_history_returns_existing_current_agent_conversation(monkeypatch):
    history = _workspace_conversation(conversation_id=3, agent_id=30)
    existing = _workspace_conversation(conversation_id=4, agent_id=30, status="active")
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=history),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.EmployeeRepository.get_by_id",
        AsyncMock(return_value=SimpleNamespace(id=30, max_concurrent=10)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.AgentStatusService.get_status",
        AsyncMock(return_value={"status": "online", "current_count": 1, "max_concurrent": 10}),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ChannelRepository.get_by_id",
        AsyncMock(return_value=history.channel),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_active_visitor_conversation",
        AsyncMock(return_value=existing),
    )

    result = await ConversationService.start_new_from_history(
        AsyncMock(),
        AsyncMock(),
        conversation_id=history.id,
        principal=_principal(),
    )

    assert result["is_new"] is False
    assert result["already_active"] is True
    assert result["conversation"]["id"] == existing.id


@pytest.mark.asyncio
async def test_start_new_from_history_requires_online_agent(monkeypatch):
    history = _workspace_conversation(conversation_id=3, agent_id=30)
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=history),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.EmployeeRepository.get_by_id",
        AsyncMock(return_value=SimpleNamespace(id=30, max_concurrent=10)),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.AgentStatusService.get_status",
        AsyncMock(return_value={"status": "busy", "current_count": 1, "max_concurrent": 10}),
    )

    with pytest.raises(BusinessError):
        await ConversationService.start_new_from_history(
            AsyncMock(),
            AsyncMock(),
            conversation_id=history.id,
            principal=_principal(),
        )
