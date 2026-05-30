"""
CallRecord repository — paginated history + lifecycle write helpers.
"""
from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_record import CallRecord


class CallRecordRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, record_id: int, tenant_id: int) -> CallRecord | None:
        q = select(CallRecord).where(
            CallRecord.id == record_id, CallRecord.tenant_id == tenant_id
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def get_by_call_id(db: AsyncSession, call_id: str, tenant_id: int) -> CallRecord | None:
        q = select(CallRecord).where(
            CallRecord.call_id == call_id, CallRecord.tenant_id == tenant_id
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def get_latest_active_for_agent(
        db: AsyncSession, tenant_id: int, agent_id: int
    ) -> CallRecord | None:
        q = (
            select(CallRecord)
            .where(
                CallRecord.tenant_id == tenant_id,
                CallRecord.agent_id == agent_id,
                CallRecord.state.in_(("ringing", "queued", "in_progress")),
            )
            .order_by(desc(CallRecord.started_at))
            .limit(1)
        )
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def find_by_media_call_id(db: AsyncSession, call_id: str) -> CallRecord | None:
        """Resolve a CDR from a FlowKit media-leg or root_call_id.

        FlowKit `call.recording.completed` uses `call_id` as the SIP leg id
        for single-leg (phase=ai) recordings, and as `root_call_id` after
        bridge (phase=bridged). Match either column.
        """

        q = select(CallRecord).where(CallRecord.call_id == call_id)
        row = (await db.execute(q)).scalar_one_or_none()
        if row is not None:
            return row
        q = select(CallRecord).where(CallRecord.root_call_id == call_id)
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        direction: str | None = None,
        agent_id: int | None = None,
        user_id: int | None = None,
        keyword: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> tuple[list[CallRecord], int]:
        q = select(CallRecord).where(CallRecord.tenant_id == tenant_id)
        if direction in ("inbound", "outbound"):
            q = q.where(CallRecord.direction == direction)
        if agent_id is not None:
            q = q.where(CallRecord.agent_id == agent_id)
        if user_id is not None:
            q = q.where(CallRecord.user_id == user_id)
        if keyword:
            kw = f"%{keyword}%"
            q = q.where(
                (CallRecord.from_number.ilike(kw))
                | (CallRecord.to_number.ilike(kw))
                | (CallRecord.call_id.ilike(kw))
            )
        if start_time is not None:
            q = q.where(CallRecord.started_at >= start_time)
        if end_time is not None:
            q = q.where(CallRecord.started_at <= end_time)

        count_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        q = q.order_by(desc(CallRecord.started_at)).offset(offset).limit(per_page)
        rows = list((await db.execute(q)).scalars().all())
        return rows, total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> CallRecord:
        row = CallRecord(**data)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def update(db: AsyncSession, row: CallRecord, patch: dict) -> CallRecord:
        for k, v in patch.items():
            setattr(row, k, v)
        await db.commit()
        await db.refresh(row)
        return row
