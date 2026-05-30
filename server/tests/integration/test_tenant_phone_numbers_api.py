"""
Integration tests for tenant admin phone numbers (/api/v1/call-center/phone-numbers)
"""
import uuid

import pytest

from app.configs.settings import settings

API_KEY = settings.TENANT_API_KEY
PLATFORM_HEADERS = {"X-API-Key": API_KEY}
PLATFORM_NUMBERS = "/api/v1/phone-numbers"
PLATFORM_TENANTS = "/api/v1/tenants"
ADMIN_NUMBERS = "/api/v1/call-center/phone-numbers"


def _unique(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _phone_number() -> str:
    return f"400{uuid.uuid4().hex[:8]}"


async def _create_tenant(client, admin_username: str | None = None) -> tuple[str, str]:
    username = admin_username or _unique("adm")
    create_resp = await client.post(PLATFORM_TENANTS, headers=PLATFORM_HEADERS, json={
        "name": _unique("tenant"),
        "admin_username": username,
        "admin_password": "Passw0rd123",
    })
    assert create_resp.status_code == 201
    return create_resp.json()["id"], username


async def _admin_headers(client, tenant_string_id: str, username: str) -> dict:
    login_resp = await client.post("/api/v1/auth/login", json={
        "tenant": tenant_string_id,
        "username": username,
        "password": "Passw0rd123",
    })
    assert login_resp.status_code == 200
    return {"Authorization": f"Bearer {login_resp.json()['access_token']}"}


async def _create_assigned_number(client, tenant_string_id: str, **overrides) -> str:
    payload = {
        "phone_number": _phone_number(),
        "call_types": ["inbound"],
        "tenant_id": tenant_string_id,
    }
    payload.update(overrides)
    create_number = await client.post(PLATFORM_NUMBERS, headers=PLATFORM_HEADERS, json=payload)
    assert create_number.status_code == 201
    return create_number.json()["id"]


@pytest.mark.asyncio
async def test_tenant_phone_number_list_and_tags(client):
    tenant_string_id, admin_username = await _create_tenant(client)
    headers = await _admin_headers(client, tenant_string_id, admin_username)
    phone_id = await _create_assigned_number(
        client,
        tenant_string_id,
        call_types=["outbound"],
        outbound_time_slots=[
            {"start": "08:30", "end": "12:30"},
            {"start": "13:30", "end": "20:30"},
        ],
    )
    number_resp = await client.get(f"{PLATFORM_NUMBERS}/{phone_id}", headers=PLATFORM_HEADERS)
    number = number_resp.json()["phone_number"]

    list_resp = await client.get(ADMIN_NUMBERS, headers=headers)
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] >= 1
    assert any(item["id"] == phone_id for item in body["items"])

    detail_resp = await client.get(f"{ADMIN_NUMBERS}/{phone_id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["tags"] == []
    assert detail_resp.json()["outbound_time_slots"] == [
        {"start": "08:30", "end": "12:30"},
        {"start": "13:30", "end": "20:30"},
    ]

    listed = next(item for item in body["items"] if item["id"] == phone_id)
    assert listed["outbound_time_slots"] == [
        {"start": "08:30", "end": "12:30"},
        {"start": "13:30", "end": "20:30"},
    ]

    update_resp = await client.put(
        f"{ADMIN_NUMBERS}/{phone_id}/tags",
        headers=headers,
        json={"tags": ["客服热线", "IVR"]},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["tags"] == ["客服热线", "IVR"]

    search_resp = await client.get(
        ADMIN_NUMBERS,
        headers=headers,
        params={"q": number[-4:]},
    )
    assert search_resp.status_code == 200
    assert search_resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_tenant_phone_number_cross_tenant_access_denied(client):
    tenant_a, admin_a = await _create_tenant(client)
    tenant_b, admin_b = await _create_tenant(client)
    headers_a = await _admin_headers(client, tenant_a, admin_a)
    headers_b = await _admin_headers(client, tenant_b, admin_b)
    phone_id = await _create_assigned_number(client, tenant_a)

    get_resp = await client.get(f"{ADMIN_NUMBERS}/{phone_id}", headers=headers_b)
    assert get_resp.status_code == 404

    put_resp = await client.put(
        f"{ADMIN_NUMBERS}/{phone_id}/tags",
        headers=headers_b,
        json={"tags": ["blocked"]},
    )
    assert put_resp.status_code == 404

    list_b = await client.get(ADMIN_NUMBERS, headers=headers_b)
    assert list_b.status_code == 200
    assert not any(item["id"] == phone_id for item in list_b.json()["items"])

    list_a = await client.get(ADMIN_NUMBERS, headers=headers_a)
    assert any(item["id"] == phone_id for item in list_a.json()["items"])


@pytest.mark.asyncio
async def test_tenant_phone_number_tag_validation(client):
    tenant_string_id, admin_username = await _create_tenant(client)
    headers = await _admin_headers(client, tenant_string_id, admin_username)
    phone_id = await _create_assigned_number(client, tenant_string_id)

    too_long = "x" * 33
    resp = await client.put(
        f"{ADMIN_NUMBERS}/{phone_id}/tags",
        headers=headers,
        json={"tags": [too_long]},
    )
    assert resp.status_code == 422

    too_many = [f"tag{i}" for i in range(21)]
    resp = await client.put(
        f"{ADMIN_NUMBERS}/{phone_id}/tags",
        headers=headers,
        json={"tags": too_many},
    )
    assert resp.status_code == 422

    resp = await client.put(
        f"{ADMIN_NUMBERS}/{phone_id}/tags",
        headers=headers,
        json={"tags": ["A", "a"]},
    )
    assert resp.status_code == 422

    resp = await client.put(
        f"{ADMIN_NUMBERS}/{phone_id}/tags",
        headers=headers,
        json={"tags": ["  ", ""]},
    )
    assert resp.status_code == 200
    assert resp.json()["tags"] == []

    missing = await client.get(f"{ADMIN_NUMBERS}/pn_missing_{uuid.uuid4().hex[:8]}", headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_unassigned_phone_number_hidden_from_tenant_admin(client):
    tenant_string_id, admin_username = await _create_tenant(client)
    headers = await _admin_headers(client, tenant_string_id, admin_username)
    unassigned_resp = await client.post(PLATFORM_NUMBERS, headers=PLATFORM_HEADERS, json={
        "phone_number": _phone_number(),
        "call_types": ["inbound"],
    })
    assert unassigned_resp.status_code == 201
    phone_id = unassigned_resp.json()["id"]

    list_resp = await client.get(ADMIN_NUMBERS, headers=headers)
    assert list_resp.status_code == 200
    assert not any(item["id"] == phone_id for item in list_resp.json()["items"])

    detail_resp = await client.get(f"{ADMIN_NUMBERS}/{phone_id}", headers=headers)
    assert detail_resp.status_code == 404

    await client.delete(f"{PLATFORM_NUMBERS}/{phone_id}", headers=PLATFORM_HEADERS)
