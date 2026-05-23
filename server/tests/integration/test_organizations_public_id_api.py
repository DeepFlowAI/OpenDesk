"""
Integration tests for organization public ID APIs.
"""
import re
import uuid

import pytest
from httpx import AsyncClient

from app.configs.settings import settings


API_KEY = settings.TENANT_API_KEY
TENANT_HEADERS = {"X-API-Key": API_KEY}


def _unique(prefix: str = "orgpub") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _setup_tenant_and_auth(client: AsyncClient) -> dict:
    tenant_name = _unique("tenant")
    admin_user = _unique("admin")
    admin_pass = "Passw0rd123"

    create_resp = await client.post(
        "/api/v1/tenants",
        headers=TENANT_HEADERS,
        json={
            "name": tenant_name,
            "admin_username": admin_user,
            "admin_password": admin_pass,
        },
    )
    assert create_resp.status_code == 201
    tenant_slug = create_resp.json()["id"]

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant": tenant_slug,
            "username": admin_user,
            "password": admin_pass,
        },
    )
    assert login_resp.status_code == 200
    return {"Authorization": f"Bearer {login_resp.json()['access_token']}"}


class TestOrganizationsPublicIdAPI:

    @pytest.mark.asyncio
    async def test_create_organization_returns_public_id_and_detail_accepts_it(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)

        create_resp = await client.post(
            "/api/v1/organizations",
            headers=headers,
            json={"name": "Acme"},
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created["public_id"].startswith("org_")
        assert re.fullmatch(r"org_[A-Za-z0-9_-]{16}", created["public_id"])

        detail_resp = await client.get(
            f"/api/v1/organizations/{created['public_id']}",
            headers=headers,
        )
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_numeric_organization_id_route_stays_compatible(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        create_resp = await client.post(
            "/api/v1/organizations",
            headers=headers,
            json={"name": "Legacy URL"},
        )
        created = create_resp.json()

        detail_resp = await client.get(f"/api/v1/organizations/{created['id']}", headers=headers)

        assert detail_resp.status_code == 200
        assert detail_resp.json()["public_id"] == created["public_id"]

    @pytest.mark.asyncio
    async def test_query_organizations_search_matches_public_id(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        create_resp = await client.post(
            "/api/v1/organizations",
            headers=headers,
            json={"name": "Searchable Org"},
        )
        public_id = create_resp.json()["public_id"]

        query_resp = await client.post(
            "/api/v1/organizations/query",
            headers=headers,
            json={"search": public_id, "page": 1, "per_page": 20},
        )

        assert query_resp.status_code == 200
        items = query_resp.json()["items"]
        assert any(item["public_id"] == public_id for item in items)

    @pytest.mark.asyncio
    async def test_public_id_detail_is_tenant_isolated(self, client: AsyncClient):
        headers_a = await _setup_tenant_and_auth(client)
        headers_b = await _setup_tenant_and_auth(client)
        create_resp = await client.post(
            "/api/v1/organizations",
            headers=headers_a,
            json={"name": "Tenant A Org"},
        )
        public_id = create_resp.json()["public_id"]

        detail_resp = await client.get(f"/api/v1/organizations/{public_id}", headers=headers_b)

        assert detail_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_public_id_users_route_resolves_internal_organization_id(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        org_resp = await client.post(
            "/api/v1/organizations",
            headers=headers,
            json={"name": "Users Org"},
        )
        org = org_resp.json()

        user_resp = await client.post(
            "/api/v1/users",
            headers=headers,
            json={"name": "Linked User", "organization_id": org["id"]},
        )
        assert user_resp.status_code == 201
        user = user_resp.json()

        users_resp = await client.get(
            f"/api/v1/organizations/{org['public_id']}/users",
            headers=headers,
        )

        assert users_resp.status_code == 200
        assert any(item["id"] == user["id"] for item in users_resp.json()["items"])
