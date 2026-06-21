"""
Integration tests for Knowledge Open API.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal


async def _create_super_admin_context() -> tuple[int, dict[str, str]]:
    suffix = uuid.uuid4().hex[:10]
    password_hash = hash_password("Test1234abc")

    async with AsyncSessionLocal() as db:
        tenant_id = int(
            (
                await db.execute(
                    text(
                        """
                        INSERT INTO tenants (tenant_id, slug, name, is_active)
                        VALUES (:tenant_key, :slug, :name, true)
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_key": f"open-knowledge-{suffix}",
                        "slug": f"open-knowledge-{suffix}",
                        "name": f"Open Knowledge {suffix}",
                    },
                )
            ).scalar_one()
        )
        employee_id = int(
            (
                await db.execute(
                    text(
                        """
                        INSERT INTO employees (
                            tenant_id, username, email, password_hash, display_name,
                            name, roles, is_active, is_super_admin
                        )
                        VALUES (
                            :tenant_id, :username, :email, :password_hash, :display_name,
                            :name, CAST(:roles AS JSON), true, true
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "username": f"open_knowledge_admin_{suffix}",
                        "email": f"open_knowledge_admin_{suffix}@example.com",
                        "password_hash": password_hash,
                        "display_name": f"Open Knowledge Admin {suffix}",
                        "name": f"Open Knowledge Admin {suffix}",
                        "roles": json.dumps(["admin"]),
                    },
                )
            ).scalar_one()
        )
        await db.commit()

    token = create_access_token({"sub": str(employee_id), "tenant_id": tenant_id, "roles": ["admin"]})
    return tenant_id, {"Authorization": f"Bearer {token}"}


async def _create_api_key(client: AsyncClient, name: str = "Open Knowledge") -> tuple[int, str, dict[str, str]]:
    tenant_id, admin_headers = await _create_super_admin_context()
    create_resp = await client.post("/api/v1/api-keys", headers=admin_headers, json={"name": name})
    assert create_resp.status_code == 201
    return tenant_id, create_resp.json()["api_key"], admin_headers


@pytest.mark.asyncio
async def test_open_knowledge_api_directory_and_document_flow(client: AsyncClient) -> None:
    _tenant_id, api_key, _admin_headers = await _create_api_key(client)
    headers = {"Authorization": f"Bearer {api_key}"}

    missing_auth = await client.get("/api/v1/open/knowledge/directories")
    assert missing_auth.status_code == 401

    root_resp = await client.post(
        "/api/v1/open/knowledge/directories",
        headers=headers,
        json={"name": "产品"},
    )
    assert root_resp.status_code == 201
    root_body = root_resp.json()
    assert root_body["created_by"]["actor_type"] == "api_key"
    assert root_body["created_by"]["actor_name"] == "API Key: Open Knowledge"
    root_id = root_body["id"]

    child_resp = await client.post(
        "/api/v1/open/knowledge/directories",
        headers=headers,
        json={"name": "退款", "parent_id": root_id},
    )
    assert child_resp.status_code == 201
    child_id = child_resp.json()["id"]

    expired_from = datetime.now() - timedelta(days=3)
    expired_to = datetime.now() - timedelta(days=1)
    expired_resp = await client.post(
        "/api/v1/open/knowledge/documents",
        headers=headers,
        json={
            "directory_id": child_id,
            "title": "过期退款说明",
            "content_html": "<p>过期内容</p>",
            "status": "published",
            "validity_type": "scheduled",
            "valid_from": expired_from.isoformat(),
            "valid_to": expired_to.isoformat(),
        },
    )
    assert expired_resp.status_code == 201
    assert expired_resp.json()["display_status"] == "expired"

    draft_resp = await client.post(
        "/api/v1/open/knowledge/documents",
        headers=headers,
        json={
            "directory_id": child_id,
            "title": "内部草稿",
            "content_html": "<p>仅同步系统可见</p>",
            "status": "draft",
            "validity_type": "permanent",
        },
    )
    assert draft_resp.status_code == 201
    draft_id = draft_resp.json()["id"]

    draft_list = await client.get(
        f"/api/v1/open/knowledge/documents?directory={root_id}&status=draft",
        headers=headers,
    )
    assert draft_list.status_code == 200
    assert draft_list.json()["total"] == 1
    assert draft_list.json()["items"][0]["title"] == "内部草稿"

    expired_list = await client.get(
        "/api/v1/open/knowledge/documents?display_status=expired",
        headers=headers,
    )
    assert expired_list.status_code == 200
    assert expired_list.json()["total"] == 1
    assert expired_list.json()["items"][0]["title"] == "过期退款说明"

    detail_resp = await client.get(f"/api/v1/open/knowledge/documents/{draft_id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "draft"

    update_resp = await client.put(
        f"/api/v1/open/knowledge/documents/{draft_id}",
        headers=headers,
        json={"title": "内部草稿更新"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["updated_by"]["actor_type"] == "api_key"

    tree_resp = await client.get("/api/v1/open/knowledge/directories", headers=headers)
    assert tree_resp.status_code == 200
    assert tree_resp.json()["items"][0]["document_count"] == 2


@pytest.mark.asyncio
async def test_open_knowledge_api_tenant_isolation_and_disabled_key(client: AsyncClient) -> None:
    _tenant_one, api_key_one, admin_headers_one = await _create_api_key(client, name="Tenant One")
    _tenant_two, api_key_two, _admin_headers_two = await _create_api_key(client, name="Tenant Two")
    headers_one = {"Authorization": f"Bearer {api_key_one}"}
    headers_two = {"Authorization": f"Bearer {api_key_two}"}

    directory_resp = await client.post(
        "/api/v1/open/knowledge/directories",
        headers=headers_two,
        json={"name": "租户二目录"},
    )
    assert directory_resp.status_code == 201
    directory_id = directory_resp.json()["id"]

    cross_tenant_resp = await client.put(
        f"/api/v1/open/knowledge/directories/{directory_id}",
        headers=headers_one,
        json={"name": "越权改名"},
    )
    assert cross_tenant_resp.status_code == 404

    key_list = await client.get("/api/v1/api-keys", headers=admin_headers_one)
    assert key_list.status_code == 200
    key_id = key_list.json()[0]["id"]
    disable_resp = await client.post(f"/api/v1/api-keys/{key_id}/disable", headers=admin_headers_one)
    assert disable_resp.status_code == 200

    disabled_resp = await client.get("/api/v1/open/knowledge/directories", headers=headers_one)
    assert disabled_resp.status_code == 403
