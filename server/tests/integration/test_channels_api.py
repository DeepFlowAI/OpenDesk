"""
Integration tests for Channel API
"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock

from app.core.security import create_access_token
from app.schemas.open_agent_settings import OpenAgentAgentListResponse, OpenAgentAgentSummary


def _make_token(tenant_id: int = 7, role: str = "admin") -> str:
    return create_access_token({"sub": "1", "tenant_id": tenant_id, "roles": [role]})


def _auth_header(tenant_id: int = 7) -> dict:
    return {"Authorization": f"Bearer {_make_token(tenant_id)}"}


SAMPLE_PAYLOAD = {
    "name": "Test Web Channel",
    "channel_type": "web",
    "config": {
        "title": "Help Center",
        "page_bg_color": "#f5f5f5",
        "header_gradient_start": "#1a1a1a",
        "header_gradient_end": "#333333",
        "header_title_color": "#ffffff",
        "message_area_bg_color": "#ffffff",
        "agent_bubble_bg_color": "#f0f0f0",
        "agent_bubble_text_color": "#1a1a1a",
        "agent_bubble_border_color": "#e5e5e5",
        "agent_bubble_radius": [10, 10, 10, 0],
        "use_agent_avatar": True,
        "user_bubble_bg_color": "#1a1a1a",
        "user_bubble_text_color": "#ffffff",
        "user_bubble_border_color": None,
        "user_bubble_radius": [10, 10, 0, 10],
        "send_button_bg_color": "#2563eb",
        "input_placeholder": "Type a message...",
        "assist_panel_enabled": True,
        "assist_panel_title": "Help",
        "assist_panel_react_code": "export default function AssistApp() { return null }",
        "assist_panel_config": {
            "items": [
                {"question": "Pricing", "message": "Tell me about pricing"},
            ],
        },
    },
}


class TestChannelAPI:

    @pytest.mark.asyncio
    async def test_list_empty_returns_200(self, client: AsyncClient):
        """Empty list should return 200 with empty array."""
        headers = _auth_header(tenant_id=6666)
        resp = await client.get("/api/v1/channels", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_create_returns_201(self, client: AsyncClient):
        """Create with valid data should return 201."""
        headers = _auth_header()
        resp = await client.post("/api/v1/channels", json=SAMPLE_PAYLOAD, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Web Channel"
        assert data["channel_type"] == "web"
        assert data["config"]["title"] == "Help Center"
        assert data["config"]["agent_bubble_radius"] == [10, 10, 10, 0]
        assert data["config"]["use_agent_avatar"] is True
        assert data["config"]["send_button_bg_color"] == "#2563eb"
        assert data["config"]["assist_panel_enabled"] is True
        assert data["config"]["assist_panel_title"] == "Help"
        assert data["config"]["assist_panel_config"]["items"][0]["question"] == "Pricing"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_get_by_id_returns_200(self, client: AsyncClient):
        """Get existing channel should return 200."""
        headers = _auth_header()
        create_resp = await client.post("/api/v1/channels", json=SAMPLE_PAYLOAD, headers=headers)
        created_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/channels/{created_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == created_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client: AsyncClient):
        """Get non-existing channel should return 404."""
        headers = _auth_header()
        resp = await client.get("/api/v1/channels/99999", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_returns_200(self, client: AsyncClient):
        """Update existing channel should return 200."""
        headers = _auth_header()
        create_resp = await client.post("/api/v1/channels", json=SAMPLE_PAYLOAD, headers=headers)
        created_id = create_resp.json()["id"]

        update_payload = {**SAMPLE_PAYLOAD, "name": "Updated Channel"}
        resp = await client.put(f"/api/v1/channels/{created_id}", json=update_payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Channel"

    @pytest.mark.asyncio
    async def test_delete_returns_200(self, client: AsyncClient):
        """Delete existing channel should return 200."""
        headers = _auth_header()
        create_resp = await client.post("/api/v1/channels", json=SAMPLE_PAYLOAD, headers=headers)
        created_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/channels/{created_id}", headers=headers)
        assert resp.status_code == 200

        resp2 = await client.get(f"/api/v1/channels/{created_id}", headers=headers)
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_create_empty_name_returns_422(self, client: AsyncClient):
        """Empty name should return 422."""
        headers = _auth_header()
        payload = {**SAMPLE_PAYLOAD, "name": ""}
        resp = await client.post("/api/v1/channels", json=payload, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_name_too_long_returns_422(self, client: AsyncClient):
        """Name exceeding 64 characters should return 422."""
        headers = _auth_header()
        payload = {**SAMPLE_PAYLOAD, "name": "x" * 65}
        resp = await client.post("/api/v1/channels", json=payload, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_with_default_config(self, client: AsyncClient):
        """Create with minimal data should use default config."""
        headers = _auth_header()
        payload = {"name": "Minimal Channel"}
        resp = await client.post("/api/v1/channels", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["config"]["agent_bubble_radius"] == [10, 10, 10, 10]
        assert data["config"]["use_agent_avatar"] is False
        assert data["config"]["send_button_bg_color"] is None
        assert data["config"]["input_placeholder"] is None
        assert data["config"]["open_agent_avatar_url"] is None
        assert data["config"]["assist_panel_enabled"] is False
        assert data["config"]["assist_panel_config"] == {}

    @pytest.mark.asyncio
    async def test_create_with_open_agent_bot_config(self, client: AsyncClient, monkeypatch):
        """Create should save OpenAgent bot config after active agent validation."""
        monkeypatch.setattr(
            "app.services.channel_service.OpenAgentSettingsService.list_active_agents",
            AsyncMock(return_value=OpenAgentAgentListResponse(
                items=[OpenAgentAgentSummary(id=10, name="Support Agent", status="active")],
                total=1,
                page=1,
                per_page=100,
                pages=1,
            )),
        )
        headers = _auth_header()
        payload = {
            "name": "Bot Channel",
            "config": {
                "open_agent_enabled": True,
                "open_agent_agent_id": 10,
                "open_agent_bot_strategy": "always",
                "open_agent_avatar_url": "https://cdn.example.com/bot.png",
                "open_agent_input_placeholder": "Ask anything",
                "open_agent_handoff_enabled": True,
                "open_agent_handoff_label": "Human",
                "open_agent_handoff_after_messages": 3,
                "open_agent_handoff_behavior": "auto",
            },
        }

        resp = await client.post("/api/v1/channels", json=payload, headers=headers)

        assert resp.status_code == 201
        data = resp.json()
        assert data["config"]["open_agent_enabled"] is True
        assert data["config"]["open_agent_agent_id"] == 10
        assert data["config"]["open_agent_agent_name"] == "Support Agent"
        assert data["config"]["open_agent_avatar_url"] == "https://cdn.example.com/bot.png"
        assert data["config"]["open_agent_handoff_after_messages"] == 3

    @pytest.mark.asyncio
    async def test_create_with_missing_open_agent_returns_422(self, client: AsyncClient):
        """Pydantic validation should reject enabled bot without an agent."""
        headers = _auth_header()
        payload = {
            "name": "Bad Bot Channel",
            "config": {"open_agent_enabled": True},
        }

        resp = await client.post("/api/v1/channels", json=payload, headers=headers)

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, client: AsyncClient):
        """Channels from one tenant should not be visible to another."""
        headers_a = _auth_header(tenant_id=7)
        headers_b = _auth_header(tenant_id=5555)

        create_resp = await client.post("/api/v1/channels", json=SAMPLE_PAYLOAD, headers=headers_a)
        created_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/channels/{created_id}", headers=headers_b)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_bubble_radius_returns_422(self, client: AsyncClient):
        """Radius with wrong count should return 422."""
        headers = _auth_header()
        payload = {
            "name": "Bad Radius",
            "config": {"agent_bubble_radius": [10, 10]},
        }
        resp = await client.post("/api/v1/channels", json=payload, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client: AsyncClient):
        """Invalid JWT should return 401."""
        headers = {"Authorization": "Bearer invalid.token"}
        resp = await client.get("/api/v1/channels", headers=headers)
        assert resp.status_code == 401
