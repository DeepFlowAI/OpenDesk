"""Unit tests for bot handoff unavailable routes (leave message / queue full)."""
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import BusinessError
from app.enums import ConversationStatus
from app.services.conversation_service import ConversationService


@dataclass
class FakeConversation:
    id: int = 101
    public_id: str = "cv_handoff"
    tenant_id: int = 1
    channel_id: int = 10
    visitor_id: int = 11
    group_id: int | None = None
    agent_id: int | None = None
    status: str = ConversationStatus.BOT.value
    open_agent_handoff_state: str | None = None
    open_agent_handoff_payload: dict = field(default_factory=dict)
    agent: object | None = None
    visitor: object = field(default_factory=lambda: SimpleNamespace(id=11))


@pytest.mark.asyncio
async def test_handoff_outside_service_hours_returns_leave_message(monkeypatch):
    conversation = FakeConversation()

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_update_handoff_state_if_unassigned(_db, conv, **_kwargs):
        conv.open_agent_handoff_state = "failed"
        conv.status = ConversationStatus.BOT.value
        return conv, True

    availability = {
        "can_start_conversation": False,
        "reason": "outside_service_hours",
        "outside_service_hours_strategy": "leave_message",
        "leave_message_prompt": "请留言",
    }

    monkeypatch.setattr(
        ConversationService,
        "get_conversation_for_visitor_session",
        fake_get_conversation,
    )
    monkeypatch.setattr(
        "app.repositories.conversation_repository.ConversationRepository.update_handoff_state_if_unassigned",
        fake_update_handoff_state_if_unassigned,
    )
    monkeypatch.setattr(
        "app.repositories.conversation_repository.ConversationRepository.get_by_id",
        AsyncMock(side_effect=lambda _db, conv_id: conversation),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.resolve_human_handoff_target",
        AsyncMock(return_value={**availability, "agent_id": None, "group_id": None}),
    )

    result = await ConversationService.request_human_handoff_for_session(
        AsyncMock(),
        AsyncMock(),
        conversation_public_id=conversation.public_id,
        visitor_context={
            "tenant_id": conversation.tenant_id,
            "channel_id": conversation.channel_id,
            "visitor_external_id": "visitor-1",
        },
    )

    assert result["ok"] is False
    assert result["leave_message"] is True
    assert result["availability"]["leave_message_prompt"] == "请留言"
    assert result["reason"] == "outside_service_hours"


@pytest.mark.asyncio
async def test_handoff_queue_limit_returns_queue_full(monkeypatch):
    conversation = FakeConversation()
    channel = SimpleNamespace(
        config={
            "queue_full_message": "<p>Queue full</p>",
            "queue_full_show_leave_message_button": True,
            "queue_full_leave_message_button_label": "留言",
        }
    )

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_update_handoff_state_if_unassigned(_db, conv, **_kwargs):
        conv.open_agent_handoff_state = "requested"
        conv.status = ConversationStatus.HANDOFF_PENDING.value
        return conv, True

    async def fake_update_open_agent_state(_db, conv, _payload):
        return conv

    async def fake_update_status(_db, conv, status):
        conv.status = status
        return conv

    monkeypatch.setattr(
        ConversationService,
        "get_conversation_for_visitor_session",
        fake_get_conversation,
    )
    monkeypatch.setattr(
        "app.repositories.conversation_repository.ConversationRepository.update_handoff_state_if_unassigned",
        fake_update_handoff_state_if_unassigned,
    )
    monkeypatch.setattr(
        "app.repositories.conversation_repository.ConversationRepository.update_open_agent_state",
        fake_update_open_agent_state,
    )
    monkeypatch.setattr(
        "app.repositories.conversation_repository.ConversationRepository.update_status",
        fake_update_status,
    )
    monkeypatch.setattr(
        "app.repositories.conversation_repository.ConversationRepository.get_by_id",
        AsyncMock(side_effect=lambda _db, conv_id: conversation),
    )
    monkeypatch.setattr(
        "app.repositories.channel_repository.ChannelRepository.get_by_id",
        AsyncMock(return_value=channel),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.resolve_human_handoff_target",
        AsyncMock(return_value={
            "can_start_conversation": False,
            "reason": "no_available_agent",
            "agent_id": None,
            "group_id": 3,
        }),
    )

    monkeypatch.setattr(
        "app.services.queue_workspace_service.QueueWorkspaceService.enqueue_conversation_if_needed",
        AsyncMock(side_effect=BusinessError("Queue limit reached", code="QUEUE_LIMIT_REACHED")),
    )

    result = await ConversationService.request_human_handoff_for_session(
        AsyncMock(),
        AsyncMock(),
        conversation_public_id=conversation.public_id,
        visitor_context={
            "tenant_id": conversation.tenant_id,
            "channel_id": conversation.channel_id,
            "visitor_external_id": "visitor-1",
        },
    )

    assert result["ok"] is False
    assert result["queue_full"] is True
    assert result["reason"] == "queue_full"
    assert result["availability"]["queue_full_message"] == "<p>Queue full</p>"
    assert result["availability"]["queue_full_leave_message_button_label"] == "留言"


def test_handoff_unavailable_status_fields():
    from app.services.open_agent_conversation_service import OpenAgentConversationService

    fields = OpenAgentConversationService._handoff_unavailable_status_fields({
        "queue_full": True,
        "availability": {
            "queue_full_message": "Full",
            "queue_full_show_leave_message_button": True,
            "queue_full_leave_message_button_label": "留言",
            "leave_message_prompt": "请留言",
        },
    })

    assert fields["queue_full"] is True
    assert fields["queue_full_message"] == "Full"
    assert fields["leave_message_prompt"] == "请留言"


def test_handoff_unavailable_socket_response_leave_message():
    from app.socketio.visitor_handlers import _handoff_unavailable_socket_response

    payload = _handoff_unavailable_socket_response({
        "leave_message": True,
        "availability": {
            "reason": "outside_service_hours",
            "leave_message_prompt": "请留言",
        },
    })

    assert payload == {
        "ok": False,
        "error": "LEAVE_MESSAGE",
        "reason": "outside_service_hours",
        "leave_message_prompt": "请留言",
    }
