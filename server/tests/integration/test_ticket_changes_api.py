"""
Integration tests for ticket change timeline API.
"""
import uuid

import pytest
from httpx import AsyncClient

from app.configs.settings import settings
from app.core.security import create_access_token


TENANT_HEADERS = {"X-API-Key": settings.TENANT_API_KEY}


def _make_token(tenant_id: int, user_id: int = 1) -> str:
    return create_access_token({"sub": str(user_id), "tenant_id": tenant_id, "roles": ["admin"]})


def _auth_header(tenant_id: int, user_id: int = 1) -> dict:
    return {"Authorization": f"Bearer {_make_token(tenant_id, user_id)}"}


async def _create_tenant(client: AsyncClient) -> int:
    suffix = uuid.uuid4().hex[:8]
    resp = await client.post(
        "/api/v1/tenants",
        headers=TENANT_HEADERS,
        json={
            "name": f"tenant_{suffix}",
            "admin_username": f"admin_{suffix}",
            "admin_password": "Passw0rd123",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_ticket(client: AsyncClient, tenant_id: int) -> int:
    resp = await client.post(
        "/api/v1/tickets",
        headers=_auth_header(tenant_id),
        json={"title": "Initial title", "status": "open", "priority": "medium"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestTicketChangesAPI:

    @pytest.mark.asyncio
    async def test_create_ticket_creates_create_record(self, client: AsyncClient):
        tenant_id = await _create_tenant(client)
        headers = _auth_header(tenant_id, user_id=66)

        create_resp = await client.post(
            "/api/v1/tickets",
            headers=headers,
            json={"title": "Created title", "status": "open", "priority": "medium"},
        )
        assert create_resp.status_code == 201
        ticket_id = create_resp.json()["id"]

        list_resp = await client.get(
            f"/api/v1/tickets/{ticket_id}/changes",
            headers=headers,
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["field_key"] == "__create__"
        assert item["old_value"] is None
        assert item["new_value"] is None
        assert item["entries"] is not None
        entry_by_key = {entry["field_key"]: entry for entry in item["entries"]}
        assert entry_by_key["title"]["old_value"] is None
        assert entry_by_key["title"]["new_value"] == "Created title"
        assert entry_by_key["status"]["new_value"] == "open"
        assert entry_by_key["priority"]["new_value"] == "medium"
        assert item["actor_id"] == 66

    @pytest.mark.asyncio
    async def test_update_ticket_creates_change_record(self, client: AsyncClient):
        tenant_id = await _create_tenant(client)
        ticket_id = await _create_ticket(client, tenant_id)
        headers = _auth_header(tenant_id, user_id=77)

        update_resp = await client.put(
            f"/api/v1/tickets/{ticket_id}",
            headers=headers,
            json={"title": "Updated title"},
        )
        assert update_resp.status_code == 200

        list_resp = await client.get(
            f"/api/v1/tickets/{ticket_id}/changes",
            headers=headers,
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] == 2
        item = data["items"][0]
        assert item["field_key"] == "__batch__"
        assert item["old_value"] is None
        assert item["new_value"] is None
        assert item["entries"] is not None
        assert len(item["entries"]) == 1
        assert item["entries"][0]["field_key"] == "title"
        assert item["entries"][0]["old_value"] == "Initial title"
        assert item["entries"][0]["new_value"] == "Updated title"
        assert item["actor_id"] == 77

    @pytest.mark.asyncio
    async def test_update_ticket_multi_field_one_batch_record(self, client: AsyncClient):
        tenant_id = await _create_tenant(client)
        ticket_id = await _create_ticket(client, tenant_id)
        headers = _auth_header(tenant_id, user_id=88)

        update_resp = await client.put(
            f"/api/v1/tickets/{ticket_id}",
            headers=headers,
            json={"title": "T2", "priority": "urgent", "status": "in_progress"},
        )
        assert update_resp.status_code == 200

        list_resp = await client.get(
            f"/api/v1/tickets/{ticket_id}/changes",
            headers=headers,
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] == 2
        item = data["items"][0]
        assert item["field_key"] == "__batch__"
        assert item["entries"] is not None
        assert len(item["entries"]) == 3
        keys = {e["field_key"] for e in item["entries"]}
        assert keys == {"title", "priority", "status"}

    @pytest.mark.asyncio
    async def test_update_ticket_without_actual_change_creates_no_record(self, client: AsyncClient):
        tenant_id = await _create_tenant(client)
        ticket_id = await _create_ticket(client, tenant_id)
        headers = _auth_header(tenant_id)

        update_resp = await client.put(
            f"/api/v1/tickets/{ticket_id}",
            headers=headers,
            json={"status": "open"},
        )
        assert update_resp.status_code == 200

        list_resp = await client.get(f"/api/v1/tickets/{ticket_id}/changes", headers=headers)
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] == 1
        assert data["items"][0]["field_key"] == "__create__"

    @pytest.mark.asyncio
    async def test_list_changes_cross_tenant_returns_404(self, client: AsyncClient):
        tenant_id = await _create_tenant(client)
        other_tenant_id = await _create_tenant(client)
        ticket_id = await _create_ticket(client, tenant_id)

        resp = await client.get(
            f"/api/v1/tickets/{ticket_id}/changes",
            headers=_auth_header(other_tenant_id),
        )
        assert resp.status_code == 404
