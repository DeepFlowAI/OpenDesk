"""Persistent platform LLM call queue data access."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_llm_call import PlatformLLMCall
from app.configs.settings import settings


class PlatformLLMCallRepository:
    @staticmethod
    async def enqueue(db: AsyncSession, call: PlatformLLMCall) -> PlatformLLMCall:
        existing = await db.scalar(select(PlatformLLMCall).where(PlatformLLMCall.idempotency_key == call.idempotency_key))
        if existing is not None:
            return existing
        db.add(call)
        await db.flush()
        return call

    @staticmethod
    async def claim_next(db: AsyncSession, worker_id: str) -> PlatformLLMCall | None:
        now = datetime.now(timezone.utc)
        stale_at = now - timedelta(seconds=settings.PLATFORM_LLM_CLAIM_STALE_SECONDS)
        result = await db.execute(
            select(PlatformLLMCall)
            .where(
                or_(
                    PlatformLLMCall.status == "queued",
                    (
                        (PlatformLLMCall.status == "running")
                        & (PlatformLLMCall.locked_at < stale_at)
                    ),
                ),
                PlatformLLMCall.available_at <= now,
            )
            .order_by(PlatformLLMCall.available_at, PlatformLLMCall.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        call = result.scalar_one_or_none()
        if call is None:
            return None
        call.status = "running"; call.locked_at = now; call.locked_by = worker_id; call.attempt_count += 1
        await db.commit()
        return call

    @staticmethod
    async def get(db: AsyncSession, call_id: int) -> PlatformLLMCall | None:
        return await db.get(PlatformLLMCall, call_id)
