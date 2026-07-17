"""
Unit tests for conversation file service helpers.
"""
import pytest
from types import SimpleNamespace

from app.core.exceptions import ValidationError
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_file_service import (
    CONVERSATION_IMAGE_DISPLAY_PROCESS,
    KNOWLEDGE_IMAGE_PROCESS_PROFILES,
    ConversationFileService,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


def test_file_id_round_trip_returns_original_key():
    key = "conversation-files/1/2/20260501/demo.pdf"

    file_id = ConversationFileService.encode_file_id(key)
    decoded = ConversationFileService.decode_file_id(file_id)

    assert decoded == key


def test_decode_invalid_file_id_raises_validation_error():
    with pytest.raises(ValidationError):
        ConversationFileService.decode_file_id("%%%")


def test_safe_download_name_strips_header_breaking_characters():
    safe_name = ConversationFileService._safe_download_name('bad"\r\nname.pdf')

    assert '"' not in safe_name
    assert "\r" not in safe_name
    assert "\n" not in safe_name


def test_safe_image_process_only_allows_known_profiles():
    assert (
        ConversationFileService._safe_image_process(CONVERSATION_IMAGE_DISPLAY_PROCESS, download=False)
        == CONVERSATION_IMAGE_DISPLAY_PROCESS
    )
    for profile in KNOWLEDGE_IMAGE_PROCESS_PROFILES:
        assert ConversationFileService._safe_image_process(profile, download=False) == profile
    assert ConversationFileService._safe_image_process(CONVERSATION_IMAGE_DISPLAY_PROCESS, download=True) is None
    assert ConversationFileService._safe_image_process(None, download=False) is None
    for unsupported in (
        "",
        "image/resize,w_4096",
        "image/resize,l_4096,limit_1/format,webp/quality,Q_90",
        "image/resize,l_4096,limit_1/format,png",
    ):
        with pytest.raises(ValidationError):
            ConversationFileService._safe_image_process(unsupported, download=False)


def test_validate_image_magic_number_rejects_mismatch():
    with pytest.raises(ValidationError):
        ConversationFileService._validate_magic_number("image/png", b"not-a-png")


def test_normalize_upload_metadata_rejects_declared_image_without_image_magic():
    with pytest.raises(ValidationError):
        ConversationFileService._normalize_upload_metadata("image/png", "png", b"not-a-png")


@pytest.mark.asyncio
async def test_upload_normalizes_mismatched_image_mime_and_extension(monkeypatch):
    class MismatchedImageUploadFile:
        filename = "screenshot.jpg"
        content_type = "image/jpeg"

        async def read(self):
            return PNG_BYTES

    class CapturingStorage:
        def __init__(self):
            self.key: str | None = None
            self.content_type: str | None = None

        async def upload(self, key, _data, *, content_type):
            self.key = key
            self.content_type = content_type

        async def get_temporary_url(self, *_args, **_kwargs):
            return "https://storage.example.com/screenshot.png?signature=1"

    storage = CapturingStorage()
    monkeypatch.setattr(
        "app.services.conversation_file_service.create_storage_client",
        lambda: storage,
    )

    result = await ConversationFileService._upload_file(
        conversation_id=2,
        tenant_id=1,
        file=MismatchedImageUploadFile(),
    )

    assert result["name"] == "screenshot.jpg"
    assert result["mime_type"] == "image/png"
    assert storage.content_type == "image/png"
    assert storage.key is not None
    assert storage.key.endswith(".png")


@pytest.mark.asyncio
async def test_managed_agent_upload_closes_db_session_before_file_io(monkeypatch):
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

    class SessionAwareUploadFile:
        filename = "demo.txt"
        content_type = "text/plain"

        def __init__(self):
            self.active_states: list[bool] = []

        async def read(self):
            self.active_states.append(SessionTracker.active)
            return b"hello"

    class SessionAwareStorage:
        def __init__(self):
            self.active_states: list[bool] = []

        async def upload(self, *_args, **_kwargs):
            self.active_states.append(SessionTracker.active)
            return "https://storage.example.com/demo.txt"

        async def get_temporary_url(self, *_args, **_kwargs):
            self.active_states.append(SessionTracker.active)
            return "https://storage.example.com/demo.txt?signature=1"

    async def fake_get_conversation_for_agent(*_args, **_kwargs):
        assert SessionTracker.active is True
        return object()

    storage = SessionAwareStorage()
    file = SessionAwareUploadFile()
    monkeypatch.setattr(
        "app.services.conversation_file_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        ConversationFileService,
        "_get_conversation_for_agent",
        fake_get_conversation_for_agent,
    )
    monkeypatch.setattr(
        "app.services.conversation_file_service.create_storage_client",
        lambda: storage,
    )

    result = await ConversationFileService.upload_agent_file_managed(
        conversation_id=2,
        tenant_id=1,
        agent_id=3,
        file=file,
        principal=EffectivePrincipal(
            user_id=3,
            tenant_id=1,
            permissions=["chat.workspace.use"],
        ),
    )

    assert result["name"] == "demo.txt"
    assert result["access_url"] == "https://storage.example.com/demo.txt?signature=1"
    assert file.active_states == [False]
    assert storage.active_states == [False, False]
    assert SessionTracker.opens == 1
    assert SessionTracker.opens == SessionTracker.closes


@pytest.mark.asyncio
async def test_managed_visitor_upload_closes_db_session_before_file_io(monkeypatch):
    class SessionTracker:
        active = False

    class FakeSessionContext:
        async def __aenter__(self):
            SessionTracker.active = True
            return object()

        async def __aexit__(self, *_exc_info):
            SessionTracker.active = False

    class SessionAwareUploadFile:
        filename = "demo.txt"
        content_type = "text/plain"

        async def read(self):
            assert SessionTracker.active is False
            return b"hello"

    class SessionAwareStorage:
        async def upload(self, *_args, **_kwargs):
            assert SessionTracker.active is False

        async def get_temporary_url(self, *_args, **_kwargs):
            assert SessionTracker.active is False
            return "https://storage.example.com/demo.txt?signature=1"

    async def fake_get_conversation(*_args, **_kwargs):
        assert SessionTracker.active is True
        return SimpleNamespace(id=2, tenant_id=1)

    monkeypatch.setattr(
        "app.services.conversation_file_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService.get_conversation_for_visitor_session",
        fake_get_conversation,
    )
    monkeypatch.setattr(
        "app.services.conversation_file_service.create_storage_client",
        lambda: SessionAwareStorage(),
    )

    result = await ConversationFileService.upload_visitor_file_for_session_managed(
        conversation_public_id="cv_test",
        visitor_context={"tenant_id": 1, "channel_id": 3, "visitor_external_id": "v_1"},
        file=SessionAwareUploadFile(),
    )

    assert result["name"] == "demo.txt"


@pytest.mark.asyncio
async def test_open_agent_attachment_regenerates_https_url_without_persisting_it(monkeypatch):
    key = "conversation-files/1/2/20260715/demo.pdf"
    file_id = ConversationFileService.encode_file_id(key)

    class Storage:
        async def get_temporary_url(self, requested_key, **_kwargs):
            assert requested_key == key
            return "https://storage.example.com/demo.pdf?signature=fresh"

    monkeypatch.setattr(
        "app.services.conversation_file_service.create_storage_client",
        lambda: Storage(),
    )

    result = await ConversationFileService.build_open_agent_attachment(
        tenant_id=1,
        conversation_id=2,
        file_id=file_id,
        attachment_type="file",
        name="demo.pdf",
        mime_type="application/pdf",
        size=12,
    )

    assert result == {
        "type": "file",
        "url": "https://storage.example.com/demo.pdf?signature=fresh",
        "name": "demo.pdf",
        "mime_type": "application/pdf",
        "size": 12,
    }


@pytest.mark.asyncio
async def test_prepare_knowledge_attachment_closes_db_session_before_copy(monkeypatch):
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
        def __init__(self):
            self.source_key: str | None = None
            self.destination_key: str | None = None

        async def copy(self, source_key, destination_key):
            assert SessionTracker.active is False
            self.source_key = source_key
            self.destination_key = destination_key

        async def get_temporary_url(self, key, **_kwargs):
            assert SessionTracker.active is False
            assert key == self.destination_key
            return "https://storage.example.com/copied?signature=1"

    async def fake_get_conversation(*_args, **_kwargs):
        assert SessionTracker.active is True
        return object()

    async def fake_get_attachment(_db, attachment_id):
        assert SessionTracker.active is True
        assert attachment_id == 9
        return SimpleNamespace(
            id=9,
            tenant_id=2,
            document_id=5,
            storage_key="knowledge-attachments/2/source/guide.pdf",
            name="guide.pdf",
            size=123,
            mime_type="application/pdf",
        )

    async def fake_get_document(_db, document_id):
        assert SessionTracker.active is True
        assert document_id == 5
        return SimpleNamespace(
            tenant_id=2,
            status="published",
            validity_type="permanent",
            valid_from=None,
            valid_to=None,
        )

    storage = Storage()
    monkeypatch.setattr(
        "app.services.conversation_file_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        ConversationFileService,
        "_get_conversation_for_agent",
        fake_get_conversation,
    )
    monkeypatch.setattr(
        "app.repositories.knowledge_repository.KnowledgeDocumentAttachmentRepository.get_by_id",
        fake_get_attachment,
    )
    monkeypatch.setattr(
        "app.repositories.knowledge_repository.KnowledgeDocumentRepository.get_by_id",
        fake_get_document,
    )
    monkeypatch.setattr(
        "app.services.conversation_file_service.create_storage_client",
        lambda: storage,
    )

    result = await ConversationFileService.prepare_knowledge_attachment_managed(
        conversation_id=4,
        attachment_id=9,
        principal=EffectivePrincipal(
            user_id=7,
            tenant_id=2,
            permissions=["chat.workspace.use", "knowledge.workspace.view"],
        ),
    )

    assert storage.source_key == "knowledge-attachments/2/source/guide.pdf"
    assert storage.destination_key is not None
    assert storage.destination_key.startswith("conversation-files/2/4/")
    assert result["name"] == "guide.pdf"
    assert result["mime_type"] == "application/pdf"
    assert result["access_url"] == "https://storage.example.com/copied?signature=1"
    assert SessionTracker.opens == 1
    assert SessionTracker.opens == SessionTracker.closes
