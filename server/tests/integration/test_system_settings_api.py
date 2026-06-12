"""
Integration tests for System Settings API
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.integration.rbac_helpers import auth_headers_for_seeded_admin, ensure_admin_principals


@pytest_asyncio.fixture(autouse=True)
async def seed_admin_principals():
    await ensure_admin_principals([7, 9999])


def _auth_header(tenant_id: int = 7) -> dict:
    return auth_headers_for_seeded_admin(tenant_id)


class TestSystemSettingsAPI:

    @pytest.mark.asyncio
    async def test_get_settings_returns_defaults_for_new_tenant(self, client: AsyncClient):
        """Tenant with no settings record should get defaults."""
        headers = _auth_header(tenant_id=9999)
        resp = await client.get("/api/v1/system-settings", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_language"] == "zh"
        assert data["default_timezone"] == "Asia/Shanghai"

    @pytest.mark.asyncio
    async def test_update_settings_creates_record(self, client: AsyncClient):
        """PUT on a tenant without settings should create a record."""
        headers = _auth_header(tenant_id=7)
        payload = {"default_language": "en", "default_timezone": "America/New_York"}
        resp = await client.put("/api/v1/system-settings", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_language"] == "en"
        assert data["default_timezone"] == "America/New_York"

    @pytest.mark.asyncio
    async def test_get_settings_returns_saved_values(self, client: AsyncClient):
        """After update, GET should return the saved values."""
        headers = _auth_header(tenant_id=7)
        await client.put(
            "/api/v1/system-settings",
            json={"default_language": "en", "default_timezone": "UTC"},
            headers=headers,
        )
        resp = await client.get("/api/v1/system-settings", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_language"] == "en"
        assert data["default_timezone"] == "UTC"

    @pytest.mark.asyncio
    async def test_update_settings_overwrites_existing(self, client: AsyncClient):
        """PUT should overwrite existing settings."""
        headers = _auth_header(tenant_id=7)
        await client.put(
            "/api/v1/system-settings",
            json={"default_language": "en", "default_timezone": "UTC"},
            headers=headers,
        )
        resp = await client.put(
            "/api/v1/system-settings",
            json={"default_language": "zh", "default_timezone": "Asia/Shanghai"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_language"] == "zh"
        assert data["default_timezone"] == "Asia/Shanghai"

    @pytest.mark.asyncio
    async def test_update_invalid_language_returns_422(self, client: AsyncClient):
        """Invalid language code should be rejected."""
        headers = _auth_header(tenant_id=7)
        payload = {"default_language": "fr", "default_timezone": "UTC"}
        resp = await client.put("/api/v1/system-settings", json=payload, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_invalid_timezone_returns_422(self, client: AsyncClient):
        """Invalid timezone should be rejected."""
        headers = _auth_header(tenant_id=7)
        payload = {"default_language": "zh", "default_timezone": "Invalid/Zone"}
        resp = await client.put("/api/v1/system-settings", json=payload, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_auth_returns_401(self, client: AsyncClient):
        """Request without Authorization header should fail."""
        resp = await client.get("/api/v1/system-settings")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client: AsyncClient):
        """Invalid JWT token should return 401."""
        headers = {"Authorization": "Bearer invalid.token.here"}
        resp = await client.get("/api/v1/system-settings", headers=headers)
        assert resp.status_code == 401
