"""
Integration tests for the Tenant Platform API (/api/v1/tenants)
Authenticated via X-API-Key header
"""
import pytest
import uuid

from app.configs.settings import settings

API_KEY = settings.TENANT_API_KEY
HEADERS = {"X-API-Key": API_KEY}
BASE = "/api/v1/tenants"


def _unique(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ── Auth ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_api_key(client):
    resp = await client.get(BASE)
    assert resp.status_code == 422  # missing required header


@pytest.mark.asyncio
async def test_invalid_api_key(client):
    resp = await client.get(BASE, headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


# ── Create ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_tenant(client):
    name = _unique("tenant")
    resp = await client.post(BASE, headers=HEADERS, json={
        "name": name,
        "admin_username": "admin_user",
        "admin_password": "Passw0rd123",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == name
    assert body["status"] == "enabled"
    assert body["admin_username"] == "admin_user"
    assert body["id"]
    assert "password" not in body


@pytest.mark.asyncio
async def test_create_tenant_with_remark(client):
    name = _unique("tenant")
    resp = await client.post(BASE, headers=HEADERS, json={
        "name": name,
        "remark": "test remark",
        "admin_username": "admin_r",
        "admin_password": "Passw0rd123",
    })
    assert resp.status_code == 201
    assert resp.json()["remark"] == "test remark"


@pytest.mark.asyncio
async def test_create_tenant_duplicate_name(client):
    name = _unique("tenant")
    await client.post(BASE, headers=HEADERS, json={
        "name": name,
        "admin_username": "adm1",
        "admin_password": "Passw0rd123",
    })
    resp = await client.post(BASE, headers=HEADERS, json={
        "name": name,
        "admin_username": "adm2",
        "admin_password": "Passw0rd123",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_tenant_validation_error(client):
    resp = await client.post(BASE, headers=HEADERS, json={
        "name": "",
        "admin_username": "ab",
        "admin_password": "short",
    })
    assert resp.status_code == 422


# ── List ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tenants(client):
    name = _unique("tenant")
    await client.post(BASE, headers=HEADERS, json={
        "name": name,
        "admin_username": "adm_list",
        "admin_password": "Passw0rd123",
    })
    resp = await client.get(BASE, headers=HEADERS, params={"page": 1, "per_page": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "per_page" in body
    assert "pages" in body
    assert body["total"] >= 1


# ── Get Detail ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_tenant(client):
    name = _unique("tenant")
    create_resp = await client.post(BASE, headers=HEADERS, json={
        "name": name,
        "admin_username": "adm_get",
        "admin_password": "Passw0rd123",
    })
    tid = create_resp.json()["id"]

    resp = await client.get(f"{BASE}/{tid}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == tid
    assert resp.json()["name"] == name


@pytest.mark.asyncio
async def test_get_tenant_not_found(client):
    resp = await client.get(f"{BASE}/nonexistent_id_999", headers=HEADERS)
    assert resp.status_code == 404


# ── Update ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_tenant(client):
    name = _unique("tenant")
    create_resp = await client.post(BASE, headers=HEADERS, json={
        "name": name,
        "admin_username": "adm_upd",
        "admin_password": "Passw0rd123",
    })
    tid = create_resp.json()["id"]

    new_name = _unique("updated")
    resp = await client.put(f"{BASE}/{tid}", headers=HEADERS, json={
        "name": new_name,
        "remark": "updated remark",
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == new_name
    assert resp.json()["remark"] == "updated remark"


@pytest.mark.asyncio
async def test_update_admin_password(client):
    name = _unique("tenant")
    create_resp = await client.post(BASE, headers=HEADERS, json={
        "name": name,
        "admin_username": "adm_pwd",
        "admin_password": "Passw0rd123",
    })
    tid = create_resp.json()["id"]

    resp = await client.put(f"{BASE}/{tid}", headers=HEADERS, json={
        "admin_password": "NewPassw0rd456",
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_admin_username(client):
    name = _unique("tenant")
    create_resp = await client.post(BASE, headers=HEADERS, json={
        "name": name,
        "admin_username": "adm_old",
        "admin_password": "Passw0rd123",
    })
    tid = create_resp.json()["id"]

    resp = await client.put(f"{BASE}/{tid}", headers=HEADERS, json={
        "admin_username": "adm_new",
    })
    assert resp.status_code == 200
    assert resp.json()["admin_username"] == "adm_new"


# ── Status Toggle ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_toggle_status(client):
    name = _unique("tenant")
    create_resp = await client.post(BASE, headers=HEADERS, json={
        "name": name,
        "admin_username": "adm_st",
        "admin_password": "Passw0rd123",
    })
    tid = create_resp.json()["id"]

    resp = await client.patch(f"{BASE}/{tid}/status", headers=HEADERS, json={
        "status": "disabled",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"

    resp = await client.patch(f"{BASE}/{tid}/status", headers=HEADERS, json={
        "status": "enabled",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "enabled"


@pytest.mark.asyncio
async def test_toggle_status_invalid(client):
    name = _unique("tenant")
    create_resp = await client.post(BASE, headers=HEADERS, json={
        "name": name,
        "admin_username": "adm_inv",
        "admin_password": "Passw0rd123",
    })
    tid = create_resp.json()["id"]

    resp = await client.patch(f"{BASE}/{tid}/status", headers=HEADERS, json={
        "status": "unknown",
    })
    assert resp.status_code == 422
