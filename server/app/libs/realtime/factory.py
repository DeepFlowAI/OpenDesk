"""
Realtime transport factory — creates the configured provider instance.
"""
from app.configs.settings import settings
from app.libs.realtime.base import BaseRealtimeTransport


_instance: BaseRealtimeTransport | None = None


def create_realtime_transport() -> BaseRealtimeTransport:
    """Return a singleton realtime transport instance."""
    global _instance
    if _instance is not None:
        return _instance

    provider = settings.REALTIME_PROVIDER
    match provider:
        case "socketio":
            from app.libs.realtime.providers.socketio_transport import SocketIOTransport

            _instance = SocketIOTransport()
        case _:
            raise ValueError(f"Unsupported realtime provider: {provider}")
    return _instance


def get_realtime_transport() -> BaseRealtimeTransport:
    """Get the existing singleton instance (raises if not yet created)."""
    if _instance is None:
        raise RuntimeError("Realtime transport not initialized. Call create_realtime_transport() first.")
    return _instance
