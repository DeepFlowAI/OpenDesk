"""
Integration tests for conversation announcement rules.
"""
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.models.conversation_announcement_rule import ConversationAnnouncementRule
from tests.integration.rbac_helpers import ensure_admin_principals, auth_headers_for_seeded_admin


TENANT_ID = 87


async def _cleanup() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ConversationAnnouncementRule).where(ConversationAnnouncementRule.tenant_id == TENANT_ID))
        await db.commit()


async def _headers() -> dict:
    await ensure_admin_principals([TENANT_ID])
    return auth_headers_for_seeded_admin(TENANT_ID)


async def _create_channel(client: AsyncClient, headers: dict, name: str | None = None) -> dict:
    resp = await client.post(
        "/api/v1/channels",
        headers=headers,
        json={"name": name or f"Web SDK {uuid.uuid4().hex[:8]}", "channel_type": "web"},
    )
    assert resp.status_code == 201
    return resp.json()


def _payload(name: str, conditions: list[dict] | None = None, **overrides) -> dict:
    payload = {
        "name": name,
        "enabled": True,
        "time_range_type": "permanent",
        "start_at": None,
        "end_at": None,
        "conditions": conditions or [],
        "auto_popup": True,
        "background_color": "yellow",
        "summary_html": "<p>Short notice</p>",
        "detail_html": "<p>Long notice detail</p>",
    }
    payload.update(overrides)
    return payload


class TestConversationAnnouncementsAPI:
    @pytest.mark.asyncio
    async def test_crud_reorder_toggle_delete_and_public_match(self, client: AsyncClient):
        await _cleanup()
        headers = await _headers()
        channel = await _create_channel(client, headers)

        now = datetime.now(timezone.utc)
        expired = await client.post(
            "/api/v1/conversation-settings/announcements",
            headers=headers,
            json=_payload(
                f"Expired {uuid.uuid4().hex[:8]}",
                [{"condition_type": "web_sdk", "operator": "eq", "value": str(channel["id"])}],
                time_range_type="limited",
                start_at=(now - timedelta(days=2)).isoformat(),
                end_at=(now - timedelta(days=1)).isoformat(),
            ),
        )
        assert expired.status_code == 201
        expired_id = expired.json()["id"]

        active = await client.post(
            "/api/v1/conversation-settings/announcements",
            headers=headers,
            json=_payload(f"Active {uuid.uuid4().hex[:8]}", background_color="blue", auto_popup=False),
        )
        assert active.status_code == 201
        active_data = active.json()
        active_id = active_data["id"]
        assert active_data["background_color"] == "blue"
        assert active_data["auto_popup"] is False

        reorder = await client.put(
            "/api/v1/conversation-settings/announcements/reorder",
            headers=headers,
            json={"ordered_ids": [expired_id, active_id]},
        )
        assert reorder.status_code == 200

        public_resp = await client.get(f"/api/v1/public/channels/{channel['channel_key']}")
        assert public_resp.status_code == 200
        announcement = public_resp.json()["announcement"]
        assert announcement["id"] == active_id
        assert announcement["background_color"] == "blue"
        assert announcement["auto_popup"] is False

        patch = await client.patch(
            f"/api/v1/conversation-settings/announcements/{active_id}",
            headers=headers,
            json={"enabled": False},
        )
        assert patch.status_code == 200
        assert patch.json()["enabled"] is False

        get_resp = await client.get(f"/api/v1/conversation-settings/announcements/{active_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["detail_html"] == "<p>Long notice detail</p>"

        update = await client.put(
            f"/api/v1/conversation-settings/announcements/{active_id}",
            headers=headers,
            json=_payload("Updated announcement", background_color="green"),
        )
        assert update.status_code == 200
        assert update.json()["name"] == "Updated announcement"
        assert update.json()["background_color"] == "green"

        delete_active = await client.delete(f"/api/v1/conversation-settings/announcements/{active_id}", headers=headers)
        assert delete_active.status_code == 200
        delete_expired = await client.delete(f"/api/v1/conversation-settings/announcements/{expired_id}", headers=headers)
        assert delete_expired.status_code == 200

    @pytest.mark.asyncio
    async def test_validation_and_permission_gate(self, client: AsyncClient):
        await _cleanup()
        headers = await _headers()

        no_auth = await client.get("/api/v1/conversation-settings/announcements")
        assert no_auth.status_code in (401, 403)

        empty_summary = await client.post(
            "/api/v1/conversation-settings/announcements",
            headers=headers,
            json=_payload("Bad summary", summary_html="<p><br></p>"),
        )
        assert empty_summary.status_code == 422

        bad_time = await client.post(
            "/api/v1/conversation-settings/announcements",
            headers=headers,
            json=_payload(
                "Bad time",
                time_range_type="limited",
                start_at=datetime.now(timezone.utc).isoformat(),
                end_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            ),
        )
        assert bad_time.status_code == 422
