"""Database access for append-only call trajectory events."""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_event import CallEvent
from app.models.call_record import CallRecord


class CallEventRepository:
    """Persist and query immutable call events."""

    @staticmethod
    async def get_duplicate(
        db: AsyncSession,
        *,
        event_id: str,
        source: str,
        source_event_id: str | None,
    ) -> CallEvent | None:
        query = select(CallEvent).where(CallEvent.event_id == event_id)
        row = (await db.execute(query)).scalar_one_or_none()
        if row is not None or source_event_id is None:
            return row
        query = select(CallEvent).where(
            CallEvent.source == source,
            CallEvent.source_event_id == source_event_id,
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def append(
        db: AsyncSession,
        *,
        call_record: CallRecord,
        data: dict,
        commit: bool = True,
    ) -> tuple[CallEvent, bool]:
        duplicate = await CallEventRepository.get_duplicate(
            db,
            event_id=data["event_id"],
            source=data["source"],
            source_event_id=data.get("source_event_id"),
        )
        if duplicate is not None:
            return duplicate, False

        locked_record = (
            await db.execute(
                select(CallRecord)
                .where(CallRecord.id == call_record.id)
                .with_for_update()
            )
        ).scalar_one()
        sequence_no = data.pop("sequence_no", None)
        if sequence_no is None:
            sequence_no = (
                await db.execute(
                    select(func.coalesce(func.max(CallEvent.sequence_no), 0)).where(
                        CallEvent.call_record_id == locked_record.id
                    )
                )
            ).scalar_one() + 1

        row = CallEvent(
            **data,
            tenant_id=locked_record.tenant_id,
            call_record_id=locked_record.id,
            root_call_id=locked_record.root_call_id or locked_record.call_id,
            sequence_no=sequence_no,
        )
        if commit:
            db.add(row)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                duplicate = await CallEventRepository.get_duplicate(
                    db,
                    event_id=data["event_id"],
                    source=data["source"],
                    source_event_id=data.get("source_event_id"),
                )
                if duplicate is None:
                    raise
                return duplicate, False
            await db.refresh(row)
            return row, True

        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
        except IntegrityError:
            duplicate = await CallEventRepository.get_duplicate(
                db,
                event_id=data["event_id"],
                source=data["source"],
                source_event_id=data.get("source_event_id"),
            )
            if duplicate is None:
                raise
            return duplicate, False
        return row, True

    @staticmethod
    async def get_latest_of_type(
        db: AsyncSession, call_record_id: int, event_type: str
    ) -> CallEvent | None:
        query = (
            select(CallEvent)
            .where(
                CallEvent.call_record_id == call_record_id,
                CallEvent.event_type == event_type,
            )
            .order_by(CallEvent.occurred_at.desc(), CallEvent.id.desc())
            .limit(1)
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def list_for_call(db: AsyncSession, call_record_id: int) -> list[CallEvent]:
        query = (
            select(CallEvent)
            .where(CallEvent.call_record_id == call_record_id)
            .order_by(
                CallEvent.occurred_at.asc(),
                CallEvent.sequence_no.asc(),
                CallEvent.id.asc(),
            )
        )
        return list((await db.execute(query)).scalars().all())
