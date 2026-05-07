"""
Integration tests for VoiceFlow API
"""
import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


def _make_token(tenant_id: int = 7, role: str = "admin") -> str:
    return create_access_token({"sub": "1", "tenant_id": tenant_id, "roles": [role]})


def _auth_header(tenant_id: int = 7) -> dict:
    return {"Authorization": f"Bearer {_make_token(tenant_id)}"}


class TestVoiceFlowsAPI:

    @pytest.mark.asyncio
    async def test_list_empty_returns_200(self, client: AsyncClient):
        headers = _auth_header(tenant_id=99999)
        resp = await client.get("/api/v1/voice-flows", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_create_and_get_select(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        name = f"Default IVR {uuid.uuid4().hex[:8]}"
        c = await client.post(
            "/api/v1/voice-flows",
            headers=headers,
            json={"name": name, "enabled": True},
        )
        assert c.status_code == 201
        fid = c.json()["id"]

        sel = await client.get("/api/v1/voice-flows/select", headers=headers)
        assert sel.status_code == 200
        items = sel.json()["items"]
        assert any(x["id"] == fid for x in items)

        one = await client.get(f"/api/v1/voice-flows/{fid}", headers=headers)
        assert one.status_code == 200
        assert one.json()["name"] == name

    @pytest.mark.asyncio
    async def test_update_and_soft_delete(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        c = await client.post(
            "/api/v1/voice-flows",
            headers=headers,
            json={"name": f"Flow A {uuid.uuid4().hex[:8]}", "enabled": True},
        )
        fid = c.json()["id"]

        u = await client.put(
            f"/api/v1/voice-flows/{fid}",
            headers=headers,
            json={"name": "Flow A2", "enabled": False},
        )
        assert u.status_code == 200
        assert u.json()["enabled"] is False

        d = await client.delete(f"/api/v1/voice-flows/{fid}", headers=headers)
        assert d.status_code == 200

        sel = await client.get("/api/v1/voice-flows/select", headers=headers)
        ids = [x["id"] for x in sel.json()["items"]]
        assert fid not in ids
