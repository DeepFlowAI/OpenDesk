"""
Unit tests for Web SDK context synchronization.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.security import create_context_token
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.fd_field_definition_repository import FdFieldDefinitionRepository
from app.repositories.user_repository import UserRepository
from app.services.cs_summary_usage_service import CsSummaryUsageService
from app.services.web_sdk_context_service import WebSdkContextService


def _context_token(payload: dict) -> str:
    return create_context_token(
        {
            "tenant_id": 7,
            "channel_key": "ch_test_channel",
            "api_key_id": 5,
            "api_key_version": 2,
            "nonce": "nonce",
            **payload,
        },
        expires_seconds=300,
    )


@pytest.mark.asyncio
async def test_resolve_visitor_identity_uses_strong_external_id(monkeypatch):
    api_key = SimpleNamespace(id=5, tenant_id=7, is_active=True, key_version=2)
    user = SimpleNamespace(id=11, tenant_id=7, external_id="mall_user_1", name="Old Name")

    monkeypatch.setattr(ApiKeyRepository, "get_by_id", AsyncMock(return_value=api_key))
    monkeypatch.setattr(UserRepository, "get_by_public_id", AsyncMock(return_value=None))
    monkeypatch.setattr(UserRepository, "get_by_external_id", AsyncMock(return_value=user))

    identity = await WebSdkContextService.resolve_visitor_identity(
        object(),
        tenant_id=7,
        channel_key="ch_test_channel",
        context_token=_context_token({"customer": {"externalUserId": "mall_user_1", "nickname": "Ada"}}),
    )

    assert identity.visitor_external_id == "mall_user_1"
    assert identity.visitor_name == "Ada"
    assert identity.warnings == []


@pytest.mark.asyncio
async def test_sync_for_conversation_updates_customer_and_summary(monkeypatch):
    visitor = SimpleNamespace(
        id=11,
        tenant_id=7,
        external_id="mall_user_1",
        name="Old Name",
        phone=None,
        email=None,
    )
    conversation = SimpleNamespace(
        id=33,
        public_id="conv_public",
        tenant_id=7,
        channel_id=9,
        visitor=visitor,
    )
    custom_field = SimpleNamespace(
        field_key="vip_level",
        status="active",
        slot_column="str_1",
    )

    update = AsyncMock(return_value=visitor)
    update_summary = AsyncMock(return_value={"updated": 1, "warnings": []})
    monkeypatch.setattr(ConversationRepository, "get_by_public_id", AsyncMock(return_value=conversation))
    monkeypatch.setattr(FdFieldDefinitionRepository, "list_custom_for_unified_domain", AsyncMock(return_value=[custom_field]))
    monkeypatch.setattr(UserRepository, "update", update)
    monkeypatch.setattr(CsSummaryUsageService, "update_fields_by_keys", update_summary)

    result = await WebSdkContextService.sync_for_conversation(
        object(),
        context_token=_context_token({
            "customer": {
                "nickname": "Ada",
                "email": " ADA@EXAMPLE.COM ",
                "fields": {"vip_level": "gold"},
            },
            "session_summary": {"fields": {"customer_intent": "咨询物流"}},
        }),
        visitor_context={
            "tenant_id": 7,
            "channel_id": 9,
            "channel_key": "ch_test_channel",
            "visitor_external_id": "mall_user_1",
        },
        conversation_public_id="conv_public",
        require_active_api_key=False,
    )

    assert result.customer_synced is True
    assert result.session_summary_synced is True
    update.assert_awaited_once()
    updated_data = update.await_args.args[2]
    assert updated_data["name"] == "Ada"
    assert updated_data["email"] == "ada@example.com"
    assert updated_data["str_1"] == "gold"
    update_summary.assert_awaited_once()
