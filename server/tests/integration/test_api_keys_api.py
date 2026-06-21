"""
Integration tests for API Key management and Open API auth.
"""
import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal


async def _create_employee_context(super_admin: bool) -> tuple[int, dict]:
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
                "tenant_key": f"api-key-{suffix}",
                "slug": f"api-key-{suffix}",
                "name": f"API Key {suffix}",
            },
        )
        tenant_id = int(tenant_result.scalar_one())
        employee_result = await db.execute(
            text(
                """
                INSERT INTO employees (
                    tenant_id, username, email, password_hash, display_name,
                    name, roles, is_active, is_super_admin
                )
                VALUES (
                    :tenant_id, :username, :email, :password_hash, :display_name,
                    :name, CAST(:roles AS JSON), true, :is_super_admin
                )
                RETURNING id
                """
            ),
            {
                "tenant_id": tenant_id,
                "username": f"api_key_admin_{suffix}",
                "email": f"api_key_admin_{suffix}@example.com",
                "password_hash": password_hash,
                "display_name": f"API Key Admin {suffix}",
                "name": f"API Key Admin {suffix}",
                "roles": json.dumps(["admin"]),
                "is_super_admin": super_admin,
            },
        )
        employee_id = int(employee_result.scalar_one())
        await db.commit()

    token = create_access_token({"sub": str(employee_id), "tenant_id": tenant_id, "roles": ["admin"]})
    return tenant_id, {"Authorization": f"Bearer {token}"}


async def _create_channel(tenant_id: int) -> str:
    channel_key = f"ch_{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                """
                INSERT INTO channels (
                    tenant_id, name, channel_type, access_mode, channel_key,
                    channel_key_version, public_access_enabled, config
                )
                VALUES (
                    :tenant_id, :name, 'web', 'url', :channel_key,
                    1, true, CAST(:config AS JSONB)
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "name": "API Key Channel",
                "channel_key": channel_key,
                "config": json.dumps({}),
            },
        )
        await db.commit()
    return channel_key


@pytest.mark.asyncio
async def test_api_key_management_requires_super_admin(client: AsyncClient):
    _tenant_id, headers = await _create_employee_context(super_admin=False)

    resp = await client.get("/api/v1/api-keys", headers=headers)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_rotate_disable_delete_api_key(client: AsyncClient):
    _tenant_id, headers = await _create_employee_context(super_admin=True)

    create_resp = await client.post("/api/v1/api-keys", headers=headers, json={"name": "Backend"})
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["api_key"].startswith("sk-odk-")
    assert created["record"]["masked_key"].endswith("********")
    assert "key_hash" not in created["record"]

    api_key_id = created["record"]["id"]
    rotate_resp = await client.post(f"/api/v1/api-keys/{api_key_id}/rotate", headers=headers)
    assert rotate_resp.status_code == 200
    assert rotate_resp.json()["api_key"] != created["api_key"]

    active_delete_resp = await client.delete(f"/api/v1/api-keys/{api_key_id}", headers=headers)
    assert active_delete_resp.status_code == 400

    disable_resp = await client.post(f"/api/v1/api-keys/{api_key_id}/disable", headers=headers)
    assert disable_resp.status_code == 200
    assert disable_resp.json()["is_active"] is False

    delete_resp = await client.delete(f"/api/v1/api-keys/{api_key_id}", headers=headers)
    assert delete_resp.status_code == 200


@pytest.mark.asyncio
async def test_context_token_uses_enabled_api_key(client: AsyncClient):
    tenant_id, headers = await _create_employee_context(super_admin=True)
    channel_key = await _create_channel(tenant_id)

    create_resp = await client.post("/api/v1/api-keys", headers=headers, json={"name": "Context"})
    api_key = create_resp.json()["api_key"]
    api_key_id = create_resp.json()["record"]["id"]

    token_resp = await client.post(
        "/api/v1/open/context-token",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "channelKey": channel_key,
            "customer": {"nickname": "Ada"},
            "sessionSummary": {"fields": {"customer_intent": "consult"}},
            "businessRecords": [{"title": "Order 1"}],
            "expiresSeconds": 300,
        },
    )
    assert token_resp.status_code == 200
    assert token_resp.json()["contextToken"]
    assert token_resp.json()["expiresIn"] == 300

    await client.post(f"/api/v1/api-keys/{api_key_id}/disable", headers=headers)
    disabled_resp = await client.post(
        "/api/v1/open/context-token",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"channelKey": channel_key, "expiresSeconds": 300},
    )
    assert disabled_resp.status_code == 403
