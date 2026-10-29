"""
System settings service
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.constants.lingomaster import DEFAULT_AGENT_TRANSLATION_PROMPT, DEFAULT_VISITOR_TRANSLATION_PROMPT
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.schemas.system_settings import (
    SystemSettingsUpdate,
    OrganizationSettingsUpdate,
    SystemSettingsResponse,
)


DEFAULTS = SystemSettingsResponse(
    default_language="zh",
    default_timezone="Asia/Shanghai",
    organization_enabled=False,
    bridge_asr_enabled=False,
    call_wrapup_seconds=30,
    call_short_abandon_threshold_seconds=5,
    lingomaster_enabled=False,
    lingomaster_visitor_prompt=DEFAULT_VISITOR_TRANSLATION_PROMPT,
    lingomaster_agent_prompt=DEFAULT_AGENT_TRANSLATION_PROMPT,
)


class SystemSettingsService:

    @staticmethod
    async def get_settings(db: AsyncSession, tenant_id: int) -> SystemSettingsResponse:
        """Get system settings for a tenant, returning defaults if not configured."""
        item = await SystemSettingsRepository.get_by_tenant_id(db, tenant_id)
        if not item:
            return DEFAULTS
        return SystemSettingsResponse.model_validate(item)

    @staticmethod
    async def update_settings(
        db: AsyncSession, tenant_id: int, data: SystemSettingsUpdate
    ) -> SystemSettingsResponse:
        """Upsert system settings for a tenant."""
        item = await SystemSettingsRepository.get_by_tenant_id(db, tenant_id)
        if item:
            item = await SystemSettingsRepository.update(db, item, data.model_dump())
        else:
            item = await SystemSettingsRepository.create(db, tenant_id, data.model_dump())
        return SystemSettingsResponse.model_validate(item)

    @staticmethod
    async def update_organization_settings(
        db: AsyncSession, tenant_id: int, data: OrganizationSettingsUpdate
    ) -> SystemSettingsResponse:
        """Toggle organization feature for a tenant."""
        item = await SystemSettingsRepository.get_by_tenant_id(db, tenant_id)
        if item:
            item = await SystemSettingsRepository.update(db, item, data.model_dump())
        else:
            defaults = DEFAULTS.model_dump()
            defaults.update(data.model_dump())
            item = await SystemSettingsRepository.create(db, tenant_id, defaults)
        return SystemSettingsResponse.model_validate(item)

    @staticmethod
    async def is_bridge_asr_enabled_managed(tenant_id: int) -> bool:
        """Read a tenant's live-transcription flag using a self-contained short session.

        Opens its own DB session, reads, and closes it before returning, so callers
        on a hot path (e.g. just before a bridge RPC) never hold a session across I/O.
        """
        async with AsyncSessionLocal() as db:
            settings = await SystemSettingsService.get_settings(db, tenant_id)
        return settings.bridge_asr_enabled

    @staticmethod
    async def update_call_transcription(
        db: AsyncSession, tenant_id: int, enabled: bool
    ) -> SystemSettingsResponse:
        """Toggle agent-workstation live transcription (FlowKit bridge ASR) for a tenant."""
        changes = {"bridge_asr_enabled": enabled}
        item = await SystemSettingsRepository.get_by_tenant_id(db, tenant_id)
        if item:
            item = await SystemSettingsRepository.update(db, item, changes)
        else:
            defaults = DEFAULTS.model_dump()
            defaults.update(changes)
            item = await SystemSettingsRepository.create(db, tenant_id, defaults)
        return SystemSettingsResponse.model_validate(item)

    @staticmethod
    async def update_call_wrapup(
        db: AsyncSession, tenant_id: int, seconds: int
    ) -> SystemSettingsResponse:
        """Save the tenant-level after-call work duration in seconds."""
        changes = {"call_wrapup_seconds": seconds}
        item = await SystemSettingsRepository.get_by_tenant_id(db, tenant_id)
        if item:
            item = await SystemSettingsRepository.update(db, item, changes)
        else:
            defaults = DEFAULTS.model_dump()
            defaults.update(changes)
            item = await SystemSettingsRepository.create(db, tenant_id, defaults)
        return SystemSettingsResponse.model_validate(item)

    @staticmethod
    async def get_call_wrapup_seconds_managed(tenant_id: int) -> int:
        """Read the tenant wrap-up duration with a self-contained short session."""
        async with AsyncSessionLocal() as db:
            settings = await SystemSettingsService.get_settings(db, tenant_id)
        return settings.call_wrapup_seconds

    @staticmethod
    async def update_call_short_abandon_threshold(
        db: AsyncSession, tenant_id: int, seconds: int
    ) -> SystemSettingsResponse:
        """Save the tenant-level customer short-abandon threshold."""
        changes = {"call_short_abandon_threshold_seconds": seconds}
        item = await SystemSettingsRepository.get_by_tenant_id(db, tenant_id)
        if item:
            item = await SystemSettingsRepository.update(db, item, changes)
        else:
            defaults = DEFAULTS.model_dump()
            defaults.update(changes)
            item = await SystemSettingsRepository.create(db, tenant_id, defaults)
        return SystemSettingsResponse.model_validate(item)
