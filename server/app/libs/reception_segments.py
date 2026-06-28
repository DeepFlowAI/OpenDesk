"""Reception-segment caliber (single source of truth).

A reception segment is a continuous period within one customer conversation
during which a single agent was responsible. Segments are derived **after the
conversation ends** from the structured reception events
(``conversation_reception_events``) — never from system-message text.

This module holds the pure, dependency-free logic that turns the ordered event
stream into ordered segment drafts (timing, entry/end reasons, transfer
counterparts). The DB orchestration (loading events/messages, per-segment
metrics, snapshots, persistence) lives in ``ReceptionSegmentService``; keeping
the structural rules here makes them unit-testable and keeps one caliber shared
by generation and any future backfill.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.enums import ReceptionEventReason, ReceptionEventType

# ── Entry reasons (why a segment started) ────────────────────────────────────
ENTRY_FIRST = "first"
ENTRY_BOT_HANDOFF = "bot_handoff"
ENTRY_TRANSFER_IN = "transfer_in"
ENTRY_REASSIGN = "reassign"

# ── End reasons (why a segment ended) ────────────────────────────────────────
END_TRANSFER_OUT = "transfer_out"
END_REASSIGN_OUT = "reassign_out"
END_SESSION_CLOSED = "session_closed"

_OWNERSHIP_GRANT_TYPES = {
    ReceptionEventType.ASSIGNED.value,
    ReceptionEventType.TRANSFERRED.value,
}


@dataclass
class ReceptionEventInput:
    """Minimal view of one reception event needed to build segments."""
    event_type: str
    reason: str | None
    occurred_at: datetime
    agent_id: int | None
    group_id: int | None
    from_agent_id: int | None
    to_agent_id: int | None


@dataclass
class SegmentDraft:
    """One reception segment before per-segment metrics / snapshots are filled."""
    agent_id: int | None
    group_id: int | None
    started_at: datetime
    entry_reason: str
    from_agent_id: int | None = None
    ended_at: datetime | None = None
    end_reason: str | None = None
    to_agent_id: int | None = None
    seq_no: int = 0


def _entry_reason_for(event: ReceptionEventInput) -> str:
    if event.event_type == ReceptionEventType.TRANSFERRED.value:
        return ENTRY_TRANSFER_IN
    if event.reason == ReceptionEventReason.BOT_HANDOFF.value:
        return ENTRY_BOT_HANDOFF
    if event.reason == ReceptionEventReason.REASSIGN.value:
        return ENTRY_REASSIGN
    return ENTRY_FIRST


def _end_reason_for_grant(event: ReceptionEventInput) -> str:
    """End reason of the segment closed by an incoming ownership-grant event."""
    if event.event_type == ReceptionEventType.TRANSFERRED.value:
        return END_TRANSFER_OUT
    return END_REASSIGN_OUT


def opening_event_count(events: list[ReceptionEventInput]) -> int:
    """Number of events that hand ownership to an agent (open a segment)."""
    return sum(
        1
        for ev in events
        if ev.event_type in _OWNERSHIP_GRANT_TYPES and ev.to_agent_id is not None
    )


def build_segment_drafts(
    events: list[ReceptionEventInput],
    conversation_ended_at: datetime | None,
) -> list[SegmentDraft]:
    """Build ordered reception-segment drafts from the conversation's events.

    Events must be in chronological order. Each ownership-grant event
    (``assigned`` / ``transferred``) closes the currently open segment (if any)
    and opens a new one; an ``ended`` event closes the open segment. A residual
    open segment (no closing event) is closed at ``conversation_ended_at``.
    Segments may be separated by a no-owner gap.
    """
    drafts: list[SegmentDraft] = []
    open_segment: SegmentDraft | None = None

    for ev in events:
        if ev.event_type in _OWNERSHIP_GRANT_TYPES and ev.to_agent_id is not None:
            if open_segment is not None:
                open_segment.ended_at = ev.occurred_at
                open_segment.end_reason = _end_reason_for_grant(ev)
                open_segment.to_agent_id = ev.to_agent_id
                drafts.append(open_segment)
            open_segment = SegmentDraft(
                agent_id=ev.to_agent_id,
                group_id=ev.group_id,
                started_at=ev.occurred_at,
                entry_reason=_entry_reason_for(ev),
                from_agent_id=ev.from_agent_id,
            )
        elif ev.event_type == ReceptionEventType.ENDED.value:
            if open_segment is not None:
                open_segment.ended_at = ev.occurred_at
                open_segment.end_reason = END_SESSION_CLOSED
                drafts.append(open_segment)
                open_segment = None

    if open_segment is not None:
        open_segment.ended_at = conversation_ended_at
        open_segment.end_reason = END_SESSION_CLOSED
        drafts.append(open_segment)

    for index, draft in enumerate(drafts, start=1):
        draft.seq_no = index
    return drafts


def windows_non_overlapping(drafts: list[SegmentDraft]) -> bool:
    """True when each segment ends no later than the next one starts."""
    for current, nxt in zip(drafts, drafts[1:]):
        if current.ended_at is None:
            return False
        if current.ended_at > nxt.started_at:
            return False
    return True
