"""
Integration tests for welcome message rules.
"""
import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


def _make_token(tenant_id: int = 7, role: str = "admin") -> str:
    return create_access_token({"sub": "1", "tenant_id": tenant_id, "roles": [role]})


def _auth_header(tenant_id: int = 7) -> dict:
    return {"Authorization": f"Bearer {_make_token(tenant_id)}"}


async def _create_channel(client: AsyncClient, headers: dict, name: str | None = None) -> dict:
    resp = await client.post(
        "/api/v1/channels",
        headers=headers,
        json={"name": name or f"Web SDK {uuid.uuid4().hex[:8]}", "channel_type": "web"},
    )
    assert resp.status_code == 201
    return resp.json()


def _rule_payload(name: str, content: str, conditions: list[dict] | None = None) -> dict:
    return {
        "name": name,
        "enabled": True,
        "conditions": conditions or [],
        "content": content,
    }


class TestWelcomeMessageRulesAPI:
    @pytest.mark.asyncio
    async def test_crud_reorder_toggle_and_delete(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        channel = await _create_channel(client, headers)

        r1 = await client.post(
            "/api/v1/conversation-settings/welcome-rules",
            headers=headers,
            json=_rule_payload(
                f"Welcome 1 {uuid.uuid4().hex[:8]}",
                "<p>Hello one</p>",
                [{"condition_type": "web_sdk", "operator": "eq", "value": str(channel["id"])}],
            ),
        )
        assert r1.status_code == 201
        id1 = r1.json()["id"]
        assert r1.json()["conditions"][0]["value"] == str(channel["id"])

        r2 = await client.post(
            "/api/v1/conversation-settings/welcome-rules",
            headers=headers,
            json=_rule_payload(f"Welcome 2 {uuid.uuid4().hex[:8]}", "<p>Hello fallback</p>"),
        )
        assert r2.status_code == 201
        id2 = r2.json()["id"]

        reorder = await client.put(
            "/api/v1/conversation-settings/welcome-rules/reorder",
            headers=headers,
            json={"ordered_ids": [id2, id1]},
        )
        assert reorder.status_code == 200

        lst = await client.get("/api/v1/conversation-settings/welcome-rules", headers=headers)
        assert lst.status_code == 200
        ids = [item["id"] for item in lst.json()["items"]]
        assert ids.index(id2) < ids.index(id1)

        patch = await client.patch(
            f"/api/v1/conversation-settings/welcome-rules/{id1}",
            headers=headers,
            json={"enabled": False},
        )
        assert patch.status_code == 200
        assert patch.json()["enabled"] is False

        get_resp = await client.get(f"/api/v1/conversation-settings/welcome-rules/{id2}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["content"] == "<p>Hello fallback</p>"

        update = await client.put(
            f"/api/v1/conversation-settings/welcome-rules/{id2}",
            headers=headers,
            json=_rule_payload("Updated welcome", "<p>Updated</p>"),
        )
        assert update.status_code == 200
        assert update.json()["name"] == "Updated welcome"

        delete = await client.delete(f"/api/v1/conversation-settings/welcome-rules/{id1}", headers=headers)
        assert delete.status_code == 200
        delete_remaining = await client.delete(f"/api/v1/conversation-settings/welcome-rules/{id2}", headers=headers)
        assert delete_remaining.status_code == 200

    @pytest.mark.asyncio
    async def test_condition_and_content_validation(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)

        empty_content = await client.post(
            "/api/v1/conversation-settings/welcome-rules",
            headers=headers,
            json=_rule_payload("Bad content", "<p><br></p>"),
        )
        assert empty_content.status_code == 422

        missing_channel = await client.post(
            "/api/v1/conversation-settings/welcome-rules",
            headers=headers,
            json=_rule_payload(
                "Bad channel",
                "<p>Hello</p>",
                [{"condition_type": "web_sdk", "operator": "eq", "value": "999999"}],
            ),
        )
        assert missing_channel.status_code == 400

        bad_channel_type = await client.post(
            "/api/v1/conversation-settings/welcome-rules",
            headers=headers,
            json=_rule_payload(
                "Bad channel type",
                "<p>Hello</p>",
                [{"condition_type": "channel", "operator": "eq", "value": "unknown"}],
            ),
        )
        assert bad_channel_type.status_code == 422

    @pytest.mark.asyncio
    async def test_public_channel_returns_matched_welcome_message(self, client: AsyncClient):
        headers = _auth_header(tenant_id=7)
        channel_a = await _create_channel(client, headers, name=f"SDK A {uuid.uuid4().hex[:8]}")
        channel_b = await _create_channel(client, headers, name=f"SDK B {uuid.uuid4().hex[:8]}")

        specific = await client.post(
            "/api/v1/conversation-settings/welcome-rules",
            headers=headers,
            json=_rule_payload(
                f"Specific {uuid.uuid4().hex[:8]}",
                "<p>Specific welcome</p>",
                [{"condition_type": "web_sdk", "operator": "eq", "value": str(channel_a["id"])}],
            ),
        )
        assert specific.status_code == 201

        fallback = await client.post(
            "/api/v1/conversation-settings/welcome-rules",
            headers=headers,
            json=_rule_payload(f"Fallback {uuid.uuid4().hex[:8]}", "<p>Fallback welcome</p>"),
        )
        assert fallback.status_code == 201
        specific_id = specific.json()["id"]
        fallback_id = fallback.json()["id"]
        all_rules = await client.get("/api/v1/conversation-settings/welcome-rules", headers=headers)
        ordered_ids = [specific_id, fallback_id] + [
            item["id"]
            for item in all_rules.json()["items"]
            if item["id"] not in {specific_id, fallback_id}
        ]
        reorder = await client.put(
            "/api/v1/conversation-settings/welcome-rules/reorder",
            headers=headers,
            json={"ordered_ids": ordered_ids},
        )
        assert reorder.status_code == 200

        resp_a = await client.get(f"/api/v1/public/channels/{channel_a['channel_key']}")
        assert resp_a.status_code == 200
        assert resp_a.json()["welcome_message"]["content"] == "<p>Specific welcome</p>"

        resp_b = await client.get(f"/api/v1/public/channels/{channel_b['channel_key']}")
        assert resp_b.status_code == 200
        assert resp_b.json()["welcome_message"]["content"] == "<p>Fallback welcome</p>"
