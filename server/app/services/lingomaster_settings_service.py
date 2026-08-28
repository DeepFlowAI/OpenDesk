"""Tenant-level LingoMaster settings service."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.lingomaster import DEFAULT_AGENT_TRANSLATION_PROMPT, DEFAULT_VISITOR_TRANSLATION_PROMPT
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.schemas.lingomaster import LingoMasterSettingsResponse, LingoMasterSettingsUpdate
from app.services.system_settings_service import DEFAULTS


class LingoMasterSettingsService:
    """Read and update tenant-level translation settings."""

    @staticmethod
    def _response(item: object | None) -> LingoMasterSettingsResponse:
        if item is None:
            return LingoMasterSettingsResponse()
        return LingoMasterSettingsResponse(
            enabled=bool(getattr(item, "lingomaster_enabled", False)),
            visitor_prompt=getattr(item, "lingomaster_visitor_prompt", None)
            or DEFAULT_VISITOR_TRANSLATION_PROMPT,
            agent_prompt=getattr(item, "lingomaster_agent_prompt", None)
            or DEFAULT_AGENT_TRANSLATION_PROMPT,
        )

    @staticmethod
    async def get_settings(db: AsyncSession, tenant_id: int) -> LingoMasterSettingsResponse:
        item = await SystemSettingsRepository.get_by_tenant_id(db, tenant_id)
        return LingoMasterSettingsService._response(item)

    @staticmethod
    async def update_settings(
        db: AsyncSession,
        tenant_id: int,
        data: LingoMasterSettingsUpdate,
    ) -> LingoMasterSettingsResponse:
        changes = {
            "lingomaster_enabled": data.enabled,
            "lingomaster_visitor_prompt": data.visitor_prompt,
            "lingomaster_agent_prompt": data.agent_prompt,
        }
        item = await SystemSettingsRepository.get_by_tenant_id(db, tenant_id)
        if item is None:
            defaults = DEFAULTS.model_dump()
            defaults.update(changes)
            item = await SystemSettingsRepository.create(db, tenant_id, defaults)
        else:
            item = await SystemSettingsRepository.update(db, item, changes)
        return LingoMasterSettingsService._response(item)
