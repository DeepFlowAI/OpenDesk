from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.core.exceptions import BusinessError, ForbiddenError
from app.db.deps import embedded_call_http_access_allowed, get_current_user
from app.services.call_center import orchestrator as orch_module
from app.socketio import chat_handlers


class _SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_exc):
        return False


class _RealtimeHarness:
    def __init__(self, session: dict | None = None):
        self.handlers = {}
        self.session = session or {}
        self.join_room = AsyncMock()
        self.leave_room = AsyncMock()

    def on(self, event, handler=None, namespace=None):
        if handler is not None:
            self.handlers[(namespace, event)] = handler
            return None

        def decorator(fn):
            self.handlers[(namespace, event)] = fn
            return fn

        return decorator

    async def save_session(self, _sid, session, namespace=None):
        self.session = session

    async def get_session(self, _sid, namespace=None):
        return self.session


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/call-center/agent-status/me"),
        ("POST", "/api/v1/call-center/embed/control/acquire"),
        ("GET", "/api/v1/call-center/embed/commands/eccmd_1"),
        ("POST", "/api/v1/call-center/agents/me/current-call/hangup"),
        ("POST", "/api/v1/call-center/agents/me/dial"),
        ("GET", "/api/v1/call-center/agents/me/current-call/satisfaction"),
        ("POST", "/api/v1/call-center/agents/me/current-call/satisfaction/invite"),
        ("GET", "/api/v1/call-center/sms/workspace/templates"),
        ("POST", "/api/v1/call-center/sms/send"),
    ],
)
def test_embedded_session_allows_only_call_runtime_endpoints(method, path):
    assert embedded_call_http_access_allowed(method, path) is True


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/employees"),
        ("GET", "/api/v1/call-center/embedded-call-integrations"),
        ("GET", "/api/v1/call-center/embed/commands/eccmd_1/internal"),
        ("POST", "/api/v1/call-center/agents/me/current-call/future-action"),
        ("DELETE", "/api/v1/call-center/agents/me/current-call/hangup"),
        ("POST", "/api/v1/call-center/agents/consultable"),
        ("GET", "/api/v1/call-center/sms/records"),
        ("POST", "/api/v1/call-center/sms/templates"),
    ],
)
def test_embedded_session_rejects_non_runtime_endpoints(method, path):
    assert embedded_call_http_access_allowed(method, path) is False


@pytest.mark.asyncio
async def test_embedded_session_is_blocked_before_non_runtime_endpoint_dependencies(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.core.security.decode_access_token",
        lambda _token: {
            "typ": "embedded_call_session",
            "sub": "10",
            "tenant_id": 1,
        },
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/employees",
            "headers": [],
            "scheme": "https",
            "server": ("opendesk.example.com", 443),
            "query_string": b"",
        }
    )

    with pytest.raises(ForbiddenError):
        await get_current_user(request, "Bearer embedded-token")


@pytest.mark.asyncio
async def test_embedded_socket_joins_only_receive_room(monkeypatch):
    session = {
        "typ": "embedded_call_session",
        "sub": "10",
        "tenant_id": 1,
        "session_id": "ecs_1",
        "integration_id": 4,
        "integration_key": "ec_test",
        "origin": "https://crm.example.com",
        "instance_id": "ecinst_1",
    }
    rt = _RealtimeHarness()
    validate = AsyncMock()
    mark_connected = AsyncMock()
    assign_queued = AsyncMock()
    republish = AsyncMock()

    monkeypatch.setattr(chat_handlers, "decode_access_token", lambda _token: session)
    monkeypatch.setattr(chat_handlers, "AsyncSessionLocal", _SessionContext)
    monkeypatch.setattr(chat_handlers, "redis_client", SimpleNamespace(client=object()))
    monkeypatch.setattr(
        chat_handlers.EmbeddedCallIntegrationService,
        "validate_session_payload",
        validate,
    )
    monkeypatch.setattr(chat_handlers.AgentStatusService, "mark_connected", mark_connected)
    monkeypatch.setattr(chat_handlers, "_assign_queued_conversations", assign_queued)
    monkeypatch.setattr(
        orch_module,
        "get_orchestrator",
        lambda: SimpleNamespace(republish_agent_call_ui=republish),
    )

    chat_handlers.register_chat_handlers(rt)
    await rt.handlers[("/chat", "connect")]("sid-1", {}, {"token": "jwt"})

    rt.join_room.assert_awaited_once_with(
        "sid-1", "embedded-call-agent:1:10", namespace="/chat"
    )
    mark_connected.assert_not_awaited()
    assign_queued.assert_not_awaited()
    assert rt.session["typ"] == "embedded_call_session"

    schedule_disconnect = AsyncMock()
    monkeypatch.setattr(
        chat_handlers.AgentStatusService,
        "schedule_disconnect",
        schedule_disconnect,
    )
    await rt.handlers[("/chat", "disconnect")]("sid-1")
    schedule_disconnect.assert_not_awaited()


@pytest.mark.asyncio
async def test_embedded_socket_cannot_send_chat_events(monkeypatch):
    rt = _RealtimeHarness(
        {
            "typ": "embedded_call_session",
            "user_id": 10,
            "tenant_id": 1,
            "session_id": "ecs_1",
        }
    )
    monkeypatch.setattr(chat_handlers, "AsyncSessionLocal", _SessionContext)
    monkeypatch.setattr(chat_handlers, "redis_client", SimpleNamespace(client=object()))
    monkeypatch.setattr(
        chat_handlers.EmbeddedCallIntegrationService,
        "validate_session_payload",
        AsyncMock(),
    )

    with pytest.raises(BusinessError) as exc_info:
        await chat_handlers._get_valid_socket_session(rt, "sid-1")

    assert exc_info.value.code == "EMBED_SOCKET_RECEIVE_ONLY"

    chat_handlers.register_chat_handlers(rt)
    response = await rt.handlers[("/chat", "leave_conversation")](
        "sid-1", {"conversation_id": 123}
    )
    assert response["error"] == "EMBED_SOCKET_RECEIVE_ONLY"
    rt.leave_room.assert_not_awaited()
