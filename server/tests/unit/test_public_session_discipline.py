"""
Session-discipline tests for visitor-facing public routes / managed services.

Asserts that no DB session is held while slow external I/O (OpenAgent HTTP or
object storage) is in flight.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ValidationError
from app.enums import ConversationStatus
from app.libs.open_agent.base import OpenAgentClientError, OpenAgentFeedbackResult
from app.repositories.message_repository import MessageRepository
from app.schemas.channel import ChannelConfig
from app.schemas.open_agent_conversation import OpenAgentFeedbackRequest
from app.schemas.open_agent_settings import OpenAgentWelcomeMessage
from app.services.channel_service import ChannelService
from app.services.conversation_file_service import ConversationFileService
from app.services.conversation_service import ConversationService
from app.services.offline_message_service import OfflineMessageService
from app.services.open_agent_conversation_service import OpenAgentConversationService
from app.services.open_agent_settings_service import OpenAgentSettingsService


class SessionTracker:
    active = False
    opens = 0
    closes = 0

    @classmethod
    def reset(cls):
        cls.active = False
        cls.opens = 0
        cls.closes = 0


class FakeSessionContext:
    async def __aenter__(self):
        assert SessionTracker.active is False
        SessionTracker.active = True
        SessionTracker.opens += 1
        return object()

    async def __aexit__(self, *_exc_info):
        SessionTracker.active = False
        SessionTracker.closes += 1


@dataclass
class FakeChannel:
    config: dict


@dataclass
class FakeVisitor:
    id: int = 11
    name: str = "访客"


@dataclass
class FakeConversation:
    id: int = 101
    public_id: str = "cv_test"
    tenant_id: int = 1
    channel_id: int = 10
    status: str = ConversationStatus.BOT.value
    visitor: FakeVisitor = field(default_factory=FakeVisitor)
    channel: FakeChannel = field(default_factory=lambda: FakeChannel({
        "open_agent_enabled": True,
        "open_agent_agent_id": 7,
        "open_agent_feedback_enabled": True,
    }))
    open_agent_conversation_id: int | None = 42


@dataclass
class FakeMessage:
    id: int
    tenant_id: int
    conversation_id: int
    sender_type: str
    content_type: str
    content: str
    sender_id: int | None = None
    metadata_: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_recalled: bool = False


@pytest.fixture(autouse=True)
def _reset_session_tracker():
    SessionTracker.reset()


@pytest.mark.asyncio
async def test_managed_public_channel_config_closes_db_before_open_agent(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=1,
        channel_key="ck_test",
        name="Widget",
        channel_type="web",
        access_mode="public",
        logo_url=None,
        favicon_url=None,
        public_access_enabled=True,
        config=ChannelConfig(
            open_agent_enabled=True,
            open_agent_agent_id=7,
        ).model_dump(),
    )
    active_during_http: list[bool] = []

    class SessionAwareClient:
        async def get_agent(self, *_args, **_kwargs):
            active_during_http.append(SessionTracker.active)
            return SimpleNamespace(
                status="active",
                welcome_message={
                    "enabled": True,
                    "blocks": [{"type": "markdown", "content": "hi"}],
                },
                faq=None,
                ai_disclaimer=None,
            )

    monkeypatch.setattr(
        "app.services.channel_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        "app.services.open_agent_settings_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        ChannelService,
        "get_public_channel_by_key",
        AsyncMock(return_value=channel),
    )
    monkeypatch.setattr(
        ChannelService,
        "check_channel_availability",
        AsyncMock(return_value={"available": True}),
    )
    monkeypatch.setattr(
        "app.services.conversation_announcement_rule_service."
        "ConversationAnnouncementRuleService.match_public_announcement",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.conversation_read_status_service."
        "ConversationReadStatusService.get_public_config",
        AsyncMock(return_value={"web_sdk_enabled": True}),
    )
    monkeypatch.setattr(
        OpenAgentSettingsService,
        "get_credentials",
        AsyncMock(return_value=("https://openagent.example.com", "sk-test")),
    )

    result = await ChannelService.get_public_config_with_availability_by_key_managed(
        object(),
        "ck_test",
        open_agent_client=SessionAwareClient(),
    )

    assert active_during_http == [False]
    assert SessionTracker.opens == SessionTracker.closes
    assert SessionTracker.opens >= 2
    assert isinstance(result["open_agent_welcome_message"], OpenAgentWelcomeMessage)


@pytest.mark.asyncio
async def test_managed_submit_feedback_closes_db_before_open_agent(monkeypatch):
    conversation = FakeConversation()
    message = FakeMessage(
        id=51,
        tenant_id=1,
        conversation_id=101,
        sender_type="bot",
        content_type="text",
        content="Hello",
        metadata_={"open_agent_feedback_step_id": 88},
    )
    active_during_http: list[bool] = []

    class SessionAwareClient:
        async def submit_feedback(self, *_args, **_kwargs):
            active_during_http.append(SessionTracker.active)
            return OpenAgentFeedbackResult(
                step_id=88,
                rating="like",
                comment=None,
                updated_at="2026-06-23T00:00:00+00:00",
            )

    async def fake_get_conversation(*_args, **_kwargs):
        assert SessionTracker.active is True
        return conversation

    async def fake_get_message(*_args, **_kwargs):
        assert SessionTracker.active is True
        return message

    async def fake_update_metadata(_db, msg, metadata):
        assert SessionTracker.active is True
        msg.metadata_ = metadata
        return msg

    monkeypatch.setattr(
        "app.services.open_agent_conversation_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(MessageRepository, "get_by_id_for_conversation", fake_get_message)
    monkeypatch.setattr(
        OpenAgentSettingsService,
        "get_credentials",
        AsyncMock(return_value=("https://openagent.example.com", "sk-test")),
    )
    monkeypatch.setattr(MessageRepository, "update_metadata", fake_update_metadata)

    result = await OpenAgentConversationService.submit_feedback_for_session_managed(
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentFeedbackRequest(message_id=51, step_id=88, rating="like"),
        open_agent_client=SessionAwareClient(),
    )

    assert active_during_http == [False]
    assert SessionTracker.opens == 2
    assert SessionTracker.opens == SessionTracker.closes
    assert result["rating"] == "like"


@pytest.mark.asyncio
async def test_managed_submit_feedback_maps_open_agent_error(monkeypatch):
    conversation = FakeConversation()
    message = FakeMessage(
        id=51,
        tenant_id=1,
        conversation_id=101,
        sender_type="bot",
        content_type="text",
        content="Hello",
        metadata_={"open_agent_feedback_step_id": 88},
    )

    class FailingClient:
        async def submit_feedback(self, *_args, **_kwargs):
            raise OpenAgentClientError("upstream rejected feedback")

    monkeypatch.setattr(
        "app.services.open_agent_conversation_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        ConversationService,
        "get_conversation_for_visitor_session",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        MessageRepository,
        "get_by_id_for_conversation",
        AsyncMock(return_value=message),
    )
    monkeypatch.setattr(
        OpenAgentSettingsService,
        "get_credentials",
        AsyncMock(return_value=("https://openagent.example.com", "sk-test")),
    )

    with pytest.raises(ValidationError, match="upstream rejected feedback"):
        await OpenAgentConversationService.submit_feedback_for_session_managed(
            "cv_test",
            {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
            OpenAgentFeedbackRequest(message_id=51, step_id=88, rating="like"),
            open_agent_client=FailingClient(),
        )


@pytest.mark.asyncio
async def test_managed_offline_create_file_closes_db_before_storage(monkeypatch):
    visitor = SimpleNamespace(id=20, name="Visitor")
    row = SimpleNamespace(
        id=12,
        public_id="om_test",
        tenant_id=1,
        channel_id=2,
        visitor_external_id="visitor-1",
        status="pending",
        visitor_id=visitor.id,
        visitor=visitor,
        visitor_name=visitor.name,
        message_count=0,
        metadata_={},
    )
    active_during_storage: list[bool] = []

    class TrackingDb:
        def add(self, obj):
            if getattr(obj, "id", None) is None:
                obj.id = 102

        async def flush(self):
            return None

        async def commit(self):
            return None

        async def rollback(self):
            return None

        async def execute(self, *_args, **_kwargs):
            return SimpleNamespace(scalar_one_or_none=lambda: None)

    class TrackingSession:
        def __init__(self):
            self.db = TrackingDb()

        async def __aenter__(self):
            assert SessionTracker.active is False
            SessionTracker.active = True
            SessionTracker.opens += 1
            return self.db

        async def __aexit__(self, *_exc_info):
            SessionTracker.active = False
            SessionTracker.closes += 1

    async def fake_upload(*, tenant_id, offline_message_id, file):
        active_during_storage.append(SessionTracker.active)
        assert tenant_id == 1
        assert offline_message_id == 12
        return {
            "schema_version": 1,
            "file_id": "file_test",
            "name": "a.pdf",
            "size": 12,
            "mime_type": "application/pdf",
            "access_url": "https://storage.example.com/a.pdf",
        }

    monkeypatch.setattr(
        "app.services.offline_message_service.AsyncSessionLocal",
        lambda: TrackingSession(),
    )
    monkeypatch.setattr(
        OfflineMessageService,
        "_prepare_leave_message_session",
        AsyncMock(return_value=(1, 2, "visitor-1", visitor, 7, {}, "")),
    )
    monkeypatch.setattr(
        "app.services.offline_message_service.OfflineMessageRepository.get_pending_by_visitor_for_update",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.offline_message_service.OfflineMessageRepository.get_by_id_for_update",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.offline_message_service.OfflineMessageRepository.get_by_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        OfflineMessageService,
        "_upload_file_for_offline_message",
        fake_upload,
    )
    monkeypatch.setattr(
        "app.services.offline_message_service.ConversationService.validate_message_content",
        lambda _content_type, content: content,
    )
    monkeypatch.setattr(
        "app.services.offline_message_service.ConversationService.build_message_preview",
        lambda *_a, **_k: "[file]",
    )
    monkeypatch.setattr(
        "app.services.offline_message_service.OfflineMessageRealtimeService.emit_updated",
        AsyncMock(),
    )
    monkeypatch.setattr(
        OfflineMessageService,
        "_public_entry_payload",
        staticmethod(lambda entry, _row: {"id": getattr(entry, "id", 102)}),
    )

    result = await OfflineMessageService.create_or_continue_and_send_file_for_session_managed(
        object(),
        {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"},
        object(),
    )

    assert active_during_storage == [False]
    assert SessionTracker.opens == 2
    assert SessionTracker.opens == SessionTracker.closes
    assert result["ok"] is True
    assert result["offline_message_public_id"] == "om_test"


@pytest.mark.asyncio
async def test_managed_offline_upload_public_file_closes_db_before_storage(monkeypatch):
    row = SimpleNamespace(id=12, tenant_id=1, status="pending")
    active_during_storage: list[bool] = []

    async def fake_upload(*, tenant_id, offline_message_id, file):
        active_during_storage.append(SessionTracker.active)
        return {
            "schema_version": 1,
            "file_id": "file_test",
            "name": "a.pdf",
            "size": 12,
            "mime_type": "application/pdf",
            "access_url": "https://storage.example.com/a.pdf",
        }

    monkeypatch.setattr(
        "app.services.offline_message_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        OfflineMessageService,
        "_get_for_session_for_update",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        OfflineMessageService,
        "_upload_file_for_offline_message",
        fake_upload,
    )

    result = await OfflineMessageService.upload_public_file_managed(
        "om_test",
        {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"},
        object(),
    )

    assert active_during_storage == [False]
    assert SessionTracker.opens == 1
    assert SessionTracker.opens == SessionTracker.closes
    assert result["file_id"] == "file_test"


@pytest.mark.asyncio
async def test_managed_offline_upload_public_file_propagates_storage_error(monkeypatch):
    row = SimpleNamespace(id=12, tenant_id=1, status="pending")

    async def failing_upload(*, tenant_id, offline_message_id, file):
        raise ValidationError("File is empty")

    monkeypatch.setattr(
        "app.services.offline_message_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        OfflineMessageService,
        "_get_for_session_for_update",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        OfflineMessageService,
        "_upload_file_for_offline_message",
        failing_upload,
    )

    with pytest.raises(ValidationError, match="File is empty"):
        await OfflineMessageService.upload_public_file_managed(
            "om_test",
            {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"},
            object(),
        )


@pytest.mark.asyncio
async def test_managed_conversation_file_url_closes_db_before_storage(monkeypatch):
    conversation = FakeConversation()
    key = f"conversation-files/{conversation.tenant_id}/{conversation.id}/20260715/demo.pdf"
    file_id = ConversationFileService.encode_file_id(key)
    active_during_storage: list[bool] = []

    class SessionAwareStorage:
        async def get_temporary_url(self, requested_key, **_kwargs):
            active_during_storage.append(SessionTracker.active)
            assert requested_key == key
            return "https://storage.example.com/demo.pdf?signature=1"

    monkeypatch.setattr(
        "app.services.conversation_file_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        ConversationService,
        "get_conversation_for_visitor_session",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        MessageRepository,
        "get_file_message_by_file_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.conversation_file_service.create_storage_client",
        lambda: SessionAwareStorage(),
    )

    result = await ConversationFileService.get_temporary_url_for_visitor_session_managed(
        conversation_public_id="cv_test",
        visitor_context={"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        file_id=file_id,
    )

    assert active_during_storage == [False]
    assert SessionTracker.opens == 1
    assert SessionTracker.opens == SessionTracker.closes
    assert result["url"].startswith("https://storage.example.com/")


@pytest.mark.asyncio
async def test_managed_offline_file_url_closes_db_before_storage(monkeypatch):
    row = SimpleNamespace(id=12, tenant_id=1, public_id="om_test")
    key = f"offline-message-files/{row.tenant_id}/{row.id}/20260715/demo.pdf"
    file_id = ConversationFileService.encode_file_id(key)
    active_during_storage: list[bool] = []

    class SessionAwareStorage:
        async def get_temporary_url(self, requested_key, **_kwargs):
            active_during_storage.append(SessionTracker.active)
            assert requested_key == key
            return "https://storage.example.com/offline.pdf?signature=1"

    monkeypatch.setattr(
        "app.services.offline_message_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        OfflineMessageService,
        "_get_for_session",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.conversation_file_service.create_storage_client",
        lambda: SessionAwareStorage(),
    )

    result = await OfflineMessageService.get_temporary_url_for_public_managed(
        "om_test",
        {"tenant_id": 1, "channel_id": 2, "visitor_external_id": "visitor-1"},
        file_id=file_id,
    )

    assert active_during_storage == [False]
    assert SessionTracker.opens == 1
    assert SessionTracker.opens == SessionTracker.closes
    assert "offline.pdf" in result["url"]
