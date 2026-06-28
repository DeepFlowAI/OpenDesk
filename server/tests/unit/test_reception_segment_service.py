from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.libs.reception_segments import SegmentDraft
from app.services.reception_segment_service import ReceptionSegmentService, _PublicMessage


BASE = datetime(2026, 6, 27, 8, 0, 0, tzinfo=timezone.utc)


def _at(seconds: int) -> datetime:
    return BASE + timedelta(seconds=seconds)


def _message(sender_type: str, sender_id: int | None, seconds: int) -> _PublicMessage:
    return _PublicMessage(sender_type, sender_id, _at(seconds))


def _conversation(first_response_seconds: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        tenant_id=1,
        started_at=BASE,
        first_human_response_seconds=first_response_seconds,
    )


def _draft(
    *,
    seq_no: int,
    agent_id: int,
    started: int,
    ended: int,
    end_reason: str = "session_closed",
) -> SegmentDraft:
    return SegmentDraft(
        agent_id=agent_id,
        group_id=10,
        started_at=_at(started),
        ended_at=_at(ended),
        entry_reason="first" if seq_no == 1 else "transfer_in",
        end_reason=end_reason,
        seq_no=seq_no,
    )


def test_first_segment_without_agent_reply_does_not_copy_conversation_first_response():
    drafts = [
        _draft(seq_no=1, agent_id=1, started=0, ended=10, end_reason="transfer_out"),
        _draft(seq_no=2, agent_id=2, started=10, ended=30),
    ]
    messages = [
        _message("visitor", None, 1),
        _message("visitor", None, 2),
        _message("agent", 2, 12),
    ]

    rows = ReceptionSegmentService._build_rows(
        _conversation(first_response_seconds=10),
        drafts,
        messages,
        {1: "Agent A", 2: "Agent B"},
        {10: "Support"},
    )

    assert rows[0]["visitor_message_count"] == 2
    assert rows[0]["agent_message_count"] == 0
    assert rows[0]["first_response_seconds"] is None
    assert rows[1]["first_response_seconds"] is None


def test_first_segment_keeps_first_response_when_segment_agent_replies():
    drafts = [_draft(seq_no=1, agent_id=1, started=0, ended=30)]
    messages = [
        _message("visitor", None, 1),
        _message("visitor", None, 3),
        _message("agent", 1, 12),
    ]

    rows = ReceptionSegmentService._build_rows(
        _conversation(first_response_seconds=9),
        drafts,
        messages,
        {1: "Agent A"},
        {10: "Support"},
    )

    assert rows[0]["agent_message_count"] == 1
    assert rows[0]["first_response_seconds"] == 9
