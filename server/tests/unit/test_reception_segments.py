"""
Unit tests for the pure reception-segment builder (app.libs.reception_segments).
"""
from datetime import datetime, timedelta, timezone

from app.libs.reception_segments import (
    ENTRY_BOT_HANDOFF,
    ENTRY_FIRST,
    ENTRY_REASSIGN,
    ENTRY_TRANSFER_IN,
    END_REASSIGN_OUT,
    END_SESSION_CLOSED,
    END_TRANSFER_OUT,
    ReceptionEventInput,
    build_segment_drafts,
    opening_event_count,
    windows_non_overlapping,
)

BASE = datetime(2026, 6, 27, 8, 0, 0, tzinfo=timezone.utc)


def _at(minutes: int) -> datetime:
    return BASE + timedelta(minutes=minutes)


def _ev(event_type, *, reason=None, occurred, agent=None, group=None, frm=None, to=None):
    return ReceptionEventInput(
        event_type=event_type,
        reason=reason,
        occurred_at=occurred,
        agent_id=agent,
        group_id=group,
        from_agent_id=frm,
        to_agent_id=to,
    )


def test_single_agent_first_to_end():
    events = [
        _ev("assigned", reason="first_human", occurred=_at(0), agent=1, group=10, to=1),
        _ev("ended", occurred=_at(30), agent=1, frm=1),
    ]
    drafts = build_segment_drafts(events, _at(30))
    assert len(drafts) == 1
    d = drafts[0]
    assert d.seq_no == 1
    assert d.agent_id == 1
    assert d.group_id == 10
    assert d.entry_reason == ENTRY_FIRST
    assert d.end_reason == END_SESSION_CLOSED
    assert d.started_at == _at(0)
    assert d.ended_at == _at(30)


def test_transfer_splits_into_two_segments():
    events = [
        _ev("assigned", reason="first_human", occurred=_at(0), agent=1, group=10, to=1),
        _ev("transferred", reason="transfer", occurred=_at(10), agent=2, group=10, frm=1, to=2),
        _ev("ended", occurred=_at(25), agent=2, frm=2),
    ]
    drafts = build_segment_drafts(events, _at(25))
    assert [d.agent_id for d in drafts] == [1, 2]
    assert drafts[0].entry_reason == ENTRY_FIRST
    assert drafts[0].end_reason == END_TRANSFER_OUT
    assert drafts[0].to_agent_id == 2
    assert drafts[0].ended_at == _at(10)
    assert drafts[1].entry_reason == ENTRY_TRANSFER_IN
    assert drafts[1].from_agent_id == 1
    assert drafts[1].end_reason == END_SESSION_CLOSED
    assert opening_event_count(events) == 2


def test_bot_handoff_entry_reason():
    events = [
        _ev("assigned", reason="bot_handoff", occurred=_at(0), agent=5, group=10, to=5),
        _ev("ended", occurred=_at(5), agent=5, frm=5),
    ]
    drafts = build_segment_drafts(events, _at(5))
    assert drafts[0].entry_reason == ENTRY_BOT_HANDOFF


def test_reassign_after_gap_produces_two_segments_with_gap():
    # Agent 1 first, conversation ends? No — agent re-queued then reassigned to 2
    # is modeled as another assigned event opening a new segment.
    events = [
        _ev("assigned", reason="first_human", occurred=_at(0), agent=1, group=10, to=1),
        _ev("assigned", reason="reassign", occurred=_at(12), agent=2, group=10, to=2),
        _ev("ended", occurred=_at(20), agent=2, frm=2),
    ]
    drafts = build_segment_drafts(events, _at(20))
    assert len(drafts) == 2
    assert drafts[0].end_reason == END_REASSIGN_OUT
    assert drafts[1].entry_reason == ENTRY_REASSIGN
    assert windows_non_overlapping(drafts)


def test_residual_open_segment_closed_at_conversation_end():
    # No explicit ended event (e.g. agent_id was null at close); the residual
    # open segment is closed at the conversation end time.
    events = [
        _ev("assigned", reason="first_human", occurred=_at(0), agent=1, group=10, to=1),
    ]
    drafts = build_segment_drafts(events, _at(40))
    assert len(drafts) == 1
    assert drafts[0].ended_at == _at(40)
    assert drafts[0].end_reason == END_SESSION_CLOSED


def test_no_events_yields_no_segments():
    assert build_segment_drafts([], _at(10)) == []
    assert opening_event_count([]) == 0
