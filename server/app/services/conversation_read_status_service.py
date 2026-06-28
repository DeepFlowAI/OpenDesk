"""
Conversation read-status setting service.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_read_status_setting import ConversationReadStatusSetting
from app.repositories.conversation_read_status_repository import ConversationReadStatusRepository
from app.schemas.conversation_read_status import (
    ConversationReadStatusPayload,
    ConversationReadStatusPublicResponse,
    ConversationReadStatusResponse,
    ConversationReadStatusTargetResponse,
)


class ConversationReadStatusService:
    @staticmethod
    def _actor_name(current_user: dict) -> str | None:
        for key in ("display_name", "name", "username", "email"):
            value = current_user.get(key)
            if value:
                return str(value)[:128]
        return None

    @staticmethod
    def default_payload() -> ConversationReadStatusPayload:
        return ConversationReadStatusPayload(
            agent_workspace_enabled=True,
            web_sdk_enabled=True,
        )

    @staticmethod
    def _row_to_payload(row: ConversationReadStatusSetting) -> ConversationReadStatusPayload:
        return ConversationReadStatusPayload(
            agent_workspace_enabled=row.agent_workspace_enabled,
            web_sdk_enabled=row.web_sdk_enabled,
        )

    @staticmethod
    def _row_to_response(row: ConversationReadStatusSetting, configured: bool = True) -> ConversationReadStatusResponse:
        data = ConversationReadStatusService._row_to_payload(row).model_dump()
        data.update(
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "configured": configured,
                "updated_by_id": row.updated_by_id,
                "updated_by_name": row.updated_by_name,
                "updated_at": row.updated_at,
            }
        )
        return ConversationReadStatusResponse.model_validate(data)

    @staticmethod
    def _default_response(tenant_id: int) -> ConversationReadStatusResponse:
        data = ConversationReadStatusService.default_payload().model_dump()
        data.update(
            {
                "id": None,
                "tenant_id": tenant_id,
                "configured": False,
                "updated_by_id": None,
                "updated_by_name": None,
                "updated_at": None,
            }
        )
        return ConversationReadStatusResponse.model_validate(data)

    @staticmethod
    async def get_current(db: AsyncSession, tenant_id: int) -> ConversationReadStatusResponse:
        row = await ConversationReadStatusRepository.get_by_tenant(db, tenant_id)
        if not row:
            return ConversationReadStatusService._default_response(tenant_id)
        return ConversationReadStatusService._row_to_response(row)

    @staticmethod
    async def save(
        db: AsyncSession,
        tenant_id: int,
        current_user: dict,
        payload: ConversationReadStatusPayload,
    ) -> ConversationReadStatusResponse:
        row = await ConversationReadStatusRepository.save(
            db,
            tenant_id,
            {
                "agent_workspace_enabled": payload.agent_workspace_enabled,
                "web_sdk_enabled": payload.web_sdk_enabled,
                "updated_by_id": current_user.get("user_id"),
                "updated_by_name": ConversationReadStatusService._actor_name(current_user),
            },
        )
        return ConversationReadStatusService._row_to_response(row)

    @staticmethod
    async def get_target(
        db: AsyncSession,
        tenant_id: int,
        target: str,
    ) -> ConversationReadStatusTargetResponse:
        row = await ConversationReadStatusRepository.get_by_tenant(db, tenant_id)
        configured = row is not None
        payload = (
            ConversationReadStatusService._row_to_payload(row)
            if row
            else ConversationReadStatusService.default_payload()
        )
        enabled = payload.agent_workspace_enabled if target == "agent_workspace" else payload.web_sdk_enabled
        return ConversationReadStatusTargetResponse(
            target="agent_workspace" if target == "agent_workspace" else "web_sdk",
            configured=configured,
            enabled=enabled,
            updated_at=row.updated_at if row else None,
        )

    @staticmethod
    async def get_public_config(db: AsyncSession, tenant_id: int) -> ConversationReadStatusPublicResponse:
        target = await ConversationReadStatusService.get_target(db, tenant_id, "web_sdk")
        return ConversationReadStatusPublicResponse(web_sdk_enabled=target.enabled)
