"""
Unit tests for OpenAgent settings service.
"""
from dataclasses import dataclass
from datetime import datetime

import pytest

from app.core.exceptions import ValidationError
from app.core.secret_store import decrypt_secret, encrypt_secret
from app.libs.open_agent.base import (
    OpenAgentAgentDetail,
    OpenAgentAgentListResult,
    OpenAgentAgentSummary,
    OpenAgentConnectionResult,
)
from app.repositories.open_agent_settings_repository import OpenAgentSettingsRepository
from app.schemas.open_agent_settings import OpenAgentConnectionTestRequest, OpenAgentSettingsUpdate
from app.services.open_agent_settings_service import OpenAgentSettingsService


@dataclass
class FakeOpenAgentSettings:
    tenant_id: int
    base_url: str
    api_key_ciphertext: str
    updated_at: datetime | None = None


class FakeOpenAgentClient:
    def __init__(self, ok: bool = True):
        self.ok = ok
        self.calls: list[tuple[str, str]] = []
        self.agent_calls: list[tuple[str, str, str, int, int]] = []
        self.agent_detail_calls: list[tuple[str, str, int]] = []

    async def test_connection(self, base_url: str, api_key: str) -> OpenAgentConnectionResult:
        self.calls.append((base_url, api_key))
        return OpenAgentConnectionResult(self.ok, "Connection successful" if self.ok else "Denied")

    async def list_agents(
        self,
        base_url: str,
        api_key: str,
        status_filter: str = "active",
        page: int = 1,
        per_page: int = 100,
    ) -> OpenAgentAgentListResult:
        self.agent_calls.append((base_url, api_key, status_filter, page, per_page))
        return OpenAgentAgentListResult(
            items=[
                OpenAgentAgentSummary(id=1, name="Support Agent", description=None, status="active"),
                OpenAgentAgentSummary(id=2, name="Inactive Agent", description=None, status="inactive"),
            ],
            total=2,
            page=page,
            per_page=per_page,
            pages=1,
        )

    async def get_agent(
        self,
        base_url: str,
        api_key: str,
        agent_id: int,
    ) -> OpenAgentAgentDetail:
        self.agent_detail_calls.append((base_url, api_key, agent_id))
        return OpenAgentAgentDetail(
            id=agent_id,
            name="Support Agent",
            description=None,
            status="active",
            welcome_message={
                "enabled": True,
                "blocks": [
                    {"type": "markdown", "content": "Hi **there**"},
                    {"type": "embed", "embed_code": "<div>Card</div>", "height": 240},
                ],
            },
            faq={
                "enabled": True,
                "title": "常见问题",
                "categories": [
                    {
                        "name": "账户",
                        "questions": [{"text": "怎么重置密码？"}],
                    }
                ],
            },
        )


@pytest.mark.asyncio
async def test_update_settings_requires_api_key_on_first_binding(monkeypatch):
    async def fake_get(_db, _tenant_id):
        return None

    monkeypatch.setattr(OpenAgentSettingsRepository, "get_by_tenant_id", fake_get)

    with pytest.raises(ValidationError):
        await OpenAgentSettingsService.update_settings(
            object(),
            1,
            OpenAgentSettingsUpdate(base_url="https://newagent.example.com"),
        )


@pytest.mark.asyncio
async def test_update_settings_creates_encrypted_secret(monkeypatch):
    created: dict = {}

    async def fake_get(_db, _tenant_id):
        return None

    async def fake_create(_db, data):
        created.update(data)
        return FakeOpenAgentSettings(
            tenant_id=data["tenant_id"],
            base_url=data["base_url"],
            api_key_ciphertext=data["api_key_ciphertext"],
        )

    monkeypatch.setattr(OpenAgentSettingsRepository, "get_by_tenant_id", fake_get)
    monkeypatch.setattr(OpenAgentSettingsRepository, "create", fake_create)

    response = await OpenAgentSettingsService.update_settings(
        object(),
        1,
        OpenAgentSettingsUpdate(
            base_url=" https://newagent.example.com/ ",
            api_key=" sk-test ",
        ),
    )

    assert response.base_url == "https://newagent.example.com"
    assert response.has_api_key is True
    assert created["api_key_ciphertext"] != "sk-test"
    assert decrypt_secret(created["api_key_ciphertext"]) == "sk-test"


