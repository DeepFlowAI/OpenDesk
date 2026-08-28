"""Unit tests for LingoMaster tenant settings."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.constants.lingomaster import DEFAULT_AGENT_TRANSLATION_PROMPT, DEFAULT_VISITOR_TRANSLATION_PROMPT
from app.schemas.lingomaster import LingoMasterSettingsUpdate
from app.services.lingomaster_settings_service import LingoMasterSettingsService
from app.services.permission_catalog import ALL_PERMISSION_KEYS


class TestLingoMasterSettingsService:
    @pytest.mark.asyncio
    async def test_get_missing_returns_defaults(self) -> None:
        db = AsyncMock()
        with patch(
            "app.services.lingomaster_settings_service.SystemSettingsRepository.get_by_tenant_id",
            new=AsyncMock(return_value=None),
        ):
            result = await LingoMasterSettingsService.get_settings(db, 1)

        assert result.enabled is False
        assert result.visitor_prompt == DEFAULT_VISITOR_TRANSLATION_PROMPT
        assert result.agent_prompt == DEFAULT_AGENT_TRANSLATION_PROMPT
        assert result.default_visitor_prompt == DEFAULT_VISITOR_TRANSLATION_PROMPT
        assert result.default_agent_prompt == DEFAULT_AGENT_TRANSLATION_PROMPT

    @pytest.mark.asyncio
    async def test_update_existing_updates_only_lingomaster_fields(self) -> None:
        db = AsyncMock()
        item = SimpleNamespace(
            lingomaster_enabled=False,
            lingomaster_visitor_prompt=DEFAULT_VISITOR_TRANSLATION_PROMPT,
            lingomaster_agent_prompt=DEFAULT_AGENT_TRANSLATION_PROMPT,
        )
        updated = SimpleNamespace(
            lingomaster_enabled=True,
            lingomaster_visitor_prompt="Visitor {{message}}",
            lingomaster_agent_prompt="Agent {{message}}",
        )
        data = LingoMasterSettingsUpdate(
            enabled=True,
            visitor_prompt="Visitor {{message}}",
            agent_prompt="Agent {{message}}",
        )
        with (
            patch(
                "app.services.lingomaster_settings_service.SystemSettingsRepository.get_by_tenant_id",
                new=AsyncMock(return_value=item),
            ),
            patch(
                "app.services.lingomaster_settings_service.SystemSettingsRepository.update",
                new=AsyncMock(return_value=updated),
            ) as update,
        ):
            result = await LingoMasterSettingsService.update_settings(db, 1, data)

        assert result.enabled is True
        assert result.default_visitor_prompt == DEFAULT_VISITOR_TRANSLATION_PROMPT
        assert result.default_agent_prompt == DEFAULT_AGENT_TRANSLATION_PROMPT
        update.assert_awaited_once_with(
            db,
            item,
            {
                "lingomaster_enabled": True,
                "lingomaster_visitor_prompt": "Visitor {{message}}",
                "lingomaster_agent_prompt": "Agent {{message}}",
            },
        )

    @pytest.mark.asyncio
    async def test_update_missing_creates_complete_system_settings(self) -> None:
        db = AsyncMock()
        data = LingoMasterSettingsUpdate(
            enabled=True,
            visitor_prompt="Visitor {{message}}",
            agent_prompt="Agent {{message}}",
        )
        created = SimpleNamespace(
            lingomaster_enabled=True,
            lingomaster_visitor_prompt=data.visitor_prompt,
            lingomaster_agent_prompt=data.agent_prompt,
        )
        with (
            patch(
                "app.services.lingomaster_settings_service.SystemSettingsRepository.get_by_tenant_id",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.lingomaster_settings_service.SystemSettingsRepository.create",
                new=AsyncMock(return_value=created),
            ) as create,
        ):
            result = await LingoMasterSettingsService.update_settings(db, 7, data)

        payload = create.await_args.args[2]
        assert payload["default_language"] == "zh"
        assert payload["lingomaster_enabled"] is True
        assert result.enabled is True

    def test_prompt_requires_message_variable(self) -> None:
        with pytest.raises(ValidationError, match="must contain"):
            LingoMasterSettingsUpdate(
                enabled=True,
                visitor_prompt="No variable",
                agent_prompt="Agent {{message}}",
            )

    def test_permission_catalog_contains_lingomaster_manage(self) -> None:
        assert "chat.admin.lingomaster.manage" in ALL_PERMISSION_KEYS
