"""
Session-discipline tests for agent-facing object-storage routes (CLAUDE.md §8).

No managed DB session may stay open while awaiting object-storage upload or
temporary-URL generation. Also covers permission rejection and storage failures
on the routes that were converted to short-session auth.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import ForbiddenError, ValidationError, register_exception_handlers
from app.db.deps import get_current_principal_short_session
from app.repositories.message_repository import MessageRepository
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_file_service import ConversationFileService
from app.services.offline_message_service import OfflineMessageService
from app.services.queue_workspace_service import QueueWorkspaceService

import app.services.conversation_file_service as conversation_file_mod
import app.services.offline_message_service as offline_message_mod
import app.services.queue_workspace_service as queue_workspace_mod


class SessionTracker:
    active = False
    opens = 0
    closes = 0


class FakeSessionContext:
    async def __aenter__(self):
        assert SessionTracker.active is False
        SessionTracker.active = True
        SessionTracker.opens += 1
        return SimpleNamespace(commit=AsyncMock())

    async def __aexit__(self, *_exc_info):
        SessionTracker.active = False
        SessionTracker.closes += 1


def _reset_tracker() -> None:
    SessionTracker.active = False
    SessionTracker.opens = 0
    SessionTracker.closes = 0


def _principal(*permissions: str) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=7,
        tenant_id=3,
        permissions=list(permissions),
    )


def _build_client(router, principal: EffectivePrincipal) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")

    async def _fake_principal_short():
        return principal

    app.dependency_overrides[get_current_principal_short_session] = _fake_principal_short
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_tracker_fixture():
    _reset_tracker()
    yield
    _reset_tracker()


# ── Session discipline (managed services) ─────────────────────────────


@pytest.mark.asyncio
async def test_managed_queue_upload_closes_db_while_storage(monkeypatch):
    active_during_storage: list[bool] = []

    async def fake_upload(*, conversation_id, tenant_id, file):
        active_during_storage.append(SessionTracker.active)
        assert conversation_id == 101
        assert tenant_id == 3
        return {
            "schema_version": 1,
            "file_id": "file_q",
            "name": "a.pdf",
            "size": 4,
            "mime_type": "application/pdf",
            "access_url": "https://storage.example.com/a.pdf",
        }

    monkeypatch.setattr(queue_workspace_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        QueueWorkspaceService,
        "_get_visible_task",
        AsyncMock(return_value=(SimpleNamespace(id=9), SimpleNamespace(id=101, tenant_id=3))),
    )
    monkeypatch.setattr(ConversationFileService, "_upload_file", fake_upload)

    result = await QueueWorkspaceService.upload_task_file_managed(
        task_id=9,
        principal=_principal("chat.queue.assign_self"),
        file=object(),
    )

    assert active_during_storage == [False]
    assert SessionTracker.opens == SessionTracker.closes == 1
    assert result["file_id"] == "file_q"


@pytest.mark.asyncio
async def test_managed_agent_conversation_url_closes_db_while_storage(monkeypatch):
    conversation = SimpleNamespace(id=101, tenant_id=3, agent_id=7)
    key = f"conversation-files/{conversation.tenant_id}/{conversation.id}/20260715/demo.pdf"
    file_id = ConversationFileService.encode_file_id(key)
    active_during_storage: list[bool] = []

    class SessionAwareStorage:
        async def get_temporary_url(self, requested_key, **_kwargs):
            active_during_storage.append(SessionTracker.active)
            assert requested_key == key
            return "https://storage.example.com/demo.pdf?signature=1"

    monkeypatch.setattr(conversation_file_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        ConversationFileService,
        "_get_conversation_for_agent",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        MessageRepository,
        "get_file_message_by_file_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(conversation_file_mod, "create_storage_client", lambda: SessionAwareStorage())

    result = await ConversationFileService.get_temporary_url_for_agent_managed(
        conversation_id=101,
        tenant_id=3,
        agent_id=7,
        file_id=file_id,
        principal=_principal("chat.workspace.use"),
    )

    assert active_during_storage == [False]
    assert SessionTracker.opens == SessionTracker.closes == 1
    assert result["url"].startswith("https://storage.example.com/")


@pytest.mark.asyncio
async def test_managed_agent_offline_url_closes_db_while_storage(monkeypatch):
    row = SimpleNamespace(id=12, tenant_id=3)
    key = f"offline-message-files/{row.tenant_id}/{row.id}/20260715/demo.pdf"
    file_id = ConversationFileService.encode_file_id(key)
    active_during_storage: list[bool] = []

    class SessionAwareStorage:
        async def get_temporary_url(self, requested_key, **_kwargs):
            active_during_storage.append(SessionTracker.active)
            assert requested_key == key
            return "https://storage.example.com/offline.pdf?signature=1"

    monkeypatch.setattr(offline_message_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        "app.services.offline_message_service.OfflineMessageRepository.get_by_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        OfflineMessageService,
        "_assert_view_access",
        AsyncMock(),
    )
    monkeypatch.setattr(conversation_file_mod, "create_storage_client", lambda: SessionAwareStorage())

    result = await OfflineMessageService.get_temporary_url_for_agent_managed(
        _principal("chat.offline_message.view"),
        12,
        file_id=file_id,
    )

    assert active_during_storage == [False]
    assert SessionTracker.opens == SessionTracker.closes == 1
    assert "offline.pdf" in result["url"]


@pytest.mark.asyncio
async def test_managed_agent_conversation_url_propagates_storage_failure(monkeypatch):
    conversation = SimpleNamespace(id=101, tenant_id=3, agent_id=7)
    key = f"conversation-files/{conversation.tenant_id}/{conversation.id}/20260715/demo.pdf"
    file_id = ConversationFileService.encode_file_id(key)

    class FailingStorage:
        async def get_temporary_url(self, *_args, **_kwargs):
            assert SessionTracker.active is False
            raise RuntimeError("oss unavailable")

    monkeypatch.setattr(conversation_file_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        ConversationFileService,
        "_get_conversation_for_agent",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        MessageRepository,
        "get_file_message_by_file_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(conversation_file_mod, "create_storage_client", lambda: FailingStorage())

    with pytest.raises(RuntimeError, match="oss unavailable"):
        await ConversationFileService.get_temporary_url_for_agent_managed(
            conversation_id=101,
            tenant_id=3,
            agent_id=7,
            file_id=file_id,
            principal=_principal("chat.workspace.use"),
        )

    assert SessionTracker.opens == SessionTracker.closes == 1


@pytest.mark.asyncio
async def test_managed_agent_offline_url_propagates_validation_error(monkeypatch):
    row = SimpleNamespace(id=12, tenant_id=3)
    bad_key = "conversation-files/3/101/20260715/demo.pdf"
    file_id = ConversationFileService.encode_file_id(bad_key)

    monkeypatch.setattr(offline_message_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        "app.services.offline_message_service.OfflineMessageRepository.get_by_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(OfflineMessageService, "_assert_view_access", AsyncMock())

    with pytest.raises(ValidationError, match="File does not belong to offline message"):
        await OfflineMessageService.get_temporary_url_for_agent_managed(
            _principal("chat.offline_message.view"),
            12,
            file_id=file_id,
        )


@pytest.mark.asyncio
async def test_managed_queue_upload_propagates_storage_failure(monkeypatch):
    async def failing_upload(*, conversation_id, tenant_id, file):
        assert SessionTracker.active is False
        raise ValidationError("File is empty")

    monkeypatch.setattr(queue_workspace_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        QueueWorkspaceService,
        "_get_visible_task",
        AsyncMock(return_value=(SimpleNamespace(id=9), SimpleNamespace(id=101, tenant_id=3))),
    )
    monkeypatch.setattr(ConversationFileService, "_upload_file", failing_upload)

    with pytest.raises(ValidationError, match="File is empty"):
        await QueueWorkspaceService.upload_task_file_managed(
            task_id=9,
            principal=_principal("chat.queue.assign_self"),
            file=object(),
        )


# ── Route permission rejection ────────────────────────────────────────


def test_queue_upload_route_rejects_missing_workspace_permission(monkeypatch):
    from app.routers.v1 import queue_workspace

    client = _build_client(
        queue_workspace.router,
        _principal("chat.queue.assign_self"),  # missing chat.workspace.use
    )
    monkeypatch.setattr(
        QueueWorkspaceService,
        "upload_task_file_managed",
        AsyncMock(return_value={"file_id": "x"}),
    )

    response = client.post(
        "/api/v1/workspace/queue/tasks/1/files",
        files={"file": ("a.txt", b"hi", "text/plain")},
    )
    assert response.status_code == 403
    assert response.json()["message"] == "Permission denied"


def test_queue_upload_route_rejects_missing_assign_self_permission(monkeypatch):
    from app.routers.v1 import queue_workspace

    client = _build_client(
        queue_workspace.router,
        _principal("chat.workspace.use"),  # missing chat.queue.assign_self
    )
    monkeypatch.setattr(
        QueueWorkspaceService,
        "upload_task_file_managed",
        AsyncMock(return_value={"file_id": "x"}),
    )

    response = client.post(
        "/api/v1/workspace/queue/tasks/1/files",
        files={"file": ("a.txt", b"hi", "text/plain")},
    )
    assert response.status_code == 403
    assert response.json()["message"] == "Permission denied"


def test_conversation_file_url_route_rejects_missing_permission(monkeypatch):
    from app.routers.v1 import conversations

    client = _build_client(conversations.file_router, _principal())
    monkeypatch.setattr(
        ConversationFileService,
        "get_temporary_url_for_agent_managed",
        AsyncMock(return_value={"url": "x", "expires_seconds": 1}),
    )

    response = client.get("/api/v1/conversations/1/files/abc/url")
    assert response.status_code == 403
    assert response.json()["message"] == "Permission denied"


def test_offline_file_url_route_rejects_missing_permission(monkeypatch):
    from app.routers.v1 import offline_messages

    client = _build_client(offline_messages.router, _principal())
    monkeypatch.setattr(
        OfflineMessageService,
        "get_temporary_url_for_agent_managed",
        AsyncMock(return_value={"url": "x", "expires_seconds": 1}),
    )

    response = client.get("/api/v1/offline-messages/1/files/abc/url")
    assert response.status_code == 403
    assert response.json()["message"] == "Permission denied"


def test_offline_upload_route_rejects_missing_assign_self_permission(monkeypatch):
    from app.routers.v1 import offline_messages

    client = _build_client(
        offline_messages.router,
        _principal("chat.offline_message.view"),  # missing assign_self
    )
    monkeypatch.setattr(
        OfflineMessageService,
        "upload_agent_file_managed",
        AsyncMock(return_value={"file_id": "x"}),
    )

    response = client.post(
        "/api/v1/offline-messages/1/files",
        files={"file": ("a.txt", b"hi", "text/plain")},
    )
    assert response.status_code == 403
    assert response.json()["message"] == "Permission denied"


# ── Route storage failure response shape ───────────────────────────────


def test_conversation_file_url_route_propagates_storage_failure(monkeypatch):
    from app.routers.v1 import conversations

    client = _build_client(
        conversations.file_router,
        _principal("chat.workspace.use"),
    )

    async def _fail(*_a, **_k):
        raise ValidationError("File does not belong to conversation")

    monkeypatch.setattr(
        ConversationFileService,
        "get_temporary_url_for_agent_managed",
        _fail,
    )

    response = client.get("/api/v1/conversations/1/files/abc/url")
    assert response.status_code == 400
    assert response.json()["message"] == "File does not belong to conversation"


def test_queue_upload_route_propagates_storage_failure(monkeypatch):
    from app.routers.v1 import queue_workspace

    client = _build_client(
        queue_workspace.router,
        _principal("chat.workspace.use", "chat.queue.assign_self"),
    )

    async def _fail(*_a, **_k):
        raise ValidationError("File is empty")

    monkeypatch.setattr(QueueWorkspaceService, "upload_task_file_managed", _fail)

    response = client.post(
        "/api/v1/workspace/queue/tasks/1/files",
        files={"file": ("a.txt", b"", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["message"] == "File is empty"


@pytest.mark.asyncio
async def test_managed_agent_conversation_url_rejects_wrong_prefix(monkeypatch):
    conversation = SimpleNamespace(id=101, tenant_id=3, agent_id=7)
    bad_key = "other-prefix/3/101/demo.pdf"
    file_id = ConversationFileService.encode_file_id(bad_key)

    monkeypatch.setattr(conversation_file_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        ConversationFileService,
        "_get_conversation_for_agent",
        AsyncMock(return_value=conversation),
    )

    with pytest.raises(ValidationError, match="File does not belong to conversation"):
        await ConversationFileService.get_temporary_url_for_agent_managed(
            conversation_id=101,
            tenant_id=3,
            agent_id=7,
            file_id=file_id,
            principal=_principal("chat.workspace.use"),
        )


@pytest.mark.asyncio
async def test_queue_upload_rejects_missing_assign_self_in_service():
    with pytest.raises(ForbiddenError, match="Permission denied"):
        await QueueWorkspaceService.upload_task_file_managed(
            task_id=9,
            principal=_principal("chat.workspace.use"),
            file=object(),
        )
