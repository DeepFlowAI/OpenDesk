"""Unit tests for tenant event subscription configuration."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.repositories.event_subscription_repository import EventSubscriptionRepository
from app.schemas.event_subscription import EventSubscriptionCreate, EventSubscriptionUpdate
from app.schemas.permission import EffectivePrincipal
from app.services.event_subscription_service import EventSubscriptionService


def _principal(*, super_admin: bool = True, tenant_id: int = 7) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=10,
        tenant_id=tenant_id,
        is_super_admin=super_admin,
        permissions=["admin.access"],
    )


def _subscription(**overrides):
    values = {
        "id": 1,
        "public_id": uuid4(),
        "tenant_id": 7,
        "name": "CRM Webhook",
        "endpoint_url": "https://hooks.example.com/opendesk",
        "description": None,
        "secret_ciphertext": "encrypted-current",
        "secret_last_four": "1234",
        "secret_version": 1,
        "is_active": True,
        "disabled_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_non_super_admin_is_rejected() -> None:
    with pytest.raises(ForbiddenError):
        EventSubscriptionService.ensure_super_admin(_principal(super_admin=False))


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.example.com/path",
        "https://user:password@hooks.example.com/path",
        "https://hooks.example.com/path#fragment",
        "not-a-url",
    ],
)
def test_create_schema_rejects_invalid_https_endpoint(url: str) -> None:
    with pytest.raises(PydanticValidationError):
        EventSubscriptionCreate(name="Test Hook", endpoint_url=url)


@pytest.mark.asyncio
async def test_create_returns_secret_once_and_persists_ciphertext(monkeypatch) -> None:
    created = _subscription()
    create_with_audit = AsyncMock(return_value=created)
    monkeypatch.setattr(
        EventSubscriptionRepository,
        "lock_tenant_and_count",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(EventSubscriptionRepository, "create_with_audit", create_with_audit)
    monkeypatch.setattr(EventSubscriptionService, "generate_secret", lambda: "odwhsec_test_secret1234")
    monkeypatch.setattr(
        "app.services.event_subscription_service.encrypt_secret",
        lambda value: f"encrypted:{value}",
    )

    result = await EventSubscriptionService.create(
        object(),
        _principal(),
        EventSubscriptionCreate(
            name="  CRM Webhook  ",
            endpoint_url="https://hooks.example.com/opendesk",
        ),
    )

    assert result == {"record": created, "secret": "odwhsec_test_secret1234"}
    payload = create_with_audit.await_args.kwargs["data"]
    assert payload["tenant_id"] == 7
    assert payload["name"] == "CRM Webhook"
    assert payload["secret_ciphertext"] == "encrypted:odwhsec_test_secret1234"
    assert payload["secret_last_four"] == "1234"
    audit = create_with_audit.await_args.kwargs["audit_data"]
    assert audit["metadata_json"] == {"endpoint_host": "hooks.example.com"}


@pytest.mark.asyncio
async def test_create_at_tenant_limit_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        EventSubscriptionRepository,
        "lock_tenant_and_count",
        AsyncMock(return_value=20),
    )

    with pytest.raises(ValidationError):
        await EventSubscriptionService.create(
            object(),
            _principal(),
            EventSubscriptionCreate(
                name="Extra Hook",
                endpoint_url="https://hooks.example.com/opendesk",
            ),
        )


@pytest.mark.asyncio
async def test_get_scoped_hides_cross_tenant_subscription(monkeypatch) -> None:
    monkeypatch.setattr(
        EventSubscriptionRepository,
        "get_for_tenant",
        AsyncMock(return_value=None),
    )

    with pytest.raises(NotFoundError):
        await EventSubscriptionService.get_scoped(object(), _principal(), uuid4())


@pytest.mark.asyncio
async def test_update_audits_only_safe_changed_fields(monkeypatch) -> None:
    item = _subscription()
    update_with_audit = AsyncMock(return_value=item)
    monkeypatch.setattr(
        EventSubscriptionService,
        "get_scoped",
        AsyncMock(return_value=item),
    )
    monkeypatch.setattr(EventSubscriptionRepository, "update_with_audit", update_with_audit)

    await EventSubscriptionService.update(
        object(),
        _principal(),
        item.public_id,
        EventSubscriptionUpdate(endpoint_url="https://new.example.com/events"),
    )

    audit = update_with_audit.await_args.kwargs["audit_data"]
    assert audit["metadata_json"] == {
        "changed_fields": ["endpoint_url"],
        "endpoint_host": "new.example.com",
    }


@pytest.mark.asyncio
async def test_rotate_keeps_previous_secret_for_24_hours(monkeypatch) -> None:
    item = _subscription(secret_version=3)
    update_with_audit = AsyncMock(return_value=item)
    monkeypatch.setattr(
        EventSubscriptionService,
        "get_scoped",
        AsyncMock(return_value=item),
    )
    monkeypatch.setattr(EventSubscriptionRepository, "update_with_audit", update_with_audit)
    monkeypatch.setattr(EventSubscriptionService, "generate_secret", lambda: "odwhsec_test_next5678")
    monkeypatch.setattr(
        "app.services.event_subscription_service.encrypt_secret",
        lambda value: f"encrypted:{value}",
    )

    before = datetime.now(timezone.utc)
    result = await EventSubscriptionService.rotate_secret(
        object(), _principal(), item.public_id
    )

    assert result["secret"] == "odwhsec_test_next5678"
    data = update_with_audit.await_args.kwargs["data"]
    assert data["previous_secret_ciphertext"] == "encrypted-current"
    assert data["secret_ciphertext"] == "encrypted:odwhsec_test_next5678"
    assert data["secret_version"] == 4
    assert data["previous_secret_expires_at"] >= before
    assert (data["previous_secret_expires_at"] - before).total_seconds() <= 24 * 60 * 60 + 1


@pytest.mark.asyncio
async def test_delete_requires_disabled_subscription(monkeypatch) -> None:
    item = _subscription(is_active=True)
    monkeypatch.setattr(
        EventSubscriptionService,
        "get_scoped",
        AsyncMock(return_value=item),
    )

    with pytest.raises(ValidationError):
        await EventSubscriptionService.delete(object(), _principal(), item.public_id)


@pytest.mark.asyncio
async def test_delete_disabled_subscription_writes_safe_audit(monkeypatch) -> None:
    item = _subscription(is_active=False)
    delete_with_audit = AsyncMock()
    monkeypatch.setattr(
        EventSubscriptionService,
        "get_scoped",
        AsyncMock(return_value=item),
    )
    monkeypatch.setattr(EventSubscriptionRepository, "delete_with_audit", delete_with_audit)
    monkeypatch.setattr(
        "app.repositories.auto_outbound_event_repository.AutoOutboundEventRepository.count_bindings_for_subscription",
        AsyncMock(return_value=0),
    )

    await EventSubscriptionService.delete(object(), _principal(), item.public_id)

    audit = delete_with_audit.await_args.kwargs["audit_data"]
    assert audit["metadata_json"] == {
        "name": "CRM Webhook",
        "endpoint_host": "hooks.example.com",
    }
