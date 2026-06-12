"""
Socket.IO implementation of BaseRealtimeTransport.

Uses python-socketio in async mode.  When REDIS_URL is configured, a Redis
manager is attached so that events are broadcast across all instances in the
cluster.
"""
import logging
from collections.abc import Callable
from typing import Any

import socketio

from app.configs.settings import settings
from app.libs.realtime.base import BaseRealtimeTransport

logger = logging.getLogger(__name__)


class SocketIOTransport(BaseRealtimeTransport):
    """Socket.IO backed realtime transport with optional Redis clustering."""

    def __init__(self) -> None:
        mgr: socketio.AsyncManager | None = None
        if settings.REDIS_URL:
            mgr = socketio.AsyncRedisManager(settings.REDIS_URL)
            logger.info("Socket.IO using Redis manager for cluster support")

        # Mirror the REST CORS policy: "*" (any origin) unless an explicit
        # allowlist is configured via CORS_ALLOW_ORIGINS.
        cors_origins = settings.cors_origins
        self._sio = socketio.AsyncServer(
            async_mode="asgi",
            cors_allowed_origins="*" if cors_origins == ["*"] else cors_origins,
            client_manager=mgr,
            logger=False,
            engineio_logger=False,
            ping_interval=settings.SOCKETIO_PING_INTERVAL,
            ping_timeout=settings.SOCKETIO_PING_TIMEOUT,
        )
        self._asgi_app: socketio.ASGIApp | None = None

    @property
    def server(self) -> socketio.AsyncServer:
        """Direct access to the underlying AsyncServer for advanced usage."""
        return self._sio

    # -- ASGI integration ------------------------------------------------------

    def wrap_asgi(self, app: Any) -> Any:
        self._asgi_app = socketio.ASGIApp(self._sio, other_asgi_app=app)
        logger.info("Socket.IO mounted onto ASGI application")
        return self._asgi_app

    # -- emit ------------------------------------------------------------------

    async def emit(
        self,
        event: str,
        data: Any,
        *,
        room: str | None = None,
        to: str | None = None,
        namespace: str | None = None,
    ) -> None:
        await self._sio.emit(event, data, room=room or to, namespace=namespace)

    # -- room management -------------------------------------------------------

    async def join_room(self, sid: str, room: str, namespace: str | None = None) -> None:
        await self._sio.enter_room(sid, room, namespace=namespace)

    async def leave_room(self, sid: str, room: str, namespace: str | None = None) -> None:
        await self._sio.leave_room(sid, room, namespace=namespace)

    # -- event registration ----------------------------------------------------

    def on(self, event: str, handler: Callable | None = None, namespace: str | None = None) -> Any:
        if handler is not None:
            self._sio.on(event, handler=handler, namespace=namespace)
            return None
        # Decorator usage: @transport.on('event', namespace='/ns')
        def decorator(fn: Callable) -> Callable:
            self._sio.on(event, handler=fn, namespace=namespace)
            return fn
        return decorator

    # -- session management ----------------------------------------------------

    async def get_session(self, sid: str, namespace: str | None = None) -> dict:
        return await self._sio.get_session(sid, namespace=namespace) or {}

    async def save_session(self, sid: str, session: dict, namespace: str | None = None) -> None:
        await self._sio.save_session(sid, session, namespace=namespace)

    # -- disconnect / close ----------------------------------------------------

    async def disconnect(self, sid: str, namespace: str | None = None) -> None:
        await self._sio.disconnect(sid, namespace=namespace)

    async def close(self) -> None:
        logger.info("Socket.IO transport closed")
