"""
Session-discipline tests for admin routes that call OpenAgent / VoiceSpeed HTTP.

Key discipline (CLAUDE.md §8): no managed DB session may stay open while the
upstream HTTP call is in flight.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ValidationError
from app.core.secret_store import encrypt_secret
from app.libs.open_agent.base import (
    OpenAgentAgentDetail,
    OpenAgentAgentListResult,
    OpenAgentAgentSummary,
    OpenAgentAgentTool,
    OpenAgentConnectionResult,
)
from app.libs.voice_speed.base import (
    VoiceSpeedAgentListResult,
    VoiceSpeedAgentSummary,
    VoiceSpeedConnectionResult,
)
from app.repositories.channel_repository import ChannelRepository
from app.repositories.open_agent_settings_repository import OpenAgentSettingsRepository
from app.schemas.channel import ChannelConfig, ChannelCreate, ChannelUpdate
from app.schemas.open_agent_settings import (
    OpenAgentConnectionTestRequest,
    VoiceSpeedConnectionTestRequest,
)
from app.services.channel_service import ChannelService
from app.services.open_agent_settings_service import OpenAgentSettingsService


class SessionTracker:
    active = False
    opens = 0
    closes = 0

    @classmethod
    def reset(cls):
        cls.active = False
        cls.opens = 0
        cls.closes = 0


class FakeSessionContext:
    async def __aenter__(self):
        assert SessionTracker.active is False
        SessionTracker.active = True
        SessionTracker.opens += 1
        return SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

    async def __aexit__(self, *_exc_info):
        SessionTracker.active = False
        SessionTracker.closes += 1


@dataclass
class FakeSettings:
    tenant_id: int = 1
    base_url: str = "https://oa.example"
    api_key_ciphertext: str = encrypt_secret("oa-secret")
    voice_speed_base_url: str = "https://vs.example"
    voice_speed_api_key_ciphertext: str = encrypt_secret("vs-secret")
    updated_at: datetime | None = None


@pytest.fixture(autouse=True)
def _reset_session_tracker():
    SessionTracker.reset()


def _patch_sessions(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.open_agent_settings_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        "app.services.channel_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )


def _patch_saved_settings(monkeypatch, settings: FakeSettings | None = FakeSettings()) -> None:
    monkeypatch.setattr(
        OpenAgentSettingsRepository,
        "get_by_tenant_id",
        AsyncMock(return_value=settings),
    )


@pytest.mark.asyncio
async def test_managed_open_agent_test_closes_db_before_http(monkeypatch):
    _patch_sessions(monkeypatch)
    _patch_saved_settings(monkeypatch)
    active_during_http: list[bool] = []

    class Client:
        async def test_connection(self, base_url: str, api_key: str):
            active_during_http.append(SessionTracker.active)
            assert base_url == "https://oa.example"
            assert api_key == "oa-secret"
            return OpenAgentConnectionResult(True, "ok")

    result = await OpenAgentSettingsService.test_connection_managed(
        1,
        OpenAgentConnectionTestRequest(base_url="https://oa.example"),
        open_agent_client=Client(),
    )

    assert result.ok is True
    assert active_during_http == [False]
    assert SessionTracker.opens == SessionTracker.closes == 1


@pytest.mark.asyncio
async def test_managed_open_agent_test_propagates_upstream_failure(monkeypatch):
    _patch_sessions(monkeypatch)
    _patch_saved_settings(monkeypatch)
    active_during_http: list[bool] = []

    class Client:
        async def test_connection(self, *_args, **_kwargs):
            active_during_http.append(SessionTracker.active)
            return OpenAgentConnectionResult(False, "Denied by upstream")

    with pytest.raises(ValidationError, match="Denied by upstream"):
        await OpenAgentSettingsService.test_connection_managed(
            1,
            OpenAgentConnectionTestRequest(base_url="https://oa.example", api_key="k"),
            open_agent_client=Client(),
        )

    assert active_during_http == [False]


@pytest.mark.asyncio
async def test_managed_voice_speed_test_closes_db_before_http(monkeypatch):
    _patch_sessions(monkeypatch)
    _patch_saved_settings(monkeypatch)
    active_during_http: list[bool] = []

    class Client:
        async def test_connection(self, base_url: str, api_key: str):
            active_during_http.append(SessionTracker.active)
            assert api_key == "vs-secret"
            return VoiceSpeedConnectionResult(True, "ok")

    result = await OpenAgentSettingsService.test_voice_speed_connection_managed(
        1,
        VoiceSpeedConnectionTestRequest(base_url="https://vs.example"),
        voice_speed_client=Client(),
    )

    assert result.ok is True
    assert active_during_http == [False]
    assert SessionTracker.opens == SessionTracker.closes == 1


@pytest.mark.asyncio
async def test_managed_list_active_agents_closes_db_before_http(monkeypatch):
    _patch_sessions(monkeypatch)
    _patch_saved_settings(monkeypatch)
    active_during_http: list[bool] = []

    class Client:
        async def list_agents(self, *_args, **_kwargs):
            active_during_http.append(SessionTracker.active)
            return OpenAgentAgentListResult(
                items=[
                    OpenAgentAgentSummary(id=7, name="Bot", description=None, status="active"),
                ],
                total=1,
                page=1,
                per_page=100,
                pages=1,
            )

    result = await OpenAgentSettingsService.list_active_agents_managed(
        1, open_agent_client=Client()
    )

    assert [item.id for item in result.items] == [7]
    assert active_during_http == [False]
    assert SessionTracker.opens == SessionTracker.closes == 1


@pytest.mark.asyncio
async def test_managed_attachment_handoff_closes_db_before_http(monkeypatch):
    _patch_sessions(monkeypatch)
    _patch_saved_settings(monkeypatch)
    active_during_http: list[bool] = []

    class Client:
        async def get_agent(self, *_args, **_kwargs):
            active_during_http.append(SessionTracker.active)
            return OpenAgentAgentDetail(
                id=7,
                name="Bot",
                description=None,
                status="active",
                welcome_message=None,
                faq=None,
                ai_disclaimer=None,
                attachment_handoff_tool_id=99,
            )

        async def get_agent_tool(self, *_args, **_kwargs):
            active_during_http.append(SessionTracker.active)
            return OpenAgentAgentTool(
                id=99,
                agent_id=7,
                name="Attachment handoff",
                tool_type="human_handoff",
                is_enabled=True,
            )

    result = await OpenAgentSettingsService.get_attachment_handoff_status_managed(
        1, 7, open_agent_client=Client()
    )

    assert result.ready is True
    assert active_during_http == [False, False]
    assert SessionTracker.opens == SessionTracker.closes == 1


@pytest.mark.asyncio
async def test_managed_list_voice_speed_agents_closes_db_before_http(monkeypatch):
    _patch_sessions(monkeypatch)
    _patch_saved_settings(monkeypatch)
    active_during_http: list[bool] = []

    class Client:
        async def list_agents(self, *_args, **_kwargs):
            active_during_http.append(SessionTracker.active)
            return VoiceSpeedAgentListResult(
                items=[
                    VoiceSpeedAgentSummary(
                        id="3", name="Voice", description=None, status="enabled"
                    ),
                ],
            )

    result = await OpenAgentSettingsService.list_voice_speed_agents_managed(
        1, voice_speed_client=Client()
    )

    assert result.configured is True
    assert [item.id for item in result.items] == ["3"]
    assert active_during_http == [False]
    assert SessionTracker.opens == SessionTracker.closes == 1


@pytest.mark.asyncio
async def test_managed_channel_create_closes_db_before_open_agent_http(monkeypatch):
    _patch_sessions(monkeypatch)
    _patch_saved_settings(monkeypatch)
    active_during_http: list[bool] = []
    create_calls: list[dict] = []

    class Client:
        async def list_agents(self, *_args, **_kwargs):
            active_during_http.append(SessionTracker.active)
            return OpenAgentAgentListResult(
                items=[
                    OpenAgentAgentSummary(id=7, name="Support", description=None, status="active"),
                ],
                total=1,
                page=1,
                per_page=100,
                pages=1,
            )

    async def _fake_create(_db, payload, commit=True):
        assert commit is False
        create_calls.append(payload)
        return SimpleNamespace(
            id=42,
            channel_key=payload["channel_key"],
            channel_key_version=1,
            public_access_enabled=True,
            key_rotated_at=None,
            name=payload["name"],
            channel_type=payload["channel_type"],
            access_mode=payload["access_mode"],
            logo_url=None,
            favicon_url=None,
            config=payload["config"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            tenant_id=payload["tenant_id"],
        )

    monkeypatch.setattr(
        ChannelRepository,
        "generate_unique_channel_key",
        AsyncMock(return_value="ch_testkey1234567890123456"),
    )
    monkeypatch.setattr(ChannelRepository, "create", _fake_create)

    data = ChannelCreate(
        name="Widget",
        config=ChannelConfig(open_agent_enabled=True, open_agent_agent_id=7),
    )
    result = await ChannelService.create_managed(1, data, open_agent_client=Client())

    assert result.id == 42
    assert result.config["open_agent_agent_name"] == "Support"
    assert len(create_calls) == 1
    assert active_during_http == [False]
    assert SessionTracker.opens >= 2
    assert SessionTracker.opens == SessionTracker.closes


@pytest.mark.asyncio
async def test_managed_channel_create_propagates_upstream_failure_without_write(monkeypatch):
    _patch_sessions(monkeypatch)
    _patch_saved_settings(monkeypatch)
    create_mock = AsyncMock()
    monkeypatch.setattr(ChannelRepository, "create", create_mock)
    monkeypatch.setattr(
        ChannelRepository,
        "generate_unique_channel_key",
        AsyncMock(return_value="ch_testkey1234567890123456"),
    )

    class Client:
        async def list_agents(self, *_args, **_kwargs):
            assert SessionTracker.active is False
            raise ValidationError("OpenAgent unreachable")

    # Bypass ValidationError wrapping — list_active_agents converts OpenAgentClientError;
    # here we raise ValidationError directly from a broken client via monkeypatch.
    async def _failing_list(*_args, **_kwargs):
        assert SessionTracker.active is False
        raise ValidationError("OpenAgent unreachable")

    monkeypatch.setattr(
        OpenAgentSettingsService,
        "list_active_agents_managed",
        _failing_list,
    )

    data = ChannelCreate(
        name="Widget",
        config=ChannelConfig(open_agent_enabled=True, open_agent_agent_id=7),
    )
    with pytest.raises(ValidationError, match="OpenAgent unreachable"):
        await ChannelService.create_managed(1, data, open_agent_client=Client())

    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_managed_channel_update_closes_db_before_open_agent_http(monkeypatch):
    _patch_sessions(monkeypatch)
    _patch_saved_settings(monkeypatch)
    active_during_http: list[bool] = []
    update_calls: list[tuple] = []
    existing = SimpleNamespace(
        id=9,
        tenant_id=1,
        name="Old",
        channel_type="web",
        access_mode="url",
        config={},
    )

    class Client:
        async def list_agents(self, *_args, **_kwargs):
            active_during_http.append(SessionTracker.active)
            return OpenAgentAgentListResult(
                items=[
                    OpenAgentAgentSummary(id=7, name="Support", description=None, status="active"),
                ],
                total=1,
                page=1,
                per_page=100,
                pages=1,
            )

        async def get_agent(self, *_args, **_kwargs):
            active_during_http.append(SessionTracker.active)
            return OpenAgentAgentDetail(
                id=7,
                name="Support",
                description=None,
                status="active",
                welcome_message=None,
                faq=None,
                ai_disclaimer=None,
                attachment_handoff_tool_id=99,
            )

        async def get_agent_tool(self, *_args, **_kwargs):
            active_during_http.append(SessionTracker.active)
            return OpenAgentAgentTool(
                id=99,
                agent_id=7,
                name="Attachment handoff",
                tool_type="human_handoff",
                is_enabled=True,
            )

    async def _fake_update(_db, item, payload, commit=True):
        assert commit is False
        update_calls.append((item.id, payload))
        return SimpleNamespace(
            id=item.id,
            channel_key="ch_existing123456789012345",
            channel_key_version=1,
            public_access_enabled=True,
            key_rotated_at=None,
            name=payload["name"],
            channel_type=payload["channel_type"],
            access_mode=payload["access_mode"],
            logo_url=None,
            favicon_url=None,
            config=payload["config"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            tenant_id=1,
        )

    monkeypatch.setattr(
        ChannelRepository,
        "get_by_id",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(ChannelRepository, "update", _fake_update)

    data = ChannelUpdate(
        name="Updated",
        config=ChannelConfig(
            open_agent_enabled=True,
            open_agent_agent_id=7,
            open_agent_attachment_upload_enabled=True,
        ),
    )
    result = await ChannelService.update_managed(9, 1, data, open_agent_client=Client())

    assert result.name == "Updated"
    assert len(update_calls) == 1
    assert update_calls[0][0] == 9
    assert all(active is False for active in active_during_http)
    assert len(active_during_http) == 3
    assert SessionTracker.opens == SessionTracker.closes
