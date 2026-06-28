"""
Unit tests for online chat message recall rules.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import BusinessError, ForbiddenError, ValidationError
from app.enums import ConversationStatus, MessageContentType, MessageSenderType
from app.services.conversation_service import ConversationService


NOW = datetime(2026, 6, 26, 8, 0, tzinfo=timezone.utc)


def _conversation(*, status: str = ConversationStatus.ACTIVE.value, channel_type: str = "web"):
    return SimpleNamespace(
        id=100,
        tenant_id=1,
        status=status,
        channel=SimpleNamespace(channel_type=channel_type),
    )


def _message(
    *,
    sender_type: str = MessageSenderType.AGENT.value,
    sender_id: int | None = 10,
    content_type: str = MessageContentType.TEXT.value,
    content: str = "hello",
    created_at: datetime = NOW - timedelta(seconds=30),
    is_recalled: bool = False,
):
    return SimpleNamespace(
        id=200,
        tenant_id=1,
        conversation_id=100,
        sender_type=sender_type,
        sender_id=sender_id,
        content_type=content_type,
        content=content,
        metadata_={"source": "unit"},
        created_at=created_at,
        visitor_read_at=None,
        agent_read_at=None,
        is_recalled=is_recalled,
        recalled_at=NOW if is_recalled else None,
        recalled_by_type=sender_type if is_recalled else None,
        recalled_by_id=sender_id if is_recalled else None,
        recalled_by_name="Alice" if is_recalled else None,
    )


def test_recall_rules_accept_owner_within_window():
    ConversationService._assert_message_recallable(
        _conversation(),
        _message(),
        actor_type=MessageSenderType.AGENT.value,
        actor_id=10,
        now=NOW,
    )


def test_recall_rules_reject_other_agent_message():
    with pytest.raises(ForbiddenError):
        ConversationService._assert_message_recallable(
            _conversation(),
            _message(sender_id=11),
            actor_type=MessageSenderType.AGENT.value,
            actor_id=10,
            now=NOW,
        )


def test_recall_rules_reject_expired_message():
    with pytest.raises(ValidationError):
        ConversationService._assert_message_recallable(
            _conversation(),
            _message(created_at=NOW - timedelta(minutes=2, seconds=1)),
            actor_type=MessageSenderType.AGENT.value,
            actor_id=10,
            now=NOW,
        )


def test_recall_rules_reject_closed_conversation():
    with pytest.raises(BusinessError):
        ConversationService._assert_message_recallable(
            _conversation(status=ConversationStatus.CLOSED.value),
            _message(),
            actor_type=MessageSenderType.AGENT.value,
            actor_id=10,
            now=NOW,
        )


def test_recalled_payload_redacts_content_for_other_viewers():
    msg = _message(
        content_type=MessageContentType.RICH_TEXT.value,
        content="<p>original</p>",
        is_recalled=True,
    )

    payload = ConversationService._message_response_payload(
        msg,
        conversation_id=100,
        sender_name="Alice",
        viewer_agent_id=99,
    )

    assert payload["content"] == ""
    assert payload["is_recalled"] is True
    assert payload["recalled_by_name"] == "Alice"
    assert payload["metadata"]["is_recalled"] is True
    assert "recall_edit_content" not in payload["metadata"]


def test_recalled_payload_includes_edit_content_for_original_agent():
    msg = _message(
        content_type=MessageContentType.RICH_TEXT.value,
        content="<p>original</p>",
        is_recalled=True,
    )

    payload = ConversationService._message_response_payload(
        msg,
        conversation_id=100,
        sender_name="Alice",
        viewer_agent_id=10,
    )

    assert payload["content"] == ""
    assert payload["metadata"]["recall_edit_content"] == "<p>original</p>"


def test_recalled_message_preview_uses_actor_type():
    assert ConversationService.build_recalled_message_preview(
        _message(sender_type=MessageSenderType.VISITOR.value, sender_id=None, is_recalled=True),
    ) == "访客撤回了一条消息"
    assert ConversationService.build_recalled_message_preview(
        _message(sender_type=MessageSenderType.AGENT.value, is_recalled=True),
    ) == "客服撤回了一条消息"
