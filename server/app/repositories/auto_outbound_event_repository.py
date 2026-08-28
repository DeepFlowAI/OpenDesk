"""Data access for auto outbound event bindings and event snapshot context."""
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auto_outbound_event_subscription import (
    AutoOutboundEventSubscription,
    AutoOutboundEventSubscriptionAudit,
)
from app.models.event_subscription import EventSubscription


class AutoOutboundEventRepository:
    @staticmethod
    async def get_binding(
        db: AsyncSession, *, tenant_id: int, task_id: int
    ) -> AutoOutboundEventSubscription | None:
        result = await db.execute(
            select(AutoOutboundEventSubscription).where(
                AutoOutboundEventSubscription.tenant_id == tenant_id,
                AutoOutboundEventSubscription.task_id == task_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_binding_with_subscription(
        db: AsyncSession, *, tenant_id: int, task_id: int
    ) -> tuple[AutoOutboundEventSubscription, EventSubscription] | None:
        """Load one task binding and its tenant-scoped subscription in one query."""
        result = await db.execute(
            select(AutoOutboundEventSubscription, EventSubscription)
            .join(
                EventSubscription,
                EventSubscription.id == AutoOutboundEventSubscription.subscription_id,
            )
            .where(
                AutoOutboundEventSubscription.tenant_id == tenant_id,
                AutoOutboundEventSubscription.task_id == task_id,
                EventSubscription.tenant_id == tenant_id,
            )
        )
        row = result.one_or_none()
        return (row[0], row[1]) if row is not None else None

    @staticmethod
    async def list_options(
        db: AsyncSession,
        *,
        tenant_id: int,
        current_public_id: UUID | None,
    ) -> list[EventSubscription]:
        condition = EventSubscription.is_active.is_(True)
        if current_public_id is not None:
            condition = or_(
                condition,
                EventSubscription.public_id == current_public_id,
            )
        result = await db.execute(
            select(EventSubscription)
            .where(EventSubscription.tenant_id == tenant_id, condition)
            .order_by(EventSubscription.name.asc(), EventSubscription.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def add_binding(
        db: AsyncSession, data: dict
    ) -> AutoOutboundEventSubscription:
        item = AutoOutboundEventSubscription(**data)
        db.add(item)
        await db.flush()
        return item

    @staticmethod
    async def delete_binding(
        db: AsyncSession, item: AutoOutboundEventSubscription
    ) -> None:
        await db.delete(item)
        await db.flush()

    @staticmethod
    async def add_audit(db: AsyncSession, data: dict) -> None:
        db.add(AutoOutboundEventSubscriptionAudit(**data))
        await db.flush()

    @staticmethod
    async def count_bindings_for_subscription(
        db: AsyncSession, *, tenant_id: int, subscription_public_id: UUID
    ) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(AutoOutboundEventSubscription)
            .where(
                AutoOutboundEventSubscription.tenant_id == tenant_id,
                AutoOutboundEventSubscription.subscription_public_id
                == subscription_public_id,
            )
        )
        return int(result.scalar_one() or 0)
