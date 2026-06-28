"""
Queue history summary service for session and call records.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.libs.queue_metrics import SUCCESS_ASSIGNMENT_EVENT_TYPES, wait_seconds as _wait_seconds
from app.repositories.queue_history_repository import QueueHistoryRepository


class QueueHistoryService:
    @staticmethod
    async def summaries_for_refs(
        db: AsyncSession,
        tenant_id: int,
        *,
        channel: str,
        task_types: list[str],
        ref_ids: list[str],
    ) -> dict[str, dict]:
        normalized_refs = [str(ref_id) for ref_id in ref_ids if str(ref_id)]
        if not normalized_refs:
            return {}

        tasks = await QueueHistoryRepository.list_tasks_for_refs(
            db,
            tenant_id,
            channel=channel,
            task_types=task_types,
            ref_ids=normalized_refs,
        )
        if not tasks:
            return {
                ref_id: {"last_assigned_queue": None, "queue_duration_seconds": None}
                for ref_id in normalized_refs
            }

        task_ref_by_id = {task.id: task.task_ref_id for task in tasks}
        total_seconds_by_ref = {ref_id: 0 for ref_id in normalized_refs}
        for task in tasks:
            total_seconds_by_ref[task.task_ref_id] = (
                total_seconds_by_ref.get(task.task_ref_id, 0) + _wait_seconds(task)
            )

        events = await QueueHistoryRepository.list_success_events(
            db,
            tenant_id,
            task_ids=list(task_ref_by_id.keys()),
            event_types=SUCCESS_ASSIGNMENT_EVENT_TYPES,
        )

        last_event_by_ref = {}
        queue_name_keys: set[tuple[str, int]] = set()
        for event in events:
            ref_id = task_ref_by_id.get(event.task_id)
            if ref_id is None:
                continue
            queue_name_keys.add((event.queue_type, event.queue_id))
            last_event_by_ref[ref_id] = event

        assigned_tasks_by_ref = {}
        for task in tasks:
            if task.assigned_at is None:
                continue
            queue_name_keys.add((task.queue_type, task.queue_id))
            current = assigned_tasks_by_ref.get(task.task_ref_id)
            if current is None or task.assigned_at > current.assigned_at:
                assigned_tasks_by_ref[task.task_ref_id] = task

        current_names = await QueueHistoryRepository.current_queue_names(db, tenant_id, queue_name_keys)

        summaries: dict[str, dict] = {}
        for ref_id in normalized_refs:
            assigned_queue = None
            last_event = last_event_by_ref.get(ref_id)
            if last_event is not None:
                name = last_event.queue_name_snapshot or current_names.get(
                    (last_event.queue_type, last_event.queue_id)
                )
                if name:
                    assigned_queue = {
                        "queue_type": last_event.queue_type,
                        "queue_id": last_event.queue_id,
                        "name": name,
                    }
            else:
                task = assigned_tasks_by_ref.get(ref_id)
                if task is not None:
                    name = current_names.get((task.queue_type, task.queue_id))
                    if name:
                        assigned_queue = {
                            "queue_type": task.queue_type,
                            "queue_id": task.queue_id,
                            "name": name,
                        }

            total_seconds = total_seconds_by_ref.get(ref_id, 0)
            summaries[ref_id] = {
                "last_assigned_queue": assigned_queue,
                "queue_duration_seconds": total_seconds if total_seconds > 0 else None,
            }

        return summaries
