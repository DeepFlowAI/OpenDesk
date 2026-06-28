"""Shared queue waiting-time caliber.

Single source of truth for how queue metrics are measured so that runtime
materialization, the session-record read path, history backfill and reports all
agree on the same numbers:

- which assignment events count as a successful assignment;
- how a single queue task's waiting duration is measured;
- how per-conversation and per-queue summaries are derived from a conversation's
  queue tasks and assignment events.

A task that is still waiting (no terminal timestamp) contributes 0 seconds; we
never fall back to ``updated_at`` / ``now()``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# Assignment event types that represent a successful assignment to an agent.
SUCCESS_ASSIGNMENT_EVENT_TYPES = frozenset(
    {
        "auto_assigned",
        "pull_assigned",
        "admin_assigned",
        "returning_agent_assigned",
    }
)


def _to_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def terminal_time(task) -> datetime | None:
    """Earliest terminal timestamp of a queue task, or None while still waiting."""
    return task.assigned_at or task.canceled_at or task.timeout_at


def task_result(task) -> str | None:
    """Terminal result of a queue task: assigned / canceled / timeout, or None.

    ``assigned`` takes priority so a task that was assigned is never reported as
    canceled/timeout. Returns None while the task is still waiting.
    """
    if task.assigned_at is not None:
        return "assigned"
    if task.canceled_at is not None:
        return "canceled"
    if task.timeout_at is not None:
        return "timeout"
    return None


def wait_seconds(task) -> int:
    """Waiting duration of a single queue task in whole seconds.

    Measured from ``enqueued_at`` to its terminal timestamp. Returns 0 when the
    task has not yet reached a terminal state.
    """
    if not task.enqueued_at:
        return 0
    end = terminal_time(task)
    if end is None:
        return 0
    return max(0, int((_to_aware(end) - _to_aware(task.enqueued_at)).total_seconds()))


@dataclass
class QueueWaitRow:
    """One conversation/queue aggregation row."""

    queue_type: str
    queue_id: int
    queue_name_snapshot: str | None
    wait_duration_seconds: int
    is_last_assigned: bool
    # Final result of this queue's latest substantial task (wait > 0): assigned /
    # canceled / timeout, or None when the queue had no substantial wait. Lets
    # queue reports tell "queued then assigned" from "queued then dropped" per
    # queue, which ``is_last_assigned`` (only the conversation's final queue)
    # cannot express.
    queue_result: str | None = None


@dataclass
class ConversationQueueResult:
    """Materialized queue summary for a single conversation."""

    last_assigned_queue_type: str | None = None
    last_assigned_queue_id: int | None = None
    last_assigned_queue_name: str | None = None
    total_queue_duration_seconds: int | None = None
    # Queue lifecycle over the conversation's substantial queue tasks (wait > 0):
    # when the visitor first entered a queue, when finally assigned, and the
    # final result of the latest substantial task.
    queue_entered_at: datetime | None = None
    queue_assigned_at: datetime | None = None
    queue_result: str | None = None
    rows: list[QueueWaitRow] = field(default_factory=list)


def compute_conversation_queue_summary(
    *,
    tasks,
    events,
    current_names: dict[tuple[str, int], str | None],
) -> ConversationQueueResult:
    """Derive the queue summary for one conversation.

    ``tasks`` are the conversation's queue tasks; ``events`` its assignment
    events; ``current_names`` maps ``(queue_type, queue_id)`` to the queue's
    current display name (fallback when no snapshot is available).
    """
    if not tasks:
        return ConversationQueueResult()

    # Per-queue accumulated waiting seconds.
    wait_by_queue: dict[tuple[str, int], int] = {}
    for task in tasks:
        key = (task.queue_type, task.queue_id)
        wait_by_queue[key] = wait_by_queue.get(key, 0) + wait_seconds(task)

    # Per-queue name snapshot: latest event carrying a snapshot wins.
    snapshot_by_queue: dict[tuple[str, int], str] = {}
    ordered_events = sorted(events, key=lambda e: (_to_aware(e.created_at), e.id))
    for event in ordered_events:
        if event.queue_name_snapshot:
            snapshot_by_queue[(event.queue_type, event.queue_id)] = event.queue_name_snapshot

    # Last assigned queue: latest successful assignment event; fall back to the
    # task with the most recent assigned_at.
    last_assigned_key: tuple[str, int] | None = None
    for event in ordered_events:
        if event.event_type in SUCCESS_ASSIGNMENT_EVENT_TYPES:
            last_assigned_key = (event.queue_type, event.queue_id)
    if last_assigned_key is None:
        latest_task = None
        for task in tasks:
            if task.assigned_at is None:
                continue
            if latest_task is None or _to_aware(task.assigned_at) > _to_aware(latest_task.assigned_at):
                latest_task = task
        if latest_task is not None:
            last_assigned_key = (latest_task.queue_type, latest_task.queue_id)

    def _name(key: tuple[str, int]) -> str | None:
        return snapshot_by_queue.get(key) or current_names.get(key)

    # Per-queue final result: the latest substantial task (wait > 0) in each
    # queue, ordered by terminal time then id. Queues with no substantial wait
    # carry no result, matching the conversation-level lifecycle rule.
    latest_substantial_by_queue: dict[tuple[str, int], tuple] = {}
    for task in tasks:
        if wait_seconds(task) <= 0:
            continue
        key = (task.queue_type, task.queue_id)
        sort_key = (terminal_time(task) or task.enqueued_at, task.id)
        existing = latest_substantial_by_queue.get(key)
        if existing is None or sort_key > existing[0]:
            latest_substantial_by_queue[key] = (sort_key, task)
    result_by_queue: dict[tuple[str, int], str | None] = {
        key: task_result(entry[1]) for key, entry in latest_substantial_by_queue.items()
    }

    rows: list[QueueWaitRow] = []
    for key in sorted(wait_by_queue.keys()):
        queue_type, queue_id = key
        rows.append(
            QueueWaitRow(
                queue_type=queue_type,
                queue_id=queue_id,
                queue_name_snapshot=_name(key),
                wait_duration_seconds=wait_by_queue[key],
                is_last_assigned=key == last_assigned_key,
                queue_result=result_by_queue.get(key),
            )
        )

    total = sum(wait_by_queue.values())
    result = ConversationQueueResult(
        total_queue_duration_seconds=total if total > 0 else None,
        rows=rows,
    )
    if last_assigned_key is not None:
        result.last_assigned_queue_type = last_assigned_key[0]
        result.last_assigned_queue_id = last_assigned_key[1]
        result.last_assigned_queue_name = _name(last_assigned_key)

    # Lifecycle is derived only from substantial tasks (wait > 0). Such a task
    # always has a terminal timestamp, so the latest one's result is one of
    # assigned / canceled / timeout (never the non-terminal waiting / failed).
    substantial = [task for task in tasks if wait_seconds(task) > 0]
    if substantial:
        result.queue_entered_at = min(task.enqueued_at for task in substantial)
        assigned_times = [task.assigned_at for task in substantial if task.assigned_at is not None]
        result.queue_assigned_at = max(assigned_times) if assigned_times else None
        latest = max(substantial, key=lambda task: (terminal_time(task) or task.enqueued_at, task.id))
        result.queue_result = task_result(latest)
    return result
