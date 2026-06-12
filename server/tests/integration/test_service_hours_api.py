"""
Integration tests for ServiceHours API
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.integration.rbac_helpers import auth_headers_for_seeded_admin, ensure_admin_principals


@pytest_asyncio.fixture(autouse=True)
async def seed_admin_principals():
    await ensure_admin_principals([7, 8888, 9999])


def _auth_header(tenant_id: int = 7) -> dict:
    return auth_headers_for_seeded_admin(tenant_id)


SAMPLE_PAYLOAD = {
    "name": "Default Schedule",
    "description": "Standard business hours",
    "weekly_schedules": [
        {"day_of_week": 1, "slots": [{"start": "09:00", "end": "18:00"}]},
        {"day_of_week": 2, "slots": [{"start": "09:00", "end": "18:00"}]},
    ],
    "holidays": [
        {"name": "National Day", "start": "2025-10-01T00:00", "end": "2025-10-07T23:59"}
    ],
    "makeup_days": [
        {"name": "Makeup", "start": "2025-02-04T09:00", "end": "2025-02-04T18:00"}
    ],
}


class TestServiceHoursAPI:

    @pytest.mark.asyncio
    async def test_list_empty_returns_200(self, client: AsyncClient):
        """Empty list should return 200 with empty array."""
        headers = _auth_header(tenant_id=8888)
        resp = await client.get("/api/v1/service-hours", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_create_returns_201(self, client: AsyncClient):
        """Create with valid data should return 201."""
        headers = _auth_header()
        resp = await client.post("/api/v1/service-hours", json=SAMPLE_PAYLOAD, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Default Schedule"
        assert len(data["weekly_schedules"]) == 2
        assert len(data["holidays"]) == 1
        assert len(data["makeup_days"]) == 1
        assert "id" in data

    @pytest.mark.asyncio
    async def test_get_by_id_returns_200(self, client: AsyncClient):
        """Get existing record should return 200."""
        headers = _auth_header()
        create_resp = await client.post("/api/v1/service-hours", json=SAMPLE_PAYLOAD, headers=headers)
        created_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/service-hours/{created_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == created_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client: AsyncClient):
        """Get non-existing record should return 404."""
        headers = _auth_header()
        resp = await client.get("/api/v1/service-hours/99999", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_returns_200(self, client: AsyncClient):
        """Update existing record should return 200."""
        headers = _auth_header()
        create_resp = await client.post("/api/v1/service-hours", json=SAMPLE_PAYLOAD, headers=headers)
        created_id = create_resp.json()["id"]

        update_payload = {**SAMPLE_PAYLOAD, "name": "Updated Schedule", "description": "Updated desc"}
        resp = await client.put(f"/api/v1/service-hours/{created_id}", json=update_payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Schedule"

    @pytest.mark.asyncio
    async def test_delete_returns_200(self, client: AsyncClient):
        """Delete existing record should return 200."""
        headers = _auth_header()
        create_resp = await client.post("/api/v1/service-hours", json=SAMPLE_PAYLOAD, headers=headers)
        created_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/service-hours/{created_id}", headers=headers)
        assert resp.status_code == 200

        resp2 = await client.get(f"/api/v1/service-hours/{created_id}", headers=headers)
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_create_empty_name_returns_422(self, client: AsyncClient):
        """Empty name should return 422."""
        headers = _auth_header()
        payload = {**SAMPLE_PAYLOAD, "name": ""}
        resp = await client.post("/api/v1/service-hours", json=payload, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_invalid_day_of_week_returns_422(self, client: AsyncClient):
        """Invalid day_of_week should return 422."""
        headers = _auth_header()
        payload = {
            "name": "Bad Day",
            "weekly_schedules": [{"day_of_week": 8, "slots": []}],
        }
        resp = await client.post("/api/v1/service-hours", json=payload, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_invalid_time_format_returns_422(self, client: AsyncClient):
        """Invalid time format should return 422."""
        headers = _auth_header()
        payload = {
            "name": "Bad Time",
            "weekly_schedules": [
                {"day_of_week": 1, "slots": [{"start": "25:00", "end": "18:00"}]}
            ],
        }
        resp = await client.post("/api/v1/service-hours", json=payload, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, client: AsyncClient):
        """Records from one tenant should not be visible to another."""
        headers_a = _auth_header(tenant_id=7)
        headers_b = _auth_header(tenant_id=9999)

        create_resp = await client.post("/api/v1/service-hours", json=SAMPLE_PAYLOAD, headers=headers_a)
        created_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/service-hours/{created_id}", headers=headers_b)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_auth_returns_401(self, client: AsyncClient):
        """Request without Authorization header should fail."""
        resp = await client.get("/api/v1/service-hours")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client: AsyncClient):
        """Invalid JWT should return 401."""
        headers = {"Authorization": "Bearer invalid.token"}
        resp = await client.get("/api/v1/service-hours", headers=headers)
        assert resp.status_code == 401
