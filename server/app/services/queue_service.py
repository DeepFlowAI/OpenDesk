"""
Unified queue engine service.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, ConflictError, NotFoundError, ValidationError
from app.enums import (
    QueueAssignmentStrategy,
    QueueAssignmentType,
    QueueChannel,
    QueuePolicyScopeType,
    QueueTaskStatus,
    QueueTaskType,
    QueueType,
)
from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup
from app.models.queue import QueueTask
from app.repositories.queue_repository import (
    QueueBusinessRepository,
    QueueCandidateRepository,
    QueueEventRepository,
    QueuePolicyRepository,
    QueueRoundRobinRepository,
    QueueReturningAgentRepository,
    QueueTaskRepository,
)
from app.schemas.queue import (
    QueueAdminAssignRequest,
    QueueDispatchRequest,
    QueueDispatchResponse,
    QueueEnqueueRequest,
    QueueEnqueueResponse,
    QueuePolicyUpsert,
    QueuePositionResponse,
    QueuePriorityStat,
    QueuePullRequest,
    QueueStateResponse,
    QueueTaskActionRequest,
    RETURNING_AGENT_DEFAULT_WINDOW_HOURS,
    RETURNING_AGENT_MAX_WINDOW_HOURS,
    RETURNING_AGENT_MIN_WINDOW_HOURS,
    RETURNING_AGENT_PRIORITY_ENABLED_KEY,
    RETURNING_AGENT_WINDOW_HOURS_KEY,
    normalize_queue_assignment_strategy,
)
from app.services.queue_resource_provider import QueueResourceProviderFactory
from app.services.queue_realtime_service import QueueRealtimeService
from app.services.queue_strategy import QueueCandidate, QueueStrategyService


DEFAULT_QUEUE_POLICY = {
    "assignment_strategy": QueueAssignmentStrategy.ROUND_ROBIN.value,
    "max_waiting_count": None,
    "max_wait_seconds": None,
    "config": {},
    "policy_source": "default",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class QueuePolicyService:
    @staticmethod
    async def list_policies(
        db: AsyncSession,
        tenant_id: int,
        *,
        channel: str | None = None,
        scope_type: str | None = None,
        scope_id: int | None = None,
    ) -> dict:
        items = await QueuePolicyRepository.list_policies(
            db,
            tenant_id,
            channel=channel,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        return {
            "items": items,
            "total": len(items),
            "page": 1,
            "per_page": len(items),
            "pages": 1 if items else 0,
        }

    @staticmethod
    async def upsert_policy(db: AsyncSession, tenant_id: int, data: QueuePolicyUpsert):
        payload = data.model_dump(mode="json")
        policy = await QueuePolicyRepository.upsert_policy(db, tenant_id, payload)
        await db.commit()
        await db.refresh(policy)
        return policy


class QueuePolicyResolver:
    @staticmethod
    async def resolve(
        db: AsyncSession,
        tenant_id: int,
        *,
        channel: str,
        queue_type: str,
        queue_id: int,
        explicit_strategy: str | None = None,
    ) -> dict[str, Any]:
        global_policy = await QueuePolicyRepository.get_policy(
            db,
            tenant_id,
            channel,
            QueuePolicyScopeType.GLOBAL.value,
            None,
        )
        effective = dict(DEFAULT_QUEUE_POLICY)
        if global_policy and global_policy.enabled:
            effective = {
                "assignment_strategy": (
                    normalize_queue_assignment_strategy(channel, global_policy.assignment_strategy)
                    or QueueAssignmentStrategy.ROUND_ROBIN.value
                ),
                "max_waiting_count": global_policy.max_waiting_count,
                "max_wait_seconds": global_policy.max_wait_seconds,
                "config": global_policy.config or {},
                "policy_source": f"{channel}_global",
            }

        scope_type = (
            QueuePolicyScopeType.EMPLOYEE.value
            if queue_type == QueueType.EMPLOYEE.value
            else QueuePolicyScopeType.EMPLOYEE_GROUP.value
        )
        scoped_policy = await QueuePolicyRepository.get_policy(db, tenant_id, channel, scope_type, queue_id)
        if scoped_policy and scoped_policy.enabled:
            effective["max_waiting_count"] = scoped_policy.max_waiting_count
            effective["max_wait_seconds"] = scoped_policy.max_wait_seconds
            effective["config"] = scoped_policy.config or {}
            effective["policy_source"] = scope_type
            scoped_strategy = normalize_queue_assignment_strategy(channel, scoped_policy.assignment_strategy)
            if queue_type == QueueType.EMPLOYEE_GROUP.value and scoped_strategy:
                effective["assignment_strategy"] = scoped_strategy

        explicit_strategy = normalize_queue_assignment_strategy(channel, explicit_strategy)
        if explicit_strategy:
            effective["assignment_strategy"] = explicit_strategy
            effective["policy_source"] = "explicit"

        if queue_type == QueueType.EMPLOYEE.value:
            effective["assignment_strategy"] = None
        return effective


class QueueTaskService:
    @staticmethod
    async def enqueue_task(db: AsyncSession, tenant_id: int, data: QueueEnqueueRequest) -> QueueEnqueueResponse:
        exists = await QueueCandidateRepository.queue_exists(db, tenant_id, data.queue_type.value, data.queue_id)
        if not exists:
            raise NotFoundError("Queue target not found")

        duplicate = await QueueTaskRepository.get_active_task_by_ref(
            db,
            tenant_id,
            data.channel.value,
            data.task_type.value,
            data.task_ref_id,
        )
        if duplicate:
            position = await QueueTaskService.get_position_for_task(db, tenant_id, duplicate.id)
            return QueueEnqueueResponse(accepted=False, duplicate=True, task=duplicate, position=position)

        policy = await QueuePolicyResolver.resolve(
            db,
            tenant_id,
            channel=data.channel.value,
            queue_type=data.queue_type.value,
            queue_id=data.queue_id,
            explicit_strategy=data.assignment_strategy.value if data.assignment_strategy else None,
        )
        waiting_count = await QueueTaskRepository.count_waiting(
            db,
            tenant_id,
            data.channel.value,
            data.queue_type.value,
            data.queue_id,
        )
        max_waiting_count = policy.get("max_waiting_count")
        if max_waiting_count is not None and waiting_count >= int(max_waiting_count):
            raise BusinessError("Queue limit reached", status_code=409, code="QUEUE_LIMIT_REACHED")

        max_wait_seconds = policy.get("max_wait_seconds")
        if max_wait_seconds is not None:
            tail = await QueueTaskRepository.get_tail_same_priority(
                db,
                tenant_id,
                data.channel.value,
                data.queue_type.value,
                data.queue_id,
                data.priority,
            )
            if tail:
                wait_seconds = (_now() - _to_aware(tail.enqueued_at)).total_seconds()
                if wait_seconds >= int(max_wait_seconds):
                    raise BusinessError("Queue limit reached", status_code=409, code="QUEUE_LIMIT_REACHED")

        payload = {
            "tenant_id": tenant_id,
            "channel": data.channel.value,
            "task_type": data.task_type.value,
            "task_ref_id": data.task_ref_id,
            "task_ref_public_id": data.task_ref_public_id,
            "queue_type": data.queue_type.value,
            "queue_id": data.queue_id,
            "priority": data.priority,
            "status": QueueTaskStatus.QUEUED.value,
            "source_type": data.source_type,
            "source_context": data.source_context,
            "policy_snapshot": policy,
            "assignment_strategy": policy.get("assignment_strategy"),
            "deadline_at": data.deadline_at,
        }
        task = await QueueTaskRepository.create_task(db, payload)
        await QueueEventRepository.create_outbox_event(
            db,
            {
                "tenant_id": tenant_id,
                "event_type": "queue.task_enqueued",
                "payload": {"task_id": task.id, "queue_type": task.queue_type, "queue_id": task.queue_id},
            },
        )
        await db.commit()
        await db.refresh(task)
        await QueueTaskService._emit_queue_change(task, "enqueued")
        position = await QueueTaskService.get_position_for_task(db, tenant_id, task.id)
        return QueueEnqueueResponse(accepted=True, duplicate=False, task=task, position=position)

    @staticmethod
    async def get_task(db: AsyncSession, tenant_id: int, task_id: int) -> QueueTask:
        task = await QueueTaskRepository.get_task(db, tenant_id, task_id)
        if not task:
            raise NotFoundError("Queue task not found")
        return task

    @staticmethod
    async def get_position_for_task(db: AsyncSession, tenant_id: int, task_id: int) -> QueuePositionResponse:
        task = await QueueTaskService.get_task(db, tenant_id, task_id)
        if task.status not in [QueueTaskStatus.QUEUED.value, QueueTaskStatus.ASSIGNING.value]:
            return QueuePositionResponse(task_id=task.id, position_overall=None, position_in_priority=None)
        overall, in_priority = await QueueTaskRepository.position_for_task(db, task)
        return QueuePositionResponse(task_id=task.id, position_overall=overall, position_in_priority=in_priority)

    @staticmethod
    async def cancel_task(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
        data: QueueTaskActionRequest,
    ) -> QueueTask:
        task = await QueueTaskRepository.get_task_for_update(db, tenant_id, task_id)
        if not task:
            raise NotFoundError("Queue task not found")
        if task.status not in [QueueTaskStatus.QUEUED.value, QueueTaskStatus.ASSIGNING.value]:
            raise ConflictError("Queue task is not active")
        await QueueTaskRepository.mark_terminal(
            db,
            task,
            QueueTaskStatus.CANCELED.value,
            now=_now(),
            reason=data.reason,
        )
        await QueueTaskService._record_event(db, task, "canceled", reason=data.reason)
        await QueueTaskService._materialize_conversation_summary(db, task)
        await db.commit()
        await db.refresh(task)
        await QueueTaskService._emit_queue_change(task, "canceled")
        return task

    @staticmethod
    async def timeout_task(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
        data: QueueTaskActionRequest,
    ) -> QueueTask:
        task = await QueueTaskRepository.get_task_for_update(db, tenant_id, task_id)
        if not task:
            raise NotFoundError("Queue task not found")
        if task.status not in [QueueTaskStatus.QUEUED.value, QueueTaskStatus.ASSIGNING.value]:
            raise ConflictError("Queue task is not active")
        await QueueTaskRepository.mark_terminal(
            db,
            task,
            QueueTaskStatus.TIMEOUT.value,
            now=_now(),
            reason=data.reason,
        )
        await QueueTaskService._record_event(db, task, "timeout", reason=data.reason)
        await QueueTaskService._materialize_conversation_summary(db, task)
        await db.commit()
        await db.refresh(task)
        await QueueTaskService._emit_queue_change(task, "timeout")
        return task

    @staticmethod
    async def state(
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        *,
        channel: str,
        queue_type: str,
        queue_id: int,
        task_id: int | None = None,
    ) -> QueueStateResponse:
        policy = await QueuePolicyResolver.resolve(
            db,
            tenant_id,
            channel=channel,
            queue_type=queue_type,
            queue_id=queue_id,
        )
        waiting_count, assigning_count = await QueueTaskRepository.queue_counts(
            db, tenant_id, channel, queue_type, queue_id
        )
        now = _now()
        priority_stats = []
        for priority, count, earliest in await QueueTaskRepository.priority_stats(db, tenant_id, channel, queue_type, queue_id):
            longest = int((now - _to_aware(earliest)).total_seconds()) if earliest else None
            priority_stats.append(
                QueuePriorityStat(
                    priority=priority,
                    waiting_count=count,
                    earliest_enqueued_at=earliest,
                    longest_wait_seconds=longest,
                )
            )

        available_agent_count = 0
        active_agent_count = 0
        try:
            provider = QueueResourceProviderFactory.create(channel)
            candidates = await provider.list_candidates(db, r, tenant_id, queue_type, queue_id)
            active_agent_count = len([candidate for candidate in candidates if candidate.metrics.get("status") not in [None, "offline"]])
            available_agent_count = len([candidate for candidate in candidates if candidate.available])
        except Exception:
            available_agent_count = 0
            active_agent_count = 0

        position_overall = None
        position_in_priority = None
        if task_id is not None:
            position = await QueueTaskService.get_position_for_task(db, tenant_id, task_id)
            position_overall = position.position_overall
            position_in_priority = position.position_in_priority

        return QueueStateResponse(
            queue_type=queue_type,
            queue_id=queue_id,
            channel=channel,
            waiting_count=waiting_count,
            assigning_count=assigning_count,
            priority_stats=priority_stats,
            available_agent_count=available_agent_count,
            active_agent_count=active_agent_count,
            effective_strategy=policy.get("assignment_strategy"),
            effective_strategy_source=policy.get("policy_source"),
            max_waiting_count=policy.get("max_waiting_count"),
            max_wait_seconds=policy.get("max_wait_seconds"),
            position_overall=position_overall,
            position_in_priority=position_in_priority,
        )

    @staticmethod
    async def pull_next(
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        data: QueuePullRequest,
    ) -> QueueTask:
        task = await QueueTaskRepository.find_pullable_task(
            db,
            tenant_id,
            employee_id,
            queue_type=data.queue_type.value if data.queue_type else None,
            queue_id=data.queue_id,
        )
        if not task:
            raise NotFoundError("No queue task available")
        await QueueTaskRepository.mark_assigning(db, task, _now())
        provider = QueueResourceProviderFactory.create(QueueChannel.ONLINE_CHAT.value)
        reserve = await provider.try_reserve(db, r, tenant_id, employee_id, task, bypass_capacity=True)
        if not reserve.success:
            await QueueTaskRepository.restore_queued(db, task, reserve.reason)
            await db.commit()
            raise ConflictError(reserve.reason or "Agent resource unavailable")
        await QueueTaskService._assign_business_object(db, tenant_id, task, employee_id)
        await QueueTaskRepository.mark_assigned(
            db,
            task,
            agent_id=employee_id,
            assigned_by=QueueAssignmentType.PULL.value,
            now=_now(),
        )
        await QueueTaskService._record_event(
            db,
            task,
            "pull_assigned",
            agent_id=employee_id,
            operator_id=employee_id,
            before_load=reserve.before_load,
            after_load=reserve.after_load,
        )
        await QueueTaskService._materialize_conversation_summary(db, task)
        await db.commit()
        await db.refresh(task)
        await QueueTaskService._emit_queue_change(task, "assigned")
        return task

    @staticmethod
    async def admin_assign(
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        operator_id: int,
        task_id: int,
        data: QueueAdminAssignRequest,
    ) -> QueueTask:
        task = await QueueTaskRepository.get_task_for_update(db, tenant_id, task_id)
        if not task:
            raise NotFoundError("Queue task not found")
        if task.channel != QueueChannel.ONLINE_CHAT.value:
            raise ValidationError("Admin assignment only supports online chat tasks")
        if task.status != QueueTaskStatus.QUEUED.value:
            raise ConflictError("Queue task is not queued")
        candidates = await QueueCandidateRepository.list_candidate_employees(
            db,
            tenant_id,
            QueueType.EMPLOYEE.value,
            data.agent_id,
        )
        if not candidates:
            raise NotFoundError("Agent not found")
        await QueueTaskRepository.mark_assigning(db, task, _now())
        provider = QueueResourceProviderFactory.create(QueueChannel.ONLINE_CHAT.value)
        reserve = await provider.try_reserve(db, r, tenant_id, data.agent_id, task, bypass_capacity=True)
        if not reserve.success:
            await QueueTaskRepository.restore_queued(db, task, reserve.reason)
            await db.commit()
            raise ConflictError(reserve.reason or "Agent resource unavailable")
        await QueueTaskService._assign_business_object(db, tenant_id, task, data.agent_id)
        await QueueTaskRepository.mark_assigned(
            db,
            task,
            agent_id=data.agent_id,
            assigned_by=QueueAssignmentType.ADMIN_ASSIGN.value,
            now=_now(),
        )
        await QueueTaskService._record_event(
            db,
            task,
            "admin_assigned",
            agent_id=data.agent_id,
            operator_id=operator_id,
            reason=data.reason,
            before_load=reserve.before_load,
            after_load=reserve.after_load,
        )
        await QueueTaskService._materialize_conversation_summary(db, task)
        await db.commit()
        await db.refresh(task)
        await QueueTaskService._emit_queue_change(task, "assigned")
        return task

    @staticmethod
    async def dispatch(
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        data: QueueDispatchRequest,
    ) -> QueueDispatchResponse:
        task = await QueueTaskRepository.lock_next_queued_task(
            db,
            tenant_id,
            data.channel.value,
            data.queue_type.value,
            data.queue_id,
        )
        if not task:
            return QueueDispatchResponse(dispatched=False, reason="no_queued_task")

        await QueueTaskRepository.mark_assigning(db, task, _now())
        provider = QueueResourceProviderFactory.create(data.channel.value)
        candidates = await provider.list_candidates(
            db,
            r,
            tenant_id,
            data.queue_type.value,
            data.queue_id,
            task.source_context,
        )
        available = [candidate for candidate in candidates if candidate.available]
        if not available:
            await QueueTaskRepository.restore_queued(db, task, "no_available_agent")
            await QueueTaskService._record_event(db, task, "reserve_failed", reason="no_available_agent")
            await db.commit()
            await db.refresh(task)
            return QueueDispatchResponse(dispatched=False, task=task, status=task.status, reason="no_available_agent")

        rr_state = await QueueRoundRobinRepository.get_state(
            db,
            tenant_id,
            data.channel.value,
            data.queue_type.value,
            data.queue_id,
        )
        ordered = QueueStrategyService.ordered_candidates(
            candidates,
            task.assignment_strategy,
            last_agent_id=rr_state.last_agent_id if rr_state else None,
            config=(task.policy_snapshot or {}).get("config") or {},
        )
        returning_candidate = await QueueTaskService._returning_agent_candidate(db, task, available)
        returning_agent_id = returning_candidate.employee_id if returning_candidate else None
        if returning_candidate is not None:
            ordered = [
                returning_candidate,
                *[candidate for candidate in ordered if candidate.employee_id != returning_candidate.employee_id],
            ]
        for candidate in ordered:
            reserve = await provider.try_reserve(db, r, tenant_id, candidate.employee_id, task)
            if not reserve.success:
                await QueueTaskService._record_event(
                    db,
                    task,
                    "reserve_failed",
                    agent_id=candidate.employee_id,
                    reason=reserve.reason,
                    before_load=reserve.before_load,
                )
                continue
            try:
                await QueueTaskService._assign_business_object(db, tenant_id, task, candidate.employee_id)
                await QueueTaskRepository.mark_assigned(
                    db,
                    task,
                    agent_id=candidate.employee_id,
                    assigned_by=QueueAssignmentType.AUTO.value,
                    now=_now(),
                )
                is_returning_agent = returning_agent_id == candidate.employee_id
                await QueueTaskService._record_event(
                    db,
                    task,
                    "returning_agent_assigned" if is_returning_agent else "auto_assigned",
                    agent_id=candidate.employee_id,
                    reason="returning_agent_priority" if is_returning_agent else None,
                    before_load=reserve.before_load,
                    after_load=reserve.after_load,
                )
                if task.assignment_strategy == QueueAssignmentStrategy.ROUND_ROBIN.value and not is_returning_agent:
                    await QueueRoundRobinRepository.set_last_agent(
                        db,
                        tenant_id,
                        data.channel.value,
                        data.queue_type.value,
                        data.queue_id,
                        candidate.employee_id,
                    )
                await QueueTaskService._materialize_conversation_summary(db, task)
                await db.commit()
                await db.refresh(task)
                await QueueTaskService._emit_queue_change(task, "assigned")
                return QueueDispatchResponse(
                    dispatched=True,
                    task=task,
                    agent_id=candidate.employee_id,
                    status=task.status,
                )
            except Exception:
                await provider.release(r, tenant_id, candidate.employee_id, task, "assignment_failed")
                raise

        await QueueTaskRepository.restore_queued(db, task, "all_candidates_busy")
        await db.commit()
        await db.refresh(task)
        return QueueDispatchResponse(dispatched=False, task=task, status=task.status, reason="all_candidates_busy")

    @staticmethod
    async def _returning_agent_candidate(
        db: AsyncSession,
        task: QueueTask,
        available: list[QueueCandidate],
    ) -> QueueCandidate | None:
        if task.queue_type != QueueType.EMPLOYEE_GROUP.value or len(available) <= 1:
            return None
        enabled, window_hours = QueueTaskService._returning_agent_config(task.policy_snapshot or {})
        if not enabled:
            return None

        cutoff = _now() - timedelta(hours=window_hours)
        agent_id: int | None = None
        if task.channel == QueueChannel.ONLINE_CHAT.value:
            if task.task_type not in [QueueTaskType.CONVERSATION.value, QueueTaskType.OPEN_AGENT_HANDOFF.value]:
                return None
            try:
                conversation_id = int(task.task_ref_id)
            except (TypeError, ValueError):
                return None
            agent_id = await QueueReturningAgentRepository.find_recent_online_chat_agent(
                db,
                task.tenant_id,
                conversation_id=conversation_id,
                cutoff=cutoff,
            )
        elif task.channel == QueueChannel.CALL_CENTER.value:
            context = task.source_context or {}
            call_id = str(context.get("call_id") or task.task_ref_id or "").strip()
            if not call_id:
                return None
            agent_id = await QueueReturningAgentRepository.find_recent_call_center_agent(
                db,
                task.tenant_id,
                call_id=call_id,
                cutoff=cutoff,
            )

        if agent_id is None:
            return None
        candidate_by_id = {candidate.employee_id: candidate for candidate in available}
        return candidate_by_id.get(agent_id)

    @staticmethod
    def _returning_agent_config(policy_snapshot: dict[str, Any]) -> tuple[bool, int]:
        config = policy_snapshot.get("config") if isinstance(policy_snapshot, dict) else None
        if not isinstance(config, dict) or config.get(RETURNING_AGENT_PRIORITY_ENABLED_KEY) is not True:
            return False, RETURNING_AGENT_DEFAULT_WINDOW_HOURS
        raw_hours = config.get(RETURNING_AGENT_WINDOW_HOURS_KEY, RETURNING_AGENT_DEFAULT_WINDOW_HOURS)
        try:
            hours = int(raw_hours)
        except (TypeError, ValueError):
            return False, RETURNING_AGENT_DEFAULT_WINDOW_HOURS
        if hours < RETURNING_AGENT_MIN_WINDOW_HOURS or hours > RETURNING_AGENT_MAX_WINDOW_HOURS:
            return False, RETURNING_AGENT_DEFAULT_WINDOW_HOURS
        return True, hours

    @staticmethod
    async def _assign_business_object(db: AsyncSession, tenant_id: int, task: QueueTask, employee_id: int) -> None:
        if task.task_type in [QueueTaskType.CONVERSATION.value, QueueTaskType.OPEN_AGENT_HANDOFF.value]:
            try:
                conversation_id = int(task.task_ref_id)
            except ValueError:
                return
            assigned_at = _now()
            await QueueBusinessRepository.assign_conversation(db, tenant_id, conversation_id, employee_id, assigned_at)
            from app.services.conversation_service import ConversationService

            await ConversationService.create_agent_assigned_system_message(
                db,
                tenant_id,
                conversation_id,
                employee_id,
            )
            await ConversationService.create_welcome_message_on_agent_assignment(
                db,
                tenant_id,
                conversation_id,
            )
            from app.services.visitor_timeout_close_service import VisitorTimeoutCloseService
            from app.repositories.conversation_repository import ConversationRepository

            conversation = await ConversationRepository.get_by_id(db, conversation_id)
            await QueueTaskService._record_reception_assignment(
                db, tenant_id, conversation, task, employee_id, assigned_at
            )
            await VisitorTimeoutCloseService.initialize_for_conversation(
                db,
                conversation,
                anchor_at=assigned_at,
                commit=False,
            )
        elif task.task_type == QueueTaskType.CALL.value:
            await QueueBusinessRepository.assign_call(db, tenant_id, task.task_ref_id, employee_id)

    @staticmethod
    async def _materialize_conversation_summary(db: AsyncSession, task: QueueTask) -> None:
        """Refresh redundant queue summary for the conversation behind an online-chat task."""
        if task.channel != QueueChannel.ONLINE_CHAT.value:
            return
        if task.task_type not in [QueueTaskType.CONVERSATION.value, QueueTaskType.OPEN_AGENT_HANDOFF.value]:
            return
        try:
            conversation_id = int(task.task_ref_id)
        except (TypeError, ValueError):
            return
        from app.services.queue_materialization_service import QueueMaterializationService

        await QueueMaterializationService.materialize_conversation(db, task.tenant_id, conversation_id)

    @staticmethod
    async def _record_reception_assignment(
        db: AsyncSession,
        tenant_id: int,
        conversation,
        task: QueueTask,
        employee_id: int,
        assigned_at: datetime,
    ) -> None:
        """Log a structured reception event when the queue assigns a conversation.

        The reason distinguishes a bot-to-human handoff, the first human takeover
        and a later re-entry (a re-queued conversation assigned again) so the
        post-end segment generation can derive the entry reason.
        """
        if conversation is None:
            return
        from app.enums import ReceptionEventReason, ReceptionEventType
        from app.repositories.reception_event_repository import ReceptionEventRepository
        from app.services.reception_event_service import ReceptionEventService

        if task.task_type == QueueTaskType.OPEN_AGENT_HANDOFF.value:
            reason = ReceptionEventReason.BOT_HANDOFF.value
        elif await ReceptionEventRepository.has_events(db, conversation.id):
            reason = ReceptionEventReason.REASSIGN.value
        else:
            reason = ReceptionEventReason.FIRST_HUMAN.value

        await ReceptionEventService.record(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            event_type=ReceptionEventType.ASSIGNED.value,
            occurred_at=assigned_at,
            agent_id=employee_id,
            group_id=conversation.group_id,
            to_agent_id=employee_id,
            reason=reason,
        )

    @staticmethod
    async def _record_event(
        db: AsyncSession,
        task: QueueTask,
        event_type: str,
        *,
        agent_id: int | None = None,
        operator_id: int | None = None,
        reason: str | None = None,
        before_load: dict[str, Any] | None = None,
        after_load: dict[str, Any] | None = None,
    ) -> None:
        policy = task.policy_snapshot or {}
        queue_name_snapshot = await QueueTaskService._queue_name_snapshot(
            db,
            task.tenant_id,
            task.queue_type,
            task.queue_id,
        )
        await QueueEventRepository.create_assignment_event(
            db,
            {
                "tenant_id": task.tenant_id,
                "task_id": task.id,
                "channel": task.channel,
                "queue_type": task.queue_type,
                "queue_id": task.queue_id,
                "queue_name_snapshot": queue_name_snapshot,
                "event_type": event_type,
                "agent_id": agent_id,
                "strategy": task.assignment_strategy,
                "policy_source": policy.get("policy_source"),
                "priority": task.priority,
                "before_load": before_load,
                "after_load": after_load,
                "operator_id": operator_id,
                "reason": reason,
            },
        )
        await QueueEventRepository.create_outbox_event(
            db,
            {
                "tenant_id": task.tenant_id,
                "event_type": f"queue.{event_type}",
                "payload": {"task_id": task.id, "agent_id": agent_id, "reason": reason},
            },
        )

    @staticmethod
    async def _queue_name_snapshot(
        db: AsyncSession,
        tenant_id: int,
        queue_type: str,
        queue_id: int,
    ) -> str | None:
        if queue_type == QueueType.EMPLOYEE.value:
            result = await db.execute(
                select(Employee).where(
                    Employee.tenant_id == tenant_id,
                    Employee.id == queue_id,
                )
            )
            employee = result.scalar_one_or_none()
            if employee is None:
                return None
            return employee.display_name or employee.nickname or employee.name or employee.username

        if queue_type == QueueType.EMPLOYEE_GROUP.value:
            result = await db.execute(
                select(EmployeeGroup).where(
                    EmployeeGroup.tenant_id == tenant_id,
                    EmployeeGroup.id == queue_id,
                )
            )
            group = result.scalar_one_or_none()
            return group.name if group else None

        return None

    @staticmethod
    async def _emit_queue_change(task: QueueTask, action: str) -> None:
        if task.channel != QueueChannel.ONLINE_CHAT.value:
            return
        await QueueRealtimeService.emit_queue_updated(
            task.tenant_id,
            action=action,
            task_id=task.id,
            queue_type=task.queue_type,
            queue_id=task.queue_id,
        )
