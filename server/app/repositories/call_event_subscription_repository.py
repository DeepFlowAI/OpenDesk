"""Data access for call event subscription rules."""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_event_subscription import (
    CallEventSubscriptionRule,
    CallEventSubscriptionRuleAudit,
)
from app.models.event_subscription import EventSubscription
from app.models.tenant import Tenant

RuleRow = tuple[CallEventSubscriptionRule, EventSubscription]


class CallEventSubscriptionRepository:
    @staticmethod
    def _rule_with_subscription():
        return select(CallEventSubscriptionRule, EventSubscription).join(
            EventSubscription,
            EventSubscription.id == CallEventSubscriptionRule.subscription_id,
        )

    @staticmethod
    async def list_paginated(
        db: AsyncSession,
        *,
        tenant_id: int,
        page: int,
        per_page: int,
        q: str | None,
        is_active: bool | None,
    ) -> tuple[list[RuleRow], int]:
        conditions = [CallEventSubscriptionRule.tenant_id == tenant_id]
        if q:
            conditions.append(CallEventSubscriptionRule.name.icontains(q, autoescape=True))
        if is_active is not None:
            conditions.append(CallEventSubscriptionRule.is_active.is_(is_active))
        total = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(CallEventSubscriptionRule)
                    .where(*conditions)
                )
            ).scalar_one()
            or 0
        )
        result = await db.execute(
            CallEventSubscriptionRepository._rule_with_subscription()
            .where(*conditions)
            .order_by(
                CallEventSubscriptionRule.updated_at.desc(),
                CallEventSubscriptionRule.id.desc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return [(row[0], row[1]) for row in result.all()], total

    @staticmethod
    async def count_for_tenant(db: AsyncSession, tenant_id: int) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(CallEventSubscriptionRule)
            .where(CallEventSubscriptionRule.tenant_id == tenant_id)
        )
        return int(result.scalar_one() or 0)

    @staticmethod
    async def lock_tenant_and_count(db: AsyncSession, tenant_id: int) -> int:
        """Serialize rule saves per tenant so limit/name/subscription checks stay consistent."""
        await db.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
        return await CallEventSubscriptionRepository.count_for_tenant(db, tenant_id)

    @staticmethod
    async def get_with_subscription(
        db: AsyncSession, *, tenant_id: int, public_id: UUID
    ) -> RuleRow | None:
        result = await db.execute(
            CallEventSubscriptionRepository._rule_with_subscription().where(
                CallEventSubscriptionRule.tenant_id == tenant_id,
                CallEventSubscriptionRule.public_id == public_id,
            )
        )
        row = result.one_or_none()
        return (row[0], row[1]) if row is not None else None

    @staticmethod
    async def get_by_name(
        db: AsyncSession, *, tenant_id: int, name: str
    ) -> CallEventSubscriptionRule | None:
        result = await db.execute(
            select(CallEventSubscriptionRule).where(
                CallEventSubscriptionRule.tenant_id == tenant_id,
                CallEventSubscriptionRule.name == name,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_subscription(
        db: AsyncSession, *, tenant_id: int, subscription_id: int
    ) -> CallEventSubscriptionRule | None:
        result = await db.execute(
            select(CallEventSubscriptionRule).where(
                CallEventSubscriptionRule.tenant_id == tenant_id,
                CallEventSubscriptionRule.subscription_id == subscription_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def rule_names_by_subscription(
        db: AsyncSession, *, tenant_id: int
    ) -> dict[int, tuple[UUID, str]]:
        result = await db.execute(
            select(
                CallEventSubscriptionRule.subscription_id,
                CallEventSubscriptionRule.public_id,
                CallEventSubscriptionRule.name,
            ).where(CallEventSubscriptionRule.tenant_id == tenant_id)
        )
        return {row[0]: (row[1], row[2]) for row in result.all()}

    @staticmethod
    async def count_for_subscription(
        db: AsyncSession, *, tenant_id: int, subscription_id: int
    ) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(CallEventSubscriptionRule)
            .where(
                CallEventSubscriptionRule.tenant_id == tenant_id,
                CallEventSubscriptionRule.subscription_id == subscription_id,
            )
        )
        return int(result.scalar_one() or 0)

    @staticmethod
    async def list_active_rules(
        db: AsyncSession, tenant_id: int
    ) -> list[CallEventSubscriptionRule]:
        result = await db.execute(
            select(CallEventSubscriptionRule).where(
                CallEventSubscriptionRule.tenant_id == tenant_id,
                CallEventSubscriptionRule.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_deliverable_subscriptions(
        db: AsyncSession, *, tenant_id: int, rule_ids: list[int]
    ) -> list[EventSubscription]:
        """Re-check cached matches inside the fact transaction: rule and subscription still active."""
        if not rule_ids:
            return []
        result = await db.execute(
            select(EventSubscription)
            .join(
                CallEventSubscriptionRule,
                CallEventSubscriptionRule.subscription_id == EventSubscription.id,
            )
            .where(
                CallEventSubscriptionRule.tenant_id == tenant_id,
                CallEventSubscriptionRule.id.in_(rule_ids),
                CallEventSubscriptionRule.is_active.is_(True),
                EventSubscription.tenant_id == tenant_id,
                EventSubscription.is_active.is_(True),
            )
            .order_by(EventSubscription.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def add(db: AsyncSession, data: dict) -> CallEventSubscriptionRule:
        item = CallEventSubscriptionRule(**data)
        db.add(item)
        await db.flush()
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: CallEventSubscriptionRule) -> None:
        await db.delete(item)
        await db.flush()

    @staticmethod
    async def add_audit(db: AsyncSession, data: dict) -> None:
        db.add(CallEventSubscriptionRuleAudit(**data))
        await db.flush()
