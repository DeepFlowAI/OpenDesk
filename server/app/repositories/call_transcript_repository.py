"""
CallTranscriptSegment repository — append a finalized line, list a call's lines.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_transcript_segment import CallTranscriptSegment


class CallTranscriptRepository:

    @staticmethod
    async def append(
        db: AsyncSession,
        *,
        tenant_id: int,
        call_id: str,
        role: str,
        text: str,
        seq: int | None = None,
    ) -> CallTranscriptSegment:
        row = CallTranscriptSegment(
            tenant_id=tenant_id,
            call_id=call_id,
            role=role,
            text=text,
            seq=seq,
        )
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def list_for_call(
        db: AsyncSession, tenant_id: int, call_id: str
    ) -> list[CallTranscriptSegment]:
        q = (
            select(CallTranscriptSegment)
            .where(
                CallTranscriptSegment.tenant_id == tenant_id,
                CallTranscriptSegment.call_id == call_id,
            )
            .order_by(CallTranscriptSegment.id.asc())
        )
        return list((await db.execute(q)).scalars().all())
