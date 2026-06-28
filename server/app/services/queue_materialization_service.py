"""
Materialize per-conversation queue summary into redundant columns and the
``conversation_queue_summaries`` table.

Called by the queue engine whenever a conversation's queue task is assigned or
reaches a terminal state. Shares the waiting-time caliber in
``app.libs.queue_metrics`` with the read path and history backfill so all of
them report identical numbers.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import QueueChannel, QueueTaskType
from app.libs.queue_metrics import compute_conversation_queue_summary
from app.models.conversation import Conversation
from app.repositories.queue_history_repository import QueueHistoryRepository
from app.repositories.queue_repository import ConversationQueueSummaryRepository

_TASK_TYPES = [QueueTaskType.CONVERSATION.value, QueueTaskType.OPEN_AGENT_HANDOFF.value]


class QueueMaterializationService:
    @staticmethod
    async def materialize_conversation(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
    ) -> None:
        """Recompute and persist queue summary for one conversation. No commit."""
        conversation = await db.get(Conversation, conversation_id)
        if conversation is None or conversation.tenant_id != tenant_id:
            return

        tasks = await QueueHistoryRepository.list_tasks_for_refs(
            db,
            tenant_id,
            channel=QueueChannel.ONLINE_CHAT.value,
            task_types=_TASK_TYPES,
            ref_ids=[str(conversation_id)],
        )
        events = await QueueHistoryRepository.list_events_for_tasks(
            db,
            tenant_id,
            task_ids=[task.id for task in tasks],
        )
        queue_keys = {(task.queue_type, task.queue_id) for task in tasks}
        current_names = await QueueHistoryRepository.current_queue_names(db, tenant_id, queue_keys)

        result = compute_conversation_queue_summary(
            tasks=tasks,
            events=events,
            current_names=current_names,
        )

        conversation.last_assigned_queue_type = result.last_assigned_queue_type
        conversation.last_assigned_queue_id = result.last_assigned_queue_id
        conversation.last_assigned_queue_name = result.last_assigned_queue_name
        conversation.total_queue_duration_seconds = result.total_queue_duration_seconds
        conversation.queue_entered_at = result.queue_entered_at
        conversation.queue_assigned_at = result.queue_assigned_at
        conversation.queue_result = result.queue_result

        rows = [
            {
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "queue_type": row.queue_type,
                "queue_id": row.queue_id,
                "queue_name_snapshot": row.queue_name_snapshot,
                "wait_duration_seconds": row.wait_duration_seconds,
                "is_last_assigned": row.is_last_assigned,
                "queue_result": row.queue_result,
                "conversation_started_at": conversation.started_at,
            }
            for row in result.rows
        ]
        await ConversationQueueSummaryRepository.replace_for_conversation(
            db, tenant_id, conversation_id, rows
        )
        await db.flush()
