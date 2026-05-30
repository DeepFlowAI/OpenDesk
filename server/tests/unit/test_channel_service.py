"""
Unit tests for channel service configuration and availability logic.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import UnauthorizedError, ValidationError
from app.core.security import create_visitor_session_token, decode_access_token
from app.schemas.channel import (
    ChannelConfig,
    DEFAULT_OFFLINE_MESSAGE,
    DEFAULT_OFFLINE_TITLE,
    DEFAULT_OPEN_AGENT_HANDOFF_LABEL,
)
from app.schemas.open_agent_settings import OpenAgentAgentListResponse, OpenAgentAgentSummary
from app.schemas.visitor_session import VisitorSessionRequest
from app.services.channel_service import ChannelService


def _service_hours(**overrides):
    data = {
        "id": 1,
        "tenant_id": 7,
        "weekly_schedules": [
            {"day_of_week": 1, "slots": [{"start": "09:00", "end": "18:00"}]},
        ],
        "holidays": [],
        "makeup_days": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_channel_config_uses_default_offline_message():
    config = ChannelConfig()

    assert config.offline_title == DEFAULT_OFFLINE_TITLE
    assert config.offline_message == DEFAULT_OFFLINE_MESSAGE
    assert config.service_hours_enabled is False
    assert config.service_hours_id is None
    assert config.use_agent_avatar is False
    assert config.send_button_bg_color is None
    assert config.open_agent_enabled is False
    assert config.open_agent_bot_strategy == "always"
    assert config.open_agent_handoff_label == DEFAULT_OPEN_AGENT_HANDOFF_LABEL
    assert config.open_agent_handoff_after_messages == 2
    assert config.open_agent_handoff_behavior == "confirm"


def test_channel_config_rejects_empty_offline_title():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(offline_title="  ")


def test_channel_config_rejects_empty_rich_text_offline_message():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(offline_message="<p>&nbsp;</p>")


def test_channel_config_requires_agent_when_open_agent_enabled():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(open_agent_enabled=True)


def test_channel_config_rejects_invalid_handoff_threshold():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(
            open_agent_enabled=True,
            open_agent_agent_id=1,
            open_agent_handoff_after_messages=100,
        )


def test_is_within_service_hours_uses_weekly_schedule():
    now = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)

    assert ChannelService.is_within_service_hours(_service_hours(), now) is True


def test_is_within_service_hours_holiday_overrides_weekly_schedule():
    now = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
    service_hours = _service_hours(
        holidays=[{"name": "Holiday", "start": "2026-05-04T00:00", "end": "2026-05-04T23:59"}]
    )

    assert ChannelService.is_within_service_hours(service_hours, now) is False


def test_is_within_service_hours_makeup_day_overrides_holiday():
    now = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
    service_hours = _service_hours(
        holidays=[{"name": "Holiday", "start": "2026-05-04T00:00", "end": "2026-05-04T23:59"}],
        makeup_days=[{"name": "Makeup", "start": "2026-05-04T09:00", "end": "2026-05-04T18:00"}],
    )

    assert ChannelService.is_within_service_hours(service_hours, now) is True


@pytest.mark.asyncio
async def test_normalize_config_requires_service_hours_when_enabled():
    with pytest.raises(ValidationError):
        await ChannelService._normalize_config(
            AsyncMock(),
            7,
            ChannelConfig(service_hours_enabled=True, service_hours_id=None),
        )


@pytest.mark.asyncio
async def test_normalize_config_requires_bot_service_hours(monkeypatch):
    monkeypatch.setattr(
        "app.services.channel_service.OpenAgentSettingsService.list_active_agents",
        AsyncMock(return_value=OpenAgentAgentListResponse(
            items=[OpenAgentAgentSummary(id=1, name="Support Agent", status="active")],
            total=1,
            page=1,
            per_page=100,
            pages=1,
        )),
    )

    with pytest.raises(PydanticValidationError):
        ChannelConfig(
            open_agent_enabled=True,
            open_agent_agent_id=1,
            open_agent_bot_strategy="service_hours",
        )


@pytest.mark.asyncio
async def test_normalize_config_saves_active_open_agent(monkeypatch):
    monkeypatch.setattr(
        "app.services.channel_service.OpenAgentSettingsService.list_active_agents",
        AsyncMock(return_value=OpenAgentAgentListResponse(
            items=[OpenAgentAgentSummary(id=1, name="Support Agent", status="active")],
            total=1,
            page=1,
            per_page=100,
            pages=1,
        )),
    )

    result = await ChannelService._normalize_config(
        AsyncMock(),
        7,
        ChannelConfig(open_agent_enabled=True, open_agent_agent_id=1),
    )

    assert result["open_agent_enabled"] is True
    assert result["open_agent_agent_id"] == 1
    assert result["open_agent_agent_name"] == "Support Agent"
    assert result["open_agent_bot_service_hours_id"] is None


@pytest.mark.asyncio
async def test_normalize_config_rejects_unavailable_open_agent(monkeypatch):
    monkeypatch.setattr(
        "app.services.channel_service.OpenAgentSettingsService.list_active_agents",
        AsyncMock(return_value=OpenAgentAgentListResponse(
            items=[OpenAgentAgentSummary(id=2, name="Other Agent", status="active")],
            total=1,
            page=1,
            per_page=100,
            pages=1,
        )),
    )

    with pytest.raises(ValidationError):
        await ChannelService._normalize_config(
            AsyncMock(),
            7,
            ChannelConfig(open_agent_enabled=True, open_agent_agent_id=1),
        )


@pytest.mark.asyncio
async def test_check_channel_availability_returns_no_agent(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        config=ChannelConfig(service_hours_enabled=False).model_dump(),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelRepository.get_by_id",
        AsyncMock(return_value=channel),
    )
    monkeypatch.setattr(
        "app.services.routing_service.RoutingService.route_conversation",
        AsyncMock(return_value=(None, [1], {1: 1})),
    )
    monkeypatch.setattr(
        "app.services.channel_service.AgentStatusService.get_status",
        AsyncMock(return_value={"status": "offline", "current_count": 0, "max_concurrent": 1}),
    )

    result = await ChannelService.check_channel_availability(AsyncMock(), AsyncMock(), 10)

    assert result["can_start_conversation"] is False
    assert result["reason"] == "no_available_agent"
    assert result["offline_title"] == DEFAULT_OFFLINE_TITLE
    assert result["offline_message"] == DEFAULT_OFFLINE_MESSAGE


@pytest.mark.asyncio
async def test_create_visitor_session_binds_channel_context(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
        channel_key_version=3,
        public_access_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.get_public_channel_by_key",
        AsyncMock(return_value=channel),
    )

    result = await ChannelService.create_visitor_session(
        AsyncMock(),
        channel.channel_key,
        VisitorSessionRequest(visitor_name="Ada"),
    )

    payload = decode_access_token(result["visitor_session_token"])
    assert result["visitor_external_id"].startswith("v_")
    assert result["visitor_secret"].startswith("vs_")
    assert result["expires_in"] > 0
    assert payload["typ"] == "visitor_session"
    assert payload["tenant_id"] == 7
    assert payload["channel_id"] == 10
    assert payload["channel_key"] == channel.channel_key
    assert payload["channel_key_version"] == 3
    assert payload["visitor_external_id"] == result["visitor_external_id"]


@pytest.mark.asyncio
async def test_create_visitor_session_renews_only_with_server_minted_secret(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
        channel_key_version=3,
        public_access_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.get_public_channel_by_key",
        AsyncMock(return_value=channel),
    )
    issued = await ChannelService.create_visitor_session(
        AsyncMock(),
        channel.channel_key,
        VisitorSessionRequest(),
    )

    renewed = await ChannelService.create_visitor_session(
        AsyncMock(),
        channel.channel_key,
        VisitorSessionRequest(
            visitor_external_id=issued["visitor_external_id"],
            visitor_secret=issued["visitor_secret"],
        ),
    )

    assert renewed["visitor_external_id"] == issued["visitor_external_id"]
    assert renewed["visitor_secret"] is None


@pytest.mark.asyncio
async def test_create_visitor_session_rejects_client_supplied_id_without_secret(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
        channel_key_version=3,
        public_access_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.get_public_channel_by_key",
        AsyncMock(return_value=channel),
    )

    with pytest.raises(UnauthorizedError):
        await ChannelService.create_visitor_session(
            AsyncMock(),
            channel.channel_key,
            VisitorSessionRequest(visitor_external_id="visitor-1"),
        )


@pytest.mark.asyncio
async def test_create_visitor_session_rejects_invalid_visitor_secret(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
        channel_key_version=3,
        public_access_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.get_public_channel_by_key",
        AsyncMock(return_value=channel),
    )

    with pytest.raises(UnauthorizedError):
        await ChannelService.create_visitor_session(
            AsyncMock(),
            channel.channel_key,
            VisitorSessionRequest(
                visitor_external_id="visitor-1",
                visitor_secret="vs_invalid",
            ),
        )


@pytest.mark.asyncio
async def test_validate_visitor_session_rejects_rotated_key(monkeypatch):
    token = create_visitor_session_token({
        "tenant_id": 7,
        "channel_id": 10,
        "channel_key": "ch_abcdefghijklmnopqrstuvwxyzabcdef",
        "channel_key_version": 1,
        "visitor_external_id": "visitor-1",
    })
    monkeypatch.setattr(
        "app.services.channel_service.ChannelRepository.get_by_id",
        AsyncMock(return_value=SimpleNamespace(
            id=10,
            tenant_id=7,
            channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
            channel_key_version=2,
            public_access_enabled=True,
        )),
    )

    with pytest.raises(UnauthorizedError):
        await ChannelService.validate_visitor_session_token(AsyncMock(), token)
