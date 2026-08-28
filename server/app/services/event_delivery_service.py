"""Durable, authenticated and retryable event webhook delivery."""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.secret_store import decrypt_secret
from app.db.session import AsyncSessionLocal
from app.libs.webhook import BaseWebhookClient, WebhookSendResult, create_webhook_client
from app.models.event_delivery import (
    EVENT_DELIVERY_FAILED,
    EVENT_DELIVERY_PENDING,
    EVENT_DELIVERY_PROCESSING,
    EVENT_DELIVERY_SUCCEEDED,
)
from app.models.event_subscription import EventSubscription
from app.repositories.event_delivery_repository import EventDeliveryRepository
from app.repositories.event_subscription_repository import EventSubscriptionRepository
from app.schemas.event_delivery import CloudEventEnvelope
from app.schemas.permission import EffectivePrincipal
from app.services.event_subscription_service import EventSubscriptionService

logger = logging.getLogger(__name__)

MAX_DELIVERY_ATTEMPTS = 8
MAX_DELIVERY_WINDOW = timedelta(hours=24)
MAX_PAYLOAD_BYTES = 256 * 1024
RETRY_DELAYS_SECONDS = (60, 300, 900, 3600, 10800, 21600, 43200)
TEST_EVENT_TYPE = "opendesk.webhook.test"


