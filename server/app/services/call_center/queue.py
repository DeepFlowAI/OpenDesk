"""
Queue picker — round-robin agent selection for an `assign_queue` node.

Two selection modes:
  - `pick`: requires the agent to have an active `online_idle` webrtc
    session. Used by the legacy "always-on agent leg" flow.
  - `pick_ready_agent`: only requires `agent_status.status == 'ready'` —
    the agent does NOT need an active WebRTC leg yet. The leg is built
    later, on accept, in the "ring-on-demand" flow.

When Redis is available, ring-on-demand uses Redis round-robin pointers and
resource reservation so multiple service instances share the same decision.
The in-process pointer remains only for legacy callers that do not pass Redis.
"""
from __future__ import annotations

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService


class QueuePicker:

    def __init__(self) -> None:
        self._pointers: dict[tuple[int, int], int] = {}

    async def pick(
        self, db: AsyncSession, tenant_id: int, group_id: int
    ) -> dict | None:
        result = await CcAgentStatusService.list_online_for_group(db, tenant_id, group_id)
        items = result["items"]
        if not items:
            return None
        key = (tenant_id, group_id)
        idx = self._pointers.get(key, 0)
        pick = items[idx % len(items)]
        self._pointers[key] = idx + 1
        return pick

    async def pick_ready_agent(
        self,
        db: AsyncSession,
        tenant_id: int,
        group_id: int,
        r: aioredis.Redis | None = None,
        *,
        call_id: str | None = None,
        offer_id: str | None = None,
        ttl_seconds: float | None = None,
        preferred_employee_id: int | None = None,
    ) -> dict | None:
        """
        Pick the next `ready` agent in the group without requiring a
        pre-established WebRTC leg. Used by the ring-on-demand flow where
        the leg is established on accept.
        """

        from sqlalchemy import select
        from app.models.agent_status import AgentStatus
        from app.models.employee import Employee
        from app.models.employee_group import EmployeeGroupMember

        q = (
            select(Employee)
            .select_from(EmployeeGroupMember)
            .join(AgentStatus, AgentStatus.employee_id == EmployeeGroupMember.employee_id)
            .join(Employee, Employee.id == EmployeeGroupMember.employee_id)
            .where(
                EmployeeGroupMember.group_id == group_id,
                AgentStatus.tenant_id == tenant_id,
                AgentStatus.status == "ready",
                Employee.tenant_id == tenant_id,
                Employee.is_active.is_(True),
            )
            .order_by(EmployeeGroupMember.employee_id)
        )
        employees = list((await db.execute(q)).scalars().all())
        if not employees:
            return None

        candidates = [
            {
                "employee_id": emp.id,
                "name": emp.display_name or emp.nickname or emp.name or emp.username,
            }
            for emp in employees
        ]
        # Only offer to agents whose browser is actually connected. The DB
        # "ready" status records the status an agent last *chose* and is never
        # cleared on disconnect, so without this a call gets offered to a
        # colleague who closed their tab — it rings a dead browser until the
        # caller gives up, while a genuinely-connected agent never gets a turn.
        # An agent inside the brief disconnect grace window still counts as
        # connected, so ordinary socket flaps don't drop them from rotation.
        if r is not None:
            from app.services.agent_status_service import AgentStatusService

            connected: list[dict] = []
            for candidate in candidates:
                if await AgentStatusService.is_connected(
                    r, tenant_id, candidate["employee_id"]
                ):
                    connected.append(candidate)
            candidates = connected
            if not candidates:
                return None
        if r is not None and call_id and offer_id:
            preferred = next(
                (candidate for candidate in candidates if candidate["employee_id"] == preferred_employee_id),
                None,
            )
            if preferred is not None:
                await CcAgentResourceService.ensure_from_visible(
                    r, tenant_id, preferred["employee_id"], "ready"
                )
                reserved = await CcAgentResourceService.reserve_inbound(
                    r,
                    tenant_id,
                    preferred["employee_id"],
                    call_id=call_id,
                    offer_id=offer_id,
                    queue_id=group_id,
                    ttl_seconds=ttl_seconds,
                )
                if reserved is not None:
                    return preferred | {"resource_state": reserved["resource_state"]}

            start = await CcAgentResourceService.next_queue_index(r, tenant_id, group_id)
            for offset in range(len(candidates)):
                pick = candidates[(start + offset) % len(candidates)]
                if pick["employee_id"] == preferred_employee_id:
                    continue
                await CcAgentResourceService.ensure_from_visible(
                    r, tenant_id, pick["employee_id"], "ready"
                )
                reserved = await CcAgentResourceService.reserve_inbound(
                    r,
                    tenant_id,
                    pick["employee_id"],
                    call_id=call_id,
                    offer_id=offer_id,
                    queue_id=group_id,
                    ttl_seconds=ttl_seconds,
                )
                if reserved is not None:
                    return pick | {"resource_state": reserved["resource_state"]}
            return None

        preferred = next(
            (candidate for candidate in candidates if candidate["employee_id"] == preferred_employee_id),
            None,
        )
        if preferred is not None:
            return preferred

        key = (tenant_id, group_id)
        idx = self._pointers.get(key, 0)
        pick = candidates[idx % len(candidates)]
        self._pointers[key] = idx + 1
        return pick

    async def pick_ready_agent_for_queue(
        self,
        db: AsyncSession,
        tenant_id: int,
        queue_type: str,
        queue_id: int,
        r: aioredis.Redis | None = None,
        *,
        call_id: str | None = None,
        offer_id: str | None = None,
        ttl_seconds: float | None = None,
        preferred_employee_id: int | None = None,
    ) -> dict | None:
        if queue_type == "employee_group":
            return await self.pick_ready_agent(
                db,
                tenant_id,
                queue_id,
                r,
                call_id=call_id,
                offer_id=offer_id,
                ttl_seconds=ttl_seconds,
                preferred_employee_id=preferred_employee_id,
            )

        from sqlalchemy import select
        from app.models.agent_status import AgentStatus
        from app.models.employee import Employee

        result = await db.execute(
            select(Employee)
            .join(AgentStatus, AgentStatus.employee_id == Employee.id)
            .where(
                Employee.id == queue_id,
                Employee.tenant_id == tenant_id,
                Employee.is_active.is_(True),
                AgentStatus.tenant_id == tenant_id,
                AgentStatus.status == "ready",
            )
            .limit(1)
        )
        employee = result.scalar_one_or_none()
        if employee is None:
            return None

        pick = {
            "employee_id": employee.id,
            "name": employee.display_name or employee.nickname or employee.name or employee.username,
        }
        if r is not None and call_id and offer_id:
            await CcAgentResourceService.ensure_from_visible(
                r, tenant_id, employee.id, "ready"
            )
            reserved = await CcAgentResourceService.reserve_inbound(
                r,
                tenant_id,
                employee.id,
                call_id=call_id,
                offer_id=offer_id,
                queue_id=queue_id,
                ttl_seconds=ttl_seconds,
            )
            if reserved is None:
                return None
            return pick | {"resource_state": reserved["resource_state"]}
        return pick

    async def has_agent_on_call_for_queue(
        self,
        db: AsyncSession,
        tenant_id: int,
        queue_type: str,
        queue_id: int,
        r: aioredis.Redis | None = None,
    ) -> bool | None:
        """Whether the queue has an agent currently *engaged on a call* (resource
        reserved / ringing / in_call) who will free up soon — the only case where
        holding the caller in queue is worthwhile.

        A genuinely available agent would already have been picked; this runs
        only after that failed. So a `ready` agent left here is unreachable
        (e.g. a SIP extension that's down) or reserved elsewhere, a `busy`/`break`
        agent chose to stop taking calls, and the caller's own open workspace tab
        is idle — none of those will take this call, so we do NOT wait for them.

        Returns None when resource state can't be read (no Redis) so callers keep
        their existing wait behavior rather than dropping a caller blindly.
        """
        if r is None:
            return None

        from sqlalchemy import select
        from app.models.employee import Employee
        from app.models.employee_group import EmployeeGroupMember
        from app.services.cc_agent_resource_service import (
            ACTIVE_RESOURCE_STATES,
            CcAgentResourceService,
        )

        if queue_type == "employee_group":
            q = (
                select(EmployeeGroupMember.employee_id)
                .join(Employee, Employee.id == EmployeeGroupMember.employee_id)
                .where(
                    EmployeeGroupMember.group_id == queue_id,
                    Employee.tenant_id == tenant_id,
                    Employee.is_active.is_(True),
                )
            )
        else:
            q = (
                select(Employee.id).where(
                    Employee.id == queue_id,
                    Employee.tenant_id == tenant_id,
                    Employee.is_active.is_(True),
                )
            )
        employee_ids = list((await db.execute(q)).scalars().all())
        for employee_id in employee_ids:
            snapshot = await CcAgentResourceService.get_snapshot(r, tenant_id, employee_id)
            if snapshot and snapshot.get("resource_state") in ACTIVE_RESOURCE_STATES:
                return True
        return False

    def reset(self) -> None:
        """Test helper."""

        self._pointers.clear()


# Module-level singleton — orchestrator + tests share one.
_default = QueuePicker()


def get_queue_picker() -> QueuePicker:
    return _default
