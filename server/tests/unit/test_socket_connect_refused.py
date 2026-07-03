"""Guard against a subtle Socket.IO regression.

The connect handlers must raise ``socketio.exceptions.ConnectionRefusedError``
(which forwards the rejection reason to the client), never the builtin
``ConnectionRefusedError`` (an ``OSError``). With the builtin, python-socketio
sends a generic "Connection refused by server" and the web client can no longer
recognize the auth failure, so it never stops its reconnect loop.
"""
import socketio.exceptions as socketio_exceptions

from app.socketio import chat_handlers, visitor_handlers


def test_chat_handler_uses_socketio_connection_refused_error():
    assert (
        chat_handlers.ConnectionRefusedError
        is socketio_exceptions.ConnectionRefusedError
    )


def test_visitor_handler_uses_socketio_connection_refused_error():
    assert (
        visitor_handlers.ConnectionRefusedError
        is socketio_exceptions.ConnectionRefusedError
    )


def test_rejection_reason_reaches_client_payload():
    # error_args is what python-socketio sends to the client; the web guard keys
    # off err.message, so the reason must land under "message".
    err = socketio_exceptions.ConnectionRefusedError("Invalid visitor session")
    assert err.error_args == {"message": "Invalid visitor session"}
