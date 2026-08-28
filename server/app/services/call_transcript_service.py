"""
CallTranscriptService — persist and read the live transcript of a bridged call.

Lines are appended as ASR finals arrive during a human↔human bridge (no
partials are stored). Reads go through the call record so tenant + data-scope
enforcement is shared with the rest of the call-record API.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.repositories.call_transcript_repository import CallTranscriptRepository
from app.schemas.call_center import CallTranscriptResponse, CallTranscriptSegmentSchema
from app.schemas.permission import EffectivePrincipal
from app.services.call_record_service import CallRecordService


class CallTranscriptService:

    @staticmethod
    async def append(
        db: AsyncSession,
        *,
        tenant_id: int,
        call_id: str,
        role: str,
        text: str,
        seq: int | None = None,
    ) -> None:
        await CallTranscriptRepository.append(
            db, tenant_id=tenant_id, call_id=call_id, role=role, text=text, seq=seq
        )
        await db.commit()

    @staticmethod
    async def get_for_record(
        db: AsyncSession,
        public_id: UUID,
        tenant_id: int,
        principal: EffectivePrincipal | None = None,
    ) -> CallTranscriptResponse:
        # Enforces existence, tenant ownership and data scope (raises NotFoundError).
        record = await CallRecordService.get_by_public_id(
            db,
            public_id,
            tenant_id,
            principal,
        )
        call_id = record["call_id"]
        segments = await CallTranscriptRepository.list_for_call(db, tenant_id, call_id)
        return CallTranscriptResponse(
            call_id=call_id,
            segments=[CallTranscriptSegmentSchema.model_validate(s) for s in segments],
        )
