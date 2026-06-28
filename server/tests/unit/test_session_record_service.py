"""
Unit tests for session record service.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.libs.conversation_metrics import bot_flags_for_conversation
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
        "visitor_system": None,
        "visitor_browser": None,
        "visitor_ip": None,
        "created_at": _dt(),
        "last_message_preview": None,
        "open_agent_agent_id": None,
        "open_agent_conversation_id": None,
        "open_agent_conversation_external_id": None,
        "open_agent_handoff_state": None,
    }
    data.update(overrides)
    conversation = SimpleNamespace(**data)
    # Mirror the materialized bot flags from the OpenAgent fields so the display
    # path reads them exactly like backfilled production rows.
    flags = bot_flags_for_conversation(conversation)
    conversation.had_bot_session = data.get("had_bot_session", flags["had_bot_session"])
    conversation.bot_handoff_succeeded = data.get(
        "bot_handoff_succeeded", flags["bot_handoff_succeeded"]
    )
    return conversation


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


def test_conversation_to_response_includes_visitor_environment():
    conversation = _conversation(
        visitor_system="macOS 15.5",
        visitor_browser="Chrome 126",
        visitor_ip="203.0.113.42",
    )

    result = SessionRecordService._conversation_to_response(conversation)

    assert result["visitor_system"] == "macOS 15.5"
    assert result["visitor_browser"] == "Chrome 126"
    assert result["visitor_ip"] == "203.0.113.42"


def test_conversation_to_response_includes_message_counts():
    conversation = _conversation(
        visitor_message_count=2,
        agent_message_count=1,
        bot_phase_message_count=4,
        human_phase_message_count=3,
        human_phase_visitor_message_count=2,
        human_phase_agent_message_count=1,
    )

    result = SessionRecordService._conversation_to_response(conversation)

    assert result["message_count"] == 3
    assert result["visitor_message_count"] == 2
    assert result["agent_message_count"] == 1
    assert result["bot_phase_message_count"] == 4
    assert result["human_phase_message_count"] == 3
    assert result["human_phase_visitor_message_count"] == 2
    assert result["human_phase_agent_message_count"] == 1


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

    result = await SessionRecordService.get_by_id(AsyncMock(), tenant_id=1, conversation_id=1)

    assert result["related_tickets"] == [
        {"id": 10, "ticket_number": "TK202605290001"},
        {"id": 11, "ticket_number": "TK202605290002"},
    ]


@pytest.mark.asyncio
async def test_get_by_id_reads_materialized_queue_fields(monkeypatch):
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
        last_assigned_queue_type="employee_group",
        last_assigned_queue_id=9,
        last_assigned_queue_name="Support Team",
        total_queue_duration_seconds=42,
        queue_entered_at=_dt(),
        queue_assigned_at=_dt() + timedelta(seconds=42),
        queue_result="assigned",
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

    result = await SessionRecordService.get_by_id(AsyncMock(), tenant_id=1, conversation_id=1)

    assert result["last_assigned_queue"] == {
        "queue_type": "employee_group",
        "queue_id": 9,
        "name": "Support Team",
    }
    assert result["queue_duration_seconds"] == 42
    assert result["has_queue"] is True
    assert result["queue_entered_at"] == _dt()
    assert result["queue_assigned_at"] == _dt() + timedelta(seconds=42)
    assert result["queue_result"] == "assigned"


@pytest.mark.asyncio
async def test_get_by_id_no_queue_without_materialized_fields(monkeypatch):
    # group/agent are populated but materialized queue columns are not: the old
    # group/agent fallback is gone, so no queue should be reported.
    conversation = SimpleNamespace(
        id=1,
        public_id="conv_pub",
        share_code="SC001",
        visitor=None,
        agent=SimpleNamespace(id=3, name="Agent A", display_name="Agent A"),
        channel=None,
        group=SimpleNamespace(id=9, name="Support Team"),
        status="closed",
        started_at=_dt(),
        ended_at=_dt() + timedelta(seconds=30),
        ended_by="agent",
        created_at=_dt(),
        last_message_preview=None,
        last_assigned_queue_type=None,
        last_assigned_queue_id=None,
        last_assigned_queue_name=None,
        total_queue_duration_seconds=None,
        queue_entered_at=None,
        queue_assigned_at=None,
        queue_result=None,
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

    result = await SessionRecordService.get_by_id(AsyncMock(), tenant_id=1, conversation_id=1)

    assert result["last_assigned_queue"] is None
    assert result["queue_duration_seconds"] is None
    assert result["has_queue"] is False
    assert result["queue_entered_at"] is None
    assert result["queue_assigned_at"] is None
    assert result["queue_result"] is None


def test_conversation_to_response_reads_materialized_queue_lifecycle():
    conversation = _conversation(
        total_queue_duration_seconds=12,
        queue_entered_at=_dt(),
        queue_assigned_at=None,
        queue_result="canceled",
    )

    result = SessionRecordService._conversation_to_response(conversation)

    assert result["has_queue"] is True
    assert result["queue_entered_at"] == _dt()
    assert result["queue_assigned_at"] is None
    assert result["queue_result"] == "canceled"


def test_conversation_to_response_no_queue_when_columns_empty():
    conversation = _conversation(
        total_queue_duration_seconds=None,
        queue_entered_at=None,
        queue_assigned_at=None,
        queue_result=None,
    )

    result = SessionRecordService._conversation_to_response(conversation)

    assert result["has_queue"] is False
    assert result["queue_entered_at"] is None
    assert result["queue_assigned_at"] is None
    assert result["queue_result"] is None


def test_conversation_to_response_reads_reception_materialized_columns():
    participants = [{"agent_id": 3, "name": "Agent A"}, {"agent_id": 7, "name": "Agent B"}]
    conversation = _conversation(
        reception_segment_count=2,
        reception_transfer_count=1,
        reception_final_agent_id=7,
        reception_participants=participants,
        reception_generation_status="generated",
    )

    result = SessionRecordService._conversation_to_response(conversation)

    assert result["reception_segment_count"] == 2
    assert result["reception_transfer_count"] == 1
    assert result["reception_final_agent_id"] == 7
    assert result["reception_participants"] == participants
    assert result["reception_generation_status"] == "generated"


def test_conversation_to_response_reception_defaults_when_missing():
    conversation = _conversation()

    result = SessionRecordService._conversation_to_response(conversation)

    assert result["reception_segment_count"] == 0
    assert result["reception_transfer_count"] == 0
    assert result["reception_final_agent_id"] is None
    assert result["reception_participants"] == []
    assert result["reception_generation_status"] is None


@pytest.mark.asyncio
async def test_get_reception_trajectory_maps_snapshots(monkeypatch):
    conversation = SimpleNamespace(
        id=1,
        status="closed",
        reception_generation_status="generated",
        agent_id=7,
        group_id=None,
    )
    segments = [
        SimpleNamespace(
            seq_no=1,
            agent_id=3,
            agent_name_snapshot="Agent A",
            group_id=9,
            group_name_snapshot="Support Team",
            started_at=_dt(),
            ended_at=_dt() + timedelta(seconds=600),
            duration_seconds=600,
            entry_reason="first",
            end_reason="transfer_out",
            from_agent_id=None,
            to_agent_id=7,
            visitor_message_count=4,
            agent_message_count=3,
            first_response_seconds=12,
            avg_response_seconds=20,
        ),
        SimpleNamespace(
            seq_no=2,
            agent_id=7,
            agent_name_snapshot="Agent B",
            group_id=9,
            group_name_snapshot="Support Team",
            started_at=_dt() + timedelta(seconds=600),
            ended_at=_dt() + timedelta(seconds=900),
            duration_seconds=300,
            entry_reason="transfer_in",
            end_reason="session_closed",
            from_agent_id=3,
            to_agent_id=None,
            visitor_message_count=2,
            agent_message_count=1,
            first_response_seconds=None,
            avg_response_seconds=15,
        ),
    ]

    monkeypatch.setattr(
        "app.services.session_record_service.SessionRecordRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        "app.services.session_record_service.ReceptionSegmentRepository.list_for_conversation",
        AsyncMock(return_value=segments),
    )

    result = await SessionRecordService.get_reception_trajectory(
        AsyncMock(), conversation_id=1, tenant_id=1
    )

    assert result["conversation_status"] == "closed"
    assert result["generation_status"] == "generated"
    assert len(result["segments"]) == 2
    first = result["segments"][0]
    assert first["agent_name"] == "Agent A"
    assert first["group_name"] == "Support Team"
    assert first["to_agent_id"] == 7
    assert first["first_response_seconds"] == 12
    assert result["segments"][1]["entry_reason"] == "transfer_in"
    assert result["segments"][1]["first_response_seconds"] is None


@pytest.mark.asyncio
async def test_get_reception_trajectory_not_found(monkeypatch):
    from app.core.exceptions import NotFoundError

    monkeypatch.setattr(
        "app.services.session_record_service.SessionRecordRepository.get_by_id",
        AsyncMock(return_value=None),
    )

    with pytest.raises(NotFoundError):
        await SessionRecordService.get_reception_trajectory(
            AsyncMock(), conversation_id=999, tenant_id=1
        )
