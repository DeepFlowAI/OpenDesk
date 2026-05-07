"""
Integration tests for EmployeeGroup API
"""
import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


def _make_token(tenant_id: int = 7, role: str = "admin") -> str:
    return create_access_token({"sub": "1", "tenant_id": tenant_id, "roles": [role]})


def _auth_header(tenant_id: int = 7) -> dict:
    return {"Authorization": f"Bearer {_make_token(tenant_id)}"}


SAMPLE_PAYLOAD = {
    "name": "Support Team",
    "description": "Front-line support agents",
    "member_ids": [],
}


class TestEmployeeGroupAPI:

    @pytest.mark.asyncio
    async def test_list_returns_200_paginated(self, client: AsyncClient):
        """List should return 200 with paginated response."""
        headers = _auth_header(tenant_id=5555)
        resp = await client.get("/api/v1/employee-groups", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data

    @pytest.mark.asyncio
    async def test_create_returns_201(self, client: AsyncClient):
        """Create with valid data should return 201."""
        headers = _auth_header()
        resp = await client.post("/api/v1/employee-groups", json=SAMPLE_PAYLOAD, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Support Team"
        assert data["description"] == "Front-line support agents"
        assert "id" in data
        assert "member_count" in data

    @pytest.mark.asyncio
    async def test_get_by_id_returns_200(self, client: AsyncClient):
        """Get existing group should return 200 with members."""
        headers = _auth_header()
        payload = {"name": "Get Test Group", "description": "For get test"}
        create_resp = await client.post("/api/v1/employee-groups", json=payload, headers=headers)
        created_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/employee-groups/{created_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == created_id
        assert "members" in data

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client: AsyncClient):
        """Get non-existing group should return 404."""
        headers = _auth_header()
        resp = await client.get("/api/v1/employee-groups/99999", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_returns_200(self, client: AsyncClient):
        """Update existing group should return 200."""
        headers = _auth_header()
        payload = {"name": "Update Test Group"}
        create_resp = await client.post("/api/v1/employee-groups", json=payload, headers=headers)
        created_id = create_resp.json()["id"]

        update_payload = {"name": "Updated Group Name", "description": "Updated desc", "member_ids": []}
        resp = await client.put(f"/api/v1/employee-groups/{created_id}", json=update_payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Group Name"

    @pytest.mark.asyncio
    async def test_delete_returns_200(self, client: AsyncClient):
        """Delete existing group should return 200."""
        headers = _auth_header()
        payload = {"name": "Delete Test Group"}
        create_resp = await client.post("/api/v1/employee-groups", json=payload, headers=headers)
        created_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/employee-groups/{created_id}", headers=headers)
        assert resp.status_code == 200

        resp2 = await client.get(f"/api/v1/employee-groups/{created_id}", headers=headers)
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_create_empty_name_returns_422(self, client: AsyncClient):
        """Empty name should return 422."""
        headers = _auth_header()
        resp = await client.post("/api/v1/employee-groups", json={"name": ""}, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_duplicate_name_returns_400(self, client: AsyncClient):
        """Duplicate name in same tenant should return 400."""
        headers = _auth_header()
        payload = {"name": "Dup Test Group"}
        await client.post("/api/v1/employee-groups", json=payload, headers=headers)
        resp = await client.post("/api/v1/employee-groups", json=payload, headers=headers)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_keyword_search(self, client: AsyncClient):
        """Keyword search should filter results."""
        headers = _auth_header()
        await client.post("/api/v1/employee-groups", json={"name": "Alpha Team"}, headers=headers)
        await client.post("/api/v1/employee-groups", json={"name": "Beta Squad"}, headers=headers)

        resp = await client.get("/api/v1/employee-groups?keyword=Alpha", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all("Alpha" in item["name"] for item in data["items"])

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, client: AsyncClient):
        """Groups from one tenant should not be visible to another."""
        headers_a = _auth_header(tenant_id=7)
        headers_b = _auth_header(tenant_id=6666)

        create_resp = await client.post(
            "/api/v1/employee-groups",
            json={"name": "Isolated Group"},
            headers=headers_a,
        )
        created_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/employee-groups/{created_id}", headers=headers_b)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_auth_returns_422(self, client: AsyncClient):
        """Request without Authorization header should fail."""
        resp = await client.get("/api/v1/employee-groups")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client: AsyncClient):
        """Invalid JWT should return 401."""
        headers = {"Authorization": "Bearer invalid.token"}
        resp = await client.get("/api/v1/employee-groups", headers=headers)
        assert resp.status_code == 401


class TestEmployeeSelectAPI:

    @pytest.mark.asyncio
    async def test_list_employees_for_selection_returns_200_paginated(self, client: AsyncClient):
        """List employees for selection should return 200 with paginated response."""
        headers = _auth_header()
        resp = await client.get("/api/v1/system-users", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
