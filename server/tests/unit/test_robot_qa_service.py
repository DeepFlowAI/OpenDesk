"""Unit tests for robot-QA configuration services."""
from dataclasses import dataclass

import pytest

from app.core.exceptions import BusinessError
from app.libs.open_agent.base import (
    OpenAgentClientError,
    OpenAgentKnowledgeBaseListResult,
    OpenAgentKnowledgeBaseSummary,
    OpenAgentQaDirectoryListResult,
    OpenAgentQaDirectory,
    OpenAgentQaResult,
)
from app.models.conversation import Conversation
from app.models.message import Message
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.open_agent_settings_repository import OpenAgentSettingsRepository
from app.schemas.permission import EffectivePrincipal
from app.schemas.robot_qa import RobotQaCreatePayload, RobotQaSettingPayload
from app.services.conversation_service import ConversationService
from app.services.open_agent_settings_service import OpenAgentSettingsService
from app.services.robot_qa_service import RobotQaService


@dataclass
class FakeSettings:
    tenant_id: int = 1
    robot_qa_enabled: bool = False
    robot_qa_knowledge_base_id: int | None = 7
    robot_qa_knowledge_base_name: str | None = "Support"


class SessionState:
    active = 0


class FakeSessionContext:
    async def __aenter__(self):
        SessionState.active += 1
        return object()

    async def __aexit__(self, *_args):
        SessionState.active -= 1


class FakeSessionFactory:
    def __call__(self):
        return FakeSessionContext()


class FakeOpenAgentClient:
    def __init__(
        self,
        *,
        error: OpenAgentClientError | None = None,
        create_error: OpenAgentClientError | None = None,
    ):
        self.error = error
        self.create_error = create_error
        self.knowledge_base_calls: list[int] = []
        self.directory_calls: list[int] = []

    async def list_knowledge_bases(self, _base_url, _api_key, page=1, per_page=100):
        assert SessionState.active == 0
        if self.error:
            raise self.error
        self.knowledge_base_calls.append(page)
        items = [
            OpenAgentKnowledgeBaseSummary(
                id=7,
                name="Support",
                description="Support docs",
                status="active",
            )
        ] if page == 1 else [
            OpenAgentKnowledgeBaseSummary(
                id=8,
                name="Sales",
                description=None,
                status="active",
            )
        ]
        return OpenAgentKnowledgeBaseListResult(
            items=items,
            total=2,
            page=page,
            per_page=per_page,
            pages=2,
        )

    async def list_qa_directories(self, _base_url, _api_key, knowledge_base_id):
        assert SessionState.active == 0
        if self.error:
            raise self.error
        self.directory_calls.append(knowledge_base_id)
        return OpenAgentQaDirectoryListResult(
            items=[
                OpenAgentQaDirectory(
                    id=11,
                    parent_id=None,
                    name="未分类",
                    sort_order=0,
                    depth=1,
                    path=["未分类"],
                )
            ],
            total_qa_count=0,
        )

    async def create_qa(self, _base_url, _api_key, knowledge_base_id, payload):
        assert SessionState.active == 0
        if self.create_error:
            raise self.create_error
        return OpenAgentQaResult(
            id=21,
            knowledge_base_id=knowledge_base_id,
            directory_id=payload["directory_id"],
            directory_path=["未分类"],
            question=payload["question"],
            answer_markdown=payload["answer_markdown"],
            enabled=payload["enabled"],
            access_keywords=payload["access_keywords"],
            process_status="processing",
        )


@pytest.fixture(autouse=True)
def reset_session_state():
    SessionState.active = 0


@pytest.fixture
def managed_dependencies(monkeypatch):
    monkeypatch.setattr("app.services.robot_qa_service.AsyncSessionLocal", FakeSessionFactory())

    async def fake_credentials(_db, tenant_id):
        assert SessionState.active == 1
        assert tenant_id == 1
        return "https://new.example.com", "sk-saved"

    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_credentials)


@pytest.mark.asyncio
async def test_list_candidates_closes_session_before_upstream_calls(managed_dependencies):
    client = FakeOpenAgentClient()

    response = await RobotQaService.list_knowledge_bases_managed(1, client)

    assert [item.id for item in response.items] == [7, 8]
    assert client.knowledge_base_calls == [1, 2]
    assert client.directory_calls == [7]
    assert SessionState.active == 0


@pytest.mark.asyncio
async def test_list_candidates_maps_scope_error(managed_dependencies):
    client = FakeOpenAgentClient(
        error=OpenAgentClientError("forbidden", status_code=403, code="FORBIDDEN")
    )

    with pytest.raises(BusinessError) as exc_info:
        await RobotQaService.list_knowledge_bases_managed(1, client)

    assert exc_info.value.code == "ROBOT_QA_OPEN_AGENT_SCOPE_ERROR"
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_disabled_setting_preserves_target_without_upstream(monkeypatch):
    monkeypatch.setattr("app.services.robot_qa_service.AsyncSessionLocal", FakeSessionFactory())
    settings = FakeSettings(robot_qa_enabled=True)

    async def fake_get(_db, tenant_id):
        assert tenant_id == 1
        return settings

    async def fake_update(_db, item, data):
        item.robot_qa_enabled = data["robot_qa_enabled"]
        return item

    monkeypatch.setattr(OpenAgentSettingsRepository, "get_by_tenant_id", fake_get)
    monkeypatch.setattr(OpenAgentSettingsRepository, "update", fake_update)

    response = await RobotQaService.save_setting_managed(
        1,
        RobotQaSettingPayload(enabled=False, knowledge_base_id=None),
    )

    assert response.enabled is False
    assert response.knowledge_base_id == 7
    assert response.knowledge_base_name == "Support"


