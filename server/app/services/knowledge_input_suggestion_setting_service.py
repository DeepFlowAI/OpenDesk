"""
Knowledge input suggestion setting business logic.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_input_suggestion_setting import KnowledgeInputSuggestionSetting
from app.repositories.knowledge_input_suggestion_setting_repository import (
    KnowledgeInputSuggestionSettingRepository,
)
from app.schemas.knowledge_input_suggestion_setting import (
    KnowledgeInputSuggestionSettingPayload,
    KnowledgeInputSuggestionSettingResponse,
)

logger = logging.getLogger(__name__)

DEFAULT_TRIGGER_LENGTH = 2


class KnowledgeInputSuggestionSettingService:
    @staticmethod
    def _actor_name(current_user: dict) -> str | None:
        for key in ("display_name", "name", "username", "email"):
            value = current_user.get(key)
            if value:
                return str(value)[:128]
        return None

    @staticmethod
    def _row_to_response(row: KnowledgeInputSuggestionSetting) -> KnowledgeInputSuggestionSettingResponse:
        return KnowledgeInputSuggestionSettingResponse(
            enabled=row.enabled,
            trigger_length=row.trigger_length,
            id=row.id,
            tenant_id=row.tenant_id,
            configured=True,
            updated_by_id=row.updated_by_id,
            updated_by_name=row.updated_by_name,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _default_response(tenant_id: int) -> KnowledgeInputSuggestionSettingResponse:
        return KnowledgeInputSuggestionSettingResponse(
            enabled=False,
            trigger_length=DEFAULT_TRIGGER_LENGTH,
            id=None,
            tenant_id=tenant_id,
            configured=False,
            updated_by_id=None,
            updated_by_name=None,
            updated_at=None,
        )

    @staticmethod
    async def get_current(db: AsyncSession, tenant_id: int) -> KnowledgeInputSuggestionSettingResponse:
        row = await KnowledgeInputSuggestionSettingRepository.get_by_tenant(db, tenant_id)
        if not row:
            return KnowledgeInputSuggestionSettingService._default_response(tenant_id)
        return KnowledgeInputSuggestionSettingService._row_to_response(row)

    @staticmethod
    async def save(
        db: AsyncSession,
        tenant_id: int,
        current_user: dict,
        payload: KnowledgeInputSuggestionSettingPayload,
    ) -> KnowledgeInputSuggestionSettingResponse:
        row = await KnowledgeInputSuggestionSettingRepository.save(
            db,
            tenant_id,
            {
                "enabled": payload.enabled,
                "trigger_length": payload.trigger_length,
                "updated_by_id": current_user.get("user_id"),
                "updated_by_name": KnowledgeInputSuggestionSettingService._actor_name(current_user),
            },
        )
        logger.info(
            "knowledge_input_suggestion_settings_saved tenant_id=%s setting_id=%s enabled=%s trigger_length=%s updated_by_id=%s",
            tenant_id,
            row.id,
            row.enabled,
            row.trigger_length,
            row.updated_by_id,
        )
        return KnowledgeInputSuggestionSettingService._row_to_response(row)

    @staticmethod
    async def get_runtime_config(db: AsyncSession, tenant_id: int) -> KnowledgeInputSuggestionSettingResponse:
        """Runtime helper for workspace clients."""
        return await KnowledgeInputSuggestionSettingService.get_current(db, tenant_id)
