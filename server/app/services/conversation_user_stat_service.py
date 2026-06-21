"""
Workspace user statistic display settings and scoped counts.
"""
from collections.abc import Awaitable, Callable
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.conversation_user_stat_repository import ConversationUserStatRepository
from app.schemas.conversation_user_statistics import (
    ConversationUserStatFieldSettingsPayload,
    ConversationUserStatFieldSettingsResponse,
    ConversationUserStatisticItem,
    ConversationUserStatisticsResponse,
)
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_service import ConversationService
from app.services.data_scope_service import (
    DataScopeService,
    RESOURCE_SESSION_RECORD,
)

logger = logging.getLogger(__name__)


class ConversationUserStatService:
    @staticmethod
    def _actor_name(current_user: dict) -> str | None:
        for key in ("display_name", "name", "username", "email"):
            value = current_user.get(key)
            if value:
                return str(value)[:128]
        return None

    @staticmethod
    def default_payload() -> ConversationUserStatFieldSettingsPayload:
        return ConversationUserStatFieldSettingsPayload()

    @staticmethod
    def _default_response(tenant_id: int) -> ConversationUserStatFieldSettingsResponse:
        data = ConversationUserStatService.default_payload().model_dump()
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
        return ConversationUserStatFieldSettingsResponse.model_validate(data)

    @staticmethod
    def _row_to_response(row) -> ConversationUserStatFieldSettingsResponse:
        return ConversationUserStatFieldSettingsResponse.model_validate(
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "configured": True,
                "show_session_count": row.show_session_count,
                "show_call_count": row.show_call_count,
                "show_unresolved_ticket_count": row.show_unresolved_ticket_count,
                "show_total_ticket_count": row.show_total_ticket_count,
                "updated_by_id": row.updated_by_id,
                "updated_by_name": row.updated_by_name,
                "updated_at": row.updated_at,
            }
        )

    @staticmethod
    async def get_settings(
        db: AsyncSession,
        tenant_id: int,
    ) -> ConversationUserStatFieldSettingsResponse:
        row = await ConversationUserStatRepository.get_settings_by_tenant(db, tenant_id)
        if not row:
            return ConversationUserStatService._default_response(tenant_id)
        return ConversationUserStatService._row_to_response(row)

    @staticmethod
    async def save_settings(
        db: AsyncSession,
        tenant_id: int,
        current_user: dict,
        payload: ConversationUserStatFieldSettingsPayload,
    ) -> ConversationUserStatFieldSettingsResponse:
        row = await ConversationUserStatRepository.save_settings(
            db,
            tenant_id,
            {
                **payload.model_dump(),
                "updated_by_id": current_user.get("user_id"),
                "updated_by_name": ConversationUserStatService._actor_name(current_user),
            },
        )
        return ConversationUserStatService._row_to_response(row)

    @staticmethod
    async def _safe_count(db: AsyncSession, counter: Callable[[], Awaitable[int]]) -> int | None:
        try:
            return await counter()
        except Exception:
            await db.rollback()
            logger.exception("Failed to load workspace user statistic")
            return None

    @staticmethod
    async def get_statistics(
        db: AsyncSession,
        conversation_id: int,
        principal: EffectivePrincipal,
    ) -> ConversationUserStatisticsResponse:
        conversation = await ConversationService.get_agent_conversation(
            db,
            conversation_id=conversation_id,
            tenant_id=principal.tenant_id,
            agent_id=principal.user_id,
            principal=principal,
        )
        visitor = conversation.get("visitor")
        user_id = getattr(visitor, "id", None)
        if not user_id:
            return ConversationUserStatisticsResponse(conversation_id=conversation_id, user_id=None, items=[])

        settings = await ConversationUserStatService.get_settings(db, principal.tenant_id)
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        items: list[ConversationUserStatisticItem] = []

        if settings.show_call_count and principal.has_permission("call.record.view"):
            call_predicate = DataScopeService.build_call_record_predicate(principal, peer_ids)
            calls = await ConversationUserStatService._safe_count(
                db,
                lambda: ConversationUserStatRepository.count_calls(
                    db,
                    principal.tenant_id,
                    user_id,
                    call_predicate,
                ),
            )
            items.append(ConversationUserStatisticItem(key="calls", value=calls))

        if settings.show_session_count and principal.has_permission("chat.session_record.view"):
            session_predicate = DataScopeService.build_session_record_predicate(
                principal,
                peer_ids,
                RESOURCE_SESSION_RECORD,
            )
            sessions = await ConversationUserStatService._safe_count(
                db,
                lambda: ConversationUserStatRepository.count_sessions(
                    db,
                    principal.tenant_id,
                    user_id,
                    session_predicate,
                ),
            )
            items.append(ConversationUserStatisticItem(key="sessions", value=sessions))

        show_ticket_item = (
            (settings.show_unresolved_ticket_count or settings.show_total_ticket_count)
            and principal.has_permission("ticket.workspace.view")
        )
        if show_ticket_item:
            ticket_predicate = DataScopeService.build_ticket_predicate(principal, peer_ids)
            unresolved = None
            total = None
            if settings.show_unresolved_ticket_count:
                unresolved = await ConversationUserStatService._safe_count(
                    db,
                    lambda: ConversationUserStatRepository.count_tickets(
                        db,
                        principal.tenant_id,
                        user_id,
                        unresolved_only=True,
                        scope_predicate=ticket_predicate,
                    ),
                )
            if settings.show_total_ticket_count:
                total = await ConversationUserStatService._safe_count(
                    db,
                    lambda: ConversationUserStatRepository.count_tickets(
                        db,
                        principal.tenant_id,
                        user_id,
                        scope_predicate=ticket_predicate,
                    ),
                )
            items.append(ConversationUserStatisticItem(key="tickets", unresolved_value=unresolved, total_value=total))

        return ConversationUserStatisticsResponse(conversation_id=conversation_id, user_id=user_id, items=items)
