"""
Integration tests for telephony catalog APIs (/api/v1/sip-trunks, /api/v1/phone-numbers)
Authenticated via X-API-Key header
"""
import uuid

import pytest

from app.configs.settings import settings

API_KEY = settings.TENANT_API_KEY
HEADERS = {"X-API-Key": API_KEY}
TRUNKS = "/api/v1/sip-trunks"
NUMBERS = "/api/v1/phone-numbers"
TENANTS = "/api/v1/tenants"


def _unique(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _phone_number() -> str:
    return f"400{uuid.uuid4().hex[:8]}"


def _trunk_payload(name: str | None = None, **overrides) -> dict:
    trunk_name = name or _unique("trunk")
    payload = {
        "supplier_name": "Test Supplier",
        "trunk_name": trunk_name,
        "trunk_types": ["inbound", "outbound"],
        "remark": "test trunk",
        "status": "enabled",
        "peer_endpoints": [{"ip": "10.0.0.1", "port": 5060}],
    }
    payload.update(overrides)
    return payload


async def _create_tenant(client) -> str:
    resp = await client.post(TENANTS, headers=HEADERS, json={
        "name": _unique("tenant"),
        "admin_username": _unique("adm"),
        "admin_password": "Passw0rd123",
    })
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_missing_api_key(client):
    resp = await client.get(TRUNKS)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_api_key(client):
    resp = await client.get(TRUNKS, headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sip_trunk_crud(client):
    create_resp = await client.post(TRUNKS, headers=HEADERS, json=_trunk_payload())
    assert create_resp.status_code == 201
    body = create_resp.json()
    trunk_id = body["id"]
    assert trunk_id.startswith("trunk_")
    assert body["peer_endpoint_count"] == 1

    get_resp = await client.get(f"{TRUNKS}/{trunk_id}", headers=HEADERS)
    assert get_resp.status_code == 200

    list_resp = await client.get(TRUNKS, headers=HEADERS, params={"q": body["trunk_name"]})
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1

    options_resp = await client.get(f"{TRUNKS}/options", headers=HEADERS)
    assert options_resp.status_code == 200
    option = next(it for it in options_resp.json() if it["id"] == trunk_id)
    assert option["trunk_types"] == ["inbound", "outbound"]

    update_resp = await client.put(
        f"{TRUNKS}/{trunk_id}",
        headers=HEADERS,
        json={**_trunk_payload(body["trunk_name"]), "remark": "updated"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["remark"] == "updated"

    export_resp = await client.get(f"{TRUNKS}/export", headers=HEADERS, params={"q": body["trunk_name"]})
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"].startswith("text/csv")
    assert body["trunk_name"] in export_resp.text

    delete_resp = await client.delete(f"{TRUNKS}/{trunk_id}", headers=HEADERS)
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_sip_trunk_duplicate_name(client):
    name = _unique("dup_trunk")
    await client.post(TRUNKS, headers=HEADERS, json=_trunk_payload(name))
    resp = await client.post(TRUNKS, headers=HEADERS, json=_trunk_payload(name))
    assert resp.status_code == 409
    assert resp.json()["code"] == "DUPLICATE_TRUNK_NAME"


@pytest.mark.asyncio
async def test_phone_number_crud_and_tenant_binding(client):
    trunk_resp = await client.post(TRUNKS, headers=HEADERS, json=_trunk_payload())
    trunk_id = trunk_resp.json()["id"]
    tenant_id = await _create_tenant(client)

    create_resp = await client.post(NUMBERS, headers=HEADERS, json={
        "phone_number": _phone_number(),
        "call_types": ["inbound"],
        "trunk_id": trunk_id,
        "tenant_id": tenant_id,
        "status": "available",
        "remark": "line 1",
    })
    assert create_resp.status_code == 201
    body = create_resp.json()
    phone_id = body["id"]
    assert body["status"] == "assigned"
    assert body["tenant_name"]
    assert body["trunk_name"]

    get_resp = await client.get(f"{NUMBERS}/{phone_id}", headers=HEADERS)
    assert get_resp.status_code == 200

    update_resp = await client.put(
        f"{NUMBERS}/{phone_id}",
        headers=HEADERS,
        json={"tenant_id": None, "status": "available"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["tenant_id"] is None
    assert update_resp.json()["status"] == "available"

    delete_resp = await client.delete(f"{NUMBERS}/{phone_id}", headers=HEADERS)
    assert delete_resp.status_code == 204
    await client.delete(f"{TRUNKS}/{trunk_id}", headers=HEADERS)


@pytest.mark.asyncio
async def test_duplicate_phone_number_409(client):
    number = _phone_number()
    await client.post(NUMBERS, headers=HEADERS, json={
        "phone_number": number,
        "call_types": ["inbound"],
    })
    resp = await client.post(NUMBERS, headers=HEADERS, json={
        "phone_number": number,
        "call_types": ["inbound"],
    })
    assert resp.status_code == 409
    assert resp.json()["code"] == "DUPLICATE_PHONE_NUMBER"


@pytest.mark.asyncio
async def test_assign_disabled_trunk_rejected(client):
    trunk_resp = await client.post(
        TRUNKS,
        headers=HEADERS,
        json=_trunk_payload(status="disabled"),
    )
    trunk_id = trunk_resp.json()["id"]
    resp = await client.post(NUMBERS, headers=HEADERS, json={
        "phone_number": _phone_number(),
        "call_types": ["inbound"],
        "trunk_id": trunk_id,
    })
    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_call_types_must_match_trunk_capabilities(client):
    trunk_resp = await client.post(
        TRUNKS,
        headers=HEADERS,
        json=_trunk_payload(trunk_types=["inbound"]),
    )
    trunk_id = trunk_resp.json()["id"]
    resp = await client.post(NUMBERS, headers=HEADERS, json={
        "phone_number": _phone_number(),
        "call_types": ["outbound"],
        "trunk_id": trunk_id,
    })
    assert resp.status_code == 400
    assert "Call types" in resp.json()["message"]


@pytest.mark.asyncio
async def test_delete_trunk_with_numbers_rejected(client):
    trunk_resp = await client.post(TRUNKS, headers=HEADERS, json=_trunk_payload())
    trunk_id = trunk_resp.json()["id"]
    await client.post(NUMBERS, headers=HEADERS, json={
        "phone_number": _phone_number(),
        "call_types": ["inbound"],
        "trunk_id": trunk_id,
    })
    resp = await client.delete(f"{TRUNKS}/{trunk_id}", headers=HEADERS)
    assert resp.status_code == 409
    assert resp.json()["code"] == "TRUNK_HAS_NUMBERS"


@pytest.mark.asyncio
async def test_phone_number_batch_update(client):
    trunk_resp = await client.post(TRUNKS, headers=HEADERS, json=_trunk_payload())
    trunk_id = trunk_resp.json()["id"]
    ids = []
    for _ in range(2):
        resp = await client.post(NUMBERS, headers=HEADERS, json={
            "phone_number": _phone_number(),
            "call_types": ["inbound"],
        })
        ids.append(resp.json()["id"])

    batch_resp = await client.post(
        f"{NUMBERS}/batch-update",
        headers=HEADERS,
        json={"ids": ids, "trunk_id": trunk_id, "call_types": ["inbound"]},
    )
    assert batch_resp.status_code == 200
    body = batch_resp.json()
    assert body["success_count"] == 2
    assert body["fail_count"] == 0

    for pid in ids:
        await client.delete(f"{NUMBERS}/{pid}", headers=HEADERS)
    await client.delete(f"{TRUNKS}/{trunk_id}", headers=HEADERS)


@pytest.mark.asyncio
async def test_phone_number_batch_update_partial_failure(client):
    tenant_id = await _create_tenant(client)

    ok_resp = await client.post(NUMBERS, headers=HEADERS, json={
        "phone_number": _phone_number(),
        "call_types": ["inbound"],
    })
    ok_id = ok_resp.json()["id"]

    bad_resp = await client.post(NUMBERS, headers=HEADERS, json={
        "phone_number": _phone_number(),
        "call_types": ["inbound"],
        "status": "disabled",
    })
    bad_id = bad_resp.json()["id"]

    batch_resp = await client.post(
        f"{NUMBERS}/batch-update",
        headers=HEADERS,
        json={"ids": [ok_id, bad_id], "tenant_id": tenant_id},
    )
    assert batch_resp.status_code == 200
    body = batch_resp.json()
    assert body["success_count"] == 1
    assert body["fail_count"] == 1

    ok_get = await client.get(f"{NUMBERS}/{ok_id}", headers=HEADERS)
    assert ok_get.status_code == 200
    assert ok_get.json()["tenant_id"] == tenant_id
    assert ok_get.json()["status"] == "assigned"

    bad_get = await client.get(f"{NUMBERS}/{bad_id}", headers=HEADERS)
    assert bad_get.status_code == 200
    assert bad_get.json()["tenant_id"] is None
    assert bad_get.json()["status"] == "disabled"

    await client.delete(f"{NUMBERS}/{ok_id}", headers=HEADERS)
    await client.delete(f"{NUMBERS}/{bad_id}", headers=HEADERS)


@pytest.mark.asyncio
async def test_phone_number_outbound_fields_create_and_update(client):
    create_resp = await client.post(NUMBERS, headers=HEADERS, json={
        "phone_number": _phone_number(),
        "call_types": ["outbound"],
        "concurrency": 10,
        "called_number_prefix": "021",
        "outbound_time_slots": [
            {"start": "8:30", "end": "12:30"},
            {"start": "13:30", "end": "20:30"},
        ],
    })
    assert create_resp.status_code == 201
    body = create_resp.json()
    phone_id = body["id"]
    assert body["concurrency"] == 10
    assert body["called_number_prefix"] == "021"
    assert body["outbound_time_slots"] == [
        {"start": "08:30", "end": "12:30"},
        {"start": "13:30", "end": "20:30"},
    ]

    update_resp = await client.put(
        f"{NUMBERS}/{phone_id}",
        headers=HEADERS,
        json={
            "concurrency": 20,
            "called_number_prefix": "010",
            "outbound_time_slots": [{"start": "09:00", "end": "18:00"}],
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["concurrency"] == 20
    assert updated["called_number_prefix"] == "010"
    assert updated["outbound_time_slots"] == [{"start": "09:00", "end": "18:00"}]

    await client.delete(f"{NUMBERS}/{phone_id}", headers=HEADERS)


@pytest.mark.asyncio
async def test_phone_number_outbound_time_slots_validation(client):
    resp = await client.post(NUMBERS, headers=HEADERS, json={
        "phone_number": _phone_number(),
        "call_types": ["outbound"],
        "outbound_time_slots": [
            {"start": "08:30", "end": "12:30"},
            {"start": "12:00", "end": "20:30"},
        ],
    })
    assert resp.status_code == 422

    resp = await client.post(NUMBERS, headers=HEADERS, json={
        "phone_number": _phone_number(),
        "call_types": ["outbound"],
        "outbound_time_slots": [{"start": "18:00", "end": "08:00"}],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_assign_tenant_to_disabled_phone_rejected(client):
    create_resp = await client.post(NUMBERS, headers=HEADERS, json={
        "phone_number": _phone_number(),
        "call_types": ["inbound"],
        "status": "disabled",
    })
    phone_id = create_resp.json()["id"]
    tenant_id = await _create_tenant(client)

    resp = await client.put(
        f"{NUMBERS}/{phone_id}",
        headers=HEADERS,
        json={"tenant_id": tenant_id},
    )
    assert resp.status_code == 400
    assert "disabled" in resp.json()["message"].lower()

    await client.delete(f"{NUMBERS}/{phone_id}", headers=HEADERS)
