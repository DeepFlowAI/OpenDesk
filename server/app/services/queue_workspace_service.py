"""
Workspace queue service.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.enums import (
    AgentOnlineStatus,
    MessageContentType,
    MessageSenderType,
    QueueChannel,
    QueueTaskType,
    QueueType,
)
from app.libs.realtime import get_realtime_transport
from app.models.conversation import Conversation
from app.models.queue import QueueTask
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.queue_repository import QueueTaskRepository
from app.repositories.queue_workspace_repository import QueueWorkspaceRepository
from app.schemas.permission import EffectivePrincipal
from app.schemas.queue import QueueAdminAssignRequest, QueueEnqueueRequest
from app.schemas.queue_workspace import (
    QueueAssignAndSendRequest,
    QueueAssignAndSendResponse,
    QueueAssignableAgentListResponse,
    QueueAssignRequest,
    QueueAssignSelfRequest,
    QueueAssignmentWorkspaceResponse,
    QueueWorkspaceCountResponse,
    QueueWorkspaceQueueBrief,
    QueueWorkspaceTaskDetail,
    QueueWorkspaceTaskItem,
    QueueWorkspaceTaskListResponse,
)
from app.services.agent_status_service import AgentStatusService
from app.services.conversation_realtime_service import ConversationRealtimeService
from app.services.conversation_service import AGENT_ASSIGNED_EVENT_TYPE, ConversationService
from app.services.data_scope_service import DataScopeService, RESOURCE_CHAT_QUEUE
from app.services.queue_service import QueueTaskService

logger = logging.getLogger(__name__)

QUEUE_VIEW_PERMISSION = "chat.queue.view"
QUEUE_ASSIGN_SELF_PERMISSION = "chat.queue.assign_self"
QUEUE_ASSIGN_OTHER_PERMISSION = "chat.queue.assign_other"
MAX_QUEUE_TASKS = 200
QUEUE_DETAIL_MESSAGE_LIMIT = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class QueueWorkspaceService:
    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        principal: EffectivePrincipal,
        *,
        queue_type: str | None = None,
        queue_id: int | None = None,
        q: str | None = None,
    ) -> QueueWorkspaceTaskListResponse:
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        scope = DataScopeService.get_scope(principal, RESOURCE_CHAT_QUEUE)
        queue_predicate = QueueWorkspaceRepository.build_queue_scope_predicate(
            employee_id=principal.user_id,
            group_ids=principal.group_ids,
            peer_employee_ids=peer_ids,
            scope=scope,
        )
        queue_filter_type, queue_filter_id = QueueWorkspaceService._normalize_queue_filter(queue_type, queue_id)

        queue_counts = await QueueWorkspaceRepository.count_queued_tasks_by_queue(
            db,
            principal.tenant_id,
            scope_predicate=queue_predicate,
        )
        queue_names = await QueueWorkspaceService._queue_names_for_keys(
            db,
            principal.tenant_id,
            [(queue_type, queue_id) for queue_type, queue_id, _count in queue_counts],
        )
        visible_queues = QueueWorkspaceService._visible_queues(queue_counts, queue_names)

        tasks = await QueueWorkspaceRepository.list_queued_tasks(
            db,
            principal.tenant_id,
            scope_predicate=queue_predicate,
            queue_type=queue_filter_type,
            queue_id=queue_filter_id,
            limit=MAX_QUEUE_TASKS,
        )

        conversation_map = await QueueWorkspaceService._conversation_map_for_tasks(db, principal.tenant_id, tasks)
        items = [
            await QueueWorkspaceService._task_item(db, task, conversation_map.get(QueueWorkspaceService._conversation_id(task)), queue_names)
            for task in tasks
        ]
        items = QueueWorkspaceService._filter_items(items, q)
        items.sort(
            key=lambda item: (
                item.priority,
                _to_utc_aware(item.enqueued_at) or datetime.max.replace(tzinfo=timezone.utc),
                item.id,
            )
        )
        return QueueWorkspaceTaskListResponse(items=items, total=len(items), visible_queues=visible_queues)

    @staticmethod
    async def count_tasks(
        db: AsyncSession,
        principal: EffectivePrincipal,
        *,
        queue_type: str | None = None,
        queue_id: int | None = None,
    ) -> QueueWorkspaceCountResponse:
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        scope = DataScopeService.get_scope(principal, RESOURCE_CHAT_QUEUE)
        queue_predicate = QueueWorkspaceRepository.build_queue_scope_predicate(
            employee_id=principal.user_id,
            group_ids=principal.group_ids,
            peer_employee_ids=peer_ids,
            scope=scope,
        )
        queue_filter_type, queue_filter_id = QueueWorkspaceService._normalize_queue_filter(queue_type, queue_id)

        task_count = await QueueWorkspaceRepository.count_queued_tasks(
            db,
            principal.tenant_id,
            scope_predicate=queue_predicate,
            queue_type=queue_filter_type,
            queue_id=queue_filter_id,
        )
        return QueueWorkspaceCountResponse(total=task_count)

    @staticmethod
    async def get_detail(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
    ) -> QueueWorkspaceTaskDetail:
        task, conversation = await QueueWorkspaceService._get_visible_task(db, principal, task_id)
        queue_names = await QueueWorkspaceService._queue_names(
            db,
            principal.tenant_id,
            [task],
        )
        item = await QueueWorkspaceService._task_item(db, task, conversation, queue_names)
        messages = []
        if conversation:
            raw_messages = await MessageRepository.get_by_conversation(
                db,
                conversation.id,
                limit=QUEUE_DETAIL_MESSAGE_LIMIT,
                include_internal=True,
            )
            messages = await QueueWorkspaceService._message_items(db, conversation.tenant_id, raw_messages)

        can_assign_self = principal.has_permission(QUEUE_ASSIGN_SELF_PERMISSION)
        can_assign_other = (
            principal.has_permission(QUEUE_ASSIGN_OTHER_PERMISSION)
            and DataScopeService.get_scope(principal, RESOURCE_CHAT_QUEUE) != "self"
        )
        return QueueWorkspaceTaskDetail(
            **item.model_dump(),
            messages=messages,
            can_assign_self=can_assign_self,
            can_assign_other=can_assign_other,
        )

    @staticmethod
    async def list_assignable_agents(
        db: AsyncSession,
        r: aioredis.Redis,
        principal: EffectivePrincipal,
        *,
        q: str | None = None,
    ) -> QueueAssignableAgentListResponse:
        scope = DataScopeService.get_scope(principal, RESOURCE_CHAT_QUEUE)
        if scope == "self":
            raise ForbiddenError("Permission denied")

        employees = await EmployeeRepository.get_transfer_candidates(
            db,
            principal.tenant_id,
            exclude_user_ids=[principal.user_id],
            keyword=q,
            limit=200,
        )
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        allowed_ids = QueueWorkspaceService._assignable_agent_ids(principal, scope, peer_ids)
        if allowed_ids is not None:
            employees = [employee for employee in employees if employee.id in allowed_ids]

        group_names = await QueueWorkspaceRepository.get_agent_group_names(
            db,
            principal.tenant_id,
            [employee.id for employee in employees],
        )
        statuses = await AgentStatusService.get_statuses_bulk(
            r,
            principal.tenant_id,
            [(employee.id, employee.max_concurrent or 10) for employee in employees],
        )
        items = []
        for employee in employees:
            status = statuses.get(employee.id) or {}
            groups = group_names.get(employee.id, [])
            online_status = status.get("status", AgentOnlineStatus.OFFLINE.value)
            items.append({
                "id": employee.id,
                "name": employee.name or employee.username,
                "display_name": employee.display_name,
                "job_number": employee.job_number,
                "avatar": employee.avatar,
                "group_ids": [group_id for group_id, _ in groups],
                "group_names": [name for _, name in groups],
                "online_status": online_status,
                "current_count": int(status.get("current_count", 0)),
                "max_concurrent": int(status.get("max_concurrent", employee.max_concurrent or 10)),
                "selectable": online_status == AgentOnlineStatus.ONLINE.value,
            })
        priority = {AgentOnlineStatus.ONLINE.value: 0, AgentOnlineStatus.BUSY.value: 1, AgentOnlineStatus.OFFLINE.value: 2}
        items.sort(key=lambda item: (priority.get(item["online_status"], 9), item["display_name"] or item["name"]))
        if not items:
            logger.warning(
                "assignable_agents_empty tenant_id=%s user_id=%s scope=%s keyword=%s",
                principal.tenant_id,
                principal.user_id,
                scope,
                q,
            )
        return QueueAssignableAgentListResponse(items=items, total=len(items))

    @staticmethod
    async def assign_self(
        db: AsyncSession,
        r: aioredis.Redis,
        principal: EffectivePrincipal,
        task_id: int,
        body: QueueAssignSelfRequest,
    ) -> QueueAssignmentWorkspaceResponse:
        if not principal.has_permission(QUEUE_ASSIGN_SELF_PERMISSION):
            raise ForbiddenError("Permission denied")
        return await QueueWorkspaceService._assign_to_agent(
            db,
            r,
            principal,
            task_id,
            principal.user_id,
            reason=body.reason,
        )

    @staticmethod
    async def assign_self_and_send(
        db: AsyncSession,
        r: aioredis.Redis,
        principal: EffectivePrincipal,
        task_id: int,
        body: QueueAssignAndSendRequest,
    ) -> QueueAssignAndSendResponse:
        if not principal.has_permission(QUEUE_ASSIGN_SELF_PERMISSION):
            raise ForbiddenError("Permission denied")

        assignment = await QueueWorkspaceService._assign_to_agent(
            db,
            r,
            principal,
            task_id,
            principal.user_id,
        )
        conversation_id = assignment.conversation_id
        if conversation_id is None:
            return QueueAssignAndSendResponse(
                **assignment.model_dump(),
                message=None,
                message_sent=False,
            )

        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        try:
            message = await ConversationService.send_message(
                db,
                conversation_id=conversation_id,
                sender_type=MessageSenderType.AGENT.value,
                sender_id=principal.user_id,
                content_type=MessageContentType.TEXT.value,
                content=body.content,
                tenant_id=principal.tenant_id,
                principal=principal,
            )
        except BusinessError:
            logger.warning(
                "queue_task_assign_send_message_failed tenant_id=%s user_id=%s queue_task_id=%s conversation_id=%s",
                principal.tenant_id,
                principal.user_id,
                task_id,
                conversation_id,
            )
            return QueueAssignAndSendResponse(
                **assignment.model_dump(),
                message=None,
                message_sent=False,
            )

        if conversation is not None:
            await QueueWorkspaceService._emit_sent_message_events(
                conversation,
                message,
                principal.user_id,
            )

        logger.info(
            "queue_task_assigned_and_sent tenant_id=%s user_id=%s queue_task_id=%s conversation_id=%s message_id=%s",
            principal.tenant_id,
            principal.user_id,
            task_id,
            conversation_id,
            message.id,
        )
        return QueueAssignAndSendResponse(
            **assignment.model_dump(),
            message=QueueWorkspaceService._message_response_item(message, conversation),
            message_sent=True,
        )

    @staticmethod
    async def assign_to_agent(
        db: AsyncSession,
        r: aioredis.Redis,
        principal: EffectivePrincipal,
        task_id: int,
        body: QueueAssignRequest,
    ) -> QueueAssignmentWorkspaceResponse:
        if not principal.has_permission(QUEUE_ASSIGN_OTHER_PERMISSION):
            raise ForbiddenError("Permission denied")
        scope = DataScopeService.get_scope(principal, RESOURCE_CHAT_QUEUE)
        if scope == "self":
            raise ForbiddenError("Permission denied")
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        allowed_ids = QueueWorkspaceService._assignable_agent_ids(principal, scope, peer_ids)
        if allowed_ids is not None and body.agent_id not in allowed_ids:
            logger.warning(
                "queue_task_assign_rejected tenant_id=%s operator_id=%s target_agent_id=%s "
                "queue_task_id=%s scope=%s reason=target_outside_scope",
                principal.tenant_id,
                principal.user_id,
                body.agent_id,
                task_id,
                scope,
            )
            raise ForbiddenError("Permission denied")
        return await QueueWorkspaceService._assign_to_agent(
            db,
            r,
            principal,
            task_id,
            body.agent_id,
            reason=body.reason,
        )

    @staticmethod
    async def enqueue_conversation_if_needed(
        db: AsyncSession,
        tenant_id: int,
        conversation: Conversation,
        *,
        source_type: str = "visitor_waiting",
    ):
        if conversation.agent_id is not None or conversation.status != "queued":
            logger.debug(
                "queue_task_enqueue_skipped tenant_id=%s conversation_id=%s agent_id=%s status=%s reason=not_queued",
                tenant_id,
                conversation.id,
                conversation.agent_id,
                conversation.status,
            )
            return None
        if conversation.group_id is None:
            logger.warning(
                "queue_task_enqueue_skipped tenant_id=%s conversation_id=%s reason=missing_group",
                tenant_id,
                conversation.id,
            )
            return None
        queue_type = QueueType.EMPLOYEE_GROUP.value
        queue_id = conversation.group_id
        duplicate = await QueueTaskRepository.get_active_task_by_ref(
            db,
            tenant_id,
            QueueChannel.ONLINE_CHAT.value,
            QueueTaskType.CONVERSATION.value,
            str(conversation.id),
        )
        if duplicate:
            logger.debug(
                "queue_task_enqueue_skipped tenant_id=%s conversation_id=%s queue_task_id=%s reason=duplicate",
                tenant_id,
                conversation.id,
                duplicate.id,
            )
            position = await QueueTaskService.get_position_for_task(db, tenant_id, duplicate.id)
            return SimpleNamespace(accepted=False, duplicate=True, task=duplicate, position=position)

        result = await QueueTaskService.enqueue_task(
            db,
            tenant_id,
            QueueEnqueueRequest(
                channel=QueueChannel.ONLINE_CHAT,
                task_type=QueueTaskType.CONVERSATION,
                task_ref_id=str(conversation.id),
                task_ref_public_id=conversation.public_id,
                queue_type=QueueType.EMPLOYEE_GROUP,
                queue_id=int(queue_id),
                priority=5,
                source_type=source_type,
                source_context={"conversation_id": conversation.id, "channel_id": conversation.channel_id},
            ),
        )
        logger.info(
            "queue_task_enqueued tenant_id=%s conversation_id=%s queue_task_id=%s "
            "queue_type=%s queue_id=%s source_type=%s",
            tenant_id,
            conversation.id,
            result.task.id if result.task else None,
            result.task.queue_type if result.task else queue_type,
            result.task.queue_id if result.task else queue_id,
            source_type,
        )
        return result

    @staticmethod
    async def _assign_to_agent(
        db: AsyncSession,
        r: aioredis.Redis,
        principal: EffectivePrincipal,
        task_id: int,
        agent_id: int,
        *,
        reason: str | None = None,
    ) -> QueueAssignmentWorkspaceResponse:
        task, conversation = await QueueWorkspaceService._get_visible_task(db, principal, task_id)
        if not await EmployeeRepository.has_effective_permission(
            db,
            principal.tenant_id,
            agent_id,
            "chat.workspace.use",
        ):
            logger.warning(
                "queue_task_assign_rejected tenant_id=%s operator_id=%s target_agent_id=%s "
                "queue_task_id=%s conversation_id=%s reason=agent_not_found_or_no_workspace",
                principal.tenant_id,
                principal.user_id,
                agent_id,
                task.id,
                conversation.id,
            )
            raise NotFoundError("Agent not found")

        assigned_task = await QueueTaskService.admin_assign(
            db,
            r,
            principal.tenant_id,
            principal.user_id,
            task.id,
            QueueAdminAssignRequest(agent_id=agent_id, reason=reason),
        )
        conversation_id = QueueWorkspaceService._conversation_id(assigned_task)
        assigned_conversation = (
            await ConversationRepository.get_by_id(db, conversation_id)
            if conversation_id is not None
            else None
        )
        assignment_note = await QueueWorkspaceService._create_assignment_internal_note(
            db,
            principal,
            assigned_conversation,
            reason,
        )
        await QueueWorkspaceService._emit_assignment_events(
            assigned_conversation,
            agent_id,
            db=db,
            operator_id=principal.user_id,
            assignment_note=assignment_note,
        )
        queue_names = await QueueWorkspaceService._queue_names(db, principal.tenant_id, [assigned_task])
        item = await QueueWorkspaceService._task_item(db, assigned_task, assigned_conversation, queue_names)
        logger.info(
            "queue_task_assigned tenant_id=%s operator_id=%s target_agent_id=%s "
            "queue_task_id=%s conversation_id=%s assigned_to_current_user=%s",
            principal.tenant_id,
            principal.user_id,
            agent_id,
            assigned_task.id,
            conversation_id,
            agent_id == principal.user_id,
        )
        return QueueAssignmentWorkspaceResponse(
            task=item,
            conversation_id=conversation_id,
            assigned_agent=assigned_conversation.agent if assigned_conversation else None,
            assigned_to_current_user=agent_id == principal.user_id,
        )

    @staticmethod
    async def _get_visible_task(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
    ) -> tuple[QueueTask, Conversation]:
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        scope = DataScopeService.get_scope(principal, RESOURCE_CHAT_QUEUE)
        task = await QueueWorkspaceRepository.get_queued_task(db, principal.tenant_id, task_id)
        if not task:
            logger.warning(
                "queue_task_not_visible tenant_id=%s user_id=%s queue_task_id=%s reason=not_found",
                principal.tenant_id,
                principal.user_id,
                task_id,
            )
            raise NotFoundError("Queue task not found")
        queue_predicate = QueueWorkspaceRepository.build_queue_scope_predicate(
            employee_id=principal.user_id,
            group_ids=principal.group_ids,
            peer_employee_ids=peer_ids,
            scope=scope,
        )
        visible = await QueueWorkspaceRepository.list_queued_tasks(
            db,
            principal.tenant_id,
            scope_predicate=queue_predicate,
            queue_type=task.queue_type,
            queue_id=task.queue_id,
            limit=MAX_QUEUE_TASKS,
        )
        if task.id not in {item.id for item in visible}:
            logger.warning(
                "queue_task_not_visible tenant_id=%s user_id=%s queue_task_id=%s "
                "queue_type=%s queue_id=%s scope=%s reason=scope_filtered",
                principal.tenant_id,
                principal.user_id,
                task.id,
                task.queue_type,
                task.queue_id,
                scope,
            )
            raise ForbiddenError("Permission denied")
        conversation = await QueueWorkspaceService._conversation_for_task(db, principal.tenant_id, task)
        if conversation is None:
            logger.warning(
                "queue_task_not_visible tenant_id=%s user_id=%s queue_task_id=%s "
                "task_ref_id=%s reason=conversation_missing",
                principal.tenant_id,
                principal.user_id,
                task.id,
                task.task_ref_id,
            )
            raise NotFoundError("Conversation not found")
        return task, conversation

    @staticmethod
    async def _conversation_map_for_tasks(
        db: AsyncSession,
        tenant_id: int,
        tasks: list[QueueTask],
    ) -> dict[int, Conversation]:
        conversation_ids = [
            conversation_id
            for conversation_id in (QueueWorkspaceService._conversation_id(task) for task in tasks)
            if conversation_id is not None
        ]
        return await QueueWorkspaceRepository.get_conversations_by_ids(db, tenant_id, conversation_ids)

    @staticmethod
    async def _conversation_for_task(
        db: AsyncSession,
        tenant_id: int,
        task: QueueTask,
    ) -> Conversation | None:
        conversation_id = QueueWorkspaceService._conversation_id(task)
        if conversation_id is None:
            return None
        return (await QueueWorkspaceRepository.get_conversations_by_ids(db, tenant_id, [conversation_id])).get(conversation_id)

    @staticmethod
    def _conversation_id(task: QueueTask) -> int | None:
        if task.task_type not in [QueueTaskType.CONVERSATION.value, QueueTaskType.OPEN_AGENT_HANDOFF.value]:
            return None
        try:
            return int(task.task_ref_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    async def _queue_names(
        db: AsyncSession,
        tenant_id: int,
        tasks: list[QueueTask],
    ) -> dict[tuple[str, int], str | None]:
        return await QueueWorkspaceService._queue_names_for_keys(
            db,
            tenant_id,
            [(task.queue_type, task.queue_id) for task in tasks],
        )

    @staticmethod
    async def _queue_names_for_keys(
        db: AsyncSession,
        tenant_id: int,
        queue_keys: list[tuple[str, int]],
    ) -> dict[tuple[str, int], str | None]:
        group_ids = {
            queue_id for queue_type, queue_id in queue_keys if queue_type == QueueType.EMPLOYEE_GROUP.value
        }
        employee_ids = {queue_id for queue_type, queue_id in queue_keys if queue_type == QueueType.EMPLOYEE.value}
        group_names = await QueueWorkspaceRepository.get_group_names(db, tenant_id, list(group_ids))
        employee_names = await QueueWorkspaceRepository.get_employee_names(db, tenant_id, list(employee_ids))
        names: dict[tuple[str, int], str | None] = {}
        for group_id, name in group_names.items():
            names[(QueueType.EMPLOYEE_GROUP.value, group_id)] = name
        for employee_id, name in employee_names.items():
            names[(QueueType.EMPLOYEE.value, employee_id)] = name
        return names

    @staticmethod
    async def _task_item(
        db: AsyncSession,
        task: QueueTask,
        conversation: Conversation | None,
        queue_names: dict[tuple[str, int], str | None],
    ) -> QueueWorkspaceTaskItem:
        position = await QueueTaskRepository.position_for_task(db, task)
        enqueued_at = _to_utc_aware(task.enqueued_at)
        return QueueWorkspaceTaskItem(
            id=task.id,
            source="queue_task",
            queue_task_id=task.id,
            conversation_id=conversation.id if conversation else QueueWorkspaceService._conversation_id(task),
            conversation_public_id=conversation.public_id if conversation else task.task_ref_public_id,
            visitor=conversation.visitor if conversation else None,
            channel=conversation.channel if conversation else None,
            group=conversation.group if conversation else None,
            queue=QueueWorkspaceQueueBrief(
                queue_type=task.queue_type,
                queue_id=task.queue_id,
                name=queue_names.get((task.queue_type, task.queue_id)),
            ),
            priority=task.priority,
            status=task.status,
            source_type=task.source_type,
            last_message_preview=conversation.last_message_preview if conversation else None,
            last_message_at=conversation.last_message_at if conversation else None,
            enqueued_at=enqueued_at,
            wait_seconds=QueueWorkspaceService._wait_seconds(enqueued_at),
            position_overall=position[0],
            position_in_priority=position[1],
        )

    @staticmethod
    def _wait_seconds(enqueued_at: datetime | None) -> int:
        if enqueued_at is None:
            return 0
        return max(0, int((_now() - enqueued_at).total_seconds()))

    @staticmethod
    def _filter_items(items: list[QueueWorkspaceTaskItem], q: str | None) -> list[QueueWorkspaceTaskItem]:
        term = (q or "").strip().lower()
        if not term:
            return items
        filtered = []
        for item in items:
            values = [
                item.visitor.name if item.visitor else None,
                item.visitor.external_id if item.visitor else None,
                item.last_message_preview,
                item.queue.name,
            ]
            if any(value and term in value.lower() for value in values):
                filtered.append(item)
        return filtered

    @staticmethod
    def _visible_queues(
        queue_counts: list[tuple[str, int, int]],
        queue_names: dict[tuple[str, int], str | None],
    ) -> list[QueueWorkspaceQueueBrief]:
        queues = [
            QueueWorkspaceQueueBrief(
                queue_type=queue_type,
                queue_id=queue_id,
                name=queue_names.get((queue_type, queue_id)),
                waiting_count=count,
            )
            for queue_type, queue_id, count in queue_counts
        ]
        queues.sort(key=lambda queue: (queue.name or "", queue.queue_type, queue.queue_id))
        return queues

    @staticmethod
    def _normalize_queue_filter(queue_type: str | None, queue_id: int | None) -> tuple[str | None, int | None]:
        if not queue_type or queue_id is None:
            return None, None
        if queue_type not in [QueueType.EMPLOYEE_GROUP.value, QueueType.EMPLOYEE.value]:
            return None, None
        return queue_type, queue_id

    @staticmethod
    def _assignable_agent_ids(
        principal: EffectivePrincipal,
        scope: str,
        peer_employee_ids: list[int],
    ) -> set[int] | None:
        if scope == "all":
            return None
        return set(peer_employee_ids) | {principal.user_id}

    @staticmethod
    async def _message_items(db: AsyncSession, tenant_id: int, messages: list) -> list[dict[str, Any]]:
        agent_ids = list({
            msg.sender_id
            for msg in messages
            if msg.sender_type == "agent" and msg.sender_id is not None
        })
        agents = await EmployeeRepository.get_by_ids(db, agent_ids)
        agent_map = {agent.id: agent for agent in agents if agent.tenant_id == tenant_id}
        items = []
        for msg in messages:
            metadata = getattr(msg, "metadata_", None) or {}
            sender_name = None
            sender_avatar = None
            if msg.sender_type == "agent" and msg.sender_id is not None:
                agent = agent_map.get(msg.sender_id)
                if agent:
                    sender_name = agent.display_name or agent.name
                    sender_avatar = agent.avatar
            elif msg.sender_type == "bot":
                sender_name = ConversationService._metadata_sender_name(msg.sender_type, metadata)
            items.append(ConversationService._message_response_payload(
                msg,
                conversation_id=msg.conversation_id,
                sender_name=sender_name,
                sender_avatar=sender_avatar,
                visitor_facing=False,
            ))
        return items

    @staticmethod
    async def _create_assignment_internal_note(
        db: AsyncSession,
        principal: EffectivePrincipal,
        conversation: Conversation | None,
        reason: str | None,
    ):
        note = (reason or "").strip()
        if not note or conversation is None:
            return None
        return await ConversationService.send_message(
            db,
            conversation_id=conversation.id,
            sender_type=MessageSenderType.AGENT.value,
            sender_id=principal.user_id,
            content_type=MessageContentType.INTERNAL_NOTE.value,
            content=note,
            tenant_id=principal.tenant_id,
        )

    @staticmethod
    async def _emit_assignment_events(
        conversation: Conversation | None,
        agent_id: int,
        *,
        db: AsyncSession | None = None,
        operator_id: int | None = None,
        assignment_note=None,
    ) -> None:
        if conversation is None:
            return
        try:
            rt = get_realtime_transport()
            tenant_id = conversation.tenant_id
            agent_room = f"agent:{tenant_id}:{agent_id}"
            await rt.emit(
                "new_conversation",
                {
                    "conversation_id": conversation.id,
                    "visitor": (
                        {
                            "id": conversation.visitor.id,
                            "public_id": conversation.visitor.public_id,
                            "name": conversation.visitor.name,
                            "avatar_color": conversation.visitor.avatar_color,
                        }
                        if conversation.visitor
                        else None
                    ),
                    "channel": {"id": conversation.channel_id} if conversation.channel_id else None,
                },
                room=agent_room,
                namespace="/chat",
            )
            await rt.emit(
                "conversation_assigned",
                {
                    "conversation_id": conversation.id,
                    "conversation_public_id": conversation.public_id,
                    "agent": (
                        {
                            "id": conversation.agent.id,
                            "name": ConversationService.visitor_agent_display_name(conversation.agent),
                            "avatar": conversation.agent.avatar,
                        }
                        if conversation.agent
                        else None
                    ),
                },
                room=f"conv:{conversation.id}",
                namespace="/visitor",
            )
            if db is not None:
                assigned_msg = await MessageRepository.get_event_message(
                    db,
                    tenant_id,
                    conversation.id,
                    AGENT_ASSIGNED_EVENT_TYPE,
                )
                if assigned_msg is not None:
                    await QueueWorkspaceService._emit_message_events(
                        rt,
                        conversation,
                        assigned_msg,
                        {agent_id},
                    )
                welcome_msg = await MessageRepository.get_welcome_message(
                    db,
                    tenant_id,
                    conversation.id,
                )
                if welcome_msg is not None:
                    await QueueWorkspaceService._emit_message_events(
                        rt,
                        conversation,
                        welcome_msg,
                        {agent_id},
                    )
                if assignment_note is not None:
                    recipient_agent_ids = {agent_id}
                    if operator_id is not None:
                        recipient_agent_ids.add(operator_id)
                    await QueueWorkspaceService._emit_message_events(
                        rt,
                        conversation,
                        assignment_note,
                        recipient_agent_ids,
                        to_visitor=False,
                    )
            await ConversationRealtimeService.emit_conversation_list_updated(
                tenant_id,
                action="assigned",
                conversation_id=conversation.id,
                rt=rt,
            )
        except Exception:
            logger.exception("Failed to emit queue assignment events for conversation %s", conversation.id)

    @staticmethod
    async def _emit_message_events(
        rt,
        conversation: Conversation,
        message,
        agent_ids: set[int],
        *,
        to_visitor: bool = True,
    ) -> None:
        tenant_id = conversation.tenant_id
        msg_payload = ConversationService._public_message_payload(message, conversation)
        conv_room = f"conv:{conversation.id}"
        agent_payload = {**msg_payload, "conversation_id": conversation.id}
        agent_payload.pop("conversation_public_id", None)
        preview = ConversationService.build_message_preview(
            message.content_type,
            message.content,
        )
        created_at = msg_payload.get("created_at")
        conversation_updated_payload = {
            "conversation_id": conversation.id,
            "last_message_preview": preview,
            "last_message_at": created_at,
            "unread_count": conversation.unread_count,
        }
        if to_visitor:
            primary_agent_id = next(iter(agent_ids))
            agent_room = f"agent:{tenant_id}:{primary_agent_id}"
            await rt.emit("new_message", msg_payload, room=conv_room, namespace="/visitor")
            await rt.emit("new_message", agent_payload, room=agent_room, namespace="/chat")
            await rt.emit("conversation_updated", conversation_updated_payload, room=agent_room, namespace="/chat")
            return
        for agent_id in agent_ids:
            agent_room = f"agent:{tenant_id}:{agent_id}"
            await rt.emit("new_message", agent_payload, room=agent_room, namespace="/chat")
            await rt.emit("conversation_updated", conversation_updated_payload, room=agent_room, namespace="/chat")
        await rt.emit("new_message", agent_payload, room=conv_room, namespace="/chat")
        await rt.emit("conversation_updated", conversation_updated_payload, room=conv_room, namespace="/chat")

    @staticmethod
    async def _emit_sent_message_events(
        conversation: Conversation,
        message,
        agent_id: int,
    ) -> None:
        try:
            rt = get_realtime_transport()
            await QueueWorkspaceService._emit_message_events(
                rt,
                conversation,
                message,
                {agent_id},
            )
        except Exception:
            logger.exception("Failed to emit queue assign-and-send message events for conversation %s", conversation.id)

    @staticmethod
    def _message_response_item(message, conversation: Conversation | None) -> dict[str, Any]:
        sender_name = None
        sender_avatar = None
        if conversation is not None and message.sender_type == MessageSenderType.AGENT.value and conversation.agent:
            sender_name = conversation.agent.display_name or conversation.agent.name
            sender_avatar = conversation.agent.avatar
        return ConversationService._message_response_payload(
            message,
            conversation_id=message.conversation_id,
            sender_name=sender_name,
            sender_avatar=sender_avatar,
            visitor_facing=False,
        )
