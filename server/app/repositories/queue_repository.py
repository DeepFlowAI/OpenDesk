"""
Unified queue engine repository.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import QueueTaskStatus
from app.models.conversation import Conversation
from app.models.call_record import CallRecord
from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup, EmployeeGroupMember
from app.models.queue import (
    QueueAssignmentEvent,
    QueueOutboxEvent,
    QueuePolicy,
    QueueRoundRobinState,
    QueueTask,
)


ACTIVE_TASK_STATUSES = [QueueTaskStatus.QUEUED.value, QueueTaskStatus.ASSIGNING.value]


class QueuePolicyRepository:
    @staticmethod
    async def list_policies(
        db: AsyncSession,
        tenant_id: int,
        *,
        channel: str | None = None,
        scope_type: str | None = None,
        scope_id: int | None = None,
    ) -> list[QueuePolicy]:
        query = select(QueuePolicy).where(QueuePolicy.tenant_id == tenant_id)
        if channel:
            query = query.where(QueuePolicy.channel == channel)
        if scope_type:
            query = query.where(QueuePolicy.scope_type == scope_type)
        if scope_id is not None:
            query = query.where(QueuePolicy.scope_id == scope_id)
        query = query.order_by(QueuePolicy.channel.asc(), QueuePolicy.scope_type.asc(), QueuePolicy.scope_id.asc())
        return list((await db.execute(query)).scalars().all())

    @staticmethod
    async def get_policy(
        db: AsyncSession,
        tenant_id: int,
        channel: str,
        scope_type: str,
        scope_id: int | None,
    ) -> QueuePolicy | None:
        query = select(QueuePolicy).where(
            QueuePolicy.tenant_id == tenant_id,
            QueuePolicy.channel == channel,
            QueuePolicy.scope_type == scope_type,
        )
        if scope_id is None:
            query = query.where(QueuePolicy.scope_id.is_(None))
        else:
            query = query.where(QueuePolicy.scope_id == scope_id)
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def upsert_policy(db: AsyncSession, tenant_id: int, payload: dict) -> QueuePolicy:
        existing = await QueuePolicyRepository.get_policy(
            db,
            tenant_id,
            payload["channel"],
            payload["scope_type"],
            payload.get("scope_id"),
        )
        if existing:
            for key, value in payload.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            await db.flush()
            return existing
        policy = QueuePolicy(tenant_id=tenant_id, **payload)
        db.add(policy)
        await db.flush()
        return policy


class QueueTaskRepository:
    @staticmethod
    async def get_task(db: AsyncSession, tenant_id: int, task_id: int) -> QueueTask | None:
        result = await db.execute(
            select(QueueTask).where(QueueTask.tenant_id == tenant_id, QueueTask.id == task_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_task_for_update(db: AsyncSession, tenant_id: int, task_id: int) -> QueueTask | None:
        result = await db.execute(
            select(QueueTask)
            .where(QueueTask.tenant_id == tenant_id, QueueTask.id == task_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_task_by_ref(
        db: AsyncSession,
        tenant_id: int,
        channel: str,
        task_type: str,
        task_ref_id: str,
    ) -> QueueTask | None:
        result = await db.execute(
            select(QueueTask).where(
                QueueTask.tenant_id == tenant_id,
                QueueTask.channel == channel,
                QueueTask.task_type == task_type,
                QueueTask.task_ref_id == task_ref_id,
                QueueTask.status.in_(ACTIVE_TASK_STATUSES),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_task(db: AsyncSession, payload: dict) -> QueueTask:
        task = QueueTask(**payload)
        db.add(task)
        await db.flush()
        return task

    @staticmethod
    async def count_waiting(
        db: AsyncSession,
        tenant_id: int,
        channel: str,
        queue_type: str,
        queue_id: int,
    ) -> int:
        result = await db.execute(
            select(func.count()).select_from(QueueTask).where(
                QueueTask.tenant_id == tenant_id,
                QueueTask.channel == channel,
                QueueTask.queue_type == queue_type,
                QueueTask.queue_id == queue_id,
                QueueTask.status == QueueTaskStatus.QUEUED.value,
            )
        )
        return int(result.scalar_one())

    @staticmethod
    async def get_tail_same_priority(
        db: AsyncSession,
        tenant_id: int,
        channel: str,
        queue_type: str,
        queue_id: int,
        priority: int,
    ) -> QueueTask | None:
        result = await db.execute(
            select(QueueTask)
            .where(
                QueueTask.tenant_id == tenant_id,
                QueueTask.channel == channel,
                QueueTask.queue_type == queue_type,
                QueueTask.queue_id == queue_id,
                QueueTask.priority == priority,
                QueueTask.status == QueueTaskStatus.QUEUED.value,
            )
            .order_by(QueueTask.enqueued_at.desc(), QueueTask.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_tail_waiting(
        db: AsyncSession,
        tenant_id: int,
        channel: str,
        queue_type: str,
        queue_id: int,
    ) -> QueueTask | None:
        result = await db.execute(
            select(QueueTask)
            .where(
                QueueTask.tenant_id == tenant_id,
                QueueTask.channel == channel,
                QueueTask.queue_type == queue_type,
                QueueTask.queue_id == queue_id,
                QueueTask.status == QueueTaskStatus.QUEUED.value,
            )
            .order_by(QueueTask.enqueued_at.desc(), QueueTask.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def lock_next_queued_task(
        db: AsyncSession,
        tenant_id: int,
        channel: str,
        queue_type: str,
        queue_id: int,
    ) -> QueueTask | None:
        result = await db.execute(
            select(QueueTask)
            .where(
                QueueTask.tenant_id == tenant_id,
                QueueTask.channel == channel,
                QueueTask.queue_type == queue_type,
                QueueTask.queue_id == queue_id,
                QueueTask.status == QueueTaskStatus.QUEUED.value,
            )
            .order_by(QueueTask.priority.asc(), QueueTask.enqueued_at.asc(), QueueTask.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def find_pullable_task(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        *,
        queue_type: str | None = None,
        queue_id: int | None = None,
    ) -> QueueTask | None:
        group_ids_result = await db.execute(
            select(EmployeeGroupMember.group_id)
            .join(EmployeeGroup, EmployeeGroup.id == EmployeeGroupMember.group_id)
            .where(
                EmployeeGroup.tenant_id == tenant_id,
                EmployeeGroupMember.employee_id == employee_id,
            )
        )
        group_ids = list(group_ids_result.scalars().all())
        allowed = [
            and_(QueueTask.queue_type == "employee", QueueTask.queue_id == employee_id),
        ]
        if group_ids:
            allowed.append(and_(QueueTask.queue_type == "employee_group", QueueTask.queue_id.in_(group_ids)))
        query = select(QueueTask).where(
            QueueTask.tenant_id == tenant_id,
            QueueTask.channel == "online_chat",
            QueueTask.status == QueueTaskStatus.QUEUED.value,
            or_(*allowed),
        )
        if queue_type and queue_id:
            query = query.where(QueueTask.queue_type == queue_type, QueueTask.queue_id == queue_id)
        query = (
            query.order_by(QueueTask.priority.asc(), QueueTask.enqueued_at.asc(), QueueTask.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def position_for_task(db: AsyncSession, task: QueueTask) -> tuple[int, int]:
        before_same_priority = and_(
            QueueTask.priority == task.priority,
            or_(
                QueueTask.enqueued_at < task.enqueued_at,
                and_(QueueTask.enqueued_at == task.enqueued_at, QueueTask.id <= task.id),
            ),
        )
        base = [
            QueueTask.tenant_id == task.tenant_id,
            QueueTask.channel == task.channel,
            QueueTask.queue_type == task.queue_type,
            QueueTask.queue_id == task.queue_id,
            QueueTask.status.in_(ACTIVE_TASK_STATUSES),
        ]
        overall_result = await db.execute(
            select(func.count()).select_from(QueueTask).where(
                *base,
                or_(QueueTask.priority < task.priority, before_same_priority),
            )
        )
        priority_result = await db.execute(
            select(func.count()).select_from(QueueTask).where(*base, before_same_priority)
        )
        return int(overall_result.scalar_one()), int(priority_result.scalar_one())

    @staticmethod
    async def queue_counts(
        db: AsyncSession,
        tenant_id: int,
        channel: str,
        queue_type: str,
        queue_id: int,
    ) -> tuple[int, int]:
        result = await db.execute(
            select(QueueTask.status, func.count())
            .where(
                QueueTask.tenant_id == tenant_id,
                QueueTask.channel == channel,
                QueueTask.queue_type == queue_type,
                QueueTask.queue_id == queue_id,
                QueueTask.status.in_(ACTIVE_TASK_STATUSES),
            )
            .group_by(QueueTask.status)
        )
        counts = {status: int(count) for status, count in result.all()}
        return counts.get(QueueTaskStatus.QUEUED.value, 0), counts.get(QueueTaskStatus.ASSIGNING.value, 0)

    @staticmethod
    async def priority_stats(
        db: AsyncSession,
        tenant_id: int,
        channel: str,
        queue_type: str,
        queue_id: int,
    ) -> list[tuple[int, int, datetime | None]]:
        result = await db.execute(
            select(QueueTask.priority, func.count(), func.min(QueueTask.enqueued_at))
            .where(
                QueueTask.tenant_id == tenant_id,
                QueueTask.channel == channel,
                QueueTask.queue_type == queue_type,
                QueueTask.queue_id == queue_id,
                QueueTask.status == QueueTaskStatus.QUEUED.value,
            )
            .group_by(QueueTask.priority)
            .order_by(QueueTask.priority.asc())
        )
        return [(int(priority), int(count), earliest) for priority, count, earliest in result.all()]

    @staticmethod
    async def mark_assigning(db: AsyncSession, task: QueueTask, now: datetime) -> QueueTask:
        task.status = QueueTaskStatus.ASSIGNING.value
        task.assigning_at = now
        task.attempts = (task.attempts or 0) + 1
        task.last_error = None
        await db.flush()
        return task

    @staticmethod
    async def mark_assigned(
        db: AsyncSession,
        task: QueueTask,
        *,
        agent_id: int,
        assigned_by: str,
        now: datetime,
    ) -> QueueTask:
        task.status = QueueTaskStatus.ASSIGNED.value
        task.assigned_agent_id = agent_id
        task.assigned_by = assigned_by
        task.assigned_at = now
        task.last_error = None
        await db.flush()
        return task

    @staticmethod
    async def restore_queued(db: AsyncSession, task: QueueTask, reason: str | None = None) -> QueueTask:
        task.status = QueueTaskStatus.QUEUED.value
        task.assigning_at = None
        task.last_error = reason
        await db.flush()
        return task

    @staticmethod
    async def mark_terminal(
        db: AsyncSession,
        task: QueueTask,
        status: str,
        *,
        now: datetime,
        reason: str | None = None,
    ) -> QueueTask:
        task.status = status
        task.last_error = reason
        if status == QueueTaskStatus.CANCELED.value:
            task.canceled_at = now
        elif status == QueueTaskStatus.TIMEOUT.value:
            task.timeout_at = now
        await db.flush()
        return task


class QueueCandidateRepository:
    @staticmethod
    async def queue_exists(db: AsyncSession, tenant_id: int, queue_type: str, queue_id: int) -> bool:
        if queue_type == "employee":
            result = await db.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id,
                    Employee.id == queue_id,
                    Employee.is_active.is_(True),
                )
            )
        else:
            result = await db.execute(
                select(EmployeeGroup.id).where(
                    EmployeeGroup.tenant_id == tenant_id,
                    EmployeeGroup.id == queue_id,
                )
            )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def list_candidate_employees(
        db: AsyncSession,
        tenant_id: int,
        queue_type: str,
        queue_id: int,
    ) -> list[Employee]:
        if queue_type == "employee":
            result = await db.execute(
                select(Employee).where(
                    Employee.tenant_id == tenant_id,
                    Employee.id == queue_id,
                    Employee.is_active.is_(True),
                )
            )
            employee = result.scalar_one_or_none()
            return [employee] if employee else []
        result = await db.execute(
            select(Employee)
            .select_from(EmployeeGroupMember)
            .join(Employee, Employee.id == EmployeeGroupMember.employee_id)
            .join(EmployeeGroup, EmployeeGroup.id == EmployeeGroupMember.group_id)
            .where(
                EmployeeGroup.tenant_id == tenant_id,
                EmployeeGroupMember.group_id == queue_id,
                Employee.tenant_id == tenant_id,
                Employee.is_active.is_(True),
            )
            .order_by(EmployeeGroupMember.employee_id.asc())
        )
        return list(result.scalars().all())


class QueueRoundRobinRepository:
    @staticmethod
    async def get_state(
        db: AsyncSession,
        tenant_id: int,
        channel: str,
        queue_type: str,
        queue_id: int,
    ) -> QueueRoundRobinState | None:
        result = await db.execute(
            select(QueueRoundRobinState).where(
                QueueRoundRobinState.tenant_id == tenant_id,
                QueueRoundRobinState.channel == channel,
                QueueRoundRobinState.queue_type == queue_type,
                QueueRoundRobinState.queue_id == queue_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def set_last_agent(
        db: AsyncSession,
        tenant_id: int,
        channel: str,
        queue_type: str,
        queue_id: int,
        agent_id: int,
    ) -> QueueRoundRobinState:
        state = await QueueRoundRobinRepository.get_state(db, tenant_id, channel, queue_type, queue_id)
        if state is None:
            state = QueueRoundRobinState(
                tenant_id=tenant_id,
                channel=channel,
                queue_type=queue_type,
                queue_id=queue_id,
                last_agent_id=agent_id,
                cursor_payload={},
                version=1,
            )
            db.add(state)
        else:
            state.last_agent_id = agent_id
            state.version = (state.version or 0) + 1
        await db.flush()
        return state


class QueueEventRepository:
    @staticmethod
    async def create_assignment_event(db: AsyncSession, payload: dict) -> QueueAssignmentEvent:
        event = QueueAssignmentEvent(**payload)
        db.add(event)
        await db.flush()
        return event

    @staticmethod
    async def create_outbox_event(db: AsyncSession, payload: dict) -> QueueOutboxEvent:
        event = QueueOutboxEvent(**payload)
        db.add(event)
        await db.flush()
        return event


class QueueBusinessRepository:
    @staticmethod
    async def assign_conversation(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        agent_id: int,
        now: datetime,
    ) -> bool:
        conversation = await db.get(Conversation, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            return False
        conversation.agent_id = agent_id
        conversation.status = "active"
        conversation.started_at = conversation.started_at or now
        conversation.open_agent_handoff_state = (
            "success" if conversation.open_agent_handoff_state else conversation.open_agent_handoff_state
        )
        await db.flush()
        return True

    @staticmethod
    async def assign_call(
        db: AsyncSession,
        tenant_id: int,
        call_id: str,
        agent_id: int,
    ) -> bool:
        result = await db.execute(
            select(CallRecord).where(CallRecord.tenant_id == tenant_id, CallRecord.call_id == call_id)
        )
        call = result.scalar_one_or_none()
        if not call:
            return False
        call.agent_id = agent_id
        await db.flush()
        return True