class EventDeliveryService:
    @staticmethod
    def build_body(
        *,
        delivery_id: UUID,
        event_id: str,
        source_module: str,
        event_type: str,
        occurred_at: datetime,
        payload: dict,
        is_test: bool,
        api_version: str | None = None,
        subject: str | None = None,
    ) -> bytes:
        resolved_version = api_version or "v1"
        envelope = CloudEventEnvelope(
            id=event_id,
            source=source_module,
            type=event_type,
            subject=subject,
            time=occurred_at.astimezone(timezone.utc),
            dataschema=f"opendesk://schemas/events/{event_type}/{resolved_version}",
            apiversion=resolved_version,
            deliveryid=delivery_id,
            test=is_test,
            data=payload,
        ).model_dump(mode="json", exclude_none=True)
        return json.dumps(
            envelope,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    @staticmethod
    def _validate_event_input(
        *,
        source_module: str,
        event_type: str,
        event_id: str,
        occurred_at: datetime,
        payload: dict,
    ) -> tuple[str, str, str]:
        normalized_source = source_module.strip()
        normalized_type = event_type.strip()
        normalized_id = event_id.strip()
        if not normalized_source or len(normalized_source) > 64:
            raise ValidationError("Source module must be 1 to 64 characters")
        if not normalized_type or len(normalized_type) > 128:
            raise ValidationError("Event type must be 1 to 128 characters")
        if not normalized_id or len(normalized_id) > 128:
            raise ValidationError("Event ID must be 1 to 128 characters")
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValidationError("Event occurred_at must be timezone-aware")
        try:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValidationError("Event payload must be JSON serializable") from exc
        if len(encoded) > MAX_PAYLOAD_BYTES:
            raise ValidationError("Event payload must be at most 256KB")
        return normalized_source, normalized_type, normalized_id

    @staticmethod
    async def enqueue(
        *,
        tenant_id: int,
        subscription_public_ids: list[UUID],
        source_module: str,
        event_type: str,
        event_id: str,
        occurred_at: datetime,
        payload: dict,
        api_version: str | None = None,
        subject: str | None = None,
    ) -> list[UUID]:
        """Persist one independent delivery for every explicitly selected subscription."""
        if not subscription_public_ids:
            return []
        unique_ids = list(dict.fromkeys(subscription_public_ids))
        normalized_source, normalized_type, normalized_event_id = (
            EventDeliveryService._validate_event_input(
                source_module=source_module,
                event_type=event_type,
                event_id=event_id,
                occurred_at=occurred_at,
                payload=payload,
            )
        )
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            public_ids = await EventDeliveryService.enqueue_in_transaction(
                db,
                tenant_id=tenant_id,
                subscription_public_ids=unique_ids,
                source_module=normalized_source,
                event_type=normalized_type,
                event_id=normalized_event_id,
                occurred_at=occurred_at,
                payload=payload,
                api_version=api_version,
                subject=subject,
                now=now,
            )
            await db.commit()
            return public_ids

    @staticmethod
    async def enqueue_in_transaction(
        db: AsyncSession,
        *,
        tenant_id: int,
        subscription_public_ids: list[UUID],
        source_module: str,
        event_type: str,
        event_id: str,
        occurred_at: datetime,
        payload: dict,
        api_version: str | None = None,
        subject: str | None = None,
        now: datetime | None = None,
    ) -> list[UUID]:
        """Persist delivery rows without committing the caller's transaction."""
        if not subscription_public_ids:
            return []
        unique_ids = list(dict.fromkeys(subscription_public_ids))
        subscriptions = await EventSubscriptionRepository.list_selected_for_tenant(
            db,
            tenant_id=tenant_id,
            public_ids=unique_ids,
        )
        by_public_id = {item.public_id: item for item in subscriptions}
        if set(by_public_id) != set(unique_ids):
            raise NotFoundError("One or more event subscriptions were not found")
        if any(not item.is_active for item in subscriptions):
            raise ValidationError("Disabled event subscriptions cannot receive new deliveries")
        return await EventDeliveryService.enqueue_resolved_in_transaction(
            db,
            tenant_id=tenant_id,
            subscriptions=subscriptions,
            source_module=source_module,
            event_type=event_type,
            event_id=event_id,
            occurred_at=occurred_at,
            payload=payload,
            api_version=api_version,
            subject=subject,
            now=now,
        )

    @staticmethod
    async def enqueue_resolved_in_transaction(
        db: AsyncSession,
        *,
        tenant_id: int,
        subscriptions: list[EventSubscription],
        source_module: str,
        event_type: str,
        event_id: str,
        occurred_at: datetime,
        payload: dict,
        api_version: str | None = None,
        subject: str | None = None,
        now: datetime | None = None,
    ) -> list[UUID]:
        """Persist deliveries for already resolved tenant subscriptions."""
        if not subscriptions:
            return []
        normalized_source, normalized_type, normalized_event_id = (
            EventDeliveryService._validate_event_input(
                source_module=source_module,
                event_type=event_type,
                event_id=event_id,
                occurred_at=occurred_at,
                payload=payload,
            )
        )
        if any(
            item.tenant_id != tenant_id or not item.is_active
            for item in subscriptions
        ):
            raise ValidationError("Resolved event subscriptions are unavailable")
        queued_at = now or datetime.now(timezone.utc)
        rows = [
            {
                "public_id": uuid4(),
                "tenant_id": tenant_id,
                "subscription_id": item.id,
                "subscription_public_id": item.public_id,
                "endpoint_url_snapshot": item.endpoint_url,
                "secret_ciphertext_snapshot": item.secret_ciphertext,
                "source_module": normalized_source,
                "event_type": normalized_type,
                "event_id": normalized_event_id,
                "api_version": api_version,
                "subject": subject,
                "occurred_at": occurred_at.astimezone(timezone.utc),
                "payload": payload,
                "is_test": False,
                "status": EVENT_DELIVERY_PENDING,
                "next_attempt_at": queued_at,
            }
            for item in subscriptions
        ]
        return await EventDeliveryRepository.create_many_idempotent(db, rows)

    @staticmethod
    async def enqueue_safely(
        *,
        tenant_id: int,
        subscription_public_ids: list[UUID],
        source_module: str,
        event_type: str,
        event_id: str,
        occurred_at: datetime,
        payload: dict,
    ) -> list[UUID]:
        """Best-effort business entry point that never fails the caller's main flow."""
        try:
            return await EventDeliveryService.enqueue(
                tenant_id=tenant_id,
                subscription_public_ids=subscription_public_ids,
                source_module=source_module,
                event_type=event_type,
                event_id=event_id,
                occurred_at=occurred_at,
                payload=payload,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "event_delivery_enqueue_failed error_type=%s",
                type(exc).__name__,
            )
            return []

    @staticmethod
    def _snapshot(item: object) -> dict:
        return {
            "public_id": item.public_id,
            "endpoint_url": item.endpoint_url_snapshot,
            "secret_ciphertext": item.secret_ciphertext_snapshot,
            "source_module": item.source_module,
            "event_type": item.event_type,
            "event_id": item.event_id,
            "api_version": getattr(item, "api_version", None),
            "subject": getattr(item, "subject", None),
            "occurred_at": item.occurred_at,
            "payload": item.payload,
            "is_test": item.is_test,
            "attempt_count": item.attempt_count,
            "first_attempt_at": item.first_attempt_at,
            "created_at": item.created_at,
        }

    @staticmethod
    async def _close_client(client: BaseWebhookClient) -> None:
        close = getattr(client, "aclose", None)
        if close is not None:
            await close()

    @staticmethod
    async def _attempt(
        snapshot: dict,
        *,
        client: BaseWebhookClient | None = None,
    ) -> tuple[WebhookSendResult, dict]:
        attempted_at = datetime.now(timezone.utc)
        body = EventDeliveryService.build_body(
            delivery_id=snapshot["public_id"],
            event_id=snapshot["event_id"],
            source_module=snapshot["source_module"],
            event_type=snapshot["event_type"],
            occurred_at=snapshot["occurred_at"],
            payload=snapshot["payload"],
            is_test=snapshot["is_test"],
            api_version=snapshot.get("api_version"),
            subject=snapshot.get("subject"),
        )
        delivery_client = client or create_webhook_client()
        owns_client = client is None
        try:
            secret = decrypt_secret(snapshot["secret_ciphertext"])
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "OpenDesk-Webhook/1.0",
                "Authorization": f"Bearer {secret}",
                "X-OpenDesk-Delivery": str(snapshot["public_id"]),
            }
            result = await delivery_client.send(
                url=snapshot["endpoint_url"],
                body=body,
                headers=headers,
                timeout_seconds=settings.EVENT_DELIVERY_TIMEOUT_SECONDS,
            )
        except ValueError:
            result = WebhookSendResult(
                success=False,
                http_status=None,
                duration_ms=0,
                error_type="secret_invalid",
                error_message="Stored webhook secret cannot be decrypted",
            )
        finally:
            if owns_client:
                await EventDeliveryService._close_client(delivery_client)

        attempt_count = snapshot["attempt_count"] + 1
        first_attempt_at = snapshot["first_attempt_at"] or attempted_at
        persisted = {
            "attempt_count": attempt_count,
            "first_attempt_at": first_attempt_at,
            "last_attempt_at": attempted_at,
            "last_http_status": result.http_status,
            "last_duration_ms": result.duration_ms,
            "last_error_type": result.error_type,
            "last_error_message": result.error_message,
            "claimed_at": None,
        }
        if result.success:
            persisted.update(
                status=EVENT_DELIVERY_SUCCEEDED,
                next_attempt_at=None,
                completed_at=attempted_at,
            )
            return result, persisted

        cutoff = snapshot["created_at"] + MAX_DELIVERY_WINDOW
        terminal = snapshot["is_test"] or attempt_count >= MAX_DELIVERY_ATTEMPTS
        next_attempt_at = None
        if not terminal:
            next_attempt_at = attempted_at + timedelta(
                seconds=RETRY_DELAYS_SECONDS[attempt_count - 1]
            )
            terminal = next_attempt_at > cutoff
        persisted.update(
            status=EVENT_DELIVERY_FAILED if terminal else EVENT_DELIVERY_PENDING,
            next_attempt_at=None if terminal else next_attempt_at,
            completed_at=attempted_at if terminal else None,
        )
        return result, persisted

    @staticmethod
    async def run_tick() -> dict[str, int]:
        """Recover stale claims and deliver bounded slices without holding DB sessions."""
        now = datetime.now(timezone.utc)
        stale_seconds = max(
            settings.EVENT_DELIVERY_CLAIM_STALE_SECONDS,
            int(settings.EVENT_DELIVERY_TIMEOUT_SECONDS) + 30,
        )
        stale_before = now - timedelta(seconds=stale_seconds)
        async with AsyncSessionLocal() as db:
            swept = await EventDeliveryRepository.sweep_stale(
                db, stale_before=stale_before, now=now
            )
        claimed = 0
        succeeded = 0
        failed = 0
        remaining = settings.EVENT_DELIVERY_SCAN_BATCH_SIZE
        concurrency = min(settings.EVENT_DELIVERY_CONCURRENCY, remaining)
        client = create_webhook_client()
        try:
            while remaining > 0:
                slice_limit = min(concurrency, remaining)
                claimed_at = datetime.now(timezone.utc)
                async with AsyncSessionLocal() as db:
                    items = await EventDeliveryRepository.claim_due(
                        db,
                        now=claimed_at,
                        limit=slice_limit,
                    )
                    snapshots = [EventDeliveryService._snapshot(item) for item in items]
                if not snapshots:
                    break

                outcomes = await asyncio.gather(
                    *(
                        EventDeliveryService._attempt(snapshot, client=client)
                        for snapshot in snapshots
                    )
                )
                attempts = [
                    (snapshot["public_id"], persisted)
                    for snapshot, (_result, persisted) in zip(snapshots, outcomes)
                ]
                async with AsyncSessionLocal() as db:
                    await EventDeliveryRepository.persist_attempts(
                        db,
                        attempts=attempts,
                        claimed_at=claimed_at,
                    )
                claimed += len(snapshots)
                succeeded += sum(1 for result, _data in outcomes if result.success)
                failed += sum(1 for result, _data in outcomes if not result.success)
                remaining -= len(snapshots)
        finally:
            await EventDeliveryService._close_client(client)
        return {
            "claimed": claimed,
            "swept": swept,
            "succeeded": succeeded,
            "failed": failed,
        }

    @staticmethod
    async def cleanup_completed(*, now: datetime | None = None) -> int:
        """Delete one bounded batch of terminal snapshots past retention."""
        current = now or datetime.now(timezone.utc)
        cutoff = current - timedelta(days=settings.EVENT_DELIVERY_RETENTION_DAYS)
        async with AsyncSessionLocal() as db:
            return await EventDeliveryRepository.delete_completed_before(
                db,
                cutoff=cutoff,
                limit=settings.EVENT_DELIVERY_CLEANUP_BATCH_SIZE,
            )

    @staticmethod
    async def test_subscription_managed(
        principal: EffectivePrincipal,
        public_id: UUID,
    ) -> dict:
        """Send one fixed test request with no active DB session during HTTP I/O."""
        EventSubscriptionService.ensure_super_admin(principal)
        now = datetime.now(timezone.utc)
        delivery_id = uuid4()
        event_id = f"test-{delivery_id}"
        async with AsyncSessionLocal() as db:
            subscription = await EventSubscriptionRepository.get_for_tenant(
                db,
                tenant_id=principal.tenant_id,
                public_id=public_id,
            )
            if subscription is None:
                raise NotFoundError("Event subscription not found")
            item = await EventDeliveryRepository.create_test_with_audit(
                db,
                data={
                    "public_id": delivery_id,
                    "tenant_id": principal.tenant_id,
                    "subscription_id": subscription.id,
                    "subscription_public_id": subscription.public_id,
                    "endpoint_url_snapshot": subscription.endpoint_url,
                    "secret_ciphertext_snapshot": subscription.secret_ciphertext,
                    "source_module": "system",
                    "event_type": TEST_EVENT_TYPE,
                    "event_id": event_id,
                    "occurred_at": now,
                    "payload": {"message": "OpenDesk webhook endpoint verification"},
                    "is_test": True,
                    "status": EVENT_DELIVERY_PROCESSING,
                    "claimed_at": now,
                    "next_attempt_at": None,
                },
                audit_data={
                    "tenant_id": principal.tenant_id,
                    "subscription_public_id": subscription.public_id,
                    "action": "test",
                    "actor_employee_id": principal.user_id,
                    "metadata_json": {"delivery_id": str(delivery_id)},
                },
            )
            snapshot = EventDeliveryService._snapshot(item)

        result, persisted = await EventDeliveryService._attempt(snapshot)
        async with AsyncSessionLocal() as db:
            record = await EventDeliveryRepository.persist_attempt_with_audit(
                db,
                public_id=delivery_id,
                data=persisted,
                audit_data={
                    "tenant_id": principal.tenant_id,
                    "subscription_public_id": public_id,
                    "action": "test_result",
                    "actor_employee_id": principal.user_id,
                    "metadata_json": {
                        "delivery_id": str(delivery_id),
                        "success": result.success,
                        "http_status": result.http_status,
                        "duration_ms": result.duration_ms,
                        "error_type": result.error_type,
                    },
                },
            )
        if record is None:
            raise NotFoundError("Event delivery not found")
        return {
            "delivery_id": delivery_id,
            "status": EVENT_DELIVERY_SUCCEEDED if result.success else EVENT_DELIVERY_FAILED,
            "http_status": result.http_status,
            "duration_ms": result.duration_ms,
            "error_type": result.error_type,
        }
