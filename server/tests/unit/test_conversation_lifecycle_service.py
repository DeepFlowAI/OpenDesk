"""Unit tests for online conversation lifecycle operations."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.enums import ConversationStatus
from app.services.conversation_service import ConversationService


@pytest.mark.asyncio
async def test_end_conversation_closes_and_runs_lifecycle_side_effects(monkeypatch):
    db = SimpleNamespace()
    redis = SimpleNamespace()
    conversation = SimpleNamespace(
        id=100,
        tenant_id=1,
        agent_id=10,
        status=ConversationStatus.ACTIVE.value,
    )
    ended = SimpleNamespace(
        id=100,
        tenant_id=1,
        agent_id=10,
        status=ConversationStatus.CLOSED.value,
    )
    principal = SimpleNamespace(user_id=10, tenant_id=1)
    end_conversation = AsyncMock(return_value=ended)
    create_message = AsyncMock()
    update_last_message = AsyncMock()
    mark_timeout_inactive = AsyncMock()
    decrement_count = AsyncMock()
    trigger_queue_backfill = AsyncMock()
    send_survey_invitation = AsyncMock()
    generate_segment = AsyncMock()

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.end_conversation",
        end_conversation,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.MessageRepository.create",
        create_message,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.update_last_message",
        update_last_message,
    )
    monkeypatch.setattr(
        "app.services.visitor_timeout_close_service.VisitorTimeoutCloseService.mark_inactive",
        mark_timeout_inactive,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.AgentStatusService.decrement_count",
        decrement_count,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.AgentStatusService.trigger_queue_backfill",
        trigger_queue_backfill,
    )
    monkeypatch.setattr(
        "app.services.satisfaction_survey_record_service.SatisfactionSurveyRecordService.send_session_end_invitation",
        send_survey_invitation,
    )
    monkeypatch.setattr(
        "app.services.reception_segment_service.ReceptionSegmentService.generate_for_conversation",
        generate_segment,
    )

    result = await ConversationService.end_conversation(
        db,
        redis,
        conversation_id=100,
        ended_by="agent",
        principal=principal,
    )

    assert result is ended
    end_conversation.assert_awaited_once_with(db, conversation, "agent")
    mark_timeout_inactive.assert_awaited_once_with(db, 100)
    decrement_count.assert_awaited_once_with(redis, 1, 10)
    trigger_queue_backfill.assert_awaited_once_with(redis, 1, 10)
    create_message.assert_awaited_once()
    message_data = create_message.await_args.args[1]
    assert message_data["conversation_id"] == 100
    assert message_data["content"] == "客服已结束会话"
    assert message_data["metadata_"] == {
        "event_type": "conversation_ended",
        "ended_by": "agent",
    }
    update_last_message.assert_awaited_once()
    assert update_last_message.await_args.args[2] == "客服已结束会话"
    send_survey_invitation.assert_awaited_once_with(db, ended)
    generate_segment.assert_awaited_once_with(db, 100)
