"""
Channel resource providers for the unified queue engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import redis.asyncio as aioredis
from redis.exceptions import WatchError
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AgentOnlineStatus, QueueChannel
from app.models.queue import QueueTask
from app.repositories.queue_repository import QueueCandidateRepository
from app.services.agent_status_service import AgentStatusService
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService
from app.services.queue_strategy import QueueCandidate


@dataclass(slots=True)
class ReserveResult:
    success: bool
    before_load: dict[str, Any] | None = None
    after_load: dict[str, Any] | None = None
    reason: str | None = None


class QueueResourceProvider(Protocol):
    async def list_candidates(
        self,
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        queue_type: str,
        queue_id: int,
        task_context: dict[str, Any] | None = None,
    ) -> list[QueueCandidate]:
        ...

    async def try_reserve(
        self,
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        task: QueueTask,
        *,
        bypass_capacity: bool = False,
    ) -> ReserveResult:
        ...

    async def release(
        self,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        task: QueueTask,
        reason: str,
    ) -> None:
        ...


class OnlineChatResourceProvider:
    async def list_candidates(
        self,
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        queue_type: str,
        queue_id: int,
        task_context: dict[str, Any] | None = None,
    ) -> list[QueueCandidate]:
        employees = await QueueCandidateRepository.list_candidate_employees(db, tenant_id, queue_type, queue_id)
        users = [(employee.id, employee.max_concurrent or 10) for employee in employees]
        statuses = await AgentStatusService.get_statuses_bulk(r, tenant_id, users)
        candidates: list[QueueCandidate] = []
        for employee in employees:
            status = statuses.get(employee.id) or {}
            current_count = int(status.get("current_count", 0))
            max_concurrent = int(status.get("max_concurrent", employee.max_concurrent or 10))
            is_online = status.get("status") == AgentOnlineStatus.ONLINE.value
            candidates.append(
                QueueCandidate(
                    employee_id=employee.id,
                    name=employee.display_name or employee.nickname or employee.name or employee.username,
                    available=is_online and current_count < max_concurrent,
                    current_load=current_count,
                    max_capacity=max_concurrent,
                    metrics={"status": status.get("status", AgentOnlineStatus.OFFLINE.value)},
                )
            )
        return candidates

    async def try_reserve(
        self,
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        task: QueueTask,
        *,
        bypass_capacity: bool = False,
    ) -> ReserveResult:
        key = AgentStatusService._key(tenant_id, employee_id)
        employees = await QueueCandidateRepository.list_candidate_employees(
            db,
            tenant_id,
            "employee",
            employee_id,
        )
        configured_max = employees[0].max_concurrent if employees else 10
        for _ in range(3):
            async with r.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.hgetall(key)
                    status = raw.get("status") if raw else None
                    current_count = int(raw.get("current_count", 0)) if raw else 0
                    max_concurrent = int(raw.get("max_concurrent", configured_max)) if raw else configured_max
                    before = {
                        "status": status or AgentOnlineStatus.OFFLINE.value,
                        "current_load": current_count,
                        "max_capacity": max_concurrent,
                    }
                    if status != AgentOnlineStatus.ONLINE.value:
                        await pipe.reset()
                        return ReserveResult(False, before_load=before, reason="agent_not_online")
                    if not bypass_capacity and current_count >= max_concurrent:
                        await pipe.reset()
                        return ReserveResult(False, before_load=before, reason="capacity_full")
                    pipe.multi()
                    pipe.hincrby(key, "current_count", 1)
                    await pipe.execute()
                    after = before | {"current_load": current_count + 1}
                    return ReserveResult(True, before_load=before, after_load=after)
                except WatchError:
                    continue
        return ReserveResult(False, reason="resource_conflict")

    async def release(
        self,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        task: QueueTask,
        reason: str,
    ) -> None:
        key = AgentStatusService._key(tenant_id, employee_id)
        value = await r.hincrby(key, "current_count", -1)
        if value < 0:
            await r.hset(key, "current_count", 0)


class CallCenterResourceProvider:
    async def list_candidates(
        self,
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        queue_type: str,
        queue_id: int,
        task_context: dict[str, Any] | None = None,
    ) -> list[QueueCandidate]:
        employees = await QueueCandidateRepository.list_candidate_employees(db, tenant_id, queue_type, queue_id)
        candidates: list[QueueCandidate] = []
        for employee in employees:
            status = await CcAgentStatusService.get_for_employee(db, tenant_id, employee.id, r)
            resource_state = status.get("resource_state") or "unavailable"
            visible_status = status.get("status")
            candidates.append(
                QueueCandidate(
                    employee_id=employee.id,
                    name=employee.display_name or employee.nickname or employee.name or employee.username,
                    available=visible_status == "ready" and resource_state == "idle",
                    current_load=0 if resource_state == "idle" else 1,
                    max_capacity=1,
                    metrics={
                        "status": visible_status,
                        "resource_state": resource_state,
                        "last_release_reason": status.get("last_release_reason"),
                    },
                )
            )
        return candidates

    async def try_reserve(
        self,
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        task: QueueTask,
        *,
        bypass_capacity: bool = False,
    ) -> ReserveResult:
        context = task.source_context or {}
        call_id = str(context.get("call_id") or task.task_ref_id)
        offer_id = str(context.get("offer_id") or f"queue-task-{task.id}")
        ttl_seconds = context.get("offer_ttl_seconds")
        before = await CcAgentStatusService.get_resource_snapshot(db, r, tenant_id, employee_id)
        reserved = await CcAgentResourceService.reserve_inbound(
            r,
            tenant_id,
            employee_id,
            call_id=call_id,
            offer_id=offer_id,
            queue_id=task.queue_id,
            ttl_seconds=ttl_seconds,
        )
        if not reserved:
            return ReserveResult(False, before_load=before, reason="resource_busy")
        try:
            after = await CcAgentResourceService.mark_ringing(
                r,
                tenant_id,
                employee_id,
                offer_id=offer_id,
                call_id=call_id,
                ttl_seconds=ttl_seconds,
            )
        except Exception:
            await CcAgentResourceService.release(
                r,
                tenant_id,
                employee_id,
                reason="queue_mark_ringing_failed",
                expected_offer_id=offer_id,
                allow_in_call=False,
            )
            raise
        return ReserveResult(True, before_load=before, after_load=after)

    async def release(
        self,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        task: QueueTask,
        reason: str,
    ) -> None:
        context = task.source_context or {}
        offer_id = str(context.get("offer_id") or f"queue-task-{task.id}")
        await CcAgentResourceService.release(
            r,
            tenant_id,
            employee_id,
            reason=reason,
            expected_offer_id=offer_id,
            allow_in_call=False,
        )


class QueueResourceProviderFactory:
    @staticmethod
    def create(channel: str) -> QueueResourceProvider:
        if channel == QueueChannel.ONLINE_CHAT.value:
            return OnlineChatResourceProvider()
        if channel == QueueChannel.CALL_CENTER.value:
            return CallCenterResourceProvider()
        raise ValueError(f"Unsupported queue channel: {channel}")
