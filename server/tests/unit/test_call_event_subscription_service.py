"""Unit tests for call event subscription rule configuration."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.auto_outbound_event_repository import AutoOutboundEventRepository
from app.repositories.call_event_subscription_repository import CallEventSubscriptionRepository
from app.repositories.event_subscription_repository import EventSubscriptionRepository
from app.schemas.call_event_subscription import CALL_SOURCES, CallEventRuleSave
from app.schemas.permission import EffectivePrincipal
from app.services.call_event_rule_cache import CallEventRuleCache
from app.services.call_event_subscription_service import CallEventSubscriptionService


def _principal(*, super_admin: bool = False) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=10,
        tenant_id=7,
        is_super_admin=super_admin,
        permissions=["admin.access", "call.admin.event_subscription.manage"],
    )


def _subscription(**overrides):
    values = {
        "id": 1,
        "public_id": uuid4(),
        "tenant_id": 7,
        "name": "CRM Webhook",
        "is_active": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _rule(**overrides):
    now = datetime.now(timezone.utc)
    values = {
        "id": 5,
        "public_id": uuid4(),
        "tenant_id": 7,
        "name": "CRM sync",
        "subscription_id": 1,
        "event_types": ["call.ended"],
        "directions": ["inbound", "outbound"],
        "call_sources": list(CALL_SOURCES),
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _save(subscription_public_id, **overrides) -> CallEventRuleSave:
    values = {
        "name": "  CRM sync  ",
        "subscription_public_id": subscription_public_id,
        "event_types": ["call.ended"],
        "directions": ["outbound", "inbound"],
        "call_sources": list(CALL_SOURCES),
    }
    values.update(overrides)
    return CallEventRuleSave(**values)


def _db() -> SimpleNamespace:
    return SimpleNamespace(commit=AsyncMock(), flush=AsyncMock(), rollback=AsyncMock())


@pytest.fixture(autouse=True)
def _no_cache_io(monkeypatch):
    monkeypatch.setattr(CallEventRuleCache, "invalidate", AsyncMock())


def test_save_schema_normalizes_explicit_lists() -> None:
    data = _save(uuid4(), event_types=["call.ended", "call.created", "call.ended"])

    assert data.name == "CRM sync"
    assert data.event_types == ["call.created", "call.ended"]
    assert data.directions == ["inbound", "outbound"]
    assert data.call_sources == list(CALL_SOURCES)
    assert "embedded_call" in data.call_sources
    assert "personal_auto_outbound" in data.call_sources


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": " a "},
        {"name": "x" * 51},
        {"event_types": []},
        {"event_types": ["call.dtmf"]},
        {"directions": []},
        {"directions": ["internal"]},
        {"call_sources": []},
        {"call_sources": ["ivr"]},
    ],
)
def test_save_schema_rejects_invalid_input(overrides) -> None:
    with pytest.raises(PydanticValidationError):
        _save(uuid4(), **overrides)


@pytest.mark.asyncio
async def test_create_rejects_eleventh_rule(monkeypatch) -> None:
    monkeypatch.setattr(
        CallEventSubscriptionRepository, "lock_tenant_and_count", AsyncMock(return_value=10)
    )
    add = AsyncMock()
    monkeypatch.setattr(CallEventSubscriptionRepository, "add", add)

    with pytest.raises(ValidationError) as exc_info:
        await CallEventSubscriptionService.create_rule(_db(), _principal(), _save(uuid4()))

    assert exc_info.value.details == {"code": "rule_limit"}
    add.assert_not_awaited()


def _patch_create_lookups(monkeypatch, *, subscription, name_owner=None, subscription_owner=None):
    monkeypatch.setattr(
        CallEventSubscriptionRepository, "lock_tenant_and_count", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(
        CallEventSubscriptionRepository, "get_by_name", AsyncMock(return_value=name_owner)
    )
    monkeypatch.setattr(
        EventSubscriptionRepository, "get_for_tenant", AsyncMock(return_value=subscription)
    )
    monkeypatch.setattr(
        CallEventSubscriptionRepository,
        "get_by_subscription",
        AsyncMock(return_value=subscription_owner),
    )


@pytest.mark.asyncio
async def test_create_rejects_duplicate_name(monkeypatch) -> None:
    subscription = _subscription()
    _patch_create_lookups(monkeypatch, subscription=subscription, name_owner=_rule())

    with pytest.raises(ValidationError) as exc_info:
        await CallEventSubscriptionService.create_rule(
            _db(), _principal(), _save(subscription.public_id)
        )

    assert exc_info.value.details == {"code": "name_taken"}


@pytest.mark.asyncio
async def test_create_rejects_unavailable_subscription(monkeypatch) -> None:
    _patch_create_lookups(monkeypatch, subscription=None)

    with pytest.raises(ValidationError) as exc_info:
        await CallEventSubscriptionService.create_rule(_db(), _principal(), _save(uuid4()))

    assert exc_info.value.details == {"code": "subscription_unavailable"}


@pytest.mark.asyncio
async def test_create_rejects_disabled_subscription(monkeypatch) -> None:
    subscription = _subscription(is_active=False)
    _patch_create_lookups(monkeypatch, subscription=subscription)

    with pytest.raises(ValidationError) as exc_info:
        await CallEventSubscriptionService.create_rule(
            _db(), _principal(), _save(subscription.public_id)
        )

    assert exc_info.value.details == {"code": "subscription_disabled"}


@pytest.mark.asyncio
async def test_create_rejects_subscription_used_by_other_rule(monkeypatch) -> None:
    subscription = _subscription()
    _patch_create_lookups(
        monkeypatch,
        subscription=subscription,
        subscription_owner=_rule(id=99, name="Quality sync"),
    )

    with pytest.raises(ValidationError) as exc_info:
        await CallEventSubscriptionService.create_rule(
            _db(), _principal(), _save(subscription.public_id)
        )

    assert exc_info.value.details == {
        "code": "subscription_in_use",
        "rule_name": "Quality sync",
    }


@pytest.mark.asyncio
async def test_create_persists_rule_audits_and_invalidates_cache(monkeypatch) -> None:
    subscription = _subscription()
    _patch_create_lookups(monkeypatch, subscription=subscription)
    created = _rule()
    add = AsyncMock(return_value=created)
    add_audit = AsyncMock()
    monkeypatch.setattr(CallEventSubscriptionRepository, "add", add)
    monkeypatch.setattr(CallEventSubscriptionRepository, "add_audit", add_audit)
    monkeypatch.setattr(
        CallEventSubscriptionRepository,
        "get_with_subscription",
        AsyncMock(return_value=(created, subscription)),
    )
    db = _db()

    result = await CallEventSubscriptionService.create_rule(
        db, _principal(), _save(subscription.public_id)
    )

    data = add.await_args.args[1]
    assert data["tenant_id"] == 7
    assert data["name"] == "CRM sync"
    assert data["is_active"] is True
    assert data["subscription_id"] == subscription.id
    audit = add_audit.await_args.args[1]
    assert audit["action"] == "created"
    assert audit["subscription_public_id"] == subscription.public_id
    assert set(audit["metadata_json"]) == {
        "name", "event_types", "directions", "call_sources", "is_active",
    }
    db.commit.assert_awaited_once()
    CallEventRuleCache.invalidate.assert_awaited_once_with(7)
    assert result.subscription.name == "CRM Webhook"


@pytest.mark.asyncio
async def test_update_keeps_current_disabled_subscription(monkeypatch) -> None:
    subscription = _subscription(is_active=False)
    rule = _rule(subscription_id=subscription.id)
    monkeypatch.setattr(
        CallEventSubscriptionRepository, "lock_tenant_and_count", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(
        CallEventSubscriptionRepository,
        "get_with_subscription",
        AsyncMock(return_value=(rule, subscription)),
    )
    monkeypatch.setattr(
        CallEventSubscriptionRepository, "get_by_name", AsyncMock(return_value=rule)
    )
    monkeypatch.setattr(
        EventSubscriptionRepository, "get_for_tenant", AsyncMock(return_value=subscription)
    )
    monkeypatch.setattr(
        CallEventSubscriptionRepository, "get_by_subscription", AsyncMock(return_value=rule)
    )
    monkeypatch.setattr(CallEventSubscriptionRepository, "add_audit", AsyncMock())

    result = await CallEventSubscriptionService.update_rule(
        _db(),
        _principal(),
        rule.public_id,
        _save(subscription.public_id, event_types=["call.created", "call.ended"]),
    )

    assert rule.event_types == ["call.created", "call.ended"]
    assert result.subscription.is_active is False


@pytest.mark.asyncio
async def test_missing_rule_is_not_found(monkeypatch) -> None:
    monkeypatch.setattr(
        CallEventSubscriptionRepository, "get_with_subscription", AsyncMock(return_value=None)
    )

    with pytest.raises(NotFoundError):
        await CallEventSubscriptionService.get_rule(_db(), _principal(), uuid4())


@pytest.mark.asyncio
async def test_toggle_and_delete_write_audits(monkeypatch) -> None:
    subscription = _subscription()
    rule = _rule()
    monkeypatch.setattr(
        CallEventSubscriptionRepository,
        "get_with_subscription",
        AsyncMock(return_value=(rule, subscription)),
    )
    add_audit = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(CallEventSubscriptionRepository, "add_audit", add_audit)
    monkeypatch.setattr(CallEventSubscriptionRepository, "delete", delete)

    await CallEventSubscriptionService.set_active(_db(), _principal(), rule.public_id, False)
    await CallEventSubscriptionService.delete_rule(_db(), _principal(), rule.public_id)

    actions = [call.args[1]["action"] for call in add_audit.await_args_list]
    assert actions == ["disabled", "deleted"]
    assert rule.is_active is False
    delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_options_mark_subscriptions_used_by_other_rules(monkeypatch) -> None:
    current_sub = _subscription(id=1, name="CRM")
    used_sub = _subscription(id=2, name="Quality")
    free_sub = _subscription(id=3, name="WFM")
    current_rule = _rule(subscription_id=1)
    monkeypatch.setattr(
        CallEventSubscriptionRepository,
        "get_with_subscription",
        AsyncMock(return_value=(current_rule, current_sub)),
    )
    monkeypatch.setattr(
        AutoOutboundEventRepository,
        "list_options",
        AsyncMock(return_value=[current_sub, used_sub, free_sub]),
    )
    monkeypatch.setattr(
        CallEventSubscriptionRepository,
        "rule_names_by_subscription",
        AsyncMock(
            return_value={
                1: (current_rule.public_id, current_rule.name),
                2: (uuid4(), "Quality sync"),
            }
        ),
    )

    result = await CallEventSubscriptionService.list_options(
        _db(), _principal(super_admin=True), current_rule.public_id
    )

    assert [option.used_by_rule_name for option in result.options] == [
        None, "Quality sync", None,
    ]
    assert result.can_manage_global is True
    dumped = result.model_dump()
    assert "endpoint_url" not in str(dumped)
