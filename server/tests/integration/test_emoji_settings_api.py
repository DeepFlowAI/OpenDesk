"""
Integration tests for emoji setting APIs.
"""
import json
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, text

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.emoji_setting import EmojiSetting


_EMOJI_CONTEXT: dict | None = None


def _auth_headers(employee_id: int, tenant_id: int) -> dict:
    token = create_access_token({"sub": str(employee_id), "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def emoji_context():
    global _EMOJI_CONTEXT
    if _EMOJI_CONTEXT is not None:
        return _EMOJI_CONTEXT

    suffix = uuid.uuid4().hex[:10]
    password_hash = hash_password("Test1234abc")

    async with AsyncSessionLocal() as db:
        tenant_result = await db.execute(
            text(
                """
                INSERT INTO tenants (tenant_id, slug, name, is_active)
                VALUES (:tenant_key, :slug, :name, true)
                RETURNING id
                """
            ),
            {
                "tenant_key": f"emoji-{suffix}",
                "slug": f"emoji-{suffix}",
                "name": f"Emoji Settings {suffix}",
            },
        )
        tenant_id = tenant_result.scalar_one()

        async def create_employee(username: str, *, super_admin: bool = False) -> int:
            result = await db.execute(
                text(
                    """
                    INSERT INTO employees (
                        tenant_id, username, email, password_hash, display_name,
                        name, roles, is_active, is_super_admin
                    )
                    VALUES (
                        :tenant_id, :username, :email, :password_hash, :display_name,
                        :name, CAST(:roles AS JSON), true, :super_admin
                    )
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "username": username,
                    "email": f"{username}@example.com",
                    "password_hash": password_hash,
                    "display_name": username,
                    "name": username,
                    "roles": json.dumps([]),
                    "super_admin": super_admin,
                },
            )
            return result.scalar_one()

        async def create_role(name: str, permissions: list[str]) -> int:
            result = await db.execute(
                text(
                    """
                    INSERT INTO roles (
                        tenant_id, name, description, is_system, is_active,
                        permissions, data_scopes
                    )
                    VALUES (
                        :tenant_id, :name, :description, false, true,
                        CAST(:permissions AS JSON), CAST(:data_scopes AS JSON)
                    )
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "name": name,
                    "description": name,
                    "permissions": json.dumps(permissions),
                    "data_scopes": json.dumps({}),
                },
            )
            return result.scalar_one()

        async def assign_role(employee_id: int, role_id: int) -> None:
            await db.execute(
                text(
                    """
                    INSERT INTO employee_roles (employee_id, role_id)
                    VALUES (:employee_id, :role_id)
                    """
                ),
                {"employee_id": employee_id, "role_id": role_id},
            )

        admin_id = await create_employee(f"emoji_admin_{suffix}", super_admin=True)
        agent_id = await create_employee(f"emoji_agent_{suffix}")
        denied_id = await create_employee(f"emoji_denied_{suffix}")
        agent_role_id = await create_role(f"emoji-agent-{suffix}", ["chat.workspace.use"])
        await assign_role(agent_id, agent_role_id)
        await db.commit()

    _EMOJI_CONTEXT = {
        "tenant_id": tenant_id,
        "admin": _auth_headers(admin_id, tenant_id),
        "agent": _auth_headers(agent_id, tenant_id),
        "denied": _auth_headers(denied_id, tenant_id),
    }
    return _EMOJI_CONTEXT


async def _cleanup(tenant_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(EmojiSetting).where(EmojiSetting.tenant_id == tenant_id))
        await db.commit()


def _strip_meta(config: dict) -> dict:
    data = dict(config)
    for key in ("id", "tenant_id", "configured", "updated_by_id", "updated_by_name", "updated_at"):
        data.pop(key, None)
    return data


class TestEmojiSettingsAPI:
    @pytest.mark.asyncio
    async def test_default_save_and_agent_config(self, client: AsyncClient, emoji_context: dict):
        await _cleanup(emoji_context["tenant_id"])

        default_resp = await client.get("/api/v1/conversation-settings/emojis", headers=emoji_context["admin"])
        assert default_resp.status_code == 200
        default_config = default_resp.json()
        assert default_config["configured"] is False
        assert default_config["user"]["enabled"] is True
        assert len(default_config["user"]["emojis"]) == 38
        assert len(default_config["agent"]["emojis"]) == 38

        payload = _strip_meta(default_config)
        payload["user"]["enabled"] = False
        payload["user"]["emojis"] = []
        payload["agent"]["emojis"] = payload["agent"]["emojis"][:2]

        save_resp = await client.put(
            "/api/v1/conversation-settings/emojis",
            headers=emoji_context["admin"],
            json=payload,
        )
        assert save_resp.status_code == 200
        saved = save_resp.json()
        assert saved["configured"] is True
        assert saved["user"]["enabled"] is False
        assert saved["user"]["emojis"] == []
        assert len(saved["agent"]["emojis"]) == 2

        agent_resp = await client.get(
            "/api/v1/conversation-settings/emojis/agent",
            headers=emoji_context["agent"],
        )
        assert agent_resp.status_code == 200
        agent_config = agent_resp.json()
        assert agent_config["target"] == "agent"
        assert agent_config["configured"] is True
        assert agent_config["enabled"] is True
        assert len(agent_config["emojis"]) == 2

    @pytest.mark.asyncio
    async def test_validation_rejects_empty_duplicate_and_too_many(self, client: AsyncClient, emoji_context: dict):
        default_resp = await client.get("/api/v1/conversation-settings/emojis", headers=emoji_context["admin"])
        payload = _strip_meta(default_resp.json())

        empty_enabled = json.loads(json.dumps(payload))
        empty_enabled["user"]["enabled"] = True
        empty_enabled["user"]["emojis"] = []
        resp = await client.put("/api/v1/conversation-settings/emojis", headers=emoji_context["admin"], json=empty_enabled)
        assert resp.status_code == 422

        duplicate = json.loads(json.dumps(payload))
        duplicate["agent"]["emojis"] = duplicate["agent"]["emojis"][:2]
        duplicate["agent"]["emojis"][1]["emoji"] = duplicate["agent"]["emojis"][0]["emoji"]
        resp = await client.put("/api/v1/conversation-settings/emojis", headers=emoji_context["admin"], json=duplicate)
        assert resp.status_code == 422

        too_many = json.loads(json.dumps(payload))
        too_many["user"]["emojis"] = [
            {"emoji": f"x{i}", "name": f"emoji {i}"}
            for i in range(49)
        ]
        resp = await client.put("/api/v1/conversation-settings/emojis", headers=emoji_context["admin"], json=too_many)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_permissions_and_public_default(self, client: AsyncClient, emoji_context: dict):
        denied = await client.get("/api/v1/conversation-settings/emojis", headers=emoji_context["denied"])
        assert denied.status_code == 403

        denied_agent = await client.get("/api/v1/conversation-settings/emojis/agent", headers=emoji_context["denied"])
        assert denied_agent.status_code == 403

        public_resp = await client.get("/api/v1/public/emojis")
        assert public_resp.status_code == 200
        data = public_resp.json()
        assert data["target"] == "user"
        assert isinstance(data["enabled"], bool)
        assert isinstance(data["emojis"], list)
