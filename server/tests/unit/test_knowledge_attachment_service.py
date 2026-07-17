"""Unit tests for managed knowledge attachment file I/O."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationError
from app.models.knowledge import KnowledgeDocumentAttachment
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_file_service import ConversationFileService
from app.services.knowledge_attachment_service import KnowledgeAttachmentService


@pytest.mark.asyncio
async def test_upload_closes_db_session_during_file_and_storage_io(monkeypatch):
    class SessionTracker:
        active = False
        opens = 0
        closes = 0

    class FakeSessionContext:
        async def __aenter__(self):
            assert SessionTracker.active is False
            SessionTracker.active = True
            SessionTracker.opens += 1
            return object()

        async def __aexit__(self, *_exc_info):
            SessionTracker.active = False
            SessionTracker.closes += 1

    class UploadFile:
        filename = "guide.pdf"
        content_type = "application/pdf"

        async def read(self):
            assert SessionTracker.active is False
            return b"pdf-data"

    class Storage:
        async def upload(self, *_args, **_kwargs):
            assert SessionTracker.active is False

        async def delete(self, *_args, **_kwargs):
            assert SessionTracker.active is False

    async def fake_cleanup(_tenant_id):
        assert SessionTracker.active is False

    async def fake_create(_db, data):
        assert SessionTracker.active is True
        now = datetime.now(timezone.utc)
        return KnowledgeDocumentAttachment(id=5, sort_order=0, created_at=now, updated_at=now, **data)

    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        KnowledgeAttachmentService,
        "_cleanup_expired_staging",
        fake_cleanup,
    )
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.KnowledgeDocumentAttachmentRepository.create",
        fake_create,
    )
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.create_storage_client",
        lambda: Storage(),
    )

    result = await KnowledgeAttachmentService.upload_managed(tenant_id=2, actor_id=7, file=UploadFile())

    assert result.id == 5
    assert result.name == "guide.pdf"
    assert SessionTracker.opens == 1
    assert SessionTracker.opens == SessionTracker.closes


@pytest.mark.asyncio
async def test_stage_from_conversation_message_closes_sessions_during_copy(monkeypatch):
    class SessionTracker:
        active = False
        opens = 0
        closes = 0

    class FakeSessionContext:
        async def __aenter__(self):
            assert SessionTracker.active is False
            SessionTracker.active = True
            SessionTracker.opens += 1
            return object()

        async def __aexit__(self, *_exc_info):
            SessionTracker.active = False
            SessionTracker.closes += 1

    class Storage:
        source_key: str | None = None
        destination_key: str | None = None

        async def copy(self, source_key, destination_key):
            assert SessionTracker.active is False
            self.source_key = source_key
            self.destination_key = destination_key

        async def delete(self, _key):
            assert SessionTracker.active is False

    source_key = "conversation-files/2/4/20260715/guide.pdf"
    file_id = ConversationFileService.encode_file_id(source_key)

    async def fake_cleanup(_tenant_id):
        assert SessionTracker.active is False

    async def fake_get_message(_db, tenant_id, message_id):
        assert SessionTracker.active is True
        assert (tenant_id, message_id) == (2, 11)
        return SimpleNamespace(
            id=11,
            conversation_id=4,
            sender_type="agent",
            content_type="file",
            content=json.dumps({
                "schema_version": 1,
                "file_id": file_id,
                "name": "guide.pdf",
                "size": 123,
                "mime_type": "application/pdf",
            }),
            is_recalled=False,
        )

    async def fake_get_conversation(_db, conversation_id):
        assert SessionTracker.active is True
        assert conversation_id == 4
        return SimpleNamespace(id=4, tenant_id=2, agent_id=7, status="active")

    async def fake_assert_access(_db, _principal, _conversation):
        assert SessionTracker.active is True
        return "own"

    async def fake_create(_db, data):
        assert SessionTracker.active is True
        now = datetime.now(timezone.utc)
        return KnowledgeDocumentAttachment(id=15, sort_order=0, created_at=now, updated_at=now, **data)

    storage = Storage()
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(KnowledgeAttachmentService, "_cleanup_expired_staging", fake_cleanup)
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.MessageRepository.get_by_id_for_tenant",
        fake_get_message,
    )
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.ConversationRepository.get_by_id",
        fake_get_conversation,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService._assert_conversation_view_access",
        fake_assert_access,
    )
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.KnowledgeDocumentAttachmentRepository.create",
        fake_create,
    )
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.create_storage_client",
        lambda: storage,
    )

    result = await KnowledgeAttachmentService.stage_from_conversation_message_managed(
        EffectivePrincipal(
            user_id=7,
            tenant_id=2,
            permissions=["chat.workspace.use", "knowledge.workspace.document.create"],
        ),
        message_id=11,
    )

    assert result.id == 15
    assert result.name == "guide.pdf"
    assert storage.source_key == source_key
    assert storage.destination_key is not None
    assert storage.destination_key.startswith("knowledge-attachments/2/")
    assert SessionTracker.opens == 2
    assert SessionTracker.opens == SessionTracker.closes


@pytest.mark.asyncio
async def test_stage_from_conversation_message_rejects_foreign_storage_key(monkeypatch):
    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_exc_info):
            return None

    file_id = ConversationFileService.encode_file_id(
        "conversation-files/2/999/20260715/guide.pdf"
    )

    async def fake_get_message(*_args):
        return SimpleNamespace(
            conversation_id=4,
            sender_type="agent",
            content_type="file",
            content=json.dumps({
                "schema_version": 1,
                "file_id": file_id,
                "name": "guide.pdf",
                "size": 123,
                "mime_type": "application/pdf",
            }),
            is_recalled=False,
        )

    async def fake_get_conversation(*_args):
        return SimpleNamespace(id=4, tenant_id=2, agent_id=7, status="active")

    async def fake_assert_access(*_args):
        return "own"

    async def fake_cleanup(_tenant_id):
        return None

    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(KnowledgeAttachmentService, "_cleanup_expired_staging", fake_cleanup)
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.MessageRepository.get_by_id_for_tenant",
        fake_get_message,
    )
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.ConversationRepository.get_by_id",
        fake_get_conversation,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService._assert_conversation_view_access",
        fake_assert_access,
    )

    with pytest.raises(ValidationError, match="File does not belong to conversation"):
        await KnowledgeAttachmentService.stage_from_conversation_message_managed(
            EffectivePrincipal(user_id=7, tenant_id=2, permissions=[]),
            message_id=11,
        )


@pytest.mark.asyncio
async def test_stage_from_conversation_message_deletes_copy_when_db_create_fails(monkeypatch):
    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_exc_info):
            return None

    class Storage:
        copied_key: str | None = None
        deleted_keys: list[str] = []

        async def copy(self, _source_key, destination_key):
            self.copied_key = destination_key

        async def delete(self, key):
            self.deleted_keys.append(key)

    source_key = "conversation-files/2/4/20260715/guide.pdf"
    file_id = ConversationFileService.encode_file_id(source_key)

    async def fake_get_message(*_args):
        return SimpleNamespace(
            conversation_id=4,
            sender_type="agent",
            content_type="file",
            content=json.dumps({
                "schema_version": 1,
                "file_id": file_id,
                "name": "guide.pdf",
                "size": 123,
                "mime_type": "application/pdf",
            }),
            is_recalled=False,
        )

    async def fake_get_conversation(*_args):
        return SimpleNamespace(id=4, tenant_id=2, agent_id=7, status="active")

    async def fake_assert_access(*_args):
        return "own"

    async def fake_cleanup(_tenant_id):
        return None

    async def fake_create(*_args):
        raise RuntimeError("database unavailable")

    storage = Storage()
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(KnowledgeAttachmentService, "_cleanup_expired_staging", fake_cleanup)
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.MessageRepository.get_by_id_for_tenant",
        fake_get_message,
    )
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.ConversationRepository.get_by_id",
        fake_get_conversation,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService._assert_conversation_view_access",
        fake_assert_access,
    )
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.KnowledgeDocumentAttachmentRepository.create",
        fake_create,
    )
    monkeypatch.setattr(
        "app.services.knowledge_attachment_service.create_storage_client",
        lambda: storage,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await KnowledgeAttachmentService.stage_from_conversation_message_managed(
            EffectivePrincipal(user_id=7, tenant_id=2, permissions=[]),
            message_id=11,
        )

    assert storage.copied_key is not None
    assert storage.deleted_keys == [storage.copied_key]
