"""
Integration tests for OpenAgent Settings API.
"""
import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.libs.open_agent.base import (
    OpenAgentAgentListResult,
    OpenAgentAgentSummary,
    OpenAgentConnectionResult,
)
from app.libs.voice_speed.base import VoiceSpeedConnectionResult


class FakeOpenAgentClient:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.agent_calls: list[tuple[str, str, str, int, int]] = []

    async def test_connection(self, base_url: str, api_key: str) -> OpenAgentConnectionResult:
        self.calls.append((base_url, api_key))
        return OpenAgentConnectionResult(True, "Connection successful")

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
            items=[OpenAgentAgentSummary(id=10, name="Support Agent", description="Help", status="active")],
            total=1,
            page=page,
            per_page=per_page,
            pages=1,
        )


class FakeVoiceSpeedClient:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def test_connection(self, base_url: str, api_key: str) -> VoiceSpeedConnectionResult:
        self.calls.append((base_url, api_key))
        return VoiceSpeedConnectionResult(True, "VoiceSpeed 连接成功")


async def _ensure_admin() -> tuple[int, int]:
    tenant_key = f"oa-{uuid.uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("""
                INSERT INTO tenants (tenant_id, name, is_active)
                VALUES (:tenant_id, :name, true)
            """),
            {"tenant_id": tenant_key, "name": tenant_key},
        )
        await db.commit()
        result = await db.execute(
            text("SELECT id FROM tenants WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_key},
        )
        tenant_id = int(result.scalar_one())
        username = f"admin-{uuid.uuid4().hex[:10]}"
        await db.execute(
            text("""
                INSERT INTO employees (
                    tenant_id, username, password_hash, display_name, name,
                    roles, is_active, is_super_admin
                )
                VALUES (
                    :tenant_id, :username, 'hash', 'Admin', 'Admin',
                    CAST(:roles AS JSON), true, true
                )
            """),
            {"tenant_id": tenant_id, "username": username, "roles": json.dumps(["admin"])},
        )
        await db.commit()
        result = await db.execute(
            text("SELECT id FROM employees WHERE tenant_id = :tenant_id AND username = :username"),
            {"tenant_id": tenant_id, "username": username},
        )
        return tenant_id, int(result.scalar_one())


def _auth_header(tenant_id: int, employee_id: int) -> dict:
    token = create_access_token({"sub": str(employee_id), "tenant_id": tenant_id, "roles": ["admin"]})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_settings_returns_empty_state_for_new_tenant(client: AsyncClient):
    tenant_id, employee_id = await _ensure_admin()

    resp = await client.get("/api/v1/open-agent-settings", headers=_auth_header(tenant_id, employee_id))

    assert resp.status_code == 200
    assert resp.json() == {"base_url": None, "has_api_key": False, "updated_at": None}


@pytest.mark.asyncio
async def test_update_settings_creates_config_without_returning_secret(client: AsyncClient):
    tenant_id, employee_id = await _ensure_admin()
    payload = {
        "base_url": " https://newagent.example.com/ ",
        "api_key": "sk-test",
    }

    resp = await client.put(
        "/api/v1/open-agent-settings",
        headers=_auth_header(tenant_id, employee_id),
        json=payload,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["base_url"] == "https://newagent.example.com"
    assert body["has_api_key"] is True
    assert "api_key" not in body


@pytest.mark.asyncio
async def test_first_update_requires_secret(client: AsyncClient):
    tenant_id, employee_id = await _ensure_admin()

    resp = await client.put(
        "/api/v1/open-agent-settings",
        headers=_auth_header(tenant_id, employee_id),
        json={"base_url": "https://newagent.example.com"},
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_connection_test_uses_saved_secret_when_secret_omitted(
    client: AsyncClient,
    monkeypatch,
):
    tenant_id, employee_id = await _ensure_admin()
    fake_client = FakeOpenAgentClient()

    from app.services import open_agent_settings_service as service_module

    monkeypatch.setattr(service_module, "create_open_agent_client", lambda: fake_client)

    await client.put(
        "/api/v1/open-agent-settings",
        headers=_auth_header(tenant_id, employee_id),
        json={"base_url": "https://newagent.example.com", "api_key": "sk-saved"},
    )
    resp = await client.post(
        "/api/v1/open-agent-settings/test",
        headers=_auth_header(tenant_id, employee_id),
        json={"base_url": "https://newagent.example.com"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "message": "Connection successful"}
    assert fake_client.calls == [("https://newagent.example.com", "sk-saved")]


@pytest.mark.asyncio
async def test_list_agents_uses_saved_secret(client: AsyncClient, monkeypatch):
    tenant_id, employee_id = await _ensure_admin()
    fake_client = FakeOpenAgentClient()

    from app.services import open_agent_settings_service as service_module

    monkeypatch.setattr(service_module, "create_open_agent_client", lambda: fake_client)

    await client.put(
        "/api/v1/open-agent-settings",
        headers=_auth_header(tenant_id, employee_id),
        json={"base_url": "https://newagent.example.com", "api_key": "sk-saved"},
    )
    resp = await client.get(
        "/api/v1/open-agent-settings/agents",
        headers=_auth_header(tenant_id, employee_id),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == [
        {"id": 10, "name": "Support Agent", "description": "Help", "status": "active"}
    ]
    assert fake_client.agent_calls == [
        ("https://newagent.example.com", "sk-saved", "active", 1, 100)
    ]


@pytest.mark.asyncio
async def test_missing_auth_returns_401(client: AsyncClient):
    resp = await client.get("/api/v1/open-agent-settings")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_voice_speed_settings_returns_empty_state_for_new_tenant(client: AsyncClient):
    tenant_id, employee_id = await _ensure_admin()

    resp = await client.get(
        "/api/v1/open-agent-settings/voice-speed",
        headers=_auth_header(tenant_id, employee_id),
    )

    assert resp.status_code == 200
    assert resp.json() == {"base_url": None, "has_api_key": False, "updated_at": None}


@pytest.mark.asyncio
async def test_update_voice_speed_settings_creates_config_without_returning_secret(client: AsyncClient):
    tenant_id, employee_id = await _ensure_admin()
    payload = {
        "base_url": " https://voicespeed.example.com/ ",
        "api_key": "vsk-test",
    }

    resp = await client.put(
        "/api/v1/open-agent-settings/voice-speed",
        headers=_auth_header(tenant_id, employee_id),
        json=payload,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["base_url"] == "https://voicespeed.example.com"
    assert body["has_api_key"] is True
    assert "api_key" not in body


@pytest.mark.asyncio
async def test_voice_speed_connection_test_uses_saved_secret_when_secret_omitted(
    client: AsyncClient,
    monkeypatch,
):
    tenant_id, employee_id = await _ensure_admin()
    fake_client = FakeVoiceSpeedClient()

    from app.services import open_agent_settings_service as service_module

    monkeypatch.setattr(service_module, "create_voice_speed_client", lambda: fake_client)

    await client.put(
        "/api/v1/open-agent-settings/voice-speed",
        headers=_auth_header(tenant_id, employee_id),
        json={"base_url": "https://voicespeed.example.com", "api_key": "vsk-saved"},
    )
    resp = await client.post(
        "/api/v1/open-agent-settings/voice-speed/test",
        headers=_auth_header(tenant_id, employee_id),
        json={"base_url": "https://voicespeed.example.com"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "message": "VoiceSpeed 连接成功"}
    assert fake_client.calls == [("https://voicespeed.example.com", "vsk-saved")]
