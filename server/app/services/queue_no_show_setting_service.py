"""
Queue no-show cancel setting business logic.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.queue_no_show_setting import QueueNoShowSetting
from app.repositories.queue_no_show_setting_repository import QueueNoShowSettingRepository
from app.schemas.queue_no_show_setting import (
    QueueNoShowSettingPayload,
    QueueNoShowSettingResponse,
)

logger = logging.getLogger(__name__)


class QueueNoShowSettingService:
    @staticmethod
    def _actor_name(current_user: dict) -> str | None:
        for key in ("display_name", "name", "username", "email"):
            value = current_user.get(key)
            if value:
                return str(value)[:128]
        return None

    @staticmethod
    def _row_to_response(row: QueueNoShowSetting) -> QueueNoShowSettingResponse:
        return QueueNoShowSettingResponse(
            enabled=row.enabled,
            id=row.id,
            tenant_id=row.tenant_id,
            configured=True,
            updated_by_id=row.updated_by_id,
            updated_by_name=row.updated_by_name,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _default_response(tenant_id: int) -> QueueNoShowSettingResponse:
        return QueueNoShowSettingResponse(
            enabled=False,
            id=None,
            tenant_id=tenant_id,
            configured=False,
            updated_by_id=None,
            updated_by_name=None,
            updated_at=None,
        )

    @staticmethod
    async def get_current(db: AsyncSession, tenant_id: int) -> QueueNoShowSettingResponse:
        row = await QueueNoShowSettingRepository.get_by_tenant(db, tenant_id)
        if not row:
            return QueueNoShowSettingService._default_response(tenant_id)
        return QueueNoShowSettingService._row_to_response(row)

    @staticmethod
    async def save(
        db: AsyncSession,
        tenant_id: int,
        current_user: dict,
        payload: QueueNoShowSettingPayload,
    ) -> QueueNoShowSettingResponse:
        row = await QueueNoShowSettingRepository.save(
            db,
            tenant_id,
            {
                "enabled": payload.enabled,
                "updated_by_id": current_user.get("user_id"),
                "updated_by_name": QueueNoShowSettingService._actor_name(current_user),
            },
        )
        logger.info(
            "queue_no_show_settings_saved tenant_id=%s setting_id=%s enabled=%s updated_by_id=%s",
            tenant_id,
            row.id,
            row.enabled,
            row.updated_by_id,
        )
        return QueueNoShowSettingService._row_to_response(row)

    @staticmethod
    async def is_enabled(db: AsyncSession, tenant_id: int) -> bool:
        """Runtime helper: whether queue no-show cancel is enabled for the tenant."""
        row = await QueueNoShowSettingRepository.get_by_tenant(db, tenant_id)
        return bool(row and row.enabled)
