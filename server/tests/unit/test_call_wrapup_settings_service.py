"""Unit tests for the tenant-level after-call work (wrap-up) duration setting."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.schemas.system_settings import CallWrapupSettingsUpdate
from app.services.system_settings_service import SystemSettingsService


class TestCallWrapupSettings:
    @pytest.mark.asyncio
    async def test_get_missing_returns_default_30(self) -> None:
        db = AsyncMock()
        with patch(
            "app.services.system_settings_service.SystemSettingsRepository.get_by_tenant_id",
            new=AsyncMock(return_value=None),
        ):
            result = await SystemSettingsService.get_settings(db, 1)

        assert result.call_wrapup_seconds == 30

    @pytest.mark.asyncio
    async def test_update_existing_updates_only_wrapup_field(self) -> None:
        db = AsyncMock()
        item = SimpleNamespace(call_wrapup_seconds=30)
        updated = SimpleNamespace(
            default_language="zh",
            default_timezone="Asia/Shanghai",
            call_wrapup_seconds=45,
        )
        with (
            patch(
                "app.services.system_settings_service.SystemSettingsRepository.get_by_tenant_id",
                new=AsyncMock(return_value=item),
            ),
            patch(
                "app.services.system_settings_service.SystemSettingsRepository.update",
                new=AsyncMock(return_value=updated),
            ) as update,
        ):
            result = await SystemSettingsService.update_call_wrapup(db, 1, 45)

        assert result.call_wrapup_seconds == 45
        update.assert_awaited_once_with(db, item, {"call_wrapup_seconds": 45})

    @pytest.mark.asyncio
    async def test_update_missing_creates_complete_system_settings(self) -> None:
        db = AsyncMock()
        created = SimpleNamespace(
            default_language="zh",
            default_timezone="Asia/Shanghai",
            call_wrapup_seconds=0,
        )
        with (
            patch(
                "app.services.system_settings_service.SystemSettingsRepository.get_by_tenant_id",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.system_settings_service.SystemSettingsRepository.create",
                new=AsyncMock(return_value=created),
            ) as create,
        ):
            result = await SystemSettingsService.update_call_wrapup(db, 7, 0)

        payload = create.await_args.args[2]
        assert payload["default_language"] == "zh"
        assert payload["call_wrapup_seconds"] == 0
        assert result.call_wrapup_seconds == 0

    def test_seconds_range_validation(self) -> None:
        with pytest.raises(ValidationError):
            CallWrapupSettingsUpdate(seconds=-1)
        with pytest.raises(ValidationError):
            CallWrapupSettingsUpdate(seconds=61)
        assert CallWrapupSettingsUpdate(seconds=0).seconds == 0
        assert CallWrapupSettingsUpdate(seconds=60).seconds == 60
