"""Resolve server-owned business context for the call workspace."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auto_outbound import AutoOutboundCallRecord
from app.models.call_record import CallRecord
from app.repositories.auto_outbound_repository import AutoOutboundRepository


class CallWorkspaceContextService:
    """Build call-screen metadata from durable backend records."""

    @staticmethod
    def _auto_outbound_context(
        record: AutoOutboundCallRecord,
    ) -> dict[str, str | int]:
        return {
            "source": "auto_outbound",
            "task_id": int(record.task_id),
            "record_id": int(record.id),
        }

    @staticmethod
    async def get_auto_outbound_context(
        db: AsyncSession,
        *,
        tenant_id: int,
        call_record: CallRecord | None,
    ) -> dict[str, str | int]:
        if call_record is None or call_record.call_source != "auto_outbound":
            return {}
        record = await AutoOutboundRepository.get_record_by_call_record_id(
            db,
            tenant_id=tenant_id,
            call_record_id=call_record.id,
        )
        if record is None:
            return {}
        return CallWorkspaceContextService._auto_outbound_context(record)

    @staticmethod
    async def get_auto_outbound_contexts(
        db: AsyncSession,
        *,
        tenant_id: int,
        call_records: list[CallRecord],
    ) -> dict[int, dict[str, str | int]]:
        call_record_ids = sorted(
            {
                record.id
                for record in call_records
                if record.call_source == "auto_outbound"
            }
        )
        if not call_record_ids:
            return {}
        records = await AutoOutboundRepository.get_latest_records_by_call_record_ids(
            db,
            tenant_id=tenant_id,
            call_record_ids=call_record_ids,
        )
        return {
            call_record_id: CallWorkspaceContextService._auto_outbound_context(record)
            for call_record_id, record in records.items()
        }
