"""
Integration tests for ticket change timeline API.
"""
import uuid

import pytest
from httpx import AsyncClient

from app.configs.settings import settings


TENANT_HEADERS = {"X-API-Key": settings.TENANT_API_KEY}


async def _bootstrap_tenant(client: AsyncClient) -> dict:
    suffix = uuid.uuid4().hex[:8]
    username = f"admin_{suffix}"
    password = "Passw0rd123"
    resp = await client.post(
        "/api/v1/tenants",
        headers=TENANT_HEADERS,
        json={
            "name": f"tenant_{suffix}",
            "admin_username": username,
            "admin_password": password,
        },
    )
    assert resp.status_code == 201, resp.text
    tenant_slug = resp.json()["id"]

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"tenant": tenant_slug, "username": username, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    data = login_resp.json()
    return {
        "admin_id": data["user"]["id"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


async def _create_ticket(client: AsyncClient, headers: dict) -> int:
    resp = await client.post(
        "/api/v1/tickets",
        headers=headers,
        json={"title": "Initial title", "status": "open", "priority": "medium"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestTicketChangesAPI:

    @pytest.mark.asyncio
    async def test_create_ticket_creates_create_record(self, client: AsyncClient):
        ctx = await _bootstrap_tenant(client)
        headers = ctx["headers"]

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
        assert item["actor_id"] == ctx["admin_id"]

    @pytest.mark.asyncio
    async def test_update_ticket_creates_change_record(self, client: AsyncClient):
        ctx = await _bootstrap_tenant(client)
        headers = ctx["headers"]
        ticket_id = await _create_ticket(client, headers)

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
        assert item["actor_id"] == ctx["admin_id"]

    @pytest.mark.asyncio
    async def test_update_ticket_multi_field_one_batch_record(self, client: AsyncClient):
        ctx = await _bootstrap_tenant(client)
        headers = ctx["headers"]
        ticket_id = await _create_ticket(client, headers)

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
        ctx = await _bootstrap_tenant(client)
        headers = ctx["headers"]
        ticket_id = await _create_ticket(client, headers)

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
        ctx = await _bootstrap_tenant(client)
        other_ctx = await _bootstrap_tenant(client)
        ticket_id = await _create_ticket(client, ctx["headers"])

        resp = await client.get(
            f"/api/v1/tickets/{ticket_id}/changes",
            headers=other_ctx["headers"],
        )
        assert resp.status_code == 404
