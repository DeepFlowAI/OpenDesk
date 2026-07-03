from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.knowledge_input_suggestion_setting import KnowledgeInputSuggestionSettingPayload
from app.services.knowledge_input_suggestion_setting_service import (
    KnowledgeInputSuggestionSettingService,
)


def test_payload_validation_rejects_trigger_length_out_of_range():
    with pytest.raises(ValidationError):
        KnowledgeInputSuggestionSettingPayload(enabled=True, trigger_length=0)

    with pytest.raises(ValidationError):
        KnowledgeInputSuggestionSettingPayload(enabled=True, trigger_length=11)


@pytest.mark.asyncio
async def test_get_current_returns_default_when_unconfigured(monkeypatch):
    async def get_by_tenant(_db, _tenant_id):
        return None

    monkeypatch.setattr(
        "app.services.knowledge_input_suggestion_setting_service.KnowledgeInputSuggestionSettingRepository.get_by_tenant",
        get_by_tenant,
    )

    result = await KnowledgeInputSuggestionSettingService.get_current(SimpleNamespace(), 12)

    assert result.configured is False
    assert result.tenant_id == 12
    assert result.enabled is False
    assert result.trigger_length == 2
    assert result.id is None


@pytest.mark.asyncio
async def test_save_persists_payload_and_actor(monkeypatch):
    captured: dict = {}
    updated_at = datetime.now(timezone.utc)

    async def save(_db, tenant_id, data):
        captured["tenant_id"] = tenant_id
        captured["data"] = data
        return SimpleNamespace(
            id=5,
            tenant_id=tenant_id,
            enabled=data["enabled"],
            trigger_length=data["trigger_length"],
            updated_by_id=data["updated_by_id"],
            updated_by_name=data["updated_by_name"],
            updated_at=updated_at,
        )

    monkeypatch.setattr(
        "app.services.knowledge_input_suggestion_setting_service.KnowledgeInputSuggestionSettingRepository.save",
        save,
    )

    payload = KnowledgeInputSuggestionSettingPayload(enabled=True, trigger_length=3)
    result = await KnowledgeInputSuggestionSettingService.save(
        SimpleNamespace(),
        12,
        {"user_id": 7, "display_name": "Agent Admin"},
        payload,
    )

    assert captured["tenant_id"] == 12
    assert captured["data"]["enabled"] is True
    assert captured["data"]["trigger_length"] == 3
    assert captured["data"]["updated_by_id"] == 7
    assert captured["data"]["updated_by_name"] == "Agent Admin"
    assert result.configured is True
    assert result.id == 5
    assert result.updated_at == updated_at
