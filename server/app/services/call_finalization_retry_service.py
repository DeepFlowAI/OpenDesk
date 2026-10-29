"""Durable retry loop for stale or failed call-record finalization."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.configs.settings import settings
from app.db.session import AsyncSessionLocal
from app.repositories.call_record_repository import CallRecordRepository
from app.services.call_record_service import CallRecordService

logger = logging.getLogger(__name__)


class CallFinalizationRetryService:
    @staticmethod
    async def run_tick() -> dict[str, int]:
        """Discover eligible CDRs, then retry each in its own short session."""
        now = datetime.now(timezone.utc)
        pending_before = now - timedelta(
            seconds=settings.CALL_FINALIZATION_PENDING_TIMEOUT_SECONDS
        )
        failed_before = now - timedelta(
            seconds=settings.CALL_FINALIZATION_FAILED_RETRY_SECONDS
        )
        async with AsyncSessionLocal() as db:
            candidate_ids = (
                await CallRecordRepository.list_finalization_retry_candidate_ids(
                    db,
                    pending_before=pending_before,
                    failed_before=failed_before,
                    limit=settings.CALL_FINALIZATION_RETRY_BATCH_SIZE,
                )
            )

        stats = {"checked": len(candidate_ids), "completed": 0, "failed": 0}
        for call_record_id in candidate_ids:
            try:
                async with AsyncSessionLocal() as db:
                    completed = await CallRecordService.retry_finalization(
                        db,
                        call_record_id=call_record_id,
                        pending_before=pending_before,
                        failed_before=failed_before,
                    )
                stats["completed"] += int(completed)
                stats["failed"] += int(not completed)
            except Exception:  # noqa: BLE001
                stats["failed"] += 1
                logger.exception(
                    "Call finalization retry failed call_record_id=%s",
                    call_record_id,
                    extra={
                        "event": "call_finalization_retry_failed",
                        "call_record_id": call_record_id,
                    },
                )
        return stats
