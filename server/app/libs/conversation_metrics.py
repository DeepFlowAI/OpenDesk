"""Conversation basic report-field caliber (single source of truth).

The materialized columns on ``conversations`` — ``had_bot_session``,
``bot_handoff_succeeded`` and ``duration_seconds`` — are redundant, read-only
copies derived from the runtime OpenAgent fields and the session timestamps.
These pure helpers define the one caliber used by every write hook so new and
historical (backfilled) rows always agree, and so filters/reports can read the
columns directly instead of re-deriving the OR / timestamp expressions.
"""
from __future__ import annotations

from datetime import datetime

BOT_HANDOFF_SUCCESS_STATE = "success"


def compute_had_bot_session(
    open_agent_agent_id: int | None,
    open_agent_conversation_id: int | None,
    open_agent_conversation_external_id: str | None,
) -> bool:
    """True when the conversation was ever served by an OpenAgent bot.

    Mirrors the OR over the three OpenAgent identity fields.
    """
    return bool(
        open_agent_agent_id
        or open_agent_conversation_id
        or open_agent_conversation_external_id
    )


def compute_bot_handoff_succeeded(open_agent_handoff_state: str | None) -> bool:
    """True when the bot-to-human handoff reached the ``success`` state."""
    return open_agent_handoff_state == BOT_HANDOFF_SUCCESS_STATE


def compute_bot_handoff_triggered(open_agent_handoff_state: str | None) -> bool:
    """True when a bot-to-human handoff was ever triggered.

    Any non-null handoff state means the handoff flow started (requested /
    pending / queued / success / failed / dismissed); ``None`` means it was
    never triggered. This is the denominator for the handoff success rate, kept
    distinct from ``bot_handoff_succeeded`` which counts only successes.
    """
    return open_agent_handoff_state is not None


def compute_duration_seconds(
    started_at: datetime | None,
    ended_at: datetime | None,
) -> int | None:
    """Whole-second session duration for an ended session.

    Returns ``None`` while the session is in progress (no ``ended_at``) or when
    it never started; clamps negative values (clock skew) to 0.
    """
    if started_at is None or ended_at is None:
        return None
    return max(0, int((ended_at - started_at).total_seconds()))


def compute_first_human_response_seconds(
    visitor_message_at: datetime | None,
    agent_reply_at: datetime | None,
) -> int | None:
    """Whole-second duration from the pending visitor message to first agent reply.

    The caller is responsible for selecting the last public visitor message
    before the first public agent reply. Returns ``None`` when either side is
    missing and clamps negative values to zero for timestamp edge cases.
    """
    if visitor_message_at is None or agent_reply_at is None:
        return None
    return max(0, int((agent_reply_at - visitor_message_at).total_seconds()))


def bot_flags_for_conversation(conversation) -> dict:
    """Recompute both bot flags from a conversation's current OpenAgent fields."""
    return {
        "had_bot_session": compute_had_bot_session(
            getattr(conversation, "open_agent_agent_id", None),
            getattr(conversation, "open_agent_conversation_id", None),
            getattr(conversation, "open_agent_conversation_external_id", None),
        ),
        "bot_handoff_succeeded": compute_bot_handoff_succeeded(
            getattr(conversation, "open_agent_handoff_state", None),
        ),
        "bot_handoff_triggered": compute_bot_handoff_triggered(
            getattr(conversation, "open_agent_handoff_state", None),
        ),
    }


# ── Materialized message counts ──────────────────────────────────────────────
#
# Redundant columns on ``conversations`` materialize the per-conversation
# message counts so reports read them directly instead of COUNT/JOIN-ing the
# ``messages`` table. The helpers below define the single caliber shared by the
# runtime per-message increment, the end-of-conversation reconcile and the
# historical backfill, so live, ended and backfilled rows always agree.

MESSAGE_SENDER_VISITOR = "visitor"
MESSAGE_SENDER_AGENT = "agent"
MESSAGE_SENDER_BOT = "bot"


def message_count_increments(sender_type: str, *, in_human_phase: bool) -> dict[str, int]:
    """Columns to increment for one persisted message.

    Caliber:
    - visitor counts toward ``visitor_message_count`` and one phase column
      (human when the conversation has been taken over, bot otherwise); each
      phase also keeps a visitor-only count
      (``human_phase_visitor_message_count`` / ``bot_phase_visitor_message_count``);
    - agent counts toward ``agent_message_count`` and always the human phase,
      including ``human_phase_agent_message_count``;
    - bot counts toward the bot phase only;
    - system (and any other sender) increments nothing — only visitor/agent
      feed the report message totals, and phase counts exclude system.
    """
    increments: dict[str, int] = {}
    if sender_type == MESSAGE_SENDER_VISITOR:
        increments["visitor_message_count"] = 1
        if in_human_phase:
            increments["human_phase_message_count"] = 1
            increments["human_phase_visitor_message_count"] = 1
        else:
            increments["bot_phase_message_count"] = 1
            increments["bot_phase_visitor_message_count"] = 1
    elif sender_type == MESSAGE_SENDER_AGENT:
        increments["agent_message_count"] = 1
        increments["human_phase_message_count"] = 1
        increments["human_phase_agent_message_count"] = 1
    elif sender_type == MESSAGE_SENDER_BOT:
        increments["bot_phase_message_count"] = 1
    return increments


def compute_agent_response_metrics(
    public_messages: list[tuple[str, datetime]],
) -> tuple[int, int | None]:
    """Count and average whole-second duration of human-agent responses.

    ``public_messages`` is the conversation's public visitor/agent messages in
    chronological order as ``(sender_type, created_at)`` pairs. A response is an
    agent message whose immediately preceding public message is a visitor
    message; its duration is measured from that last consecutive visitor message
    to the agent reply. Consecutive visitor messages collapse to their last one
    and consecutive agent replies count only the first. Returns the response
    count and the rounded (half-up) average seconds, ``(0, None)`` when there is
    no response; negative deltas are clamped to zero for timestamp edge cases.
    """
    durations: list[int] = []
    prev_sender: str | None = None
    prev_at: datetime | None = None
    for sender_type, created_at in public_messages:
        if sender_type == MESSAGE_SENDER_AGENT and prev_sender == MESSAGE_SENDER_VISITOR:
            durations.append(max(0, int((created_at - prev_at).total_seconds())))
        prev_sender = sender_type
        prev_at = created_at
    if not durations:
        return 0, None
    return len(durations), int(sum(durations) / len(durations) + 0.5)


def conversation_in_human_phase(conversation) -> bool:
    """Whether new activity on a conversation belongs to the human phase.

    A conversation that never had a bot is always in the human phase. A bot
    conversation enters the human phase once a human has taken it over, which is
    exactly when ``started_at`` is stamped (the queue engine sets it on
    assignment). This is the live-moment form of the backfill rule
    ``message.created_at >= started_at``: a message created after takeover
    necessarily has ``now >= started_at``.
    """
    if not getattr(conversation, "had_bot_session", False):
        return True
    return getattr(conversation, "started_at", None) is not None
