"""
Integration tests for voice flow versions API:
- list versions
- get specific version
- rollback to a version
"""
import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


def _auth(tenant_id: int = 7) -> dict:
    token = create_access_token({"sub": "1", "tenant_id": tenant_id, "roles": ["admin"]})
    return {"Authorization": f"Bearer {token}"}


def _graph(text: str) -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "start", "type": "start", "data": {}},
            {"id": "p1", "type": "play",
             "data": {"prompt": {"kind": "tts", "text": text}}},
            {"id": "h1", "type": "hangup", "data": {"pre_play": None}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "p1", "source_handle": "next"},
            {"id": "e2", "source": "p1", "target": "h1", "source_handle": "next"},
        ],
        "variables": [],
    }


class TestVoiceFlowVersionsAPI:

    @pytest.mark.asyncio
    async def test_list_versions(self, client: AsyncClient):
        headers = _auth()
        c = await client.post("/api/v1/voice-flows", headers=headers,
                              json={"name": f"VF {uuid.uuid4().hex[:6]}"})
        fid = c.json()["id"]
        # Save 2 more versions
        await client.put(f"/api/v1/voice-flows/{fid}", headers=headers,
                         json={"graph_json": _graph("hello")})
        await client.put(f"/api/v1/voice-flows/{fid}", headers=headers,
                         json={"graph_json": _graph("world")})

        r = await client.get(f"/api/v1/voice-flows/{fid}/versions", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["current_version_no"] == 3
        nos = [v["version_no"] for v in body["items"]]
        assert nos[:3] == [3, 2, 1]
        assert body["items"][0]["is_current"] is True

    @pytest.mark.asyncio
    async def test_get_specific_version(self, client: AsyncClient):
        headers = _auth()
        c = await client.post("/api/v1/voice-flows", headers=headers,
                              json={"name": f"VF {uuid.uuid4().hex[:6]}"})
        fid = c.json()["id"]
        await client.put(f"/api/v1/voice-flows/{fid}", headers=headers,
                         json={"graph_json": _graph("hi v2")})

        v1 = await client.get(f"/api/v1/voice-flows/{fid}/versions/1", headers=headers)
        assert v1.status_code == 200
        # v1 is default graph: start only
        assert len(v1.json()["graph_json"]["nodes"]) == 1
        assert v1.json()["is_current"] is False

        v2 = await client.get(f"/api/v1/voice-flows/{fid}/versions/2", headers=headers)
        assert v2.status_code == 200
        nodes = v2.json()["graph_json"]["nodes"]
        play = next(n for n in nodes if n["type"] == "play")
        assert play["data"]["prompt"]["text"] == "hi v2"

    @pytest.mark.asyncio
    async def test_rollback_creates_new_version(self, client: AsyncClient):
        headers = _auth()
        c = await client.post("/api/v1/voice-flows", headers=headers,
                              json={"name": f"VF {uuid.uuid4().hex[:6]}"})
        fid = c.json()["id"]
        await client.put(f"/api/v1/voice-flows/{fid}", headers=headers,
                         json={"graph_json": _graph("snap A")})
        await client.put(f"/api/v1/voice-flows/{fid}", headers=headers,
                         json={"graph_json": _graph("snap B")})
        # Rollback to version 2 (snap A)
        rb = await client.post(f"/api/v1/voice-flows/{fid}/rollback/2", headers=headers)
        assert rb.status_code == 200
        assert rb.json()["current_version_no"] == 4  # new version on top of 3
        play = next(n for n in rb.json()["graph_json"]["nodes"] if n["type"] == "play")
        assert play["data"]["prompt"]["text"] == "snap A"

    @pytest.mark.asyncio
    async def test_rollback_nonexistent_version_404(self, client: AsyncClient):
        headers = _auth()
        c = await client.post("/api/v1/voice-flows", headers=headers,
                              json={"name": f"VF {uuid.uuid4().hex[:6]}"})
        fid = c.json()["id"]
        rb = await client.post(f"/api/v1/voice-flows/{fid}/rollback/99", headers=headers)
        assert rb.status_code == 404
