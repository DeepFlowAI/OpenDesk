"""
Integration tests for the three view-group aggregation endpoints:
  - POST /api/v1/tickets/views/{view_id}/groups
  - POST /api/v1/users/views/{view_id}/groups
  - POST /api/v1/organizations/views/{view_id}/groups
"""
import uuid

import pytest
from httpx import AsyncClient

from app.configs.settings import settings


API_KEY = settings.TENANT_API_KEY
TENANT_HEADERS = {"X-API-Key": API_KEY}


def _unique(prefix: str = "vg") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _setup_tenant_and_auth(client: AsyncClient) -> dict:
    """Create a fresh tenant for an isolated test, return auth headers."""
    tenant_name = _unique("vg_test")
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


def _select_field(domain: str, name: str | None = None) -> dict:
    return {
        "domain": domain,
        "name": name or _unique("级别"),
        "field_type": "single_select",
        "type_config": {},
        "options": [
            {"label": "VIP", "value": "vip", "sort_order": 0},
            {"label": "普通", "value": "normal", "sort_order": 1},
        ],
    }


def _view_payload(group_field_id: int | None = None, name: str | None = None) -> dict:
    return {
        "name": name or _unique("view"),
        "condition_logic": "and",
        "conditions": [],
        "group_field_id": group_field_id,
        "custom_columns_enabled": False,
        "columns_config": [],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Common contract: 404 / no group field / empty-but-configured
# Run for one domain — the same Service code path serves all three.
# ──────────────────────────────────────────────────────────────────────────────


class TestViewGroupsContract:

    @pytest.mark.asyncio
    async def test_user_view_groups_view_not_found_returns_404(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        resp = await client.post(
            "/api/v1/users/views/99999/groups", headers=headers, json={}
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_ticket_view_groups_view_not_found_returns_404(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        resp = await client.post(
            "/api/v1/tickets/views/99999/groups", headers=headers, json={}
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_view_groups_view_not_found_returns_404(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        resp = await client.post(
            "/api/v1/organizations/views/99999/groups", headers=headers, json={}
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_user_view_without_group_field_returns_empty(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        # View with no group_field_id configured
        v_resp = await client.post(
            "/api/v1/user-views", headers=headers, json=_view_payload()
        )
        assert v_resp.status_code == 201
        view_id = v_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/users/views/{view_id}/groups", headers=headers, json={}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["group_field"] is None
        assert body["items"] == []
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_user_view_groups_empty_request_body(self, client: AsyncClient):
        """The endpoint must accept missing/empty body — no client filter is sent."""
        headers = await _setup_tenant_and_auth(client)
        v_resp = await client.post(
            "/api/v1/user-views", headers=headers, json=_view_payload()
        )
        view_id = v_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/users/views/{view_id}/groups", headers=headers
        )
        assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# End-to-end: configure group field, seed data, verify aggregation + null group
# ──────────────────────────────────────────────────────────────────────────────


class TestUserViewGroupsAggregation:

    @pytest.mark.asyncio
    async def test_groups_aggregated_with_null_group(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)

        # Step 1: create a custom select field on the user domain
        field_resp = await client.post(
            "/api/v1/field-definitions",
            headers=headers,
            json=_select_field("user", "VIP等级"),
        )
        assert field_resp.status_code == 201
        field_id = field_resp.json()["id"]

        # Step 2: create the view with this field as group field
        view_resp = await client.post(
            "/api/v1/user-views",
            headers=headers,
            json=_view_payload(group_field_id=field_id),
        )
        assert view_resp.status_code == 201
        view_id = view_resp.json()["id"]

        # Step 3: seed users — 2 vip, 1 normal, 1 with no group field
        for name, value in (("u1", "vip"), ("u2", "vip"), ("u3", "normal")):
            r = await client.post(
                "/api/v1/users",
                headers=headers,
                json={"name": name, "custom_fields": {str(field_id): value}},
            )
            assert r.status_code == 201

        r = await client.post(
            "/api/v1/users",
            headers=headers,
            json={"name": "u4", "custom_fields": {}},
        )
        assert r.status_code == 201

        # Step 4: query groups
        groups_resp = await client.post(
            f"/api/v1/users/views/{view_id}/groups", headers=headers, json={}
        )
        assert groups_resp.status_code == 200
        body = groups_resp.json()

        assert body["group_field"] is not None
        assert body["group_field"]["id"] == field_id
        assert body["group_field"]["field_type"] == "single_select"
        assert body["total"] == 4

        items = body["items"]
        # vip(2) and normal(1) come first sorted by count desc; null group last
        values = [it["value"] for it in items]
        counts = [it["count"] for it in items]
        assert values[0] == "vip"
        assert counts[0] == 2
        assert "normal" in values
        # null group must be last
        assert items[-1]["value"] is None
        assert items[-1]["count"] == 1

    @pytest.mark.asyncio
    async def test_query_with_empty_group_value_filters_null(self, client: AsyncClient):
        """`group_value == "__EMPTY__"` should filter records whose group field is NULL."""
        headers = await _setup_tenant_and_auth(client)

        field_resp = await client.post(
            "/api/v1/field-definitions",
            headers=headers,
            json=_select_field("user", "渠道"),
        )
        field_id = field_resp.json()["id"]

        view_resp = await client.post(
            "/api/v1/user-views",
            headers=headers,
            json=_view_payload(group_field_id=field_id),
        )
        view_id = view_resp.json()["id"]

        # Seed: 1 with field, 2 without
        await client.post(
            "/api/v1/users",
            headers=headers,
            json={"name": "u_with", "custom_fields": {str(field_id): "vip"}},
        )
        await client.post(
            "/api/v1/users",
            headers=headers,
            json={"name": "u_empty1", "custom_fields": {}},
        )
        await client.post(
            "/api/v1/users",
            headers=headers,
            json={"name": "u_empty2", "custom_fields": {}},
        )

        # Filter list by empty group
        list_resp = await client.post(
            "/api/v1/users/query",
            headers=headers,
            json={
                "view_id": view_id,
                "group_value": "__EMPTY__",
                "page": 1,
                "per_page": 20,
            },
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] == 2

        # Filter list by concrete group value
        list_resp_vip = await client.post(
            "/api/v1/users/query",
            headers=headers,
            json={
                "view_id": view_id,
                "group_value": "vip",
                "page": 1,
                "per_page": 20,
            },
        )
        assert list_resp_vip.status_code == 200
        assert list_resp_vip.json()["total"] == 1
