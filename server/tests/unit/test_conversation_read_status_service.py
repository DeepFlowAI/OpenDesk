"""
Unit tests for conversation read-status settings.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.conversation_read_status import ConversationReadStatusPayload
from app.services.conversation_read_status_service import ConversationReadStatusService


@pytest.mark.asyncio
async def test_get_current_returns_default_when_not_configured(monkeypatch):
    monkeypatch.setattr(
        "app.services.conversation_read_status_service.ConversationReadStatusRepository.get_by_tenant",
        AsyncMock(return_value=None),
    )

    result = await ConversationReadStatusService.get_current(AsyncMock(), tenant_id=1)

    assert result.configured is False
    assert result.agent_workspace_enabled is True
    assert result.web_sdk_enabled is True
    assert result.updated_at is None


@pytest.mark.asyncio
async def test_save_persists_payload_and_actor_snapshot(monkeypatch):
    captured: dict = {}
    updated_at = datetime.now(timezone.utc)

    async def save(_db, tenant_id: int, data: dict):
        captured["tenant_id"] = tenant_id
        captured["data"] = data
        return SimpleNamespace(id=3, tenant_id=tenant_id, updated_at=updated_at, **data)

    monkeypatch.setattr(
        "app.services.conversation_read_status_service.ConversationReadStatusRepository.save",
        save,
    )

    payload = ConversationReadStatusPayload(
        agent_workspace_enabled=False,
        web_sdk_enabled=True,
    )
    result = await ConversationReadStatusService.save(
        AsyncMock(),
        tenant_id=1,
        current_user={"user_id": 10, "display_name": "Agent One"},
        payload=payload,
    )

    assert captured["tenant_id"] == 1
    assert captured["data"]["agent_workspace_enabled"] is False
    assert captured["data"]["web_sdk_enabled"] is True
    assert captured["data"]["updated_by_id"] == 10
    assert captured["data"]["updated_by_name"] == "Agent One"
    assert result.agent_workspace_enabled is False
    assert result.web_sdk_enabled is True
    assert result.updated_at == updated_at


@pytest.mark.asyncio
async def test_get_public_config_uses_web_sdk_flag(monkeypatch):
    row = SimpleNamespace(
        id=1,
        tenant_id=1,
        agent_workspace_enabled=True,
        web_sdk_enabled=False,
        updated_by_id=None,
        updated_by_name=None,
        updated_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        "app.services.conversation_read_status_service.ConversationReadStatusRepository.get_by_tenant",
        AsyncMock(return_value=row),
    )

    result = await ConversationReadStatusService.get_public_config(AsyncMock(), tenant_id=1)

    assert result.web_sdk_enabled is False
