"""
Repository helpers for conversation pins.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_pin import ConversationPin


class ConversationPinRepository:
    @staticmethod
    async def get_by_agent_conversation(
        db: AsyncSession,
        *,
        tenant_id: int,
        agent_id: int,
        conversation_id: int,
    ) -> ConversationPin | None:
        result = await db.execute(
            select(ConversationPin).where(
                ConversationPin.tenant_id == tenant_id,
                ConversationPin.agent_id == agent_id,
                ConversationPin.conversation_id == conversation_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_conversation_ids(
        db: AsyncSession,
        *,
        tenant_id: int,
        agent_id: int,
        conversation_ids: list[int],
    ) -> dict[int, ConversationPin]:
        if not conversation_ids:
            return {}
        result = await db.execute(
            select(ConversationPin).where(
                ConversationPin.tenant_id == tenant_id,
                ConversationPin.agent_id == agent_id,
                ConversationPin.conversation_id.in_(conversation_ids),
            )
        )
        return {pin.conversation_id: pin for pin in result.scalars().all()}

    @staticmethod
    async def upsert(
        db: AsyncSession,
        *,
        tenant_id: int,
        agent_id: int,
        conversation_id: int,
        pinned_at: datetime,
    ) -> ConversationPin:
        existing = await ConversationPinRepository.get_by_agent_conversation(
            db,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
        )
        if existing:
            existing.pinned_at = pinned_at
            await db.commit()
            await db.refresh(existing)
            return existing

        pin = ConversationPin(
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            pinned_at=pinned_at,
        )
        db.add(pin)
        await db.commit()
        await db.refresh(pin)
        return pin

    @staticmethod
    async def delete(
        db: AsyncSession,
        *,
        tenant_id: int,
        agent_id: int,
        conversation_id: int,
    ) -> bool:
        existing = await ConversationPinRepository.get_by_agent_conversation(
            db,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
        )
        if not existing:
            return False
        await db.delete(existing)
        await db.commit()
        return True
