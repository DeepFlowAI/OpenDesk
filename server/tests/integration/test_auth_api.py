"""
Integration tests for Auth API
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import create_access_token, hash_password
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
            INSERT INTO tenants (tenant_id, slug, name, is_active)
            VALUES ('test-corp', 'test-corp-slug', 'Test Corp', true)
            ON CONFLICT (tenant_id) DO NOTHING
        """))
        await db.execute(text("""
            UPDATE tenants
            SET slug = 'test-corp-slug'
            WHERE tenant_id = 'test-corp'
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
    async def test_login_with_slug_success(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "tenant": "TEST-CORP-SLUG",
            "username": "testuser",
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

    @pytest.mark.asyncio
    async def test_me_reflects_current_role_permissions(self, client: AsyncClient):
        async with AsyncSessionLocal() as db:
            tenant_pk = (
                await db.execute(text("SELECT id FROM tenants WHERE tenant_id = 'test-corp'"))
            ).scalar_one()
            role_id = (
                await db.execute(
                    text(
                        """
                        INSERT INTO roles (
                            tenant_id, name, description, is_system, is_active,
                            permissions, data_scopes
                        )
                        VALUES (
                            :tid, 'auth-me-call-only', 'Auth me call-only test role',
                            false, true, CAST(:permissions AS JSON), '{}'::json
                        )
                        ON CONFLICT ON CONSTRAINT uq_roles_tenant_name
                        DO UPDATE SET
                            is_active = true,
                            permissions = EXCLUDED.permissions,
                            data_scopes = EXCLUDED.data_scopes
                        RETURNING id
                        """
                    ),
                    {"tid": tenant_pk, "permissions": '["call.workspace.use"]'},
                )
            ).scalar_one()
            employee_id = (
                await db.execute(
                    text(
                        """
                        INSERT INTO employees (
                            tenant_id, username, email, password_hash,
                            display_name, name, roles, is_active
                        )
                        VALUES (
                            :tid, 'auth_me_refresh_user', 'auth-me-refresh@example.com',
                            :pw, 'Auth Me Refresh', 'Auth Me Refresh',
                            '["agent"]'::json, true
                        )
                        ON CONFLICT ON CONSTRAINT uq_employees_tenant_username
                        DO UPDATE SET
                            roles = EXCLUDED.roles,
                            is_active = true
                        RETURNING id
                        """
                    ),
                    {"tid": tenant_pk, "pw": hash_password("Test1234")},
                )
            ).scalar_one()
            await db.execute(
                text("DELETE FROM employee_roles WHERE employee_id = :employee_id"),
                {"employee_id": employee_id},
            )
            await db.execute(
                text(
                    """
                    INSERT INTO employee_roles (employee_id, role_id)
                    VALUES (:employee_id, :role_id)
                    """
                ),
                {"employee_id": employee_id, "role_id": role_id},
            )
            await db.commit()

        token = create_access_token(
            {"sub": str(employee_id), "tenant_id": tenant_pk, "roles": ["agent"]}
        )
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        user = resp.json()
        assert user["username"] == "auth_me_refresh_user"
        assert user["role_ids"] == [role_id]
        assert user["permissions"] == ["call.workspace.use"]

    @pytest.mark.asyncio
    async def test_preferences_patch_merges_current_employee_workspace_layout(self, client: AsyncClient):
        async with AsyncSessionLocal() as db:
            tenant_pk = (
                await db.execute(text("SELECT id FROM tenants WHERE tenant_id = 'test-corp'"))
            ).scalar_one()
            employee_id = (
                await db.execute(
                    text(
                        """
                        INSERT INTO employees (
                            tenant_id, username, email, password_hash,
                            display_name, name, roles, is_active, preferences
                        )
                        VALUES (
                            :tid, 'auth_preferences_user', 'auth-preferences@example.com',
                            :pw, 'Auth Preferences', 'Auth Preferences',
                            '["agent"]'::json, true, '{}'::jsonb
                        )
                        ON CONFLICT ON CONSTRAINT uq_employees_tenant_username
                        DO UPDATE SET
                            preferences = '{}'::jsonb,
                            is_active = true
                        RETURNING id
                        """
                    ),
                    {"tid": tenant_pk, "pw": hash_password("Test1234")},
                )
            ).scalar_one()
            await db.commit()

        token = create_access_token(
            {"sub": str(employee_id), "tenant_id": tenant_pk, "roles": ["agent"]}
        )
        headers = {"Authorization": f"Bearer {token}"}

        first_resp = await client.patch(
            "/api/v1/auth/me/preferences",
            headers=headers,
            json={"preferences": {"workspace_chat": {"auxiliary_panel_width": 420}}},
        )
        second_resp = await client.patch(
            "/api/v1/auth/me/preferences",
            headers=headers,
            json={"preferences": {"workspace_chat": {"composer_input_height": 88}}},
        )
        me_resp = await client.get("/api/v1/auth/me", headers=headers)

        assert first_resp.status_code == 200
        assert second_resp.status_code == 200
        assert me_resp.status_code == 200
        assert second_resp.json()["preferences"]["workspace_chat"] == {
            "auxiliary_panel_width": 420,
            "composer_input_height": 88,
        }
        assert me_resp.json()["preferences"]["workspace_chat"] == {
            "auxiliary_panel_width": 420,
            "composer_input_height": 88,
        }
