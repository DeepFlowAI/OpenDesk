"""
Integration tests for SessionRoutingRule API
"""
import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


def _make_token(tenant_id: int = 7, role: str = "admin") -> str:
    return create_access_token({"sub": "1", "tenant_id": tenant_id, "roles": [role]})


def _auth_header(tenant_id: int = 7) -> dict:
    return {"Authorization": f"Bearer {_make_token(tenant_id)}"}


def _sh_payload() -> dict:
    u = uuid.uuid4().hex[:8]
    return {
        "name": f"Biz hours {u}",
        "description": "x",
        "weekly_schedules": [
            {"day_of_week": 1, "slots": [{"start": "09:00", "end": "18:00"}]},
        ],
        "holidays": [],
        "makeup_days": [],
    }


async def _create_employee_group(client: AsyncClient, headers: dict) -> int:
    resp = await client.post(
        "/api/v1/employee-groups",
        headers=headers,
        json={
            "name": f"Group {uuid.uuid4().hex[:8]}",
            "description": "test group",
            "member_ids": [],
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestSessionRoutingRulesAPI:

    @pytest.mark.asyncio
    async def test_crud_and_reorder(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        group_id = await _create_employee_group(client, headers)

        r1 = await client.post(
            "/api/v1/session-routing-rules",
            headers=headers,
            json={
                "name": f"SR Rule 1 {uuid.uuid4().hex[:8]}",
                "enabled": True,
                "conditions": [{"condition_type": "channel", "operator": "eq", "value": "websdk"}],
                "target_group_id": group_id,
            },
        )
        assert r1.status_code == 201
        id1 = r1.json()["id"]
        assert r1.json()["priority"] == 1

        r2 = await client.post(
            "/api/v1/session-routing-rules",
            headers=headers,
            json={
                "name": f"SR Rule 2 {uuid.uuid4().hex[:8]}",
                "enabled": True,
                "conditions": [],
                "target_group_id": group_id,
            },
        )
        assert r2.status_code == 201
        id2 = r2.json()["id"]
        assert r2.json()["priority"] == 2

        reorder = await client.put(
            "/api/v1/session-routing-rules/reorder",
            headers=headers,
            json={"ordered_ids": [id2, id1]},
        )
        assert reorder.status_code == 200

        lst = await client.get("/api/v1/session-routing-rules", headers=headers)
        assert lst.status_code == 200
        items = lst.json()["items"]
        assert items[0]["id"] == id2
        assert items[0]["priority"] == 1
        assert items[1]["id"] == id1
        assert items[1]["priority"] == 2

        patch = await client.patch(
            f"/api/v1/session-routing-rules/{id1}",
            headers=headers,
            json={"enabled": False},
        )
        assert patch.status_code == 200
        assert patch.json()["enabled"] is False

        g = await client.get(f"/api/v1/session-routing-rules/{id2}", headers=headers)
        assert g.status_code == 200
        assert g.json()["target_group_name"] != ""

        upd = await client.put(
            f"/api/v1/session-routing-rules/{id1}",
            headers=headers,
            json={
                "name": "Updated name",
                "enabled": True,
                "conditions": [],
                "target_group_id": group_id,
            },
        )
        assert upd.status_code == 200
        assert upd.json()["name"] == "Updated name"

        dl = await client.delete(f"/api/v1/session-routing-rules/{id1}", headers=headers)
        assert dl.status_code == 200

        bad_reorder = await client.put(
            "/api/v1/session-routing-rules/reorder",
            headers=headers,
            json={"ordered_ids": [id1, id2]},
        )
        assert bad_reorder.status_code == 400

    @pytest.mark.asyncio
    async def test_current_time_condition_validates_service_hours(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        group_id = await _create_employee_group(client, headers)

        sh = await client.post("/api/v1/service-hours", headers=headers, json=_sh_payload())
        sh_id = sh.json()["id"]

        bad = await client.post(
            "/api/v1/session-routing-rules",
            headers=headers,
            json={
                "name": "Bad time cond",
                "target_group_id": group_id,
                "conditions": [
                    {"condition_type": "current_time", "operator": "in_schedule", "value": "999999"}
                ],
            },
        )
        assert bad.status_code == 400

        ok = await client.post(
            "/api/v1/session-routing-rules",
            headers=headers,
            json={
                "name": "Ok time cond",
                "target_group_id": group_id,
                "conditions": [
                    {"condition_type": "current_time", "operator": "in_schedule", "value": str(sh_id)}
                ],
            },
        )
        assert ok.status_code == 201

    @pytest.mark.asyncio
    async def test_channel_condition(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        group_id = await _create_employee_group(client, headers)

        ok = await client.post(
            "/api/v1/session-routing-rules",
            headers=headers,
            json={
                "name": "Channel eq web",
                "target_group_id": group_id,
                "conditions": [
                    {"condition_type": "channel", "operator": "eq", "value": "websdk"}
                ],
            },
        )
        assert ok.status_code == 201

        bad_val = await client.post(
            "/api/v1/session-routing-rules",
            headers=headers,
            json={
                "name": "Bad channel val",
                "target_group_id": group_id,
                "conditions": [
                    {"condition_type": "channel", "operator": "eq", "value": "unknown"}
                ],
            },
        )
        assert bad_val.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_target_group(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)

        resp = await client.post(
            "/api/v1/session-routing-rules",
            headers=headers,
            json={
                "name": "Bad group",
                "target_group_id": 999999,
                "conditions": [],
            },
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_get_not_found(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        resp = await client.get("/api/v1/session-routing-rules/999999", headers=headers)
        assert resp.status_code == 404
