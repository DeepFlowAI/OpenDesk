"""
Conversation agent display-name setting business logic.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_agent_display_setting import ConversationAgentDisplaySetting
from app.repositories.conversation_agent_display_setting_repository import (
    ConversationAgentDisplaySettingRepository,
)
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.conversation_agent_display_setting import (
    AgentDisplayMode,
    ConversationAgentDisplaySettingPayload,
    ConversationAgentDisplaySettingResponse,
    ConversationAgentDisplayTargetResponse,
)

logger = logging.getLogger(__name__)

DEFAULT_AGENT_DISPLAY_MODE: AgentDisplayMode = "name"


class ConversationAgentDisplaySettingService:
    @staticmethod
    def _actor_name(current_user: dict) -> str | None:
        for key in ("display_name", "name", "username", "email"):
            value = current_user.get(key)
            if value:
                return str(value)[:128]
        return None

    @staticmethod
    def _row_to_response(row: ConversationAgentDisplaySetting) -> ConversationAgentDisplaySettingResponse:
        return ConversationAgentDisplaySettingResponse(
            display_mode=row.display_mode,
            id=row.id,
            tenant_id=row.tenant_id,
            configured=True,
            updated_by_id=row.updated_by_id,
            updated_by_name=row.updated_by_name,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _default_response(tenant_id: int) -> ConversationAgentDisplaySettingResponse:
        return ConversationAgentDisplaySettingResponse(
            display_mode=DEFAULT_AGENT_DISPLAY_MODE,
            id=None,
            tenant_id=tenant_id,
            configured=False,
            updated_by_id=None,
            updated_by_name=None,
            updated_at=None,
        )

    @staticmethod
    def resolve_agent_name(agent, display_mode: AgentDisplayMode | str | None = None) -> str | None:
        if agent is None:
            return None

        mode = display_mode if display_mode in ("name", "nickname") else DEFAULT_AGENT_DISPLAY_MODE
        if mode == "nickname":
            return (
                getattr(agent, "nickname", None)
                or getattr(agent, "name", None)
                or getattr(agent, "username", None)
                or getattr(agent, "display_name", None)
                or None
            )
        return (
            getattr(agent, "display_name", None)
            or getattr(agent, "name", None)
            or getattr(agent, "username", None)
            or getattr(agent, "nickname", None)
            or None
        )

    @staticmethod
    async def get_current(db: AsyncSession, tenant_id: int) -> ConversationAgentDisplaySettingResponse:
        row = await ConversationAgentDisplaySettingRepository.get_by_tenant(db, tenant_id)
        if not row:
            return ConversationAgentDisplaySettingService._default_response(tenant_id)
        return ConversationAgentDisplaySettingService._row_to_response(row)

    @staticmethod
    async def get_display_mode(db: AsyncSession, tenant_id: int) -> AgentDisplayMode:
        current = await ConversationAgentDisplaySettingService.get_current(db, tenant_id)
        return current.display_mode

    @staticmethod
    async def get_agent_target(
        db: AsyncSession,
        tenant_id: int,
        agent_id: int,
    ) -> ConversationAgentDisplayTargetResponse:
        current = await ConversationAgentDisplaySettingService.get_current(db, tenant_id)
        agent = await EmployeeRepository.get_by_id(db, agent_id)
        if agent is not None and agent.tenant_id != tenant_id:
            agent = None
        return ConversationAgentDisplayTargetResponse(
            display_mode=current.display_mode,
            sender_name=ConversationAgentDisplaySettingService.resolve_agent_name(agent, current.display_mode),
        )

    @staticmethod
    async def save(
        db: AsyncSession,
        tenant_id: int,
        current_user: dict,
        payload: ConversationAgentDisplaySettingPayload,
    ) -> ConversationAgentDisplaySettingResponse:
        row = await ConversationAgentDisplaySettingRepository.save(
            db,
            tenant_id,
            {
                "display_mode": payload.display_mode,
                "updated_by_id": current_user.get("user_id"),
                "updated_by_name": ConversationAgentDisplaySettingService._actor_name(current_user),
            },
        )
        logger.info(
            "conversation_agent_display_setting_saved tenant_id=%s setting_id=%s display_mode=%s updated_by_id=%s",
            tenant_id,
            row.id,
            row.display_mode,
            row.updated_by_id,
        )
        return ConversationAgentDisplaySettingService._row_to_response(row)
