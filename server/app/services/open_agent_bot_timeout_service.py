"""
OpenAgent bot conversation idle timeout service.
"""
from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.enums import ConversationStatus
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services.conversation_realtime_service import ConversationRealtimeService

logger = logging.getLogger(__name__)

OPEN_AGENT_BOT_TIMEOUT_ENDED_BY = "bot_timeout"


class OpenAgentBotTimeoutService:
    """Close idle bot conversations after the last bot-side activity times out."""

    @staticmethod
    async def is_stale(
        db: AsyncSession,
        conversation,
        *,
        now: datetime | None = None,
    ) -> bool:
        if not conversation or conversation.status != ConversationStatus.BOT.value:
            return False

        latest_bot_activity = await MessageRepository.get_latest_open_agent_bot_activity(
            db,
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
        )
        if not latest_bot_activity or not latest_bot_activity.created_at:
            return False

        checked_at = now or datetime.now(timezone.utc)
        timeout_at = latest_bot_activity.created_at + timedelta(
            seconds=settings.OPEN_AGENT_BOT_TIMEOUT_SECONDS
        )
        if timeout_at > checked_at:
            return False

        return not await MessageRepository.has_visitor_message_after(
            db,
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            anchor_message_id=latest_bot_activity.id,
            anchor_created_at=latest_bot_activity.created_at,
        )

    @staticmethod
    async def close_if_stale(
        db: AsyncSession,
        conversation,
        *,
        now: datetime | None = None,
    ) -> bool:
        checked_at = now or datetime.now(timezone.utc)
        if not await OpenAgentBotTimeoutService.is_stale(db, conversation, now=checked_at):
            return False

        conversation = await ConversationRepository.end_conversation(
            db,
            conversation,
            OPEN_AGENT_BOT_TIMEOUT_ENDED_BY,
        )
        await OpenAgentBotTimeoutService._emit_conversation_ended(conversation)
        logger.info(
            "open_agent_bot_timeout_closed tenant_id=%s conversation_id=%s "
            "visitor_id=%s timeout_seconds=%s closed_at=%s",
            conversation.tenant_id,
            conversation.id,
            conversation.visitor_id,
            settings.OPEN_AGENT_BOT_TIMEOUT_SECONDS,
            checked_at.isoformat(),
        )
        return True

    @staticmethod
    async def process_expired_conversations(
        db: AsyncSession,
        *,
        now: datetime | None = None,
        limit: int | None = None,
    ) -> dict[str, int]:
        checked_at = now or datetime.now(timezone.utc)
        cutoff_at = checked_at - timedelta(seconds=settings.OPEN_AGENT_BOT_TIMEOUT_SECONDS)
        conversations = await ConversationRepository.list_stale_open_agent_bot_conversations(
            db,
            cutoff_at=cutoff_at,
            limit=limit or settings.OPEN_AGENT_BOT_TIMEOUT_SCAN_BATCH_SIZE,
        )
        result = {"checked": len(conversations), "closed": 0, "skipped": 0}
        for conversation in conversations:
            if await OpenAgentBotTimeoutService.close_if_stale(db, conversation, now=checked_at):
                result["closed"] += 1
            else:
                result["skipped"] += 1
        return result

    @staticmethod
    async def _emit_conversation_ended(conversation) -> None:
        try:
            from app.libs.realtime import get_realtime_transport

            rt = get_realtime_transport()
        except RuntimeError:
            return

        payload = {
            "conversation_id": conversation.id,
            "conversation_public_id": conversation.public_id,
            "ended_by": OPEN_AGENT_BOT_TIMEOUT_ENDED_BY,
        }
        conv_room = f"conv:{conversation.id}"
        await rt.emit("conversation_ended", payload, room=conv_room, namespace="/chat")
        await rt.emit("conversation_ended", payload, room=conv_room, namespace="/visitor")
        await ConversationRealtimeService.emit_conversation_list_updated(
            conversation.tenant_id,
            action="ended",
            conversation_id=conversation.id,
            rt=rt,
        )
