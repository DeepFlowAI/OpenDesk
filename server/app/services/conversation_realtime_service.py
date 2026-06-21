"""
Realtime notifications for conversation list changes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.libs.realtime import get_realtime_transport
from app.libs.realtime.base import BaseRealtimeTransport

logger = logging.getLogger(__name__)


class ConversationRealtimeService:
    """Emit lightweight conversation list invalidation events to agent workspaces."""

    EVENT_NAME = "conversation_list_updated"
    NAMESPACE = "/chat"

    @staticmethod
    def peers_list_room(tenant_id: int) -> str:
        return f"workspace:{tenant_id}:conversation:peers:list"

    @staticmethod
    async def emit_conversation_list_updated(
        tenant_id: int,
        *,
        action: str,
        conversation_id: int | None = None,
        rt: BaseRealtimeTransport | None = None,
        message_flow_id: str | None = None,
    ) -> None:
        payload = {
            "action": action,
            "conversation_id": conversation_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if message_flow_id:
            payload["message_flow_id"] = message_flow_id
        try:
            transport = rt or get_realtime_transport()
        except RuntimeError:
            logger.debug("Realtime transport is not initialized; conversation list update event skipped")
            return

        room = ConversationRealtimeService.peers_list_room(tenant_id)
        try:
            await transport.emit(
                ConversationRealtimeService.EVENT_NAME,
                payload,
                room=room,
                namespace=ConversationRealtimeService.NAMESPACE,
            )
        except Exception:
            logger.exception(
                "workspace_realtime_emit_failed event=%s tenant_id=%s action=%s "
                "conversation_id=%s room=%s namespace=%s message_flow_id=%s",
                ConversationRealtimeService.EVENT_NAME,
                tenant_id,
                action,
                conversation_id,
                room,
                ConversationRealtimeService.NAMESPACE,
                message_flow_id,
            )
            return
        logger.info(
            "workspace_realtime_emit_succeeded event=%s tenant_id=%s action=%s "
            "conversation_id=%s room=%s namespace=%s message_flow_id=%s",
            ConversationRealtimeService.EVENT_NAME,
            tenant_id,
            action,
            conversation_id,
            room,
            ConversationRealtimeService.NAMESPACE,
            message_flow_id,
        )
