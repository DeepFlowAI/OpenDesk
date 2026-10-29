"""Platform-wide persistent LLM dispatcher."""
from __future__ import annotations

import json
import socket
from datetime import datetime, timedelta, timezone

from app.db.session import AsyncSessionLocal
from app.libs.llm import create_llm_client
from app.repositories.platform_llm_call_repository import PlatformLLMCallRepository


class PlatformLLMQueueService:
    """Claim work in a short session, call the provider session-free, then persist."""

    @staticmethod
    async def run_tick() -> bool:
        worker_id = socket.gethostname()
        async with AsyncSessionLocal() as db:
            call = await PlatformLLMCallRepository.claim_next(db, worker_id)
            if call is None:
                return False
            call_id = call.id
            request_payload = dict(call.request_payload)
        try:
            text = await create_llm_client().complete(
                request_payload["messages"],
                temperature=0,
                max_tokens=1000,
            )
            payload = json.loads(text)
            from app.services.quality_review_execution_service import QualityReviewExecutionService

            await QualityReviewExecutionService.complete_call_managed(call_id, payload)
        except Exception as exc:  # noqa: BLE001
            from app.services.quality_review_execution_service import QualityReviewExecutionService

            await QualityReviewExecutionService.fail_call_managed(call_id, type(exc).__name__)
        return True

    @staticmethod
    def schedule_retry(call, now: datetime) -> bool:
        if call.attempt_count >= call.max_attempts:
            call.status = "failed"; call.completed_at = now
            return False
        call.status = "queued"
        call.available_at = now + timedelta(seconds=min(60, 2 ** call.attempt_count))
        call.locked_at = None; call.locked_by = None
        return True
