"""
Push Socket.IO events to a call-center agent's browser room.

Orchestrator and CallControlService both need this; keep the room/namespace
convention in one place (see constants.agent_socket_room / CcSocketEvent).
"""
from __future__ import annotations

import logging
from typing import Any

from app.constants.call_center import agent_socket_room

logger = logging.getLogger(__name__)

_CHAT_NAMESPACE = "/chat"


async def emit_to_agent(
    *,
    tenant_id: int,
    employee_id: int,
    method: str,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Emit ``method`` to ``agent:{tenant}:{employee}`` under /chat.

    Returns True on success. Failures are logged and return False — callers
    treat push as best-effort.
    """
    try:
        from app.libs.realtime import get_realtime_transport

        rt = get_realtime_transport()
        room = agent_socket_room(tenant_id, employee_id)
        await rt.emit(
            method,
            payload if payload is not None else {},
            room=room,
            namespace=_CHAT_NAMESPACE,
        )
        return True
    except Exception:  # noqa: BLE001
        logger.exception(
            "%s push failed agent=%s/%s", method, tenant_id, employee_id
        )
        return False
