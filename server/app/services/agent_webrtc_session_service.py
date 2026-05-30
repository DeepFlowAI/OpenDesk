"""
Agent WebRTC session service — open/close the agent's WebRTC leg mapping.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.repositories.agent_webrtc_session_repository import (
    AgentWebRTCSessionRepository,
)


class AgentWebRTCSessionService:

    @staticmethod
    async def get_active(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> dict | None:
        row = await AgentWebRTCSessionRepository.get_active(db, tenant_id, employee_id)
        if not row:
            return None
        return _to_resp(row)

    @staticmethod
    async def open(
        db: AsyncSession, tenant_id: int, employee_id: int, webrtc_call_id: str
    ) -> dict:
        existing = await AgentWebRTCSessionRepository.get_active(db, tenant_id, employee_id)
        if existing:
            raise ConflictError("Active WebRTC session already exists")
        row = await AgentWebRTCSessionRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "employee_id": employee_id,
                "webrtc_call_id": webrtc_call_id,
                "state": "online_idle",
            },
        )
        return _to_resp(row)

    @staticmethod
    async def upsert_with_real_call_id(
        db: AsyncSession, tenant_id: int, employee_id: int, webrtc_call_id: str
    ) -> dict:
        """
        Idempotent: replace any active session's call_id with the real one
        returned by FlowKit's `webrtc.offer`. Closes any prior stale session
        for the same agent.
        """

        existing = await AgentWebRTCSessionRepository.get_active(db, tenant_id, employee_id)
        if existing:
            if existing.webrtc_call_id == webrtc_call_id:
                return _to_resp(existing)
            await AgentWebRTCSessionRepository.close(db, existing)
        row = await AgentWebRTCSessionRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "employee_id": employee_id,
                "webrtc_call_id": webrtc_call_id,
                "state": "online_idle",
            },
        )
        return _to_resp(row)

    @staticmethod
    async def get_employee_for_call_id(
        db: AsyncSession, call_id: str
    ) -> dict | None:
        """Reverse lookup used when FlowKit pushes events targeting an agent leg."""

        from sqlalchemy import select, desc as sa_desc
        from app.models.agent_webrtc_session import AgentWebRTCSession

        q = (
            select(AgentWebRTCSession)
            .where(AgentWebRTCSession.webrtc_call_id == call_id)
            .order_by(sa_desc(AgentWebRTCSession.started_at))
            .limit(1)
        )
        row = (await db.execute(q)).scalar_one_or_none()
        if row is None:
            return None
        return {
            "tenant_id": row.tenant_id,
            "employee_id": row.employee_id,
            "state": row.state,
        }

    @staticmethod
    async def close(db: AsyncSession, tenant_id: int, employee_id: int) -> None:
        row = await AgentWebRTCSessionRepository.get_active(db, tenant_id, employee_id)
        if not row:
            raise NotFoundError("No active session")
        await AgentWebRTCSessionRepository.close(db, row)

    @staticmethod
    async def set_busy(
        db: AsyncSession, tenant_id: int, employee_id: int, busy: bool
    ) -> dict | None:
        """Called by orchestrator before/after a bridge to flip the leg's state."""

        row = await AgentWebRTCSessionRepository.get_active(db, tenant_id, employee_id)
        if not row:
            return None
        updated = await AgentWebRTCSessionRepository.update_state(
            db, row, "busy" if busy else "online_idle"
        )
        return _to_resp(updated)


def _to_resp(row) -> dict:
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "webrtc_call_id": row.webrtc_call_id,
        "state": row.state,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
    }
