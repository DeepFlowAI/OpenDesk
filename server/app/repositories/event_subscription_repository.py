"""Data access for event subscriptions and their management audits."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_subscription import EventSubscription, EventSubscriptionAudit
from app.models.tenant import Tenant


class EventSubscriptionRepository:
    @staticmethod
    async def list_for_tenant(
        db: AsyncSession,
        *,
        tenant_id: int,
        page: int,
        per_page: int,
        query: str | None,
        is_active: bool | None,
    ) -> tuple[list[EventSubscription], int]:
        conditions = [EventSubscription.tenant_id == tenant_id]
        if query:
            conditions.append(EventSubscription.name.ilike(f"%{query}%"))
        if is_active is not None:
            conditions.append(EventSubscription.is_active == is_active)

        total = (
            await db.execute(
                select(func.count()).select_from(EventSubscription).where(*conditions)
            )
        ).scalar_one()
        result = await db.execute(
            select(EventSubscription)
            .where(*conditions)
            .order_by(EventSubscription.updated_at.desc(), EventSubscription.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_for_tenant(
        db: AsyncSession, *, tenant_id: int, public_id: UUID
    ) -> EventSubscription | None:
        result = await db.execute(
            select(EventSubscription).where(
                EventSubscription.tenant_id == tenant_id,
                EventSubscription.public_id == public_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_selected_for_tenant(
        db: AsyncSession,
        *,
        tenant_id: int,
        public_ids: list[UUID],
    ) -> list[EventSubscription]:
        if not public_ids:
            return []
        result = await db.execute(
            select(EventSubscription).where(
                EventSubscription.tenant_id == tenant_id,
                EventSubscription.public_id.in_(public_ids),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def lock_tenant_and_count(db: AsyncSession, tenant_id: int) -> int:
        await db.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
        return (
            await db.execute(
                select(func.count())
                .select_from(EventSubscription)
                .where(EventSubscription.tenant_id == tenant_id)
            )
        ).scalar_one()

    @staticmethod
    async def create_with_audit(
        db: AsyncSession,
        *,
        data: dict,
        audit_data: dict,
    ) -> EventSubscription:
        item = EventSubscription(**data)
        db.add(item)
        await db.flush()
        db.add(EventSubscriptionAudit(**audit_data, subscription_public_id=item.public_id))
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update_with_audit(
        db: AsyncSession,
        *,
        item: EventSubscription,
        data: dict,
        audit_data: dict,
    ) -> EventSubscription:
        for key, value in data.items():
            setattr(item, key, value)
        db.add(EventSubscriptionAudit(**audit_data, subscription_public_id=item.public_id))
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete_with_audit(
        db: AsyncSession,
        *,
        item: EventSubscription,
        audit_data: dict,
    ) -> None:
        db.add(EventSubscriptionAudit(**audit_data, subscription_public_id=item.public_id))
        await db.delete(item)
        await db.commit()


class EventSubscriptionAuditRepository:
    @staticmethod
    async def record(
        db: AsyncSession,
        *,
        tenant_id: int,
        subscription_public_id: UUID,
        action: str,
        actor_employee_id: int | None,
        metadata: dict,
        created_at: datetime | None = None,
    ) -> EventSubscriptionAudit:
        item = EventSubscriptionAudit(
            tenant_id=tenant_id,
            subscription_public_id=subscription_public_id,
            action=action,
            actor_employee_id=actor_employee_id,
            metadata_json=metadata,
        )
        if created_at is not None:
            item.created_at = created_at
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item
