"""
Integration tests for InboundRoutingRule API
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


class TestInboundRoutingRulesAPI:

    @pytest.mark.asyncio
    async def test_crud_and_reorder(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)

        sh = await client.post("/api/v1/service-hours", headers=headers, json=_sh_payload())
        assert sh.status_code == 201
        sh_id = sh.json()["id"]

        vf = await client.post(
            "/api/v1/voice-flows",
            headers=headers,
            json={"name": f"Target {uuid.uuid4().hex[:8]}", "enabled": True},
        )
        assert vf.status_code == 201
        vf_id = vf.json()["id"]

        r1 = await client.post(
            "/api/v1/inbound-routing-rules",
            headers=headers,
            json={
                "name": f"Rule 1 {uuid.uuid4().hex[:8]}",
                "enabled": True,
                "conditions": [{"condition_type": "caller_number", "operator": "eq", "value": "10086"}],
                "target_voice_flow_id": vf_id,
            },
        )
        assert r1.status_code == 201
        id1 = r1.json()["id"]
        assert r1.json()["priority"] == 1

        r2 = await client.post(
            "/api/v1/inbound-routing-rules",
            headers=headers,
            json={
                "name": f"Rule 2 {uuid.uuid4().hex[:8]}",
                "enabled": True,
                "conditions": [],
                "target_voice_flow_id": vf_id,
            },
        )
        assert r2.status_code == 201
        id2 = r2.json()["id"]
        assert r2.json()["priority"] == 2

        reorder = await client.put(
            "/api/v1/inbound-routing-rules/reorder",
            headers=headers,
            json={"ordered_ids": [id2, id1]},
        )
        assert reorder.status_code == 200

        lst = await client.get("/api/v1/inbound-routing-rules", headers=headers)
        assert lst.status_code == 200
        items = lst.json()["items"]
        assert items[0]["id"] == id2
        assert items[0]["priority"] == 1
        assert items[1]["id"] == id1
        assert items[1]["priority"] == 2

        patch = await client.patch(
            f"/api/v1/inbound-routing-rules/{id1}",
            headers=headers,
            json={"enabled": False},
        )
        assert patch.status_code == 200
        assert patch.json()["enabled"] is False

        g = await client.get(f"/api/v1/inbound-routing-rules/{id2}", headers=headers)
        assert g.status_code == 200
        assert "Target" in (g.json().get("target_flow_name") or "")

        dl = await client.delete(f"/api/v1/inbound-routing-rules/{id1}", headers=headers)
        assert dl.status_code == 200

        bad_reorder = await client.put(
            "/api/v1/inbound-routing-rules/reorder",
            headers=headers,
            json={"ordered_ids": [id1, id2]},
        )
        assert bad_reorder.status_code == 400

    @pytest.mark.asyncio
    async def test_call_time_condition_validates_service_hours(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)

        sh = await client.post("/api/v1/service-hours", headers=headers, json=_sh_payload())
        sh_id = sh.json()["id"]

        vf = await client.post(
            "/api/v1/voice-flows",
            headers=headers,
            json={"name": f"T {uuid.uuid4().hex[:8]}", "enabled": True},
        )
        vf_id = vf.json()["id"]

        bad = await client.post(
            "/api/v1/inbound-routing-rules",
            headers=headers,
            json={
                "name": "Bad",
                "target_voice_flow_id": vf_id,
                "conditions": [
                    {"condition_type": "call_time", "operator": "in_schedule", "value": "999999"}
                ],
            },
        )
        assert bad.status_code == 400

        ok = await client.post(
            "/api/v1/inbound-routing-rules",
            headers=headers,
            json={
                "name": "Ok",
                "target_voice_flow_id": vf_id,
                "conditions": [
                    {"condition_type": "call_time", "operator": "in_schedule", "value": str(sh_id)}
                ],
            },
        )
        assert ok.status_code == 201
