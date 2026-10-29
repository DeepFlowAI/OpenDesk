"""Configuration rules that route call facts to global event subscriptions."""
from __future__ import annotations

import math
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.call_event_subscription import CallEventSubscriptionRule
from app.models.event_subscription import EventSubscription
from app.repositories.auto_outbound_event_repository import AutoOutboundEventRepository
from app.repositories.call_event_subscription_repository import CallEventSubscriptionRepository
from app.repositories.event_subscription_repository import EventSubscriptionRepository
from app.schemas.call_event_subscription import (
    MAX_CALL_EVENT_RULES,
    CallEventRuleListResponse,
    CallEventRuleOption,
    CallEventRuleOptionsResponse,
    CallEventRuleResponse,
    CallEventRuleSave,
    CallEventRuleSubscription,
)
from app.schemas.permission import EffectivePrincipal
from app.services.call_event_rule_cache import CallEventRuleCache

MANAGE_PERMISSION = "call.admin.event_subscription.manage"


class CallEventSubscriptionService:
    @staticmethod
    def _to_response(
        rule: CallEventSubscriptionRule, subscription: EventSubscription
    ) -> CallEventRuleResponse:
        return CallEventRuleResponse(
            public_id=rule.public_id,
            name=rule.name,
            subscription=CallEventRuleSubscription(
                public_id=subscription.public_id,
                name=subscription.name,
                is_active=subscription.is_active,
            ),
            event_types=list(rule.event_types or []),
            directions=list(rule.directions or []),
            call_sources=list(rule.call_sources or []),
            is_active=rule.is_active,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )

    @staticmethod
    async def _get_row(
        db: AsyncSession, principal: EffectivePrincipal, rule_id: UUID
    ) -> tuple[CallEventSubscriptionRule, EventSubscription]:
        row = await CallEventSubscriptionRepository.get_with_subscription(
            db, tenant_id=principal.tenant_id, public_id=rule_id
        )
        if row is None:
            raise NotFoundError("Call event subscription rule not found")
        return row

    @staticmethod
    async def list_rules(
        db: AsyncSession,
        principal: EffectivePrincipal,
        *,
        page: int,
        per_page: int,
        q: str | None,
        status: str | None,
    ) -> CallEventRuleListResponse:
        is_active = {"active": True, "inactive": False}.get(status or "")
        keyword = (q or "").strip()[:50] or None
        rows, total = await CallEventSubscriptionRepository.list_paginated(
            db,
            tenant_id=principal.tenant_id,
            page=page,
            per_page=per_page,
            q=keyword,
            is_active=is_active,
        )
        tenant_count = (
            total
            if keyword is None and is_active is None
            else await CallEventSubscriptionRepository.count_for_tenant(db, principal.tenant_id)
        )
        return CallEventRuleListResponse(
            items=[
                CallEventSubscriptionService._to_response(rule, subscription)
                for rule, subscription in rows
            ],
            total=total,
            page=page,
            per_page=per_page,
            pages=math.ceil(total / per_page) if total else 0,
            tenant_rule_count=tenant_count,
            max_rules=MAX_CALL_EVENT_RULES,
        )

    @staticmethod
    async def get_rule(
        db: AsyncSession, principal: EffectivePrincipal, rule_id: UUID
    ) -> CallEventRuleResponse:
        rule, subscription = await CallEventSubscriptionService._get_row(db, principal, rule_id)
        return CallEventSubscriptionService._to_response(rule, subscription)

    @staticmethod
    async def list_options(
        db: AsyncSession,
        principal: EffectivePrincipal,
        rule_id: UUID | None = None,
    ) -> CallEventRuleOptionsResponse:
        current_subscription_public_id: UUID | None = None
        current_rule_public_id: UUID | None = None
        if rule_id is not None:
            rule, subscription = await CallEventSubscriptionService._get_row(
                db, principal, rule_id
            )
            current_subscription_public_id = subscription.public_id
            current_rule_public_id = rule.public_id
        subscriptions = await AutoOutboundEventRepository.list_options(
            db,
            tenant_id=principal.tenant_id,
            current_public_id=current_subscription_public_id,
        )
        used_by = await CallEventSubscriptionRepository.rule_names_by_subscription(
            db, tenant_id=principal.tenant_id
        )
        options = []
        for item in subscriptions:
            owner = used_by.get(item.id)
            used_by_rule_name = (
                owner[1] if owner is not None and owner[0] != current_rule_public_id else None
            )
            options.append(
                CallEventRuleOption(
                    public_id=item.public_id,
                    name=item.name,
                    is_active=item.is_active,
                    used_by_rule_name=used_by_rule_name,
                )
            )
        return CallEventRuleOptionsResponse(
            options=options, can_manage_global=principal.is_super_admin
        )

    @staticmethod
    async def _resolve_subscription(
        db: AsyncSession,
        principal: EffectivePrincipal,
        data: CallEventRuleSave,
        current: CallEventSubscriptionRule | None,
    ) -> EventSubscription:
        subscription = await EventSubscriptionRepository.get_for_tenant(
            db, tenant_id=principal.tenant_id, public_id=data.subscription_public_id
        )
        if subscription is None:
            raise ValidationError(
                "Subscription is unavailable",
                details={"code": "subscription_unavailable"},
            )
        keeps_current = current is not None and current.subscription_id == subscription.id
        if not subscription.is_active and not keeps_current:
            raise ValidationError(
                "The subscription is disabled",
                details={"code": "subscription_disabled"},
            )
        owner = await CallEventSubscriptionRepository.get_by_subscription(
            db, tenant_id=principal.tenant_id, subscription_id=subscription.id
        )
        if owner is not None and (current is None or owner.id != current.id):
            raise ValidationError(
                "This subscription is already used by another rule",
                details={"code": "subscription_in_use", "rule_name": owner.name},
            )
        return subscription

    @staticmethod
    async def _ensure_name_available(
        db: AsyncSession,
        principal: EffectivePrincipal,
        name: str,
        current: CallEventSubscriptionRule | None,
    ) -> None:
        existing = await CallEventSubscriptionRepository.get_by_name(
            db, tenant_id=principal.tenant_id, name=name
        )
        if existing is not None and (current is None or existing.id != current.id):
            raise ValidationError("Rule name already exists", details={"code": "name_taken"})

    @staticmethod
    def _integrity_error(exc: IntegrityError) -> ValidationError:
        text = str(exc.orig)
        if "uq_call_event_rule_tenant_name" in text:
            return ValidationError("Rule name already exists", details={"code": "name_taken"})
        if "uq_call_event_rule_tenant_subscription" in text:
            return ValidationError(
                "This subscription is already used by another rule",
                details={"code": "subscription_in_use", "rule_name": None},
            )
        return ValidationError(
            "Subscription is unavailable", details={"code": "subscription_unavailable"}
        )

    @staticmethod
    async def _audit(
        db: AsyncSession,
        principal: EffectivePrincipal,
        rule: CallEventSubscriptionRule,
        subscription_public_id: UUID | None,
        action: str,
    ) -> None:
        await CallEventSubscriptionRepository.add_audit(
            db,
            {
                "tenant_id": principal.tenant_id,
                "rule_public_id": rule.public_id,
                "subscription_public_id": subscription_public_id,
                "action": action,
                "actor_employee_id": principal.user_id,
                "metadata_json": {
                    "name": rule.name,
                    "event_types": list(rule.event_types or []),
                    "directions": list(rule.directions or []),
                    "call_sources": list(rule.call_sources or []),
                    "is_active": rule.is_active,
                },
            },
        )

    @staticmethod
    async def create_rule(
        db: AsyncSession, principal: EffectivePrincipal, data: CallEventRuleSave
    ) -> CallEventRuleResponse:
        count = await CallEventSubscriptionRepository.lock_tenant_and_count(
            db, principal.tenant_id
        )
        if count >= MAX_CALL_EVENT_RULES:
            raise ValidationError(
                f"You can create up to {MAX_CALL_EVENT_RULES} rules",
                details={"code": "rule_limit"},
            )
        await CallEventSubscriptionService._ensure_name_available(db, principal, data.name, None)
        subscription = await CallEventSubscriptionService._resolve_subscription(
            db, principal, data, None
        )
        try:
            rule = await CallEventSubscriptionRepository.add(
                db,
                {
                    "tenant_id": principal.tenant_id,
                    "name": data.name,
                    "subscription_id": subscription.id,
                    "event_types": data.event_types,
                    "directions": data.directions,
                    "call_sources": data.call_sources,
                    "is_active": True,
                    "created_by_employee_id": principal.user_id,
                    "updated_by_employee_id": principal.user_id,
                },
            )
        except IntegrityError as exc:
            await db.rollback()
            raise CallEventSubscriptionService._integrity_error(exc) from exc
        await CallEventSubscriptionService._audit(
            db, principal, rule, subscription.public_id, "created"
        )
        await db.commit()
        await CallEventRuleCache.invalidate(principal.tenant_id)
        return await CallEventSubscriptionService.get_rule(db, principal, rule.public_id)

    @staticmethod
    async def update_rule(
        db: AsyncSession,
        principal: EffectivePrincipal,
        rule_id: UUID,
        data: CallEventRuleSave,
    ) -> CallEventRuleResponse:
        await CallEventSubscriptionRepository.lock_tenant_and_count(db, principal.tenant_id)
        rule, _ = await CallEventSubscriptionService._get_row(db, principal, rule_id)
        await CallEventSubscriptionService._ensure_name_available(db, principal, data.name, rule)
        subscription = await CallEventSubscriptionService._resolve_subscription(
            db, principal, data, rule
        )
        rule.name = data.name
        rule.subscription_id = subscription.id
        rule.event_types = data.event_types
        rule.directions = data.directions
        rule.call_sources = data.call_sources
        rule.updated_by_employee_id = principal.user_id
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise CallEventSubscriptionService._integrity_error(exc) from exc
        await CallEventSubscriptionService._audit(
            db, principal, rule, subscription.public_id, "updated"
        )
        await db.commit()
        await CallEventRuleCache.invalidate(principal.tenant_id)
        return await CallEventSubscriptionService.get_rule(db, principal, rule_id)

    @staticmethod
    async def set_active(
        db: AsyncSession,
        principal: EffectivePrincipal,
        rule_id: UUID,
        is_active: bool,
    ) -> CallEventRuleResponse:
        rule, subscription = await CallEventSubscriptionService._get_row(db, principal, rule_id)
        if rule.is_active != is_active:
            rule.is_active = is_active
            rule.updated_by_employee_id = principal.user_id
            await db.flush()
            await CallEventSubscriptionService._audit(
                db,
                principal,
                rule,
                subscription.public_id,
                "enabled" if is_active else "disabled",
            )
            await db.commit()
            await CallEventRuleCache.invalidate(principal.tenant_id)
        return await CallEventSubscriptionService.get_rule(db, principal, rule_id)

    @staticmethod
    async def delete_rule(
        db: AsyncSession, principal: EffectivePrincipal, rule_id: UUID
    ) -> None:
        rule, subscription = await CallEventSubscriptionService._get_row(db, principal, rule_id)
        await CallEventSubscriptionService._audit(
            db, principal, rule, subscription.public_id, "deleted"
        )
        await CallEventSubscriptionRepository.delete(db, rule)
        await db.commit()
        await CallEventRuleCache.invalidate(principal.tenant_id)
