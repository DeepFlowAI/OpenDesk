"""Data access for per-call recording artifacts."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_recording import CallRecording


class CallRecordingRepository:
    @staticmethod
    async def upsert(
        db: AsyncSession,
        data: dict,
        *,
        commit: bool = True,
    ) -> CallRecording:
        statement = (
            insert(CallRecording)
            .values(**data)
            .on_conflict_do_update(
                constraint="uq_call_recordings_tenant_recording",
                set_={
                    "call_record_id": data["call_record_id"],
                    "call_leg_id": data.get("call_leg_id"),
                    "phase": data.get("phase"),
                    "status": data["status"],
                    "storage_key": data.get("storage_key"),
                    "started_at": data.get("started_at"),
                    "ended_at": data.get("ended_at"),
                    "duration_ms": data.get("duration_ms"),
                    "source_event_id": data["source_event_id"],
                },
            )
            .returning(CallRecording.id)
        )
        recording_id = (await db.execute(statement)).scalar_one()
        if commit:
            await db.commit()
        else:
            await db.flush()
        row = await db.get(CallRecording, recording_id)
        assert row is not None
        return row

    @staticmethod
    async def get_by_recording_id(
        db: AsyncSession, tenant_id: int, recording_id: str
    ) -> CallRecording | None:
        query = (
            select(CallRecording)
            .where(
                CallRecording.tenant_id == tenant_id,
                CallRecording.recording_id == recording_id,
            )
            .execution_options(populate_existing=True)
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def list_for_call(
        db: AsyncSession, call_record_id: int
    ) -> list[CallRecording]:
        query = (
            select(CallRecording)
            .where(CallRecording.call_record_id == call_record_id)
            .order_by(CallRecording.started_at.asc().nulls_last(), CallRecording.id.asc())
        )
        return list((await db.execute(query)).scalars().all())
