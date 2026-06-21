"""
Realtime notifications for offline message changes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.libs.realtime import get_realtime_transport
from app.models.offline_message import OfflineMessage

logger = logging.getLogger(__name__)


class OfflineMessageRealtimeService:
    """Emit lightweight offline-message invalidation events to agent workspaces."""

    COUNT_EVENT_NAME = "offline_count_updated"
    LIST_EVENT_NAME = "offline_list_updated"
    NAMESPACE = "/chat"

    @staticmethod
    def count_room(tenant_id: int) -> str:
        return f"workspace:{tenant_id}:offline:count"

    @staticmethod
    def list_room(tenant_id: int) -> str:
        return f"workspace:{tenant_id}:offline:list"

    @staticmethod
    async def emit_updated(
        row: OfflineMessage,
        *,
        action: str,
    ) -> None:
        payload = {
            "action": action,
            "offline_message_id": row.id,
            "offline_message_public_id": row.public_id,
            "status": row.status,
            "target_group_id": row.target_group_id,
            "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
            "message_count": row.message_count,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            rt = get_realtime_transport()
        except RuntimeError:
            logger.debug("Realtime transport is not initialized; offline message update event skipped")
            return

        events = [
            (
                OfflineMessageRealtimeService.LIST_EVENT_NAME,
                OfflineMessageRealtimeService.list_room(row.tenant_id),
            )
        ]
        if action != "message":
            events.append(
                (
                    OfflineMessageRealtimeService.COUNT_EVENT_NAME,
                    OfflineMessageRealtimeService.count_room(row.tenant_id),
                )
            )
        for event_name, room in events:
            try:
                await rt.emit(
                    event_name,
                    payload,
                    room=room,
                    namespace=OfflineMessageRealtimeService.NAMESPACE,
                )
                logger.info(
                    "workspace_realtime_emit_succeeded event=%s tenant_id=%s action=%s "
                    "offline_message_id=%s room=%s namespace=%s",
                    event_name,
                    row.tenant_id,
                    action,
                    row.id,
                    room,
                    OfflineMessageRealtimeService.NAMESPACE,
                )
            except Exception:
                logger.exception(
                    "workspace_realtime_emit_failed event=%s tenant_id=%s action=%s "
                    "offline_message_id=%s room=%s namespace=%s",
                    event_name,
                    row.tenant_id,
                    action,
                    row.id,
                    room,
                    OfflineMessageRealtimeService.NAMESPACE,
                )
