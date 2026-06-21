"""
Workspace queue repository.
"""
from __future__ import annotations

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.enums import QueueChannel, QueueTaskStatus
from app.models.conversation import Conversation
from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup, EmployeeGroupMember
from app.models.queue import QueueTask


class QueueWorkspaceRepository:
    @staticmethod
    async def list_queued_tasks(
        db: AsyncSession,
        tenant_id: int,
        *,
        scope_predicate: ColumnElement | None = None,
        queue_type: str | None = None,
        queue_id: int | None = None,
        limit: int = 200,
    ) -> list[QueueTask]:
        query = select(QueueTask).where(
            QueueTask.tenant_id == tenant_id,
            QueueTask.channel == QueueChannel.ONLINE_CHAT.value,
            QueueTask.status == QueueTaskStatus.QUEUED.value,
        )
        if scope_predicate is not None:
            query = query.where(scope_predicate)
        if queue_type and queue_id:
            query = query.where(QueueTask.queue_type == queue_type, QueueTask.queue_id == queue_id)
        query = query.order_by(QueueTask.priority.asc(), QueueTask.enqueued_at.asc(), QueueTask.id.asc()).limit(limit)
        return list((await db.execute(query)).scalars().all())

    @staticmethod
    async def count_queued_tasks(
        db: AsyncSession,
        tenant_id: int,
        *,
        scope_predicate: ColumnElement | None = None,
        queue_type: str | None = None,
        queue_id: int | None = None,
    ) -> int:
        query = select(func.count()).select_from(QueueTask).where(
            QueueTask.tenant_id == tenant_id,
            QueueTask.channel == QueueChannel.ONLINE_CHAT.value,
            QueueTask.status == QueueTaskStatus.QUEUED.value,
        )
        if scope_predicate is not None:
            query = query.where(scope_predicate)
        if queue_type and queue_id:
            query = query.where(QueueTask.queue_type == queue_type, QueueTask.queue_id == queue_id)
        return int((await db.execute(query)).scalar_one() or 0)

    @staticmethod
    async def count_queued_tasks_by_queue(
        db: AsyncSession,
        tenant_id: int,
        *,
        scope_predicate: ColumnElement | None = None,
    ) -> list[tuple[str, int, int]]:
        query = (
            select(QueueTask.queue_type, QueueTask.queue_id, func.count())
            .where(
                QueueTask.tenant_id == tenant_id,
                QueueTask.channel == QueueChannel.ONLINE_CHAT.value,
                QueueTask.status == QueueTaskStatus.QUEUED.value,
            )
            .group_by(QueueTask.queue_type, QueueTask.queue_id)
        )
        if scope_predicate is not None:
            query = query.where(scope_predicate)
        result = await db.execute(query)
        return [(str(queue_type), int(queue_id), int(count)) for queue_type, queue_id, count in result.all()]

    @staticmethod
    async def get_queued_task(db: AsyncSession, tenant_id: int, task_id: int) -> QueueTask | None:
        result = await db.execute(
            select(QueueTask).where(
                QueueTask.tenant_id == tenant_id,
                QueueTask.id == task_id,
                QueueTask.channel == QueueChannel.ONLINE_CHAT.value,
                QueueTask.status == QueueTaskStatus.QUEUED.value,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_conversations_by_ids(
        db: AsyncSession,
        tenant_id: int,
        conversation_ids: list[int],
    ) -> dict[int, Conversation]:
        if not conversation_ids:
            return {}
        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(Conversation.tenant_id == tenant_id, Conversation.id.in_(conversation_ids))
        )
        return {conversation.id: conversation for conversation in result.scalars().all()}

    @staticmethod
    async def get_group_names(db: AsyncSession, tenant_id: int, group_ids: list[int]) -> dict[int, str]:
        if not group_ids:
            return {}
        result = await db.execute(
            select(EmployeeGroup.id, EmployeeGroup.name).where(
                EmployeeGroup.tenant_id == tenant_id,
                EmployeeGroup.id.in_(group_ids),
            )
        )
        return {int(group_id): name for group_id, name in result.all()}

    @staticmethod
    async def get_employee_names(db: AsyncSession, tenant_id: int, employee_ids: list[int]) -> dict[int, str]:
        if not employee_ids:
            return {}
        result = await db.execute(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.id.in_(employee_ids),
            )
        )
        names: dict[int, str] = {}
        for employee in result.scalars().all():
            names[employee.id] = employee.display_name or employee.nickname or employee.name or employee.username
        return names

    @staticmethod
    async def get_agent_group_names(
        db: AsyncSession,
        tenant_id: int,
        employee_ids: list[int],
    ) -> dict[int, list[tuple[int, str]]]:
        if not employee_ids:
            return {}
        result = await db.execute(
            select(EmployeeGroupMember.employee_id, EmployeeGroup.id, EmployeeGroup.name)
            .join(EmployeeGroup, EmployeeGroup.id == EmployeeGroupMember.group_id)
            .where(
                EmployeeGroup.tenant_id == tenant_id,
                EmployeeGroupMember.employee_id.in_(employee_ids),
            )
            .order_by(EmployeeGroup.name.asc())
        )
        grouped: dict[int, list[tuple[int, str]]] = {employee_id: [] for employee_id in employee_ids}
        for employee_id, group_id, group_name in result.all():
            grouped.setdefault(int(employee_id), []).append((int(group_id), group_name))
        return grouped

    @staticmethod
    def build_queue_scope_predicate(
        *,
        employee_id: int,
        group_ids: list[int],
        peer_employee_ids: list[int],
        scope: str,
    ) -> ColumnElement | None:
        if scope == "all":
            return None
        clauses: list[ColumnElement] = []
        if group_ids:
            clauses.append(and_(QueueTask.queue_type == "employee_group", QueueTask.queue_id.in_(group_ids)))
        if scope == "group":
            allowed_employee_ids = sorted(set(peer_employee_ids) | {employee_id})
            if allowed_employee_ids:
                clauses.append(and_(QueueTask.queue_type == "employee", QueueTask.queue_id.in_(allowed_employee_ids)))
        else:
            clauses.append(and_(QueueTask.queue_type == "employee", QueueTask.queue_id == employee_id))
        return or_(*clauses) if clauses else false()
