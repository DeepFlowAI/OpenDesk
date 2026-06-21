"""
Unit tests for API Key service.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ForbiddenError, ValidationError
from app.core.security import decode_context_token
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.channel_repository import ChannelRepository
from app.schemas.api_key import ApiKeyCreate, ContextTokenRequest
from app.schemas.open_api import OpenApiContext
from app.schemas.permission import EffectivePrincipal
from app.services.api_key_service import ApiKeyService


def _principal(super_admin: bool = True) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=10,
        tenant_id=7,
        is_super_admin=super_admin,
        permissions=["admin.access"],
    )


def test_hash_api_key_is_stable_and_not_plaintext():
    api_key = "sk-odk-test-example"

    first = ApiKeyService.hash_api_key(api_key)
    second = ApiKeyService.hash_api_key(api_key)

    assert first == second
    assert first != api_key
    assert len(first) == 64


def test_mask_api_key_keeps_only_safe_prefix():
    masked = ApiKeyService.mask_api_key("sk-odk-test-abcdefghijklmnopqrstuvwxyz")

    assert masked == "sk-odk-test-abcd********"


def test_non_super_admin_is_rejected():
    with pytest.raises(ForbiddenError):
        ApiKeyService.ensure_super_admin(_principal(super_admin=False))


@pytest.mark.asyncio
async def test_create_returns_secret_once(monkeypatch):
    created_payload: dict = {}

    async def fake_generate_unique_key(_db):
        return "sk-odk-test-secret", "hash", "sk-odk-test-sec********"

    async def fake_create(_db, data):
        created_payload.update(data)
        return SimpleNamespace(id=1, **data)

    monkeypatch.setattr(ApiKeyService, "generate_unique_key", fake_generate_unique_key)
    monkeypatch.setattr(ApiKeyRepository, "create", fake_create)

    response = await ApiKeyService.create(object(), _principal(), ApiKeyCreate(name=" Main Key "))

    assert response["api_key"] == "sk-odk-test-secret"
    assert response["record"].name == "Main Key"
    assert created_payload["key_hash"] == "hash"
    assert created_payload["tenant_id"] == 7
    assert created_payload["created_by_employee_id"] == 10


@pytest.mark.asyncio
async def test_delete_active_key_requires_disable(monkeypatch):
    item = SimpleNamespace(id=1, tenant_id=7, is_active=True)
    monkeypatch.setattr(ApiKeyRepository, "get_by_id", AsyncMock(return_value=item))

    with pytest.raises(ValidationError):
        await ApiKeyService.delete(object(), _principal(), 1)


@pytest.mark.asyncio
async def test_authenticate_open_api_context_updates_last_used(monkeypatch):
    api_key = SimpleNamespace(id=5, tenant_id=7, key_version=2, is_active=True, name="Context")

    monkeypatch.setattr(ApiKeyService, "authenticate", AsyncMock(return_value=api_key))
    monkeypatch.setattr(ApiKeyRepository, "update_last_used", AsyncMock(return_value=api_key))

    context = await ApiKeyService.authenticate_open_api_context(object(), "sk-odk-test-secret")

    assert context.tenant_id == 7
    assert context.api_key_id == 5
    assert context.api_key_name == "Context"
    assert context.api_key_version == 2
    assert context.is_active is True
    ApiKeyRepository.update_last_used.assert_awaited_once()


@pytest.mark.asyncio
async def test_issue_context_token_binds_key_channel_and_payload(monkeypatch):
    context = OpenApiContext(
        tenant_id=7,
        api_key_id=5,
        api_key_name="Context",
        api_key_version=2,
        is_active=True,
    )
    channel = SimpleNamespace(
        id=9,
        tenant_id=7,
        channel_key="ch_test_channel",
        public_access_enabled=True,
    )

    monkeypatch.setattr(ChannelRepository, "get_by_key", AsyncMock(return_value=channel))

    response = await ApiKeyService.issue_context_token(
        object(),
        context,
        ContextTokenRequest(
            channelKey=channel.channel_key,
            customer={"nickname": "Ada"},
            sessionSummary={"fields": {"customer_intent": "consult"}},
            businessRecords=[{"title": "Order 1"}],
            expiresSeconds=300,
        ),
    )

    payload = decode_context_token(response.context_token)
    assert response.expires_in == 300
    assert payload["typ"] == "context_token"
    assert payload["tenant_id"] == 7
    assert payload["channel_key"] == channel.channel_key
    assert payload["api_key_id"] == 5
    assert payload["api_key_version"] == 2
    assert payload["customer"] == {"nickname": "Ada"}
    assert payload["session_summary"] == {"fields": {"customer_intent": "consult"}}
    assert "business_records" not in payload
