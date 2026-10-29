"""Unit tests for the tenant-level customer short-abandon threshold."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.schemas.system_settings import CallShortAbandonSettingsUpdate
from app.services.system_settings_service import SystemSettingsService


class TestCallShortAbandonSettings:
    @pytest.mark.asyncio
    async def test_get_missing_returns_default_five_seconds(self) -> None:
        db = AsyncMock()
        with patch(
            "app.services.system_settings_service.SystemSettingsRepository.get_by_tenant_id",
            new=AsyncMock(return_value=None),
        ):
            result = await SystemSettingsService.get_settings(db, 1)

        assert result.call_short_abandon_threshold_seconds == 5

    @pytest.mark.asyncio
    async def test_update_existing_changes_only_short_abandon_field(self) -> None:
        db = AsyncMock()
        item = SimpleNamespace(call_short_abandon_threshold_seconds=5)
        updated = SimpleNamespace(
            default_language="zh",
            default_timezone="Asia/Shanghai",
            call_short_abandon_threshold_seconds=12,
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
            result = await SystemSettingsService.update_call_short_abandon_threshold(
                db, 1, 12
            )

        assert result.call_short_abandon_threshold_seconds == 12
        update.assert_awaited_once_with(
            db,
            item,
            {"call_short_abandon_threshold_seconds": 12},
        )

    @pytest.mark.asyncio
    async def test_update_missing_creates_complete_settings(self) -> None:
        db = AsyncMock()
        created = SimpleNamespace(
            default_language="zh",
            default_timezone="Asia/Shanghai",
            call_short_abandon_threshold_seconds=9,
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
            result = await SystemSettingsService.update_call_short_abandon_threshold(
                db, 7, 9
            )

        payload = create.await_args.args[2]
        assert payload["call_wrapup_seconds"] == 30
        assert payload["call_short_abandon_threshold_seconds"] == 9
        assert result.call_short_abandon_threshold_seconds == 9

    def test_seconds_range_validation(self) -> None:
        with pytest.raises(ValidationError):
            CallShortAbandonSettingsUpdate(seconds=0)
        with pytest.raises(ValidationError):
            CallShortAbandonSettingsUpdate(seconds=61)
        assert CallShortAbandonSettingsUpdate(seconds=1).seconds == 1
        assert CallShortAbandonSettingsUpdate(seconds=60).seconds == 60
