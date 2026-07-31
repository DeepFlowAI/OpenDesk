"""
Integration tests for GET /api/v1/call-center/transfer-queues.
"""
import json
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from tests.integration.rbac_helpers import auth_headers_for_seeded_admin, ensure_admin_principals


@pytest_asyncio.fixture(autouse=True)
async def seed_admin_principals():
    await ensure_admin_principals([7])


def _admin_auth(tenant_id: int = 7) -> dict:
    return auth_headers_for_seeded_admin(tenant_id)


async def _create_employee_without_permission(tenant_id: int) -> dict:
    suffix = uuid.uuid4().hex[:8]
    password_hash = hash_password("Test1234abc")
    async with AsyncSessionLocal() as db:
        employee_id = (
            await db.execute(
                text(
                    """
                    INSERT INTO employees (
                        tenant_id, username, email, password_hash, display_name,
                        name, roles, is_active
                    )
                    VALUES (
                        :tenant_id, :username, :email, :password_hash, :display_name,
                        :name, CAST(:roles AS JSON), true
                    )
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "username": f"no_perm_transfer_{suffix}",
                    "email": f"no_perm_transfer_{suffix}@example.com",
                    "password_hash": password_hash,
                    "display_name": f"No Perm {suffix}",
                    "name": f"No Perm {suffix}",
                    "roles": json.dumps([]),
                },
            )
        ).scalar_one()
        await db.commit()

    token = create_access_token(
        {
            "sub": str(employee_id),
            "tenant_id": tenant_id,
            "roles": [],
        }
    )
    return {"Authorization": f"Bearer {token}"}


class TestTransferQueuesAPI:
    @pytest.mark.asyncio
    async def test_list_transfer_queues_returns_200_shape(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/call-center/transfer-queues",
            headers=_admin_auth(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        for item in body:
            assert set(item.keys()) >= {
                "queue_type",
                "queue_id",
                "name",
                "available_agent_count",
            }
            assert item["queue_type"] == "employee_group"
            assert isinstance(item["queue_id"], int)
            assert isinstance(item["name"], str)
            assert isinstance(item["available_agent_count"], int)
            assert item["available_agent_count"] >= 0

    @pytest.mark.asyncio
    async def test_list_transfer_queues_without_permission_returns_403(
        self, client: AsyncClient
    ):
        headers = await _create_employee_without_permission(7)
        resp = await client.get(
            "/api/v1/call-center/transfer-queues",
            headers=headers,
        )
        assert resp.status_code == 403
