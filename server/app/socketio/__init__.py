"""
Socket.IO event handlers registration.
"""
from app.libs.realtime import get_realtime_transport


def register_socketio_handlers() -> None:
    """Register all Socket.IO namespace handlers on the realtime transport."""
    rt = get_realtime_transport()

    from app.socketio.chat_handlers import register_chat_handlers
    from app.socketio.visitor_handlers import register_visitor_handlers

    register_chat_handlers(rt)
    register_visitor_handlers(rt)
