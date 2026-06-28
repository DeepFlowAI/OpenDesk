"""
Unit tests for conversation file service helpers.
"""
import pytest

from app.core.exceptions import ValidationError
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_file_service import ConversationFileService


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


def test_validate_image_magic_number_rejects_mismatch():
    with pytest.raises(ValidationError):
        ConversationFileService._validate_magic_number("image/png", b"not-a-png")


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
