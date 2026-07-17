"""
Call-center agent status service — DB-backed, per-employee state for the
call center module (ready / busy / break / after_call_work / offline).

Different from `agent_status_service.py` which tracks live presence for the
online-chat workspace in Redis. The two are intentionally separate:
  - This one: low-frequency state transitions (~1-2/min), persistent in DB,
    used by orchestrator (queue assignment) and by call history reports.
  - That one: high-frequency Socket.IO presence (per second), Redis-only.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.exceptions import ConflictError, NotFoundError
from app.repositories.agent_status_repository import AgentStatusRepository
from app.repositories.agent_webrtc_session_repository import AgentWebRTCSessionRepository
from app.repositories.call_record_repository import CallRecordRepository
from app.services.cc_agent_resource_service import CcAgentResourceService


logger = logging.getLogger(__name__)

VALID_STATUS = {"ready", "busy", "break", "after_call_work", "offline"}


class CcAgentStatusService:

    @staticmethod
    async def get_for_employee(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        r: aioredis.Redis | None = None,
    ) -> dict:
        row = await AgentStatusRepository.get_for_employee(db, tenant_id, employee_id)
        if not row:
            base = {
                "employee_id": employee_id,
                "status": "offline",
                "reason": None,
                "status_changed_at": None,
                "updated_at": None,
            }
        else:
            base = {
                "employee_id": row.employee_id,
                "status": row.status,
                "reason": row.reason,
                "status_changed_at": row.status_changed_at,
                "updated_at": row.updated_at,
            }
        if r is None:
            return base | _empty_resource_fields()
        try:
            snapshot = await CcAgentResourceService.get_snapshot(
                r, tenant_id, employee_id
            )
            if snapshot is None:
                active_call = await CallRecordRepository.get_latest_active_for_agent(
                    db, tenant_id, employee_id
                )
                active_session = await AgentWebRTCSessionRepository.get_active(
                    db, tenant_id, employee_id
                )
                snapshot = await CcAgentResourceService.recover_from_sources(
                    r,
                    tenant_id,
                    employee_id,
                    visible_status=base["status"],
                    active_call_id=active_call.call_id if active_call else None,
                    active_call_direction=active_call.direction if active_call else None,
                    active_call_state=active_call.state if active_call else None,
                    webrtc_state=active_session.state if active_session else None,
                )
            else:
                # Self-heal a ghost in_call left by a lost call-end event, so a
                # stranded agent recovers on the next status poll instead of
                # being locked out for the 4h lease.
                snapshot = await CcAgentStatusService.reconcile_agent(
                    db, r, tenant_id, employee_id,
                    snapshot=snapshot, chosen_status=base["status"],
                )
        except Exception:  # noqa: BLE001
            return base | _empty_resource_fields()
        return base | _resource_fields(snapshot)

    @staticmethod
    async def reconcile_agent(
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        *,
        snapshot: dict | None = None,
        chosen_status: str | None = None,
    ) -> dict | None:
        """Single reconcile point: heal a call resource that has drifted from
        reality. Two drifts are healed:

        1. **Ghost in_call** — stuck ``in_call`` with **no** active call record
           and **no** active WebRTC session (its kernel call-end event was lost).
           It would otherwise hold the 4h in_call lease and lock the agent out.
           Released.
        2. **Stale-offline presence** — the agent chose ``ready`` and their
           browser is connected, but the Redis resource drifted to ``offline``
           while idle (e.g. left behind by a release). It would wrongly make the
           agent unreservable for inbound / consult / transfer. Restored to
           ready. (``chosen_status`` is the durable PG status; passing it lets
           this run on the ordinary status poll without an extra DB read.)

        Cheap in the common case: the extra DB reads only run for an ``in_call``
        snapshot, and the presence heal only for an ``offline`` snapshot — so a
        healthy ready/idle agent (the vast majority of polls) does neither.
        Gated strictly to ``in_call`` for (1) — a genuine in_call always has an
        ``in_progress`` call record, so it can't race a live ringing offer.
        """
        if snapshot is None:
            snapshot = await CcAgentResourceService.get_snapshot(
                r, tenant_id, employee_id
            )
        if not snapshot:
            return snapshot
        state = snapshot.get("resource_state")

        if state == "in_call":
            active_call = await CallRecordRepository.get_latest_active_for_agent(
                db, tenant_id, employee_id
            )
            active_session = await AgentWebRTCSessionRepository.get_active(
                db, tenant_id, employee_id
            )
            if active_call or active_session:
                return snapshot  # a real call backs the in_call state — leave it
            logger.info(
                "reconcile_agent: releasing ghost in_call for agent=%s/%s "
                "(no active call record or WebRTC session)",
                tenant_id, employee_id,
            )
            try:
                await CcAgentResourceService.force_release(
                    r, tenant_id, employee_id, reason="reconcile_ghost",
                )
            except Exception:  # noqa: BLE001
                return snapshot
            return await CcAgentResourceService.get_snapshot(
                r, tenant_id, employee_id
            )

        # Stale-offline presence: the agent chose ready and is connected, but
        # the resource drifted offline while idle → restore so they're reservable.
        if (
            chosen_status == "ready"
            and snapshot.get("visible_status") == "offline"
            and state in {"idle", "unavailable"}
        ):
            from app.services.agent_status_service import AgentStatusService

            if await AgentStatusService.is_connected(r, tenant_id, employee_id):
                logger.info(
                    "reconcile_agent: restoring ready presence for agent=%s/%s "
                    "(chose ready, connected, resource drifted offline)",
                    tenant_id, employee_id,
                )
                try:
                    return await CcAgentResourceService.set_visible_status(
                        r, tenant_id, employee_id, "ready"
                    )
                except Exception:  # noqa: BLE001
                    return snapshot
        return snapshot

    @staticmethod
    async def get_resource_snapshot(
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
    ) -> dict:
        data = await CcAgentStatusService.get_for_employee(
            db, tenant_id, employee_id, r
        )
        return {
            "employee_id": data["employee_id"],
            "visible_status": data["status"],
            "resource_state": data.get("resource_state") or "unavailable",
            "current_call_id": data.get("current_call_id"),
            "offer_id": data.get("offer_id"),
            "queue_id": data.get("queue_id"),
            "direction": data.get("direction"),
            "reserved_until": data.get("reserved_until"),
            "last_release_reason": data.get("last_release_reason"),
        }

    @staticmethod
    async def sync_pg_status(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        status: str,
        reason: str | None = None,
    ) -> dict:
        row = await AgentStatusRepository.upsert(db, tenant_id, employee_id, status, reason)
        return {
            "employee_id": row.employee_id,
            "status": row.status,
            "reason": row.reason,
            "status_changed_at": row.status_changed_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    async def set_status(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        status: str,
        reason: str | None,
        r: aioredis.Redis | None = None,
    ) -> dict:
        if status not in VALID_STATUS:
            raise NotFoundError(f"Invalid status: {status}")
        snapshot = None
        if r is not None:
            try:
                snapshot = await CcAgentResourceService.set_visible_status(
                    r, tenant_id, employee_id, status
                )
            except ConflictError:
                # The resource is flagged occupied, but this is a *manual* status
                # change the agent explicitly requested. Occupation left behind by
                # a failed accept / stale in_call lease would otherwise lock them
                # out of changing status forever. Honor the explicit action:
                # force-release the stuck resource and apply the new status.
                logger.info(
                    "set_status: force-releasing stuck resource for manual change "
                    "agent=%s/%s -> %s",
                    tenant_id, employee_id, status,
                )
                await CcAgentResourceService.force_release(
                    r, tenant_id, employee_id, reason="manual_status_change",
                )
                snapshot = await CcAgentResourceService.set_visible_status(
                    r, tenant_id, employee_id, status
                )
        base = await CcAgentStatusService.sync_pg_status(
            db, tenant_id, employee_id, status, reason
        )
        return base | (_resource_fields(snapshot) if snapshot else _empty_resource_fields())

    @staticmethod
    async def list_consultable_agents(
        db: AsyncSession,
        tenant_id: int,
        actor_employee_id: int,
        keyword: str | None,
        r: aioredis.Redis | None = None,
    ) -> list[dict]:
        """Agents an in-call operator may consult / transfer / conference to.

        Returns every active agent in the tenant holding ``call.workspace.use``
        (the caller themselves excluded), each annotated with their current
        call-center status (ready / busy / break / after_call_work / offline).

        The DB ``agent_status`` only records the status an agent last *chose* —
        it is never flipped to offline when their browser disconnects. So the
        reported status is downgraded to ``offline`` for any agent whose
        Socket.IO connection is gone, otherwise a colleague who closed their tab
        would still appear "就绪" here and be picked as an unreachable target.
        """
        from app.repositories.sip_extension_repository import SipExtensionRepository
        from app.services.agent_status_service import AgentStatusService

        employees = await SipExtensionRepository.list_workspace_agents(
            db, tenant_id, keyword, exclude_employee_id=actor_employee_id
        )
        status_rows = await AgentStatusRepository.list_for_employees(
            db, tenant_id, [e.id for e in employees]
        )
        status_by_id = {row.employee_id: row.status for row in status_rows}

        async def _effective_status(employee_id: int) -> str:
            status = status_by_id.get(employee_id, "offline")
            if status == "offline" or r is None:
                return status
            # A live status only counts if the browser is actually connected.
            if not await AgentStatusService.is_connected(r, tenant_id, employee_id):
                return "offline"
            return status

        return [
            {
                "employee_id": emp.id,
                "name": emp.display_name or emp.name or emp.username,
                "avatar": emp.avatar,
                "status": await _effective_status(emp.id),
            }
            for emp in employees
        ]

    @staticmethod
    async def list_online_for_group(
        db: AsyncSession, tenant_id: int, group_id: int
    ) -> dict:
        """
        Return online + ready agents for an employee group, including their
        active webrtc session id. Used internally by the orchestrator when
        an assign_queue node fires.
        """

        from sqlalchemy import select

        from app.models.agent_status import AgentStatus
        from app.models.employee import Employee
        from app.models.employee_group import EmployeeGroupMember
        from app.repositories.agent_webrtc_session_repository import (
            AgentWebRTCSessionRepository,
        )

        q = (
            select(EmployeeGroupMember.employee_id)
            .join(AgentStatus, AgentStatus.employee_id == EmployeeGroupMember.employee_id)
            .where(
                EmployeeGroupMember.group_id == group_id,
                AgentStatus.tenant_id == tenant_id,
                AgentStatus.status == "ready",
            )
        )
        ready_ids = list((await db.execute(q)).scalars().all())

        sessions = await AgentWebRTCSessionRepository.list_active_for_employees(
            db, tenant_id, ready_ids
        )
        session_by_emp = {s.employee_id: s for s in sessions}

        if ready_ids:
            emps = list(
                (
                    await db.execute(select(Employee).where(Employee.id.in_(ready_ids)))
                )
                .scalars()
                .all()
            )
        else:
            emps = []
        name_by_id = {e.id: (e.display_name or e.nickname or e.name or e.username) for e in emps}

        items = []
        for emp_id in ready_ids:
            sess = session_by_emp.get(emp_id)
            if not sess or sess.state != "online_idle":
                continue
            # Guard against legacy placeholder ids ("webrtc-xxxxxxxx") left
            # over from the pre-real-SDP flow — they look online_idle in the
            # DB but FlowKit doesn't know them, so `call.bridge` fails with
            # `-32002 call not found`. Real FlowKit call_ids are UUIDs (36
            # chars with 4 dashes).
            wcid = sess.webrtc_call_id or ""
            if wcid.startswith("webrtc-") or len(wcid) != 36:
                continue
            items.append({
                "employee_id": emp_id,
                "name": name_by_id.get(emp_id),
                "webrtc_call_id": wcid,
                "status": "ready",
            })
        return {"items": items}


def _empty_resource_fields() -> dict:
    return {
        "resource_state": None,
        "current_call_id": None,
        "offer_id": None,
        "queue_id": None,
        "direction": None,
        "reserved_until": None,
        "resource_updated_at": None,
        "last_release_reason": None,
    }


def _resource_fields(snapshot: dict | None) -> dict:
    if snapshot is None:
        return _empty_resource_fields()
    return {
        "resource_state": snapshot.get("resource_state"),
        "current_call_id": snapshot.get("current_call_id"),
        "offer_id": snapshot.get("offer_id"),
        "queue_id": snapshot.get("queue_id"),
        "direction": snapshot.get("direction"),
        "reserved_until": snapshot.get("reserved_until"),
        "resource_updated_at": snapshot.get("resource_updated_at"),
        "last_release_reason": snapshot.get("last_release_reason"),
    }
