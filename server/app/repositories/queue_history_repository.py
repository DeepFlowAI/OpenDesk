"""
Read-side queries for queue history summaries.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup
from app.models.queue import QueueAssignmentEvent, QueueTask


class QueueHistoryRepository:
    @staticmethod
    async def list_tasks_for_refs(
        db: AsyncSession,
        tenant_id: int,
        *,
        channel: str,
        task_types: list[str],
        ref_ids: list[str],
    ) -> list[QueueTask]:
        if not ref_ids or not task_types:
            return []
        result = await db.execute(
            select(QueueTask)
            .where(
                QueueTask.tenant_id == tenant_id,
                QueueTask.channel == channel,
                QueueTask.task_type.in_(task_types),
                QueueTask.task_ref_id.in_(ref_ids),
            )
            .order_by(QueueTask.enqueued_at.asc(), QueueTask.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_success_events(
        db: AsyncSession,
        tenant_id: int,
        *,
        task_ids: list[int],
        event_types: set[str],
    ) -> list[QueueAssignmentEvent]:
        if not task_ids:
            return []
        result = await db.execute(
            select(QueueAssignmentEvent)
            .where(
                QueueAssignmentEvent.tenant_id == tenant_id,
                QueueAssignmentEvent.task_id.in_(task_ids),
                QueueAssignmentEvent.event_type.in_(event_types),
            )
            .order_by(QueueAssignmentEvent.created_at.asc(), QueueAssignmentEvent.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_events_for_tasks(
        db: AsyncSession,
        tenant_id: int,
        *,
        task_ids: list[int],
    ) -> list[QueueAssignmentEvent]:
        """All assignment events for the given tasks, ordered by created_at."""
        if not task_ids:
            return []
        result = await db.execute(
            select(QueueAssignmentEvent)
            .where(
                QueueAssignmentEvent.tenant_id == tenant_id,
                QueueAssignmentEvent.task_id.in_(task_ids),
            )
            .order_by(QueueAssignmentEvent.created_at.asc(), QueueAssignmentEvent.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def current_queue_names(
        db: AsyncSession,
        tenant_id: int,
        keys: set[tuple[str, int]],
    ) -> dict[tuple[str, int], str]:
        names: dict[tuple[str, int], str] = {}
        group_ids = sorted({queue_id for queue_type, queue_id in keys if queue_type == "employee_group"})
        employee_ids = sorted({queue_id for queue_type, queue_id in keys if queue_type == "employee"})

        if group_ids:
            result = await db.execute(
                select(EmployeeGroup.id, EmployeeGroup.name).where(
                    EmployeeGroup.tenant_id == tenant_id,
                    EmployeeGroup.id.in_(group_ids),
                )
            )
            names.update({("employee_group", group_id): name for group_id, name in result.all() if name})

        if employee_ids:
            result = await db.execute(
                select(
                    Employee.id,
                    Employee.display_name,
                    Employee.nickname,
                    Employee.name,
                    Employee.username,
                ).where(
                    Employee.tenant_id == tenant_id,
                    Employee.id.in_(employee_ids),
                )
            )
            for employee_id, display_name, nickname, name, username in result.all():
                label = display_name or nickname or name or username
                if label:
                    names[("employee", employee_id)] = label

        return names
