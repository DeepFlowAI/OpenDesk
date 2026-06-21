"""
Unit tests for session record service.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.session_record_service import SessionRecordService


def _dt() -> datetime:
    return datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)


def _conversation(**overrides):
    data = {
        "id": 1,
        "public_id": "conv_pub",
        "share_code": "SC001",
        "visitor": None,
        "agent": None,
        "channel": None,
        "group": None,
        "status": "closed",
        "started_at": _dt(),
        "ended_at": _dt(),
        "ended_by": "agent",
        "created_at": _dt(),
        "last_message_preview": None,
        "open_agent_agent_id": None,
        "open_agent_conversation_id": None,
        "open_agent_conversation_external_id": None,
        "open_agent_handoff_state": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.parametrize(
    ("conversation", "session_type", "handoff_status"),
    [
        (_conversation(), "human", None),
        (_conversation(open_agent_agent_id=12), "bot", "not_triggered"),
        (
            _conversation(open_agent_conversation_id=34, open_agent_handoff_state="pending"),
            "bot",
            "waiting_confirmation",
        ),
        (
            _conversation(
                open_agent_conversation_external_id="oa_1",
                open_agent_handoff_state="requested",
            ),
            "bot",
            "handoff_in_progress",
        ),
        (_conversation(open_agent_agent_id=12, open_agent_handoff_state="queued"), "bot", "in_queue"),
        (_conversation(open_agent_agent_id=12, open_agent_handoff_state="success"), "bot_human", "succeeded"),
        (_conversation(open_agent_agent_id=12, open_agent_handoff_state="failed"), "bot", "failed"),
        (_conversation(open_agent_agent_id=12, open_agent_handoff_state="dismissed"), "bot", "dismissed"),
        (_conversation(open_agent_agent_id=12, open_agent_handoff_state="legacy_unknown"), "bot", None),
    ],
)
def test_conversation_to_response_maps_session_type_and_bot_handoff_status(
    conversation,
    session_type,
    handoff_status,
):
    result = SessionRecordService._conversation_to_response(conversation)

    assert result["session_type"] == session_type
    assert result["bot_handoff_status"] == handoff_status


@pytest.mark.asyncio
async def test_get_messages_enriches_bot_sender_name(monkeypatch):
    conversation = SimpleNamespace(
        id=1,
        visitor=None,
        agent=None,
        open_agent_agent_name="Fallback Bot",
    )
    bot_message = SimpleNamespace(
        id=10,
        conversation_id=1,
        sender_type="bot",
        sender_id=None,
        content_type="text",
        content="Hello",
        metadata_={"open_agent_agent_name": "Support Bot"},
        created_at=_dt(),
    )

    monkeypatch.setattr(
        "app.services.session_record_service.SessionRecordRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.session_record_service.SessionRecordRepository.get_messages",
        AsyncMock(return_value=[bot_message]),
    )
    monkeypatch.setattr(
        "app.services.session_record_service.EmployeeRepository.get_by_ids",
        AsyncMock(return_value=[]),
    )

    result = await SessionRecordService.get_messages(AsyncMock(), conversation_id=1)

    assert result["items"][0]["sender_type"] == "bot"
    assert result["items"][0]["sender_name"] == "Support Bot"


@pytest.mark.asyncio
async def test_get_by_id_includes_related_tickets(monkeypatch):
    conversation = SimpleNamespace(
        id=1,
        public_id="conv_pub",
        share_code="SC001",
        visitor=None,
        agent=None,
        channel=None,
        status="closed",
        started_at=_dt(),
        ended_at=_dt(),
        ended_by="agent",
        created_at=_dt(),
        last_message_preview=None,
    )
    tickets = [
        SimpleNamespace(id=10, ticket_number="TK202605290001"),
        SimpleNamespace(id=11, ticket_number="TK202605290002"),
    ]

    monkeypatch.setattr(
        "app.services.session_record_service.SessionRecordRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.session_record_service.SatisfactionSurveyRecordRepository.get_by_conversation",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.session_record_service.TicketRepository.list_by_conversation_id",
        AsyncMock(return_value=tickets),
    )
    monkeypatch.setattr(
        "app.services.session_record_service.QueueHistoryService.summaries_for_refs",
        AsyncMock(return_value={"1": {"last_assigned_queue": None, "queue_duration_seconds": None}}),
    )

    result = await SessionRecordService.get_by_id(AsyncMock(), tenant_id=1, conversation_id=1)

    assert result["related_tickets"] == [
        {"id": 10, "ticket_number": "TK202605290001"},
        {"id": 11, "ticket_number": "TK202605290002"},
    ]


@pytest.mark.asyncio
async def test_get_by_id_uses_conversation_group_as_queue_fallback_without_duration(monkeypatch):
    conversation = SimpleNamespace(
        id=1,
        public_id="conv_pub",
        share_code="SC001",
        visitor=None,
        agent=SimpleNamespace(id=3, name="Agent A", display_name="Agent A"),
        channel=None,
        group=SimpleNamespace(id=9, name="Support Team"),
        status="closed",
        started_at=_dt() + timedelta(seconds=12),
        ended_at=_dt() + timedelta(seconds=30),
        ended_by="agent",
        created_at=_dt(),
        last_message_preview=None,
    )

    monkeypatch.setattr(
        "app.services.session_record_service.SessionRecordRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.session_record_service.SatisfactionSurveyRecordRepository.get_by_conversation",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.session_record_service.TicketRepository.list_by_conversation_id",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.session_record_service.QueueHistoryService.summaries_for_refs",
        AsyncMock(return_value={"1": {"last_assigned_queue": None, "queue_duration_seconds": None}}),
    )

    result = await SessionRecordService.get_by_id(AsyncMock(), tenant_id=1, conversation_id=1)

    assert result["last_assigned_queue"] == {
        "queue_type": "employee_group",
        "queue_id": 9,
        "name": "Support Team",
    }
    assert result["queue_duration_seconds"] is None


@pytest.mark.asyncio
async def test_get_by_id_uses_agent_personal_queue_when_group_missing(monkeypatch):
    conversation = SimpleNamespace(
        id=1,
        public_id="conv_pub",
        share_code="SC001",
        visitor=None,
        agent=SimpleNamespace(id=3, name="Agent A", display_name="Agent A"),
        channel=None,
        group=None,
        status="closed",
        started_at=_dt(),
        ended_at=_dt() + timedelta(seconds=30),
        ended_by="agent",
        created_at=_dt(),
        last_message_preview=None,
    )

    monkeypatch.setattr(
        "app.services.session_record_service.SessionRecordRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.session_record_service.SatisfactionSurveyRecordRepository.get_by_conversation",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.session_record_service.TicketRepository.list_by_conversation_id",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.session_record_service.QueueHistoryService.summaries_for_refs",
        AsyncMock(return_value={"1": {"last_assigned_queue": None, "queue_duration_seconds": None}}),
    )

    result = await SessionRecordService.get_by_id(AsyncMock(), tenant_id=1, conversation_id=1)

    assert result["last_assigned_queue"] == {
        "queue_type": "employee",
        "queue_id": 3,
        "name": "Agent A",
    }
    assert result["queue_duration_seconds"] is None