@pytest.mark.asyncio
async def test_update_settings_keeps_existing_secret_when_blank(monkeypatch):
    existing = FakeOpenAgentSettings(
        tenant_id=1,
        base_url="https://old.example.com",
        api_key_ciphertext=encrypt_secret("sk-existing"),
    )
    updates: dict = {}

    async def fake_get(_db, _tenant_id):
        return existing

    async def fake_update(_db, item, data):
        updates.update(data)
        item.base_url = data["base_url"]
        if "api_key_ciphertext" in data:
            item.api_key_ciphertext = data["api_key_ciphertext"]
        return item

    monkeypatch.setattr(OpenAgentSettingsRepository, "get_by_tenant_id", fake_get)
    monkeypatch.setattr(OpenAgentSettingsRepository, "update", fake_update)

    response = await OpenAgentSettingsService.update_settings(
        object(),
        1,
        OpenAgentSettingsUpdate(base_url="https://new.example.com", api_key=""),
    )

    assert response.base_url == "https://new.example.com"
    assert "api_key_ciphertext" not in updates
    assert decrypt_secret(existing.api_key_ciphertext) == "sk-existing"


@pytest.mark.asyncio
async def test_connection_uses_saved_secret_when_api_key_blank(monkeypatch):
    existing = FakeOpenAgentSettings(
        tenant_id=1,
        base_url="https://new.example.com",
        api_key_ciphertext=encrypt_secret("sk-saved"),
    )
    client = FakeOpenAgentClient()

    async def fake_get(_db, _tenant_id):
        return existing

    monkeypatch.setattr(OpenAgentSettingsRepository, "get_by_tenant_id", fake_get)

    response = await OpenAgentSettingsService.test_connection(
        object(),
        1,
        OpenAgentConnectionTestRequest(base_url="https://new.example.com", api_key=None),
        open_agent_client=client,
    )

    assert response.ok is True
    assert client.calls == [("https://new.example.com", "sk-saved")]


@pytest.mark.asyncio
async def test_connection_uses_request_secret_before_saved_secret(monkeypatch):
    client = FakeOpenAgentClient()

    async def fake_get(_db, _tenant_id):
        raise AssertionError("saved secret should not be loaded")

    monkeypatch.setattr(OpenAgentSettingsRepository, "get_by_tenant_id", fake_get)

    await OpenAgentSettingsService.test_connection(
        object(),
        1,
        OpenAgentConnectionTestRequest(base_url="https://new.example.com", api_key="sk-new"),
        open_agent_client=client,
    )

    assert client.calls == [("https://new.example.com", "sk-new")]


@pytest.mark.asyncio
async def test_list_active_agents_uses_saved_credentials(monkeypatch):
    existing = FakeOpenAgentSettings(
        tenant_id=1,
        base_url="https://new.example.com",
        api_key_ciphertext=encrypt_secret("sk-saved"),
    )
    client = FakeOpenAgentClient()

    async def fake_get(_db, _tenant_id):
        return existing

    monkeypatch.setattr(OpenAgentSettingsRepository, "get_by_tenant_id", fake_get)

    response = await OpenAgentSettingsService.list_active_agents(
        object(),
        1,
        open_agent_client=client,
    )

    assert [item.name for item in response.items] == ["Support Agent"]
    assert client.agent_calls == [("https://new.example.com", "sk-saved", "active", 1, 100)]


@pytest.mark.asyncio
async def test_list_active_agents_requires_saved_credentials(monkeypatch):
    async def fake_get(_db, _tenant_id):
        return None

    monkeypatch.setattr(OpenAgentSettingsRepository, "get_by_tenant_id", fake_get)

    with pytest.raises(ValidationError):
        await OpenAgentSettingsService.list_active_agents(object(), 1)


@pytest.mark.asyncio
async def test_get_agent_welcome_message_uses_agent_detail(monkeypatch):
    existing = FakeOpenAgentSettings(
        tenant_id=1,
        base_url="https://new.example.com/api/v1",
        api_key_ciphertext=encrypt_secret("sk-saved"),
    )
    client = FakeOpenAgentClient()

    async def fake_get(_db, _tenant_id):
        return existing

    monkeypatch.setattr(OpenAgentSettingsRepository, "get_by_tenant_id", fake_get)

    response = await OpenAgentSettingsService.get_agent_welcome_message(
        object(),
        1,
        10,
        open_agent_client=client,
    )

    assert response is not None
    assert response.enabled is True
    assert response.blocks[0].type == "markdown"
    assert response.blocks[0].content == "Hi **there**"
    assert response.blocks[1].type == "embed"
    assert response.blocks[1].height == 240
    assert response.faq is not None
    assert response.faq.title == "常见问题"
    assert response.faq.categories[0].questions[0].text == "怎么重置密码？"
    assert client.agent_detail_calls == [("https://new.example.com/api/v1", "sk-saved", 10)]
