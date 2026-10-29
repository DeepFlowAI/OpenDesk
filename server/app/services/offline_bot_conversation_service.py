"""Shared idle Web bot cleanup for agent-initiated conversations."""
import logging

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ConversationStatus
from app.models.conversation import Conversation
from app.repositories.conversation_repository import ConversationRepository
from app.services.conversation_realtime_service import ConversationRealtimeService
from app.services.visitor_web_status_service import VisitorWebStatusService

logger = logging.getLogger(__name__)


class OfflineBotConversationService:
    @staticmethod
    async def check(
        db: AsyncSession, r: aioredis.Redis, conversation: Conversation, *, source: str,
    ) -> str:
        count = None
        web_status = "unknown"
        reason = "not_unassigned_bot"
        if conversation.status == ConversationStatus.BOT.value and conversation.agent_id is None:
            count = await ConversationRepository.count_active_visitor_conversations(
                db, tenant_id=conversation.tenant_id,
                visitor_id=conversation.visitor_id, channel_id=conversation.channel_id,
            )
            reason = "multiple_active" if count != 1 else "visitor_unavailable"
            if count == 1 and VisitorWebStatusService.can_display(conversation):
                try:
                    web_status = await VisitorWebStatusService.get_status(
                        r, conversation.tenant_id, int(conversation.channel_id),
                        conversation.visitor.external_id,
                    )
                except Exception:
                    logger.exception("offline_bot_status_failed source=%s conversation_id=%s", source, conversation.id)
                reason = {"offline": "eligible", "online": "online"}.get(web_status, "status_unavailable")
        logger.info(
            "offline_bot_cleanup_checked source=%s tenant_id=%s conversation_id=%s "
            "visitor_id=%s active_count=%s web_status=%s reason=%s",
            source, conversation.tenant_id, conversation.id, conversation.visitor_id,
            count, web_status, reason,
        )
        return reason

    @staticmethod
    async def close(db: AsyncSession, conversation: Conversation, *, ended_by: str) -> None:
        await ConversationRepository.end_conversation(db, conversation, ended_by, commit=False)

    @staticmethod
    async def emit_closed(conversation: Conversation, *, ended_by: str) -> None:
        try:
            from app.libs.realtime import get_realtime_transport

            rt = get_realtime_transport()
        except RuntimeError:
            return
        payload = {
            "conversation_id": conversation.id,
            "conversation_public_id": conversation.public_id,
            "ended_by": ended_by,
        }
        try:
            for namespace in ("/chat", "/visitor"):
                await rt.emit("conversation_ended", payload, room=f"conv:{conversation.id}", namespace=namespace)
            await ConversationRealtimeService.emit_conversation_list_updated(
                conversation.tenant_id, action="ended", conversation_id=conversation.id, rt=rt,
            )
        except Exception:
            logger.exception("offline_bot_close_notify_failed conversation_id=%s ended_by=%s", conversation.id, ended_by)