@pytest.mark.asyncio
async def test_enabled_setting_validates_then_persists(managed_dependencies, monkeypatch):
    client = FakeOpenAgentClient()
    settings = FakeSettings()

    async def fake_get(_db, _tenant_id):
        return settings

    async def fake_update(_db, item, data):
        for key, value in data.items():
            setattr(item, key, value)
        return item

    monkeypatch.setattr(OpenAgentSettingsRepository, "get_by_tenant_id", fake_get)
    monkeypatch.setattr(OpenAgentSettingsRepository, "update", fake_update)

    response = await RobotQaService.save_setting_managed(
        1,
        RobotQaSettingPayload(enabled=True, knowledge_base_id=7),
        client,
    )

    assert response.enabled is True
    assert response.knowledge_base_id == 7
    assert response.knowledge_base_name == "Support"
    assert client.directory_calls == [7]


@pytest.mark.asyncio
async def test_create_from_message_closes_session_before_upstream(managed_dependencies, monkeypatch):
    client = FakeOpenAgentClient()
    settings = FakeSettings(robot_qa_enabled=True)
    conversation = Conversation(id=5, tenant_id=1, visitor_id=3, public_id="conv", share_code="share", status="active")
    message = Message(
        id=9,
        tenant_id=1,
        conversation_id=5,
        sender_type="visitor",
        content_type="text",
        content="Original answer",
        is_recalled=False,
    )
    principal = EffectivePrincipal(
        user_id=2,
        tenant_id=1,
        permissions=["chat.workspace.use", "chat.conversation.robot_qa.create"],
    )

    async def fake_settings(_db, _tenant_id):
        return settings

    async def fake_conversation(_db, _conversation_id):
        return conversation

    async def fake_message(_db, **_kwargs):
        return message

    async def fake_access(_db, _principal, _conversation):
        return "own"

    monkeypatch.setattr(OpenAgentSettingsRepository, "get_by_tenant_id", fake_settings)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_conversation)
    monkeypatch.setattr(MessageRepository, "get_by_id_for_conversation", fake_message)
    monkeypatch.setattr(ConversationService, "_assert_conversation_view_access", fake_access)

    response = await RobotQaService.create_from_message_managed(
        conversation_id=5,
        message_id=9,
        principal=principal,
        data=RobotQaCreatePayload(
            directory_id=11,
            question="Question?",
            answer_markdown="Edited answer",
            access_keywords=["VIP"],
            enabled=True,
        ),
        open_agent_client=client,
    )

    assert response.id == 21
    assert response.process_status == "processing"
    assert SessionState.active == 0


@pytest.mark.asyncio
async def test_create_from_message_rejects_recalled_source(managed_dependencies, monkeypatch):
    settings = FakeSettings(robot_qa_enabled=True)
    conversation = Conversation(id=5, tenant_id=1, visitor_id=3, public_id="conv", share_code="share", status="active")
    message = Message(
        id=9,
        tenant_id=1,
        conversation_id=5,
        sender_type="visitor",
        content_type="text",
        content="Original answer",
        is_recalled=True,
    )
    principal = EffectivePrincipal(user_id=2, tenant_id=1)

    async def fake_settings(_db, _tenant_id):
        return settings

    async def fake_conversation(_db, _conversation_id):
        return conversation

    async def fake_message(_db, **_kwargs):
        return message

    async def fake_access(_db, _principal, _conversation):
        return "own"

    monkeypatch.setattr(OpenAgentSettingsRepository, "get_by_tenant_id", fake_settings)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_conversation)
    monkeypatch.setattr(MessageRepository, "get_by_id_for_conversation", fake_message)
    monkeypatch.setattr(ConversationService, "_assert_conversation_view_access", fake_access)

    with pytest.raises(BusinessError) as exc_info:
        await RobotQaService.create_from_message_managed(
            conversation_id=5,
            message_id=9,
            principal=principal,
            data=RobotQaCreatePayload(
                directory_id=11,
                question="Question?",
                answer_markdown="Answer",
            ),
            open_agent_client=FakeOpenAgentClient(),
        )

    assert exc_info.value.code == "ROBOT_QA_MESSAGE_UNAVAILABLE"


def test_create_payload_normalizes_access_keywords():
    payload = RobotQaCreatePayload(
        directory_id=11,
        question="Question?",
        answer_markdown="Answer",
        access_keywords=[" VIP_User ", "vip_user", "Support2"],
    )

    assert payload.access_keywords == ["vip_user", "support2"]


def test_duplicate_upstream_error_maps_to_question_error():
    with pytest.raises(BusinessError) as exc_info:
        RobotQaService._raise_open_agent_error(
            OpenAgentClientError("duplicate", status_code=409, code="CONFLICT"),
            allow_duplicate=True,
        )

    assert exc_info.value.code == "ROBOT_QA_QUESTION_DUPLICATE"
    assert exc_info.value.status_code == 409
