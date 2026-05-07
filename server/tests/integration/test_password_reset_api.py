"""
Integration tests for Password Reset API
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal

_SEEDED = False


@pytest_asyncio.fixture(autouse=True)
async def seed_data():
    """Idempotent seed for password reset tests."""
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

        hashed = hash_password("OldPass123")
        await db.execute(text("""
            INSERT INTO employees (tenant_id, username, email, password_hash, display_name, role, is_active)
            VALUES (:tid, 'resetuser', 'reset@example.com', :pw, 'Reset User', 'admin', true)
            ON CONFLICT ON CONSTRAINT uq_employees_tenant_username DO NOTHING
        """), {"tid": tenant_pk, "pw": hashed})
        await db.commit()
    _SEEDED = True


class TestSendVerifyCodeAPI:

    @pytest.mark.asyncio
    @patch("app.services.password_reset_service.create_email_client")
    async def test_send_code_success(self, mock_factory, client: AsyncClient):
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        resp = await client.post("/api/v1/auth/send-verify-code", json={
            "tenant": "test-corp",
            "username": "resetuser",
            "locale": "zh",
        })
        assert resp.status_code == 200
        mock_client.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_code_tenant_not_found_returns_404(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/send-verify-code", json={
            "tenant": "no-such-tenant",
            "username": "resetuser",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_send_code_user_not_found_returns_404(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/send-verify-code", json={
            "tenant": "test-corp",
            "username": "nonexistent",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @patch("app.services.password_reset_service.create_email_client")
    async def test_send_code_rate_limited(self, mock_factory, client: AsyncClient):
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        await client.post("/api/v1/auth/send-verify-code", json={
            "tenant": "test-corp",
            "username": "resetuser",
        })

        resp = await client.post("/api/v1/auth/send-verify-code", json={
            "tenant": "test-corp",
            "username": "resetuser",
        })
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_send_code_missing_field_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/send-verify-code", json={
            "tenant": "test-corp",
        })
        assert resp.status_code == 422


class TestResetPasswordAPI:

    @pytest.mark.asyncio
    @patch("app.services.password_reset_service.create_email_client")
    async def test_reset_password_success(self, mock_factory, client: AsyncClient):
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        from tests.conftest import _get_fake_redis
        fake_redis = await _get_fake_redis()

        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT id FROM tenants WHERE tenant_id = 'test-corp'"))
            tenant_pk = result.scalar_one()
            result = await db.execute(text(
                "SELECT id FROM employees WHERE tenant_id = :tid AND username = 'resetuser'"
            ), {"tid": tenant_pk})
            user_id = result.scalar_one()

        await fake_redis.setex(f"verify_code:{tenant_pk}:{user_id}", 600, "123456")

        resp = await client.post("/api/v1/auth/reset-password", json={
            "tenant": "test-corp",
            "username": "resetuser",
            "verify_code": "123456",
            "new_password": "NewPass123",
        })
        assert resp.status_code == 200

        login_resp = await client.post("/api/v1/auth/login", json={
            "tenant": "test-corp",
            "username": "resetuser",
            "password": "NewPass123",
        })
        assert login_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_reset_password_wrong_code_returns_400(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/reset-password", json={
            "tenant": "test-corp",
            "username": "resetuser",
            "verify_code": "000000",
            "new_password": "NewPass456",
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_tenant_not_found_returns_404(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/reset-password", json={
            "tenant": "no-such-tenant",
            "username": "resetuser",
            "verify_code": "123456",
            "new_password": "NewPass456",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reset_password_missing_field_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/reset-password", json={
            "tenant": "test-corp",
            "username": "resetuser",
        })
        assert resp.status_code == 422
