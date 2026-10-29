"""Business rules for tenant event subscription configuration."""
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import ENV
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.secret_store import encrypt_secret
from app.db.session import AsyncSessionLocal
from app.libs.webhook import WebhookUrlError, create_webhook_client
from app.models.event_subscription import EventSubscription
from app.repositories.event_subscription_repository import EventSubscriptionRepository
from app.schemas.event_subscription import (
    EventSubscriptionCreate,
    EventSubscriptionResponse,
    EventSubscriptionUpdate,
)
from app.schemas.permission import EffectivePrincipal

MAX_SUBSCRIPTIONS_PER_TENANT = 20
SECRET_RANDOM_BYTES = 32
SECRET_TRANSITION_HOURS = 24
PRODUCTION_ENVS = {"prod", "production", "staging"}


class EventSubscriptionService:
    @staticmethod
    def ensure_super_admin(principal: EffectivePrincipal) -> None:
        if not principal.is_super_admin:
            raise ForbiddenError("Super admin required")

    @staticmethod
    def generate_secret() -> str:
        environment = "live" if ENV.lower() in PRODUCTION_ENVS else "test"
        return f"odwhsec_{environment}_{secrets.token_urlsafe(SECRET_RANDOM_BYTES)}"

    @staticmethod
    def _audit_data(
        principal: EffectivePrincipal,
        action: str,
        metadata: dict | None = None,
    ) -> dict:
        return {
            "tenant_id": principal.tenant_id,
            "action": action,
            "actor_employee_id": principal.user_id,
            "metadata_json": metadata or {},
        }

    @staticmethod
    def _safe_endpoint_metadata(endpoint_url: str) -> dict:
        parsed = urlparse(endpoint_url)
        return {"endpoint_host": parsed.hostname or ""}

    @staticmethod
    async def list_paginated(
        db: AsyncSession,
        principal: EffectivePrincipal,
        *,
        page: int,
        per_page: int,
        query: str | None,
        status: str | None,
    ) -> dict:
        EventSubscriptionService.ensure_super_admin(principal)
        normalized_query = query.strip() if query else None
        if normalized_query and len(normalized_query) > 80:
            raise ValidationError("Search query must be at most 80 characters")
        is_active = None if status is None else status == "active"
        items, total = await EventSubscriptionRepository.list_for_tenant(
            db,
            tenant_id=principal.tenant_id,
            page=page,
            per_page=per_page,
            query=normalized_query,
            is_active=is_active,
        )
        from app.repositories.event_delivery_repository import EventDeliveryRepository

        recent = await EventDeliveryRepository.latest_for_subscriptions(
            db,
            tenant_id=principal.tenant_id,
            subscription_public_ids=[item.public_id for item in items],
        )
        serialized_items = []
        for item in items:
            serialized = EventSubscriptionResponse.model_validate(item).model_dump()
            serialized["recent_delivery"] = recent.get(item.public_id)
            serialized_items.append(serialized)
        return {
            "items": serialized_items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    @staticmethod
    async def get_scoped(
        db: AsyncSession,
        principal: EffectivePrincipal,
        public_id: UUID,
    ) -> EventSubscription:
        EventSubscriptionService.ensure_super_admin(principal)
        item = await EventSubscriptionRepository.get_for_tenant(
            db, tenant_id=principal.tenant_id, public_id=public_id
        )
        if item is None:
            raise NotFoundError("Event subscription not found")
        return item

    @staticmethod
    async def create(
        db: AsyncSession,
        principal: EffectivePrincipal,
        data: EventSubscriptionCreate,
    ) -> dict:
        EventSubscriptionService.ensure_super_admin(principal)
        count = await EventSubscriptionRepository.lock_tenant_and_count(
            db, principal.tenant_id
        )
        if count >= MAX_SUBSCRIPTIONS_PER_TENANT:
            raise ValidationError("A tenant can have at most 20 event subscriptions")

        secret = EventSubscriptionService.generate_secret()
        record = await EventSubscriptionRepository.create_with_audit(
            db,
            data={
                "tenant_id": principal.tenant_id,
                "name": data.name,
                "endpoint_url": data.endpoint_url,
                "description": data.description,
                "secret_ciphertext": encrypt_secret(secret),
                "secret_last_four": secret[-4:],
                "created_by_employee_id": principal.user_id,
                "updated_by_employee_id": principal.user_id,
            },
            audit_data=EventSubscriptionService._audit_data(
                principal,
                "create",
                EventSubscriptionService._safe_endpoint_metadata(data.endpoint_url),
            ),
        )
        return {"record": record, "secret": secret}

    @staticmethod
    async def create_managed(
        principal: EffectivePrincipal,
        data: EventSubscriptionCreate,
    ) -> dict:
        """Validate DNS without a DB session, then persist in a short session."""
        EventSubscriptionService.ensure_super_admin(principal)
        try:
            await create_webhook_client().validate_url(data.endpoint_url)
        except WebhookUrlError as exc:
            raise ValidationError(str(exc)) from exc
        async with AsyncSessionLocal() as db:
            return await EventSubscriptionService.create(db, principal, data)

    @staticmethod
    async def update(
        db: AsyncSession,
        principal: EffectivePrincipal,
        public_id: UUID,
        data: EventSubscriptionUpdate,
    ) -> EventSubscription:
        item = await EventSubscriptionService.get_scoped(db, principal, public_id)
        changes = data.model_dump(exclude_unset=True)
        if not changes:
            return item
        changes["updated_by_employee_id"] = principal.user_id
        safe_metadata = {"changed_fields": sorted(changes.keys() - {"updated_by_employee_id"})}
        endpoint_url = changes.get("endpoint_url")
        if endpoint_url:
            safe_metadata.update(EventSubscriptionService._safe_endpoint_metadata(endpoint_url))
        return await EventSubscriptionRepository.update_with_audit(
            db,
            item=item,
            data=changes,
            audit_data=EventSubscriptionService._audit_data(principal, "update", safe_metadata),
        )

    @staticmethod
    async def update_managed(
        principal: EffectivePrincipal,
        public_id: UUID,
        data: EventSubscriptionUpdate,
    ) -> EventSubscription:
        """Validate a changed endpoint before opening the persistence session."""
        EventSubscriptionService.ensure_super_admin(principal)
        if data.endpoint_url is not None:
            try:
                await create_webhook_client().validate_url(data.endpoint_url)
            except WebhookUrlError as exc:
                raise ValidationError(str(exc)) from exc
        async with AsyncSessionLocal() as db:
            return await EventSubscriptionService.update(db, principal, public_id, data)

    @staticmethod
    async def set_active(
        db: AsyncSession,
        principal: EffectivePrincipal,
        public_id: UUID,
        *,
        is_active: bool,
    ) -> EventSubscription:
        item = await EventSubscriptionService.get_scoped(db, principal, public_id)
        if item.is_active == is_active:
            return item
        now = datetime.now(timezone.utc)
        return await EventSubscriptionRepository.update_with_audit(
            db,
            item=item,
            data={
                "is_active": is_active,
                "disabled_at": None if is_active else now,
                "updated_by_employee_id": principal.user_id,
            },
            audit_data=EventSubscriptionService._audit_data(
                principal, "enable" if is_active else "disable"
            ),
        )

    @staticmethod
    async def rotate_secret(
        db: AsyncSession,
        principal: EffectivePrincipal,
        public_id: UUID,
    ) -> dict:
        item = await EventSubscriptionService.get_scoped(db, principal, public_id)
        secret = EventSubscriptionService.generate_secret()
        record = await EventSubscriptionRepository.update_with_audit(
            db,
            item=item,
            data={
                "previous_secret_ciphertext": item.secret_ciphertext,
                "previous_secret_expires_at": datetime.now(timezone.utc)
                + timedelta(hours=SECRET_TRANSITION_HOURS),
                "secret_ciphertext": encrypt_secret(secret),
                "secret_last_four": secret[-4:],
                "secret_version": item.secret_version + 1,
                "updated_by_employee_id": principal.user_id,
            },
            audit_data=EventSubscriptionService._audit_data(
                principal,
                "rotate",
                {"secret_version": item.secret_version + 1},
            ),
        )
        return {"record": record, "secret": secret}

    @staticmethod
    async def delete(
        db: AsyncSession,
        principal: EffectivePrincipal,
        public_id: UUID,
    ) -> None:
        item = await EventSubscriptionService.get_scoped(db, principal, public_id)
        if item.is_active:
            raise ValidationError("Disable the event subscription before deleting it")
        from app.repositories.auto_outbound_event_repository import AutoOutboundEventRepository
        from app.repositories.call_event_subscription_repository import (
            CallEventSubscriptionRepository,
        )

        task_count = await AutoOutboundEventRepository.count_bindings_for_subscription(
            db,
            tenant_id=principal.tenant_id,
            subscription_public_id=public_id,
        )
        rule_count = await CallEventSubscriptionRepository.count_for_subscription(
            db,
            tenant_id=principal.tenant_id,
            subscription_id=item.id,
        )
        if task_count or rule_count:
            parts = []
            if task_count:
                parts.append(f"{task_count} auto outbound tasks")
            if rule_count:
                parts.append(f"{rule_count} call event subscription rules")
            raise ValidationError(
                f"This subscription is used by {' and '.join(parts)}. Remove the bindings first",
                details={
                    "code": "subscription_in_use",
                    "auto_outbound_task_count": task_count,
                    "call_event_rule_count": rule_count,
                },
            )
        await EventSubscriptionRepository.delete_with_audit(
            db,
            item=item,
            audit_data=EventSubscriptionService._audit_data(
                principal,
                "delete",
                {
                    "name": item.name,
                    **EventSubscriptionService._safe_endpoint_metadata(item.endpoint_url),
                },
            ),
        )
