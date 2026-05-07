"""
Integration tests for OrganizationView API
"""
import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


def _make_token(tenant_id: int = 7, role: str = "admin") -> str:
    return create_access_token({"sub": "1", "tenant_id": tenant_id, "roles": [role]})


def _auth_header(tenant_id: int = 7) -> dict:
    return {"Authorization": f"Bearer {_make_token(tenant_id)}"}


def _view_payload(name: str | None = None) -> dict:
    return {
        "name": name or f"View {uuid.uuid4().hex[:8]}",
        "condition_logic": "and",
        "conditions": [],
        "group_field_id": None,
        "custom_columns_enabled": False,
        "columns_config": [],
    }


class TestOrganizationViewsAPI:

    @pytest.mark.asyncio
    async def test_list_returns_200(self, client: AsyncClient):
        headers = _auth_header()
        resp = await client.get("/api/v1/organization-views", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_create_returns_201(self, client: AsyncClient):
        headers = _auth_header()
        payload = _view_payload("重点客户")
        resp = await client.post("/api/v1/organization-views", headers=headers, json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "重点客户"
        assert data["is_enabled"] is True
        assert data["sort_order"] >= 1

    @pytest.mark.asyncio
    async def test_create_missing_name_returns_422(self, client: AsyncClient):
        headers = _auth_header()
        resp = await client.post("/api/v1/organization-views", headers=headers, json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_by_id_returns_200(self, client: AsyncClient):
        headers = _auth_header()
        create_resp = await client.post(
            "/api/v1/organization-views", headers=headers, json=_view_payload()
        )
        view_id = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/organization-views/{view_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == view_id

    @pytest.mark.asyncio
    async def test_get_not_found_returns_404(self, client: AsyncClient):
        headers = _auth_header()
        resp = await client.get("/api/v1/organization-views/99999", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_returns_200(self, client: AsyncClient):
        headers = _auth_header()
        create_resp = await client.post(
            "/api/v1/organization-views", headers=headers, json=_view_payload()
        )
        view_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/organization-views/{view_id}",
            headers=headers,
            json={"name": "Updated Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_delete_returns_200(self, client: AsyncClient):
        headers = _auth_header()
        create_resp = await client.post(
            "/api/v1/organization-views", headers=headers, json=_view_payload()
        )
        view_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/organization-views/{view_id}", headers=headers)
        assert resp.status_code == 200

        get_resp = await client.get(f"/api/v1/organization-views/{view_id}", headers=headers)
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_toggle_enabled(self, client: AsyncClient):
        headers = _auth_header()
        create_resp = await client.post(
            "/api/v1/organization-views", headers=headers, json=_view_payload()
        )
        view_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/organization-views/{view_id}/toggle",
            headers=headers,
            json={"is_enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["is_enabled"] is False

        resp = await client.put(
            f"/api/v1/organization-views/{view_id}/toggle",
            headers=headers,
            json={"is_enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_enabled"] is True

    @pytest.mark.asyncio
    async def test_sort_order(self, client: AsyncClient):
        headers = _auth_header()
        r1 = await client.post(
            "/api/v1/organization-views", headers=headers, json=_view_payload()
        )
        r2 = await client.post(
            "/api/v1/organization-views", headers=headers, json=_view_payload()
        )
        id1 = r1.json()["id"]
        id2 = r2.json()["id"]

        resp = await client.put(
            "/api/v1/organization-views/sort",
            headers=headers,
            json={"items": [{"id": id2, "sort_order": 1}, {"id": id1, "sort_order": 2}]},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_with_conditions(self, client: AsyncClient):
        headers = _auth_header()
        payload = _view_payload()
        payload["conditions"] = [
            {"field_id": 1, "operator": "eq", "value": "test"},
            {"field_key": "industry", "operator": "is_not_empty", "value": None},
        ]
        payload["condition_logic"] = "or"
        resp = await client.post("/api/v1/organization-views", headers=headers, json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["conditions"]) == 2
        assert data["condition_logic"] == "or"

    @pytest.mark.asyncio
    async def test_create_with_columns_config(self, client: AsyncClient):
        headers = _auth_header()
        payload = _view_payload()
        payload["custom_columns_enabled"] = True
        payload["columns_config"] = [
            {"field_id": 1, "visible": True, "sort_order": 0},
            {"field_key": "name", "visible": False, "sort_order": 1},
        ]
        resp = await client.post("/api/v1/organization-views", headers=headers, json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["custom_columns_enabled"] is True
        assert len(data["columns_config"]) == 2
