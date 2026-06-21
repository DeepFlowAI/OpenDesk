"""
Integration tests for agent max concurrent self-edit API.
"""
import json
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal


@pytest_asyncio.fixture
async def max_concurrent_context():
    suffix = uuid.uuid4().hex[:10]
    password_hash = hash_password("Test1234abc")

    async with AsyncSessionLocal() as db:
        tenant_result = await db.execute(
            text(
                """
                INSERT INTO tenants (tenant_id, slug, name, is_active)
                VALUES (:tenant_key, :slug, :name, true)
                RETURNING id
                """
            ),
            {
                "tenant_key": f"mc-{suffix}",
                "slug": f"mc-{suffix}",
                "name": f"Max Concurrent {suffix}",
            },
        )
        tenant_id = tenant_result.scalar_one()

        async def create_employee(username: str) -> int:
            result = await db.execute(
                text(
                    """
                    INSERT INTO employees (
                        tenant_id, username, email, password_hash, display_name,
                        name, roles, is_active, max_concurrent
                    )
                    VALUES (
                        :tenant_id, :username, :email, :password_hash, :display_name,
                        :name, CAST(:roles AS JSON), true, 10
                    )
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "username": username,
                    "email": f"{username}@example.com",
                    "password_hash": password_hash,
                    "display_name": username,
                    "name": username,
                    "roles": json.dumps([]),
                },
            )
            return result.scalar_one()

        async def create_role(name: str, permissions: list[str]) -> int:
            result = await db.execute(
                text(
                    """
                    INSERT INTO roles (
                        tenant_id, name, description, is_system, is_active,
                        permissions, data_scopes
                    )
                    VALUES (
                        :tenant_id, :name, :description, false, true,
                        CAST(:permissions AS JSON), CAST(:data_scopes AS JSON)
                    )
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "name": name,
                    "description": name,
                    "permissions": json.dumps(permissions),
                    "data_scopes": json.dumps({}),
                },
            )
            return result.scalar_one()

        async def assign_role(employee_id: int, role_id: int) -> None:
            await db.execute(
                text(
                    """
                    INSERT INTO employee_roles (employee_id, role_id)
                    VALUES (:employee_id, :role_id)
                    """
                ),
                {"employee_id": employee_id, "role_id": role_id},
            )

        editor_id = await create_employee(f"mc_editor_{suffix}")
        readonly_id = await create_employee(f"mc_readonly_{suffix}")
        editor_role_id = await create_role(
            f"mc-editor-{suffix}",
            ["chat.workspace.use", "chat.workspace.max_concurrent.edit"],
        )
        readonly_role_id = await create_role(
            f"mc-readonly-{suffix}",
            ["chat.workspace.use"],
        )
        await assign_role(editor_id, editor_role_id)
        await assign_role(readonly_id, readonly_role_id)
        await db.commit()

    def auth_headers(user_id: int) -> dict:
        token = create_access_token({"sub": str(user_id), "tenant_id": tenant_id, "roles": []})
        return {"Authorization": f"Bearer {token}"}

    yield {
        "tenant_id": tenant_id,
        "editor": auth_headers(editor_id),
        "readonly": auth_headers(readonly_id),
        "editor_id": editor_id,
    }


class TestAgentMaxConcurrentAPI:
    @pytest.mark.asyncio
    async def test_update_own_max_concurrent_returns_stats(
        self,
        client: AsyncClient,
        max_concurrent_context: dict,
    ):
        resp = await client.put(
            "/api/v1/agent/max-concurrent",
            json={"max_concurrent": 15},
            headers=max_concurrent_context["editor"],
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["max_concurrent"] == 15
        assert "current_count" in data

        stats_resp = await client.get(
            "/api/v1/agent/stats",
            headers=max_concurrent_context["editor"],
        )
        assert stats_resp.status_code == 200
        assert stats_resp.json()["max_concurrent"] == 15

    @pytest.mark.asyncio
    async def test_update_without_permission_returns_403(
        self,
        client: AsyncClient,
        max_concurrent_context: dict,
    ):
        resp = await client.put(
            "/api/v1/agent/max-concurrent",
            json={"max_concurrent": 12},
            headers=max_concurrent_context["readonly"],
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_invalid_value_returns_422(
        self,
        client: AsyncClient,
        max_concurrent_context: dict,
    ):
        resp = await client.put(
            "/api/v1/agent/max-concurrent",
            json={"max_concurrent": 0},
            headers=max_concurrent_context["editor"],
        )
        assert resp.status_code == 422
