"""
Integration tests for satisfaction survey config APIs.
"""
import copy

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.satisfaction_survey_config import SatisfactionSurveyConfig, SatisfactionSurveyConfigVersion


def _make_token(tenant_id: int = 7, role: str = "admin") -> str:
    return create_access_token({"sub": "1", "tenant_id": tenant_id, "roles": [role], "name": "Admin"})


def _auth_header(tenant_id: int = 7) -> dict:
    return {"Authorization": f"Bearer {_make_token(tenant_id)}"}


async def _cleanup(tenant_id: int = 7) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(SatisfactionSurveyConfigVersion).where(SatisfactionSurveyConfigVersion.tenant_id == tenant_id)
        )
        await db.execute(delete(SatisfactionSurveyConfig).where(SatisfactionSurveyConfig.tenant_id == tenant_id))
        await db.commit()


async def _default_payload(client: AsyncClient, headers: dict) -> dict:
    resp = await client.get("/api/v1/conversation-settings/satisfaction", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    for key in ("id", "tenant_id", "configured", "current_version", "updated_by_id", "updated_by_name", "updated_at"):
        data.pop(key, None)
    return data


class TestSatisfactionSurveyConfigAPI:
    @pytest.mark.asyncio
    async def test_save_toggle_versions_and_snapshot(self, client: AsyncClient):
        await _cleanup()
        headers = _auth_header()
        payload = await _default_payload(client, headers)
        payload["name"] = "Post chat survey"
        payload["product"]["enabled"] = False
        payload["service"]["rating_options"][3]["is_default"] = True

        save = await client.put("/api/v1/conversation-settings/satisfaction", headers=headers, json=payload)
        assert save.status_code == 200
        saved = save.json()
        assert saved["configured"] is True
        assert saved["current_version"] == 1
        assert saved["name"] == "Post chat survey"
        assert saved["product"]["enabled"] is False

        current = await client.get("/api/v1/conversation-settings/satisfaction", headers=headers)
        assert current.status_code == 200
        assert current.json()["current_version"] == 1

        patch = await client.patch(
            "/api/v1/conversation-settings/satisfaction/enabled",
            headers=headers,
            json={"enabled": False},
        )
        assert patch.status_code == 200
        assert patch.json()["enabled"] is False
        assert patch.json()["current_version"] == 1

        versions = await client.get("/api/v1/conversation-settings/satisfaction/versions", headers=headers)
        assert versions.status_code == 200
        body = versions.json()
        assert body["total"] == 1
        assert body["current_version"] == 1
        assert body["items"][0]["version"] == 1
        assert body["items"][0]["survey_types"] == ["service"]
        assert body["items"][0]["trigger_modes"] == ["agent_invite", "session_end_invite"]

        snapshot = await client.get("/api/v1/conversation-settings/satisfaction/versions/1", headers=headers)
        assert snapshot.status_code == 200
        assert snapshot.json()["snapshot"]["enabled"] is False
        assert snapshot.json()["snapshot"]["name"] == "Post chat survey"

    @pytest.mark.asyncio
    async def test_rating_structure_change_bumps_version(self, client: AsyncClient):
        await _cleanup()
        headers = _auth_header()
        payload = await _default_payload(client, headers)

        first = await client.put("/api/v1/conversation-settings/satisfaction", headers=headers, json=payload)
        assert first.status_code == 200
        assert first.json()["current_version"] == 1

        renamed = copy.deepcopy(payload)
        renamed["service"]["rating_options"][3]["name"] = "比较满意"
        second = await client.put("/api/v1/conversation-settings/satisfaction", headers=headers, json=renamed)
        assert second.status_code == 200
        assert second.json()["current_version"] == 2

        rescore = copy.deepcopy(renamed)
        rescore["service"]["rating_options"][3]["score"] = 9
        third = await client.put("/api/v1/conversation-settings/satisfaction", headers=headers, json=rescore)
        assert third.status_code == 200
        assert third.json()["current_version"] == 2

        versions = await client.get("/api/v1/conversation-settings/satisfaction/versions", headers=headers)
        assert versions.status_code == 200
        assert versions.json()["total"] == 2

    @pytest.mark.asyncio
    async def test_validation_rejects_invalid_type_and_options(self, client: AsyncClient):
        await _cleanup()
        headers = _auth_header()
        payload = await _default_payload(client, headers)

        both_disabled = copy.deepcopy(payload)
        both_disabled["service"]["enabled"] = False
        both_disabled["product"]["enabled"] = False
        resp = await client.put("/api/v1/conversation-settings/satisfaction", headers=headers, json=both_disabled)
        assert resp.status_code == 422

        no_triggers = copy.deepcopy(payload)
        no_triggers["triggers"]["agent_invite"] = False
        no_triggers["triggers"]["user_initiated"] = False
        no_triggers["triggers"]["session_end_invite"] = False
        resp = await client.put("/api/v1/conversation-settings/satisfaction", headers=headers, json=no_triggers)
        assert resp.status_code == 422

        duplicate_names = copy.deepcopy(payload)
        duplicate_names["service"]["rating_options"][0]["name"] = "重复"
        duplicate_names["service"]["rating_options"][1]["name"] = "重复"
        resp = await client.put("/api/v1/conversation-settings/satisfaction", headers=headers, json=duplicate_names)
        assert resp.status_code == 422

        disabled_default = copy.deepcopy(payload)
        disabled_default["service"]["rating_options"][0]["is_default"] = True
        disabled_default["service"]["rating_options"][0]["enabled"] = False
        resp = await client.put("/api/v1/conversation-settings/satisfaction", headers=headers, json=disabled_default)
        assert resp.status_code == 422
