"""
Visitor Web status service.

Tracks visitor-side Web SDK Socket.IO connections in Redis and exposes the
agent-facing status for a workspace conversation.
"""
import logging
from datetime import datetime, timezone
from typing import Literal

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.enums import ConversationStatus
from app.libs.realtime.base import BaseRealtimeTransport
from app.models.conversation import Conversation
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import DataScopeService

logger = logging.getLogger(__name__)

CHAT_NAMESPACE = "/chat"
VISITOR_WEB_STATUS_EVENT = "visitor_web_status_updated"
VISITOR_WEB_DISCONNECT_GRACE_SECONDS = 3

VisitorWebStatus = Literal["online", "offline", "unknown"]

_CONNECTIONS_KEY = "visitor:web:connections:{tenant_id}:{channel_id}:{visitor_external_id}"


class VisitorWebStatusService:
    """Manage visitor Web SDK connection state."""

    @staticmethod
    def _key(tenant_id: int, channel_id: int, visitor_external_id: str) -> str:
        return _CONNECTIONS_KEY.format(
            tenant_id=tenant_id,
            channel_id=channel_id,
            visitor_external_id=visitor_external_id,
        )

    @staticmethod
    def is_web_conversation(conversation: Conversation) -> bool:
        channel_type = getattr(conversation.channel, "channel_type", None)
        return str(channel_type or "").lower() == "web"

    @staticmethod
    def can_display(conversation: Conversation) -> bool:
        visitor_external_id = getattr(conversation.visitor, "external_id", None)
        return bool(
            VisitorWebStatusService.is_web_conversation(conversation)
            and conversation.channel_id
            and visitor_external_id
        )

    @staticmethod
    async def mark_connected(
        r: aioredis.Redis,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
        sid: str,
    ) -> None:
        """Record an active visitor Web SDK socket connection."""
        key = VisitorWebStatusService._key(tenant_id, channel_id, visitor_external_id)
        await r.sadd(key, sid)

    @staticmethod
    async def mark_disconnected(
        r: aioredis.Redis,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
        sid: str,
    ) -> VisitorWebStatus:
        """Remove a visitor socket connection and return the resulting status."""
        key = VisitorWebStatusService._key(tenant_id, channel_id, visitor_external_id)
        await r.srem(key, sid)
        count = await r.scard(key)
        if count <= 0:
            await r.delete(key)
            return "offline"
        return "online"

    @staticmethod
    async def get_status(
        r: aioredis.Redis,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
    ) -> VisitorWebStatus:
        """Return online when any Web SDK connection remains for the visitor."""
        key = VisitorWebStatusService._key(tenant_id, channel_id, visitor_external_id)
        return "online" if await r.scard(key) > 0 else "offline"

    @staticmethod
    def _response(
        conversation_id: int,
        status: VisitorWebStatus,
        can_display: bool,
    ) -> dict:
        return {
            "conversation_id": conversation_id,
            "status": status,
            "can_display": can_display,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    async def build_status_response(
        r: aioredis.Redis,
        conversation: Conversation,
    ) -> dict:
        """Build the response payload for a loaded conversation."""
        if not VisitorWebStatusService.can_display(conversation):
            return VisitorWebStatusService._response(
                conversation.id,
                "unknown",
                False,
            )

        try:
            status = await VisitorWebStatusService.get_status(
                r,
                conversation.tenant_id,
                int(conversation.channel_id),
                conversation.visitor.external_id,
            )
        except Exception:
            logger.exception(
                "Failed to read visitor Web status for conversation=%s",
                conversation.id,
            )
            status = "unknown"

        return VisitorWebStatusService._response(
            conversation.id,
            status,
            True,
        )

    @staticmethod
    async def get_conversation_status(
        db: AsyncSession,
        r: aioredis.Redis,
        conversation_id: int,
        tenant_id: int,
        agent_id: int,
        roles: list[str] | None = None,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        """Return visitor Web status for an agent-authorized conversation."""
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")

        if principal is not None:
            await DataScopeService.assert_conversation_access(db, principal, conversation)
        else:
            can_view_all = "admin" in (roles or ["agent"])
            if not can_view_all and conversation.agent_id != agent_id:
                raise ForbiddenError("No permission to view conversation")

        return await VisitorWebStatusService.build_status_response(r, conversation)

    @staticmethod
    async def get_active_conversation_for_visitor(
        db: AsyncSession,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
    ) -> Conversation | None:
        """Load the active workspace conversation for a visitor context."""
        visitor = await UserRepository.get_by_external_id(
            db,
            tenant_id,
            visitor_external_id,
        )
        if not visitor:
            return None
        conversation = await ConversationRepository.get_active_visitor_conversation(
            db,
            tenant_id=tenant_id,
            visitor_id=visitor.id,
            channel_id=channel_id,
        )
        if not conversation or conversation.status == ConversationStatus.CLOSED.value:
            return None
        return conversation

    @staticmethod
    async def emit_status_for_conversation(
        rt: BaseRealtimeTransport,
        r: aioredis.Redis,
        conversation: Conversation,
    ) -> None:
        """Push a status snapshot to the assigned agent, if any."""
        try:
            if not conversation.agent_id:
                return
            payload = await VisitorWebStatusService.build_status_response(r, conversation)
            if not payload["can_display"]:
                return
            agent_room = f"agent:{conversation.tenant_id}:{conversation.agent_id}"
            await rt.emit(
                VISITOR_WEB_STATUS_EVENT,
                payload,
                room=agent_room,
                namespace=CHAT_NAMESPACE,
            )
        except Exception:
            logger.exception(
                "Failed to emit visitor Web status for conversation=%s",
                getattr(conversation, "id", None),
            )

    @staticmethod
    async def emit_status_for_visitor_context(
        rt: BaseRealtimeTransport,
        r: aioredis.Redis,
        db: AsyncSession,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
    ) -> None:
        """Push the status for the visitor's active conversation, if assigned."""
        try:
            conversation = await VisitorWebStatusService.get_active_conversation_for_visitor(
                db,
                tenant_id=tenant_id,
                channel_id=channel_id,
                visitor_external_id=visitor_external_id,
            )
            if conversation:
                await VisitorWebStatusService.emit_status_for_conversation(rt, r, conversation)
        except Exception:
            logger.exception(
                "Failed to emit visitor Web status for tenant=%s channel=%s visitor=%s",
                tenant_id,
                channel_id,
                visitor_external_id,
            )
