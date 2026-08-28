"""Data access for materialized call-record access facts."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_record_access_scope import CallRecordAccessScope


class CallRecordAccessScopeRepository:
    @staticmethod
    async def add(
        db: AsyncSession,
        *,
        tenant_id: int,
        call_record_id: int,
        subject_type: str,
        subject_id: int,
        reason: str,
        source_event_id: str,
        commit: bool = True,
    ) -> bool:
        statement = (
            insert(CallRecordAccessScope)
            .values(
                tenant_id=tenant_id,
                call_record_id=call_record_id,
                subject_type=subject_type,
                subject_id=subject_id,
                reason=reason,
                source_event_id=source_event_id,
            )
            .on_conflict_do_nothing()
            .returning(CallRecordAccessScope.id)
        )
        created_id = (await db.execute(statement)).scalar_one_or_none()
        if commit:
            await db.commit()
        else:
            await db.flush()
        return created_id is not None

    @staticmethod
    async def has_subject(
        db: AsyncSession,
        *,
        tenant_id: int,
        call_record_id: int,
        subject_type: str,
        subject_ids: list[int],
    ) -> bool:
        if not subject_ids:
            return False
        query = select(CallRecordAccessScope.id).where(
            CallRecordAccessScope.tenant_id == tenant_id,
            CallRecordAccessScope.call_record_id == call_record_id,
            CallRecordAccessScope.subject_type == subject_type,
            CallRecordAccessScope.subject_id.in_(subject_ids),
        )
        return (await db.execute(query.limit(1))).scalar_one_or_none() is not None
