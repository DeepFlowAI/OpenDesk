"""Tenant-scoped recording lookups by public ID for the Open API."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_record import CallRecord
from app.models.call_recording import CallRecording
from app.models.call_recording_link_audit import CallRecordingLinkAudit


class OpenCallRecordingRepository:
    @staticmethod
    async def get_call(
        db: AsyncSession, *, tenant_id: int, call_public_id: UUID
    ) -> CallRecord | None:
        query = select(CallRecord).where(
            CallRecord.tenant_id == tenant_id,
            CallRecord.public_id == call_public_id,
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def list_for_call(db: AsyncSession, call_record_id: int) -> list[CallRecording]:
        query = (
            select(CallRecording)
            .where(
                CallRecording.call_record_id == call_record_id,
                CallRecording.public_id.is_not(None),
                CallRecording.status != "recording",
            )
            .order_by(CallRecording.started_at.asc().nulls_last(), CallRecording.id.asc())
        )
        return list((await db.execute(query)).scalars().all())

    @staticmethod
    async def get_recording(
        db: AsyncSession, *, tenant_id: int, recording_public_id: UUID
    ) -> tuple[CallRecording, UUID] | None:
        query = (
            select(CallRecording, CallRecord.public_id)
            .join(CallRecord, CallRecord.id == CallRecording.call_record_id)
            .where(
                CallRecording.tenant_id == tenant_id,
                CallRecording.public_id == recording_public_id,
                CallRecording.status != "recording",
            )
        )
        row = (await db.execute(query)).first()
        if row is None:
            return None
        return row[0], row[1]

    @staticmethod
    def add_audits(db: AsyncSession, audits: list[CallRecordingLinkAudit]) -> None:
        db.add_all(audits)
