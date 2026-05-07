"""
Unit tests for channel service configuration and availability logic.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ValidationError
from app.schemas.channel import ChannelConfig, DEFAULT_OFFLINE_MESSAGE, DEFAULT_OFFLINE_TITLE
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


def test_channel_config_rejects_empty_offline_title():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(offline_title="  ")


def test_channel_config_rejects_empty_rich_text_offline_message():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(offline_message="<p>&nbsp;</p>")


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
        "app.services.channel_service.RoutingService.route_conversation",
        AsyncMock(return_value=(None, [1], {1: 1})),
    )
    monkeypatch.setattr(
        "app.services.channel_service.AgentStatusService.find_available_agent",
        AsyncMock(return_value=None),
    )

    result = await ChannelService.check_channel_availability(AsyncMock(), AsyncMock(), 10)

    assert result["can_start_conversation"] is False
    assert result["reason"] == "no_available_agent"
    assert result["offline_title"] == DEFAULT_OFFLINE_TITLE
    assert result["offline_message"] == DEFAULT_OFFLINE_MESSAGE
