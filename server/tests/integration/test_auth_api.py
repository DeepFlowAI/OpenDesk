"""
Integration tests for Auth API
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal

_SEEDED = False


@pytest_asyncio.fixture(autouse=True)
async def seed_data():
    """Idempotent seed — safe to call per-test due to ON CONFLICT."""
    global _SEEDED
    if _SEEDED:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO tenants (tenant_id, name, is_active)
            VALUES ('test-corp', 'Test Corp', true)
            ON CONFLICT (tenant_id) DO NOTHING
        """))
        await db.commit()

        result = await db.execute(text("SELECT id FROM tenants WHERE tenant_id = 'test-corp'"))
        tenant_pk = result.scalar_one()

        hashed = hash_password("Test1234")
        await db.execute(text("""
            INSERT INTO employees (tenant_id, username, email, password_hash, display_name, roles, is_active)
            VALUES (:tid, 'testuser', 'test@example.com', :pw, 'Test User', '["admin"]'::jsonb, true)
            ON CONFLICT ON CONSTRAINT uq_employees_tenant_username DO NOTHING
        """), {"tid": tenant_pk, "pw": hashed})

        await db.execute(text("""
            INSERT INTO employees (tenant_id, username, email, password_hash, display_name, roles, is_active)
            VALUES (:tid, 'disabled_user', 'disabled@example.com', :pw, 'Disabled User', '["agent"]'::jsonb, false)
            ON CONFLICT ON CONSTRAINT uq_employees_tenant_username DO NOTHING
        """), {"tid": tenant_pk, "pw": hashed})

        await db.commit()
    _SEEDED = True


class TestAuthAPI:

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "tenant": "test-corp",
            "username": "testuser",
            "password": "Test1234",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "testuser"
        assert data["user"]["roles"] == ["admin"]

    @pytest.mark.asyncio
    async def test_login_with_email_success(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "tenant": "test-corp",
            "username": "test@example.com",
            "password": "Test1234",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "tenant": "test-corp",
            "username": "testuser",
            "password": "WrongPass1",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_wrong_username_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "tenant": "test-corp",
            "username": "nonexistent",
            "password": "Test1234",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_wrong_tenant_returns_404(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "tenant": "no-such-tenant",
            "username": "testuser",
            "password": "Test1234",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_login_disabled_user_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "tenant": "test-corp",
            "username": "disabled_user",
            "password": "Test1234",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_missing_field_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "tenant": "test-corp",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_empty_body_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422
