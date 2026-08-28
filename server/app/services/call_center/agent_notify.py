"""
Push Socket.IO events to a call-center agent's browser room.

Orchestrator and CallControlService both need this; keep the room/namespace
convention in one place (see constants.agent_socket_room / CcSocketEvent).
"""
from __future__ import annotations

import logging
from typing import Any

from app.constants.call_center import agent_socket_room, embedded_call_socket_room

logger = logging.getLogger(__name__)

_CHAT_NAMESPACE = "/chat"

# Media and transcript pushes fire tens to hundreds of times per call, so they
# are emitted without a log line. Everything else is a call-lifecycle push the
# agent workspace depends on to leave a phase, and is worth recording: pairing
# it with the browser-side telemetry event shows whether a desk stuck on the
# wrong phase never received the push, or received it and ignored it.
_UNLOGGED_METHODS = frozenset({"cc.webrtc.ice", "cc.transcript"})


async def emit_to_agent(
    *,
    tenant_id: int,
    employee_id: int,
    method: str,
    payload: dict[str, Any] | None = None,
    transport: Any | None = None,
) -> bool:
    """Emit a call event to workspace and embedded-call agent rooms.

    Returns True on success. Failures are logged and return False — callers
    treat push as best-effort.
    """
    try:
        from app.libs.realtime import get_realtime_transport

        rt = transport or get_realtime_transport()
        rooms = (
            agent_socket_room(tenant_id, employee_id),
            embedded_call_socket_room(tenant_id, employee_id),
        )
        for room in rooms:
            await rt.emit(
                method,
                payload if payload is not None else {},
                room=room,
                namespace=_CHAT_NAMESPACE,
            )
        if method not in _UNLOGGED_METHODS:
            data = payload or {}
            logger.info(
                "%s pushed agent=%s/%s call=%s",
                method,
                tenant_id,
                employee_id,
                data.get("call_id") or data.get("customer_call_id"),
            )
        return True
    except Exception:  # noqa: BLE001
        logger.exception(
            "%s push failed agent=%s/%s", method, tenant_id, employee_id
        )
        return False
