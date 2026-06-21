"""
Realtime notifications for queue task changes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.libs.realtime import get_realtime_transport

logger = logging.getLogger(__name__)


class QueueRealtimeService:
    """Emit lightweight queue invalidation events to agent workspaces."""

    COUNT_EVENT_NAME = "queue_count_updated"
    LIST_EVENT_NAME = "queue_list_updated"
    NAMESPACE = "/chat"

    @staticmethod
    def count_room(tenant_id: int) -> str:
        return f"workspace:{tenant_id}:queue:count"

    @staticmethod
    def list_room(tenant_id: int) -> str:
        return f"workspace:{tenant_id}:queue:list"

    @staticmethod
    async def emit_queue_updated(
        tenant_id: int,
        *,
        action: str,
        task_id: int | None = None,
        queue_type: str | None = None,
        queue_id: int | None = None,
    ) -> None:
        payload = {
            "action": action,
            "task_id": task_id,
            "queue_type": queue_type,
            "queue_id": queue_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            rt = get_realtime_transport()
        except RuntimeError:
            logger.debug("Realtime transport is not initialized; queue update event skipped")
            return

        for event_name, room in (
            (
                QueueRealtimeService.COUNT_EVENT_NAME,
                QueueRealtimeService.count_room(tenant_id),
            ),
            (
                QueueRealtimeService.LIST_EVENT_NAME,
                QueueRealtimeService.list_room(tenant_id),
            ),
        ):
            try:
                await rt.emit(
                    event_name,
                    payload,
                    room=room,
                    namespace=QueueRealtimeService.NAMESPACE,
                )
                logger.info(
                    "workspace_realtime_emit_succeeded event=%s tenant_id=%s action=%s "
                    "queue_task_id=%s queue_type=%s queue_id=%s room=%s namespace=%s",
                    event_name,
                    tenant_id,
                    action,
                    task_id,
                    queue_type,
                    queue_id,
                    room,
                    QueueRealtimeService.NAMESPACE,
                )
            except Exception:
                logger.exception(
                    "workspace_realtime_emit_failed event=%s tenant_id=%s action=%s "
                    "queue_task_id=%s queue_type=%s queue_id=%s room=%s namespace=%s",
                    event_name,
                    tenant_id,
                    action,
                    task_id,
                    queue_type,
                    queue_id,
                    room,
                    QueueRealtimeService.NAMESPACE,
                )
