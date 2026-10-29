"""Persistence and query helpers for the call-record projection."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.call_record import CallRecord

class CallRecordRepository:
    @staticmethod
    async def lock_creation(db: AsyncSession, tenant_id: int, call_id: str) -> None:
        """Serialize creation even before a call record exists across workers."""
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"call-record:{tenant_id}:{call_id}"},
        )

    @staticmethod
    async def get_by_id_unscoped(db: AsyncSession, record_id: int) -> CallRecord | None:
        return await db.get(CallRecord, record_id)

    @staticmethod
    async def lock_by_id(db: AsyncSession, record_id: int) -> CallRecord | None:
        query = select(CallRecord).where(CallRecord.id == record_id).with_for_update()
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def list_finalization_retry_candidate_ids(
        db: AsyncSession,
        *,
        pending_before: datetime,
        failed_before: datetime,
        limit: int,
    ) -> list[int]:
        query = (
            select(CallRecord.id)
            .where(
                CallRecord.lifecycle_status == "ended",
                or_(
                    and_(
                        CallRecord.finalization_status == "pending",
                        CallRecord.updated_at <= pending_before,
                    ),
                    and_(
                        CallRecord.finalization_status == "failed",
                        CallRecord.updated_at <= failed_before,
                    ),
                ),
            )
            .order_by(CallRecord.updated_at.asc(), CallRecord.id.asc())
            .limit(limit)
        )
        return list((await db.execute(query)).scalars().all())

    @staticmethod
    async def get_by_id(
        db: AsyncSession, record_id: int, tenant_id: int
    ) -> CallRecord | None:
        query = select(CallRecord).where(
            CallRecord.id == record_id,
            CallRecord.tenant_id == tenant_id,
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def get_by_public_id(
        db: AsyncSession, public_id: UUID | str, tenant_id: int
    ) -> CallRecord | None:
        query = select(CallRecord).where(
            CallRecord.public_id == public_id,
            CallRecord.tenant_id == tenant_id,
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def get_by_call_id(
        db: AsyncSession, call_id: str, tenant_id: int
    ) -> CallRecord | None:
        query = select(CallRecord).where(
            CallRecord.call_id == call_id,
            CallRecord.tenant_id == tenant_id,
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def get_latest_active_for_agent(
        db: AsyncSession, tenant_id: int, agent_id: int
    ) -> CallRecord | None:
        # Only the agent currently holding the call. Agents who served it
        # earlier (e.g. transferred it away) keep record access but must not
        # be treated as still in the call.
        query = (
            select(CallRecord)
            .where(
                CallRecord.tenant_id == tenant_id,
                CallRecord.lifecycle_status == "active",
                or_(
                    CallRecord.last_serving_agent_id == agent_id,
                    and_(
                        CallRecord.last_serving_agent_id.is_(None),
                        CallRecord.initiator_agent_id == agent_id,
                    ),
                ),
            )
            .order_by(desc(CallRecord.started_at))
            .limit(1)
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def get_by_call_id_unscoped(
        db: AsyncSession, call_id: str
    ) -> CallRecord | None:
        query = select(CallRecord).where(CallRecord.call_id == call_id)
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def find_by_media_call_id(
        db: AsyncSession, call_id: str
    ) -> CallRecord | None:
        query = select(CallRecord).where(CallRecord.call_id == call_id)
        row = (await db.execute(query)).scalar_one_or_none()
        if row is not None:
            return row
        query = select(CallRecord).where(CallRecord.root_call_id == call_id)
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        *,
        page: int = 1,
        per_page: int = 20,
        direction: str | None = None,
        call_source: str | None = None,
        lifecycle_status: str | None = None,
        finalization_status: str | None = None,
        actual_reception_type: str | None = None,
        call_result: str | None = None,
        hangup_party: str | None = None,
        hangup_reason_code: str | None = None,
        initiator_agent_id: int | None = None,
        last_serving_agent_id: int | None = None,
        user_id: int | None = None,
        last_queue_type: str | None = None,
        last_queue_id: int | None = None,
        recording_status: str | None = None,
        satisfaction_results: list[str] | None = None,
        satisfaction_trigger_sources: list[str] | None = None,
        keyword: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        min_total_duration_ms: int | None = None,
        max_total_duration_ms: int | None = None,
        min_customer_ring_duration_ms: int | None = None,
        max_customer_ring_duration_ms: int | None = None,
        min_agent_wait_duration_ms: int | None = None,
        max_agent_wait_duration_ms: int | None = None,
        min_customer_agent_talk_duration_ms: int | None = None,
        max_customer_agent_talk_duration_ms: int | None = None,
        scope_predicate: ColumnElement | None = None,
    ) -> tuple[list[CallRecord], int]:
        query = select(CallRecord).where(CallRecord.tenant_id == tenant_id)
        if scope_predicate is not None:
            query = query.where(scope_predicate)

        equality_filters = {
            CallRecord.direction: direction,
            CallRecord.call_source: call_source,
            CallRecord.lifecycle_status: lifecycle_status,
            CallRecord.finalization_status: finalization_status,
            CallRecord.actual_reception_type: actual_reception_type,
            CallRecord.call_result: call_result,
            CallRecord.hangup_party: hangup_party,
            CallRecord.hangup_reason_code: hangup_reason_code,
            CallRecord.initiator_agent_id: initiator_agent_id,
            CallRecord.last_serving_agent_id: last_serving_agent_id,
            CallRecord.user_id: user_id,
            CallRecord.last_queue_type: last_queue_type,
            CallRecord.last_queue_id: last_queue_id,
            CallRecord.recording_status: recording_status,
        }
        for column, value in equality_filters.items():
            if value is not None:
                query = query.where(column == value)

        if satisfaction_results:
            query = query.where(CallRecord.satisfaction_result.in_(satisfaction_results))
        if satisfaction_trigger_sources:
            query = query.where(
                CallRecord.satisfaction_trigger_source.in_(satisfaction_trigger_sources)
            )

        if keyword:
            pattern = f"%{keyword}%"
            query = query.where(
                or_(
                    CallRecord.customer_number.ilike(pattern),
                    CallRecord.service_number.ilike(pattern),
                    CallRecord.call_id.ilike(pattern),
                )
            )
        if start_time is not None:
            query = query.where(CallRecord.started_at >= start_time)
        if end_time is not None:
            query = query.where(CallRecord.started_at <= end_time)
        duration_filters = (
            (CallRecord.total_duration_ms, min_total_duration_ms, max_total_duration_ms),
            (
                CallRecord.customer_ring_duration_ms,
                min_customer_ring_duration_ms,
                max_customer_ring_duration_ms,
            ),
            (
                CallRecord.agent_wait_duration_ms,
                min_agent_wait_duration_ms,
                max_agent_wait_duration_ms,
            ),
            (
                CallRecord.customer_agent_talk_duration_ms,
                min_customer_agent_talk_duration_ms,
                max_customer_agent_talk_duration_ms,
            ),
        )
        for column, minimum, maximum in duration_filters:
            if minimum is not None:
                query = query.where(column >= minimum)
            if maximum is not None:
                query = query.where(column <= maximum)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar_one()
        offset = (page - 1) * per_page
        query = (
            query.order_by(desc(CallRecord.started_at), desc(CallRecord.id))
            .offset(offset)
            .limit(per_page)
        )
        rows = list((await db.execute(query)).scalars().all())
        return rows, total

    @staticmethod
    async def create(
        db: AsyncSession, data: dict, *, commit: bool = True
    ) -> CallRecord:
        row = CallRecord(**data)
        db.add(row)
        if commit:
            await db.commit()
            await db.refresh(row)
        else:
            await db.flush()
        return row

    @staticmethod
    async def update(
        db: AsyncSession,
        row: CallRecord,
        patch: dict,
        *,
        commit: bool = True,
    ) -> CallRecord:
        for key, value in patch.items():
            setattr(row, key, value)
        if commit:
            await db.commit()
            await db.refresh(row)
        else:
            await db.flush()
        return row
