"""
Abstract base class for realtime transport implementations.

Provides a pluggable interface for bidirectional real-time communication
between server and clients.  Current implementation: Socket.IO.
"""
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, overload


class BaseRealtimeTransport(ABC):
    """Abstract bidirectional realtime transport with room semantics."""

    @abstractmethod
    def wrap_asgi(self, app: Any) -> Any:
        """Wrap the ASGI application to add realtime capabilities.

        Returns the wrapped ASGI app that should be used by the server.
        """
        ...

    @abstractmethod
    async def emit(
        self,
        event: str,
        data: Any,
        *,
        room: str | None = None,
        to: str | None = None,
        namespace: str | None = None,
    ) -> None:
        """Emit an event to a room, a specific sid, or broadcast."""
        ...

    @abstractmethod
    async def join_room(self, sid: str, room: str, namespace: str | None = None) -> None:
        """Add a client to a room."""
        ...

    @abstractmethod
    async def leave_room(self, sid: str, room: str, namespace: str | None = None) -> None:
        """Remove a client from a room."""
        ...

    @abstractmethod
    def on(self, event: str, handler: Callable | None = None, namespace: str | None = None) -> Any:
        """Register an event handler.

        Can be used as a direct call: ``transport.on('event', handler, namespace='/ns')``
        or as a decorator: ``@transport.on('event', namespace='/ns')``.
        """
        ...

    @abstractmethod
    async def disconnect(self, sid: str, namespace: str | None = None) -> None:
        """Forcibly disconnect a client."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release resources held by the transport."""
        ...

    @abstractmethod
    async def get_session(self, sid: str, namespace: str | None = None) -> dict:
        """Retrieve session data for a connected client."""
        ...

    @abstractmethod
    async def save_session(self, sid: str, session: dict, namespace: str | None = None) -> None:
        """Persist session data for a connected client."""
        ...
