"""Data access for durable webhook delivery records."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_delivery import (
    EVENT_DELIVERY_FAILED,
    EVENT_DELIVERY_PENDING,
    EVENT_DELIVERY_PROCESSING,
    EVENT_DELIVERY_SUCCEEDED,
    EventDelivery,
)
from app.models.event_subscription import EventSubscriptionAudit


class EventDeliveryRepository:
    @staticmethod
    async def create(db: AsyncSession, data: dict) -> EventDelivery:
        item = EventDelivery(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def create_test_with_audit(
        db: AsyncSession,
        *,
        data: dict,
        audit_data: dict,
    ) -> EventDelivery:
        item = EventDelivery(**data)
        db.add(item)
        await db.flush()
        db.add(EventSubscriptionAudit(**audit_data))
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def create_many_idempotent(
        db: AsyncSession,
        rows: list[dict],
    ) -> list[UUID]:
        if not rows:
            return []
        result = await db.execute(
            insert(EventDelivery)
            .values(rows)
            .on_conflict_do_nothing(
                constraint="uq_event_deliveries_tenant_subscription_event"
            )
            .returning(EventDelivery.public_id)
        )
        await db.flush()
        return list(result.scalars().all())

    @staticmethod
    async def get_by_public_id(
        db: AsyncSession, public_id: UUID
    ) -> EventDelivery | None:
        result = await db.execute(
            select(EventDelivery).where(EventDelivery.public_id == public_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def claim_due(
        db: AsyncSession,
        *,
        now: datetime,
        limit: int,
    ) -> list[EventDelivery]:
        result = await db.execute(
            select(EventDelivery)
            .where(
                EventDelivery.status == EVENT_DELIVERY_PENDING,
                EventDelivery.next_attempt_at.isnot(None),
                EventDelivery.next_attempt_at <= now,
            )
            .order_by(EventDelivery.next_attempt_at.asc(), EventDelivery.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        items = list(result.scalars().all())
        for item in items:
            item.status = EVENT_DELIVERY_PROCESSING
            item.claimed_at = now
            item.updated_at = now
        if items:
            await db.commit()
        return items

    @staticmethod
    async def sweep_stale(
        db: AsyncSession,
        *,
        stale_before: datetime,
        now: datetime,
    ) -> int:
        result = await db.execute(
            update(EventDelivery)
            .where(
                EventDelivery.status == EVENT_DELIVERY_PROCESSING,
                EventDelivery.claimed_at.isnot(None),
                EventDelivery.claimed_at < stale_before,
            )
            .values(
                status=EVENT_DELIVERY_PENDING,
                claimed_at=None,
                next_attempt_at=now,
                updated_at=now,
            )
        )
        await db.commit()
        return result.rowcount or 0

    @staticmethod
    async def delete_completed_before(
        db: AsyncSession,
        *,
        cutoff: datetime,
        limit: int,
    ) -> int:
        """Delete one bounded batch of terminal delivery snapshots."""
        ids = (
            select(EventDelivery.id)
            .where(
                EventDelivery.status.in_(
                    [EVENT_DELIVERY_SUCCEEDED, EVENT_DELIVERY_FAILED]
                ),
                EventDelivery.completed_at.isnot(None),
                EventDelivery.completed_at < cutoff,
            )
            .order_by(EventDelivery.completed_at.asc(), EventDelivery.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(delete(EventDelivery).where(EventDelivery.id.in_(ids)))
        await db.commit()
        return result.rowcount or 0

    @staticmethod
    async def persist_attempt(
        db: AsyncSession,
        *,
        public_id: UUID,
        data: dict,
    ) -> EventDelivery | None:
        item = await EventDeliveryRepository.get_by_public_id(db, public_id)
        if item is None:
            return None
        for key, value in data.items():
            setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def persist_attempts(
        db: AsyncSession,
        *,
        attempts: list[tuple[UUID, dict]],
        claimed_at: datetime,
    ) -> int:
        """Persist a worker-owned slice in one transaction."""
        if not attempts:
            return 0
        data_by_id = dict(attempts)
        result = await db.execute(
            select(EventDelivery).where(
                EventDelivery.public_id.in_(data_by_id),
                EventDelivery.status == EVENT_DELIVERY_PROCESSING,
                EventDelivery.claimed_at == claimed_at,
            )
        )
        items = list(result.scalars().all())
        for item in items:
            for key, value in data_by_id[item.public_id].items():
                setattr(item, key, value)
        if items:
            await db.commit()
        return len(items)

    @staticmethod
    async def persist_attempt_with_audit(
        db: AsyncSession,
        *,
        public_id: UUID,
        data: dict,
        audit_data: dict,
    ) -> EventDelivery | None:
        item = await EventDeliveryRepository.get_by_public_id(db, public_id)
        if item is None:
            return None
        for key, value in data.items():
            setattr(item, key, value)
        db.add(EventSubscriptionAudit(**audit_data))
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def latest_for_subscriptions(
        db: AsyncSession,
        *,
        tenant_id: int,
        subscription_public_ids: list[UUID],
    ) -> dict[UUID, dict]:
        if not subscription_public_ids:
            return {}
        ranked = (
            select(
                EventDelivery.subscription_public_id.label("subscription_public_id"),
                EventDelivery.status.label("status"),
                EventDelivery.last_http_status.label("http_status"),
                EventDelivery.last_duration_ms.label("duration_ms"),
                EventDelivery.last_error_type.label("error_type"),
                EventDelivery.last_attempt_at.label("attempted_at"),
                func.row_number()
                .over(
                    partition_by=EventDelivery.subscription_public_id,
                    order_by=(EventDelivery.created_at.desc(), EventDelivery.id.desc()),
                )
                .label("row_number"),
            )
            .where(
                EventDelivery.tenant_id == tenant_id,
                EventDelivery.subscription_public_id.in_(subscription_public_ids),
            )
            .subquery()
        )
        result = await db.execute(select(ranked).where(ranked.c.row_number == 1))
        return {
            row.subscription_public_id: {
                "status": row.status,
                "http_status": row.http_status,
                "duration_ms": row.duration_ms,
                "error_type": row.error_type,
                "attempted_at": row.attempted_at,
            }
            for row in result.all()
        }
