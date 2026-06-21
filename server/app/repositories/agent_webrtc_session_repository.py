"""
AgentWebRTCSession repository.
"""
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_webrtc_session import AgentWebRTCSession


class AgentWebRTCSessionRepository:

    @staticmethod
    async def get_active(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> AgentWebRTCSession | None:
        q = (
            select(AgentWebRTCSession)
            .where(
                AgentWebRTCSession.tenant_id == tenant_id,
                AgentWebRTCSession.employee_id == employee_id,
                AgentWebRTCSession.state != "disconnected",
            )
            .order_by(desc(AgentWebRTCSession.started_at))
            .limit(1)
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def list_active_for_employees(
        db: AsyncSession, tenant_id: int, employee_ids: list[int]
    ) -> list[AgentWebRTCSession]:
        if not employee_ids:
            return []
        q = select(AgentWebRTCSession).where(
            AgentWebRTCSession.tenant_id == tenant_id,
            AgentWebRTCSession.employee_id.in_(employee_ids),
            AgentWebRTCSession.state != "disconnected",
        )
        return list((await db.execute(q)).scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> AgentWebRTCSession:
        row = AgentWebRTCSession(**data)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def close(db: AsyncSession, row: AgentWebRTCSession) -> None:
        row.state = "disconnected"
        row.ended_at = datetime.now(timezone.utc)
        await db.commit()

    @staticmethod
    async def update_state(
        db: AsyncSession, row: AgentWebRTCSession, state: str
    ) -> AgentWebRTCSession:
        row.state = state
        await db.commit()
        await db.refresh(row)
        return row
