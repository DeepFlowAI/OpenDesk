"""
Integration tests for VoiceFlow API — basic CRUD + graph versioning +
/validate + /system-variables endpoints.
"""
import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


def _make_token(tenant_id: int = 7, role: str = "admin") -> str:
    return create_access_token({"sub": "1", "tenant_id": tenant_id, "roles": [role]})


def _auth_header(tenant_id: int = 7) -> dict:
    return {"Authorization": f"Bearer {_make_token(tenant_id)}"}


def _start_play_hangup_graph() -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "start", "type": "start", "data": {}},
            {"id": "p1", "type": "play",
             "data": {"prompt": {"kind": "tts", "text": "hi"}}},
            {"id": "h1", "type": "hangup", "data": {"pre_play": None}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "p1", "source_handle": "next"},
            {"id": "e2", "source": "p1", "target": "h1", "source_handle": "next"},
        ],
        "variables": [],
    }


class TestVoiceFlowsAPI:

    @pytest.mark.asyncio
    async def test_list_empty_returns_200(self, client: AsyncClient):
        headers = _auth_header(tenant_id=99999)
        resp = await client.get("/api/v1/voice-flows", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_create_seeds_v1_default_graph(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        name = f"Default IVR {uuid.uuid4().hex[:8]}"
        c = await client.post(
            "/api/v1/voice-flows",
            headers=headers,
            json={"name": name, "description": "demo"},
        )
        assert c.status_code == 201
        body = c.json()
        assert body["name"] == name
        assert body["description"] == "demo"
        assert body["current_version_no"] == 1
        # Default graph is a single start node
        assert body["graph_json"]["nodes"][0]["type"] == "start"

    @pytest.mark.asyncio
    async def test_create_and_get_select(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        name = f"Default IVR {uuid.uuid4().hex[:8]}"
        c = await client.post(
            "/api/v1/voice-flows", headers=headers, json={"name": name},
        )
        assert c.status_code == 201
        fid = c.json()["id"]

        sel = await client.get("/api/v1/voice-flows/select", headers=headers)
        assert sel.status_code == 200
        items = sel.json()["items"]
        assert any(x["id"] == fid for x in items)

        one = await client.get(f"/api/v1/voice-flows/{fid}", headers=headers)
        assert one.status_code == 200
        assert one.json()["name"] == name

    @pytest.mark.asyncio
    async def test_metadata_update_does_not_bump_version(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        c = await client.post(
            "/api/v1/voice-flows", headers=headers,
            json={"name": f"Flow A {uuid.uuid4().hex[:8]}"},
        )
        fid = c.json()["id"]
        u = await client.put(
            f"/api/v1/voice-flows/{fid}", headers=headers,
            json={"name": "Flow A2", "enabled": False, "description": "x"},
        )
        assert u.status_code == 200
        assert u.json()["enabled"] is False
        assert u.json()["current_version_no"] == 1

    @pytest.mark.asyncio
    async def test_update_with_graph_bumps_version(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        c = await client.post(
            "/api/v1/voice-flows", headers=headers,
            json={"name": f"VF {uuid.uuid4().hex[:6]}"},
        )
        fid = c.json()["id"]

        u = await client.put(
            f"/api/v1/voice-flows/{fid}",
            headers=headers,
            json={"graph_json": _start_play_hangup_graph()},
        )
        assert u.status_code == 200, u.text
        assert u.json()["current_version_no"] == 2

        # Saving again bumps version
        u2 = await client.put(
            f"/api/v1/voice-flows/{fid}",
            headers=headers,
            json={"graph_json": _start_play_hangup_graph()},
        )
        assert u2.json()["current_version_no"] == 3

    @pytest.mark.asyncio
    async def test_update_rejects_graph_missing_outlet(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        c = await client.post(
            "/api/v1/voice-flows", headers=headers,
            json={"name": f"VF {uuid.uuid4().hex[:6]}"},
        )
        fid = c.json()["id"]

        bad = {
            "version": 1,
            "nodes": [
                {"id": "start", "type": "start", "data": {}},
                {"id": "p1", "type": "play",
                 "data": {"prompt": {"kind": "tts", "text": "x"}}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "p1", "source_handle": "next"},
            ],
            "variables": [],
        }
        u = await client.put(
            f"/api/v1/voice-flows/{fid}", headers=headers,
            json={"graph_json": bad},
        )
        assert u.status_code == 400
        codes = {e["code"] for e in u.json()["details"]["errors"]}
        assert "missing_next_edge" in codes

    @pytest.mark.asyncio
    async def test_validate_endpoint_ok_and_errors(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        c = await client.post(
            "/api/v1/voice-flows", headers=headers,
            json={"name": f"VF {uuid.uuid4().hex[:6]}"},
        )
        fid = c.json()["id"]
        ok = await client.post(
            f"/api/v1/voice-flows/{fid}/validate",
            headers=headers,
            json={"graph_json": _start_play_hangup_graph()},
        )
        assert ok.status_code == 200
        assert ok.json()["ok"] is True

        bad = {
            "version": 1,
            "nodes": [
                {"id": "start", "type": "start", "data": {}},
                {"id": "p1", "type": "play",
                 "data": {"prompt": {"kind": "tts", "text": "x"}}},
            ],
            "edges": [],
            "variables": [],
        }
        v = await client.post(
            f"/api/v1/voice-flows/{fid}/validate",
            headers=headers,
            json={"graph_json": bad},
        )
        assert v.status_code == 200
        body = v.json()
        assert body["ok"] is False
        assert any(e["code"] == "missing_next_edge" for e in body["errors"])

    @pytest.mark.asyncio
    async def test_validate_phantom_queue_rejected(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        c = await client.post(
            "/api/v1/voice-flows", headers=headers,
            json={"name": f"VF {uuid.uuid4().hex[:6]}"},
        )
        fid = c.json()["id"]
        graph = {
            "version": 1,
            "nodes": [
                {"id": "start", "type": "start", "data": {}},
                {"id": "q1", "type": "assign_queue",
                 "data": {"employee_group_id": 999999, "timeout_seconds": 30}},
                {"id": "h1", "type": "hangup", "data": {"pre_play": None}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "q1", "source_handle": "next"},
                {"id": "e2", "source": "q1", "target": "h1", "source_handle": "next"},
            ],
            "variables": [],
        }
        v = await client.post(
            f"/api/v1/voice-flows/{fid}/validate",
            headers=headers, json={"graph_json": graph},
        )
        assert v.status_code == 200
        codes = {e["code"] for e in v.json()["errors"]}
        assert "queue_not_found" in codes

    @pytest.mark.asyncio
    async def test_validate_phantom_employee_queue_rejected(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        c = await client.post(
            "/api/v1/voice-flows", headers=headers,
            json={"name": f"VF {uuid.uuid4().hex[:6]}"},
        )
        fid = c.json()["id"]
        graph = {
            "version": 1,
            "nodes": [
                {"id": "start", "type": "start", "data": {}},
                {
                    "id": "q1",
                    "type": "assign_queue",
                    "data": {
                        "target_strategy": "least_waiting_count",
                        "queue_targets": [{"queue_type": "employee", "queue_id": 999999}],
                        "timeout_seconds": 30,
                    },
                },
                {"id": "h1", "type": "hangup", "data": {"pre_play": None}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "q1", "source_handle": "next"},
                {"id": "e2", "source": "q1", "target": "h1", "source_handle": "timeout"},
            ],
            "variables": [],
        }
        v = await client.post(
            f"/api/v1/voice-flows/{fid}/validate",
            headers=headers, json={"graph_json": graph},
        )
        assert v.status_code == 200
        codes = {e["code"] for e in v.json()["errors"]}
        assert "queue_not_found" in codes

    @pytest.mark.asyncio
    async def test_system_variables_endpoint(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        r = await client.get("/api/v1/voice-flows/system-variables", headers=headers)
        assert r.status_code == 200
        names = {i["name"] for i in r.json()["items"]}
        assert {
            "sys.caller_number",
            "sys.called_number",
            "sys.current_time",
            "sys.assign_queue_status",
            "sys.assign_queue_limit_reason",
        } <= names

    @pytest.mark.asyncio
    async def test_soft_delete_removes_from_select(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        c = await client.post(
            "/api/v1/voice-flows", headers=headers,
            json={"name": f"Flow {uuid.uuid4().hex[:8]}"},
        )
        fid = c.json()["id"]
        d = await client.delete(f"/api/v1/voice-flows/{fid}", headers=headers)
        assert d.status_code == 200
        sel = await client.get("/api/v1/voice-flows/select", headers=headers)
        ids = [x["id"] for x in sel.json()["items"]]
        assert fid not in ids
