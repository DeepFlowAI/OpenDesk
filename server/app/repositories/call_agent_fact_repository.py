"""Database access for projected call employee facts."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_agent_fact import (
    CallAgentAfterCallWork,
    CallAgentOperation,
    CallAgentReceptionSegment,
)


class CallAgentFactRepository:
    """Persist idempotent employee facts using stable event identities."""

    @staticmethod
    async def upsert_segments(db: AsyncSession, rows: list[dict]) -> None:
        mutable = {
            "ended_event_id",
            "agent_id",
            "agent_name_snapshot",
            "ended_at",
            "entry_reason",
            "end_reason",
            "duration_ms",
            "talk_duration_ms",
            "hold_duration_ms",
            "consult_duration_ms",
            "held",
            "result_reliable",
        }
        for row in rows:
            statement = insert(CallAgentReceptionSegment).values(**row)
            statement = statement.on_conflict_do_update(
                index_elements=[CallAgentReceptionSegment.started_event_id],
                set_={key: getattr(statement.excluded, key) for key in mutable}
                | {"updated_at": func.now()},
            )
            await db.execute(statement)

    @staticmethod
    async def upsert_operations(db: AsyncSession, rows: list[dict]) -> None:
        mutable = {
            "actor_name_snapshot",
            "target_type",
            "target_id",
            "target_name_snapshot",
            "ended_event_id",
            "ended_at",
            "result",
            "result_reliable",
        }
        for row in rows:
            statement = insert(CallAgentOperation).values(**row)
            statement = statement.on_conflict_do_update(
                constraint="uq_call_agent_operations_identity",
                set_={key: getattr(statement.excluded, key) for key in mutable}
                | {"updated_at": func.now()},
            )
            await db.execute(statement)

    @staticmethod
    async def latest_segment_id(
        db: AsyncSession, call_record_id: int, agent_id: int
    ) -> int | None:
        return await db.scalar(
            select(CallAgentReceptionSegment.id)
            .where(
                CallAgentReceptionSegment.call_record_id == call_record_id,
                CallAgentReceptionSegment.agent_id == agent_id,
            )
            .order_by(CallAgentReceptionSegment.started_at.desc())
            .limit(1)
        )

    @staticmethod
    async def start_after_call_work(db: AsyncSession, row: dict) -> None:
        statement = insert(CallAgentAfterCallWork).values(**row)
        statement = statement.on_conflict_do_nothing(
            constraint="uq_call_agent_acw_call_agent",
        )
        await db.execute(statement)

    @staticmethod
    async def close_after_call_work(
        db: AsyncSession,
        *,
        tenant_id: int,
        agent_id: int,
        call_record_id: int | None,
        ended_at: datetime,
        end_reason: str,
    ) -> bool:
        query = select(CallAgentAfterCallWork).where(
            CallAgentAfterCallWork.tenant_id == tenant_id,
            CallAgentAfterCallWork.agent_id == agent_id,
            CallAgentAfterCallWork.ended_at.is_(None),
        )
        if call_record_id is not None:
            query = query.where(CallAgentAfterCallWork.call_record_id == call_record_id)
        row = (await db.execute(query.order_by(CallAgentAfterCallWork.started_at.desc()).limit(1))).scalar_one_or_none()
        if row is None:
            return False
        row.ended_at = max(row.started_at, ended_at)
        row.duration_ms = max(0, int((row.ended_at - row.started_at).total_seconds() * 1000))
        row.end_reason = end_reason
        row.result_reliable = True
        await db.flush()
        return True
