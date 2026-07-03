from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.schemas.conversation_agent_display_setting import ConversationAgentDisplaySettingPayload
from app.services.conversation_agent_display_setting_service import ConversationAgentDisplaySettingService


def test_payload_validation_rejects_unknown_display_mode():
    with pytest.raises(ValidationError):
        ConversationAgentDisplaySettingPayload(display_mode="display_name")


@pytest.mark.asyncio
async def test_get_current_returns_default_when_unconfigured(monkeypatch):
    monkeypatch.setattr(
        "app.services.conversation_agent_display_setting_service.ConversationAgentDisplaySettingRepository.get_by_tenant",
        AsyncMock(return_value=None),
    )

    result = await ConversationAgentDisplaySettingService.get_current(AsyncMock(), tenant_id=12)

    assert result.configured is False
    assert result.tenant_id == 12
    assert result.display_mode == "name"
    assert result.id is None


@pytest.mark.asyncio
async def test_save_persists_display_mode_and_actor(monkeypatch):
    captured: dict = {}
    updated_at = datetime.now(timezone.utc)

    async def save(_db, tenant_id: int, data: dict):
        captured["tenant_id"] = tenant_id
        captured["data"] = data
        return SimpleNamespace(id=5, tenant_id=tenant_id, updated_at=updated_at, **data)

    monkeypatch.setattr(
        "app.services.conversation_agent_display_setting_service.ConversationAgentDisplaySettingRepository.save",
        save,
    )

    payload = ConversationAgentDisplaySettingPayload(display_mode="nickname")
    result = await ConversationAgentDisplaySettingService.save(
        AsyncMock(),
        tenant_id=12,
        current_user={"user_id": 7, "display_name": "Agent Admin"},
        payload=payload,
    )

    assert captured["tenant_id"] == 12
    assert captured["data"]["display_mode"] == "nickname"
    assert captured["data"]["updated_by_id"] == 7
    assert captured["data"]["updated_by_name"] == "Agent Admin"
    assert result.configured is True
    assert result.id == 5
    assert result.updated_at == updated_at


def test_resolve_agent_name_prefers_name_mode_display_name():
    agent = SimpleNamespace(display_name="Legal Name", name="Name", nickname="Nick", username="user")

    result = ConversationAgentDisplaySettingService.resolve_agent_name(agent, "name")

    assert result == "Legal Name"


def test_resolve_agent_name_prefers_nickname_mode_nickname():
    agent = SimpleNamespace(display_name="Legal Name", name="Name", nickname="Nick", username="user")

    result = ConversationAgentDisplaySettingService.resolve_agent_name(agent, "nickname")

    assert result == "Nick"


def test_resolve_agent_name_falls_back_when_nickname_missing():
    agent = SimpleNamespace(display_name="Legal Name", name="Name", nickname=None, username="user")

    result = ConversationAgentDisplaySettingService.resolve_agent_name(agent, "nickname")

    assert result == "Name"
