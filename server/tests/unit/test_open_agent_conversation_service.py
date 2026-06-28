"""
Unit tests for OpenAgent conversation proxy service.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json

import pytest

from app.core.exceptions import ValidationError
from app.enums import ConversationStatus
from app.libs.open_agent.base import OpenAgentFeedbackResult
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.open_agent_conversation import OpenAgentChatRequest, OpenAgentFeedbackRequest
from app.services.conversation_service import ConversationService
from app.services.open_agent_conversation_service import OpenAgentConversationService
from app.services.open_agent_settings_service import OpenAgentSettingsService


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
    agent_id: int | None = None
    visitor: FakeVisitor = field(default_factory=FakeVisitor)
    channel: FakeChannel = field(default_factory=lambda: FakeChannel({
        "open_agent_enabled": True,
        "open_agent_agent_id": 7,
        "open_agent_agent_name": "Support Bot",
    }))
    open_agent_agent_name: str | None = "Support Bot"
    open_agent_conversation_id: int | None = None
    open_agent_conversation_external_id: str | None = None
    open_agent_last_event_id: str | None = None
    open_agent_handoff_state: str | None = None
    open_agent_handoff_payload: dict = field(default_factory=dict)


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


class FakeOpenAgentClient:
    async def stream_chat(self, _base_url, _api_key, _agent_id, _payload):
        yield b"event: content_delta\ndata: {\"content\":\"Hello\"}\n\n"
        yield b"event: done\ndata: {\"final_content\":\"Hello\"}\n\n"


class FakeToolOpenAgentClient:
    async def stream_chat(self, _base_url, _api_key, _agent_id, _payload):
        yield b"event: content_delta\ndata: {\"content\":\"Let me check.\"}\n\n"
        yield (
            b"event: tool_call\n"
            b"data: {\"tool_call_id\":\"call_1\",\"tool_name\":\"search\",\"brief\":\"Search docs\",\"arguments\":{\"query\":\"pricing\"}}\n\n"
        )
        yield b"event: tool_result\ndata: {\"tool_call_id\":\"call_1\",\"result\":\"pricing found\"}\n\n"
        yield b"event: done\ndata: {\"final_content\":\"Pricing is available.\"}\n\n"


class FakeInterleavedContentOpenAgentClient:
    async def stream_chat(self, _base_url, _api_key, _agent_id, _payload):
        yield (
            b"event: tool_call\n"
            b"data: {\"tool_call_id\":\"call_1\",\"tool_name\":\"search\",\"brief\":\"Search docs\"}\n\n"
        )
        yield b"event: tool_result\ndata: {\"tool_call_id\":\"call_1\",\"result\":\"found\"}\n\n"
        yield b"event: content_delta\ndata: {\"content\":\"Detailed answer.\"}\n\n"
        yield (
            b"event: tool_call\n"
            b"data: {\"tool_call_id\":\"call_2\",\"tool_name\":\"search\",\"brief\":\"Search more\"}\n\n"
        )
        yield b"event: tool_result\ndata: {\"tool_call_id\":\"call_2\",\"result\":\"more found\"}\n\n"
        yield b"event: done\ndata: {\"final_content\":\"Final summary.\"}\n\n"


class FakeThinkingOpenAgentClient:
    async def stream_chat(self, _base_url, _api_key, _agent_id, _payload):
        yield b"event: llm_step_created\ndata: {\"step_id\":42}\n\n"
        yield b"event: thinking_delta\ndata: {\"content\":\"Need to inspect the doc.\"}\n\n"
        yield b"event: content_delta\ndata: {\"content\":\"Here is the answer.\"}\n\n"
        yield b"event: done\ndata: {\"final_content\":\"Here is the answer.\"}\n\n"


class CapturingOpenAgentClient:
    def __init__(self, chunks: list[bytes] | None = None):
        self.payloads: list[dict] = []
        self.chunks = chunks or [b"event: done\ndata: {}\n\n"]

    async def stream_chat(self, _base_url, _api_key, _agent_id, payload):
        self.payloads.append(payload)
        for chunk in self.chunks:
            yield chunk


class FakeHandoffClient:
    async def stream_chat(self, _base_url, _api_key, _agent_id, _payload):
        payload = {
            "event_kind": "human_handoff",
            "schema_version": 1,
            "handoff": {"brief": "需要人工处理", "reason": "complex"},
        }
        yield f"event: human_handoff_event\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
        yield b"event: done\ndata: {}\n\n"


class FakeToolResultHandoffClient:
    async def stream_chat(self, _base_url, _api_key, _agent_id, _payload):
        tool_call = {
            "tool_call_id": "call_handoff",
            "tool_name": "human_handoff",
            "arguments": {"brief": "需要人工协助", "reason": "billing issue"},
        }
        tool_result = {
            "tool_call_id": "call_handoff",
            "tool_name": "human_handoff",
            "result": {"brief": "需要人工协助", "reason": "billing issue"},
        }
        yield f"event: tool_call\ndata: {json.dumps(tool_call, ensure_ascii=False)}\n\n".encode()
        yield f"event: tool_result\ndata: {json.dumps(tool_result, ensure_ascii=False)}\n\n".encode()
        yield f"event: content_delta\ndata: {json.dumps({'content': '已为您记录。'}, ensure_ascii=False)}\n\n".encode()
        yield f"event: done\ndata: {json.dumps({'final_content': '已为您记录。'}, ensure_ascii=False)}\n\n".encode()


class FakeDuplicateHandoffClient:
    async def stream_chat(self, _base_url, _api_key, _agent_id, _payload):
        payload = {
            "event_kind": "human_handoff",
            "schema_version": 1,
            "tool_call_id": "call_handoff",
            "handoff": {"brief": "需要人工处理", "reason": "complex"},
        }
        tool_result = {
            "tool_call_id": "call_handoff",
            "tool_name": "human_handoff",
            "result": {"brief": "需要人工处理", "reason": "complex"},
        }
        yield f"event: tool_result\ndata: {json.dumps(tool_result, ensure_ascii=False)}\n\n".encode()
        yield f"event: human_handoff_event\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
        yield b"event: done\ndata: {}\n\n"


class FakeToolResultHandoffWithoutToolNameClient:
    async def stream_chat(self, _base_url, _api_key, _agent_id, _payload):
        tool_call = {
            "call_id": "call_handoff",
            "name": "human_handoff",
            "arguments": {"brief": "需要人工协助", "reason": "billing issue"},
        }
        tool_result = {
            "call_id": "call_handoff",
            "result": {"brief": "需要人工协助", "reason": "billing issue"},
        }
        yield f"event: tool_call\ndata: {json.dumps(tool_call, ensure_ascii=False)}\n\n".encode()
        yield f"event: tool_result\ndata: {json.dumps(tool_result, ensure_ascii=False)}\n\n".encode()
        yield b"event: done\ndata: {}\n\n"


class FakeRequiredActionHandoffClient:
    def __init__(self, tool_result_chunks: list[bytes] | None = None):
        self.tool_result_payloads: list[dict] = []
        self.tool_result_conversation_ids: list[int] = []
        self.tool_result_chunks = tool_result_chunks or [
            (
                "event: human_handoff_event\n"
                f"data: {json.dumps({'event_kind': 'human_handoff', 'schema_version': 1, 'tool_call_id': 'call_handoff', 'handoff': {'brief': '需要人工协助', 'reason': 'billing issue'}}, ensure_ascii=False)}\n\n"
            ).encode(),
            b"event: done\ndata: {\"finish_reason\":\"handoff_success\"}\n\n",
        ]

    async def stream_chat(self, _base_url, _api_key, _agent_id, _payload):
        tool_call = {
            "tool_call_id": "call_handoff",
            "tool_name": "human_handoff",
            "arguments": {"brief": "需要人工协助", "reason": "billing issue"},
        }
        action = {
            "type": "submit_tool_result",
            "tool_call_step_id": 55,
            "tool_call_id": "call_handoff",
            "tool_name": "human_handoff",
            "tool_type": "human_handoff",
            "brief": "需要人工协助",
        }
        yield b"event: conversation_created\ndata: {\"conversation_id\": 42, \"external_id\":\"conv_42\"}\n\n"
        yield f"event: tool_call\ndata: {json.dumps(tool_call, ensure_ascii=False)}\n\n".encode()
        yield f"event: requires_action\ndata: {json.dumps(action, ensure_ascii=False)}\n\n".encode()
        yield b"event: done\ndata: {\"finish_reason\":\"tool_result_required\"}\n\n"

    async def stream_tool_result(self, _base_url, _api_key, _agent_id, conversation_id, payload):
        self.tool_result_conversation_ids.append(conversation_id)
        self.tool_result_payloads.append(payload)
        for chunk in self.tool_result_chunks:
            yield chunk


class FakeFeedbackOpenAgentClient:
    def __init__(self):
        self.agent_ids: list[int] = []
        self.conversation_ids: list[int] = []
        self.step_ids: list[int] = []
        self.payloads: list[dict] = []

    async def submit_feedback(self, _base_url, _api_key, agent_id, conversation_id, step_id, payload):
        self.agent_ids.append(agent_id)
        self.conversation_ids.append(conversation_id)
        self.step_ids.append(step_id)
        self.payloads.append(payload)
        return OpenAgentFeedbackResult(
            step_id=step_id,
            rating=payload["rating"],
            comment=payload.get("comment"),
            updated_at="2026-06-23T00:00:00+00:00",
        )


class FakeAsyncSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_exc_info):
        return None


@pytest.fixture(autouse=True)
def patch_managed_stream_session(monkeypatch):
    monkeypatch.setattr(
        "app.services.open_agent_conversation_service.AsyncSessionLocal",
        lambda: FakeAsyncSessionContext(),
    )


async def stream_chat_for_session_under_test(
    _db,
    conversation_public_id: str,
    visitor_context: dict,
    body: OpenAgentChatRequest,
    open_agent_client=None,
    redis=None,
):
    async for chunk in OpenAgentConversationService.stream_chat_for_session_managed(
        conversation_public_id,
        visitor_context,
        body,
        open_agent_client=open_agent_client,
        redis=redis,
    ):
        yield chunk


def patch_required_action_stream_dependencies(monkeypatch, conversation, created_messages: list[dict]):
    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **_kwargs):
        return None

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_update_handoff_state_if_unassigned(
        _db,
        conv,
        *,
        state,
        payload,
        status=None,
        allowed_previous_states=None,
    ):
        if (
            allowed_previous_states is not None
            and conv.open_agent_handoff_state not in allowed_previous_states
        ):
            return conv, False
        conv.open_agent_handoff_state = state
        conv.open_agent_handoff_payload = payload or {}
        if status:
            conv.status = status
        return conv, True

    async def fake_create(_db, data):
        created_messages.append(data)
        return FakeMessage(id=len(created_messages) + 20, **data)

    async def fake_noop(*_args, **_kwargs):
        return None

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(
        ConversationRepository,
        "update_handoff_state_if_unassigned",
        fake_update_handoff_state_if_unassigned,
    )
    monkeypatch.setattr(MessageRepository, "create", fake_create)
    monkeypatch.setattr(ConversationRepository, "update_last_message", fake_noop)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)


@pytest.mark.asyncio
async def test_stream_chat_saves_final_bot_message(monkeypatch):
    conversation = FakeConversation()
    created_messages: list[dict] = []

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **_kwargs):
        return FakeMessage(
            id=1,
            tenant_id=1,
            conversation_id=conversation.id,
            sender_type="visitor",
            sender_id=11,
            content_type="text",
            content="hi",
            metadata_={},
        )

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_create(_db, data):
        created_messages.append(data)
        return FakeMessage(id=len(created_messages) + 10, **data)

    async def fake_noop(*_args, **_kwargs):
        return None

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(MessageRepository, "create", fake_create)
    monkeypatch.setattr(ConversationRepository, "update_last_message", fake_noop)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    client = CapturingOpenAgentClient([
        b"event: content_delta\ndata: {\"content\":\"Hello\"}\n\n",
        b"event: done\ndata: {\"final_content\":\"Hello\"}\n\n",
    ])

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="hi", client_message_id="cm_1"),
        open_agent_client=client,
    )
    chunks = [chunk async for chunk in stream]

    assert any(b"open_desk_message_saved" in chunk for chunk in chunks)
    assert client.payloads
    assert client.payloads[0]["message"] == "hi"
    assert "messages" not in client.payloads[0]
    assert "open_agent_welcome_blocks" not in json.dumps(client.payloads[0], ensure_ascii=False)
    assert created_messages[-1]["sender_type"] == "bot"
    assert created_messages[-1]["content"] == "Hello"
    assert created_messages[-1]["metadata_"]["client_message_id"] == "cm_1"


@pytest.mark.asyncio
async def test_managed_stream_chat_closes_db_session_while_waiting_for_open_agent(monkeypatch):
    conversation = FakeConversation()
    created_messages: list[dict] = []

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

    class SessionAwareOpenAgentClient:
        def __init__(self):
            self.payloads: list[dict] = []
            self.active_states: list[bool] = []

        async def stream_chat(self, _base_url, _api_key, _agent_id, payload):
            self.payloads.append(payload)
            self.active_states.append(SessionTracker.active)
            yield b"event: content_delta\ndata: {\"content\":\"Hello\"}\n\n"
            self.active_states.append(SessionTracker.active)
            yield b"event: done\ndata: {\"final_content\":\"Hello\"}\n\n"
            self.active_states.append(SessionTracker.active)

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **_kwargs):
        return None

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_create(_db, data):
        created_messages.append(data)
        return FakeMessage(id=len(created_messages) + 10, **data)

    async def fake_noop(*_args, **_kwargs):
        return None

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(
        "app.services.open_agent_conversation_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(MessageRepository, "create", fake_create)
    monkeypatch.setattr(ConversationRepository, "update_last_message", fake_noop)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    client = SessionAwareOpenAgentClient()
    stream = OpenAgentConversationService.stream_chat_for_session_managed(
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="hi", client_message_id="cm_managed"),
        open_agent_client=client,
    )
    chunks = [chunk async for chunk in stream]

    assert any(b"open_desk_message_saved" in chunk for chunk in chunks)
    assert client.active_states == [False, False, False]
    assert SessionTracker.opens >= 2
    assert SessionTracker.opens == SessionTracker.closes
    assert created_messages[-1]["sender_type"] == "bot"
    assert created_messages[-1]["metadata_"]["client_message_id"] == "cm_managed"


@pytest.mark.asyncio
async def test_managed_auto_handoff_tool_result_closes_db_session_while_waiting(monkeypatch):
    conversation = FakeConversation(
        channel=FakeChannel({
            "open_agent_enabled": True,
            "open_agent_agent_id": 7,
            "open_agent_agent_name": "Support Bot",
            "open_agent_handoff_behavior": "auto",
        }),
    )
    created_messages: list[dict] = []

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

    class SessionAwareRequiredActionClient(FakeRequiredActionHandoffClient):
        def __init__(self):
            super().__init__([
                b"event: content_delta\ndata: {\"content\":\"handoff routed\"}\n\n",
                b"event: done\ndata: {\"final_content\":\"handoff routed\"}\n\n",
            ])
            self.tool_result_active_states: list[bool] = []

        async def stream_tool_result(self, base_url, api_key, agent_id, conversation_id, payload):
            self.tool_result_active_states.append(SessionTracker.active)
            async for chunk in super().stream_tool_result(
                base_url,
                api_key,
                agent_id,
                conversation_id,
                payload,
            ):
                self.tool_result_active_states.append(SessionTracker.active)
                yield chunk

    patch_required_action_stream_dependencies(monkeypatch, conversation, created_messages)
    monkeypatch.setattr(
        "app.services.open_agent_conversation_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )

    async def fake_request_handoff(*_args, **_kwargs):
        conversation.status = ConversationStatus.ACTIVE.value
        conversation.agent_id = 33
        return {
            "ok": True,
            "conversation": conversation,
            "message": {
                "id": 101,
                "conversation_public_id": conversation.public_id,
                "sender_type": "system",
                "content_type": "system",
                "content": "已为您转接人工客服",
                "metadata": {"event_type": "open_agent_handoff_success"},
            },
            "messages": [],
            "agent": None,
        }

    monkeypatch.setattr(ConversationService, "request_human_handoff_for_session", fake_request_handoff)

    client = SessionAwareRequiredActionClient()
    stream = OpenAgentConversationService.stream_chat_for_session_managed(
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="help", client_message_id="cm_managed_auto_handoff"),
        open_agent_client=client,
        redis=object(),
    )
    chunks = [chunk async for chunk in stream]

    assert any(b"open_desk_conversation_status" in chunk for chunk in chunks)
    assert client.tool_result_payloads == [{
        "tool_call_id": "call_handoff",
        "status": "handoff_success",
        "message": "已为您转接人工客服",
    }]
    assert client.tool_result_active_states == [False, False, False]
    assert SessionTracker.opens == SessionTracker.closes
    assert created_messages[-1]["sender_type"] == "bot"


@pytest.mark.asyncio
async def test_managed_submit_handoff_tool_result_closes_db_session_while_waiting(monkeypatch):
    conversation = FakeConversation(open_agent_conversation_id=42)
    created_messages: list[dict] = []

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

    class SessionAwareToolResultClient:
        def __init__(self):
            self.payloads: list[dict] = []
            self.active_states: list[bool] = []

        async def stream_tool_result(self, _base_url, _api_key, _agent_id, _conversation_id, payload):
            self.payloads.append(payload)
            self.active_states.append(SessionTracker.active)
            yield b"event: content_delta\ndata: {\"content\":\"handoff recorded\"}\n\n"
            self.active_states.append(SessionTracker.active)
            yield b"event: done\ndata: {\"final_content\":\"handoff recorded\"}\n\n"
            self.active_states.append(SessionTracker.active)

    patch_required_action_stream_dependencies(monkeypatch, conversation, created_messages)
    monkeypatch.setattr(
        "app.services.open_agent_conversation_service.AsyncSessionLocal",
        lambda: FakeSessionContext(),
    )

    client = SessionAwareToolResultClient()
    events = await OpenAgentConversationService.submit_handoff_tool_result_for_session_managed(
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        tool_call_id="call_handoff",
        status=OpenAgentConversationService._HANDOFF_TOOL_RESULT_FAILED,
        message="用户选择继续咨询智能助手。",
        open_agent_client=client,
    )

    assert any(b"open_desk_message_saved" in event for event in events)
    assert client.payloads == [{
        "tool_call_id": "call_handoff",
        "status": "handoff_failed",
        "message": "用户选择继续咨询智能助手。",
    }]
    assert client.active_states == [False, False, False]
    assert SessionTracker.opens >= 2
    assert SessionTracker.opens == SessionTracker.closes
    assert created_messages[-1]["sender_type"] == "bot"


@pytest.mark.asyncio
@pytest.mark.parametrize("step_id_key", ["feedback_step_id", "assistant_step_id"])
async def test_stream_chat_saves_done_payload_step_id_for_feedback(monkeypatch, step_id_key):
    conversation = FakeConversation()
    created_messages: list[dict] = []

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **_kwargs):
        return None

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_create(_db, data):
        created_messages.append(data)
        return FakeMessage(id=len(created_messages) + 10, **data)

    async def fake_noop(*_args, **_kwargs):
        return None

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(MessageRepository, "create", fake_create)
    monkeypatch.setattr(ConversationRepository, "update_last_message", fake_noop)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    client = CapturingOpenAgentClient([
        b"event: content_delta\ndata: {\"content\":\"Hello\"}\n\n",
        (
            b"event: done\ndata: "
            + json.dumps({"final_content": "Hello", step_id_key: 88}).encode()
            + b"\n\n"
        ),
    ])

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="hi", client_message_id="cm_feedback"),
        open_agent_client=client,
    )
    _chunks = [chunk async for chunk in stream]

    assert created_messages[-1]["metadata_"]["open_agent_feedback_step_id"] == 88


@pytest.mark.asyncio
async def test_submit_feedback_updates_bot_message_metadata(monkeypatch):
    conversation = FakeConversation(
        open_agent_conversation_id=42,
        channel=FakeChannel({
            "open_agent_enabled": True,
            "open_agent_agent_id": 7,
            "open_agent_agent_name": "Support Bot",
            "open_agent_feedback_enabled": True,
        }),
    )
    message = FakeMessage(
        id=51,
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        sender_type="bot",
        content_type="text",
        content="Hello",
        metadata_={
            "open_agent_feedback_step_id": 88,
            "open_agent_feedback": {
                "schema_version": 1,
                "step_id": 88,
                "rating": "dislike",
                "comment": "old",
                "updated_at": "2026-06-22T00:00:00+00:00",
            },
        },
    )

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_message(*_args, **_kwargs):
        return message

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_update_metadata(_db, msg, metadata):
        msg.metadata_ = metadata
        return msg

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(MessageRepository, "get_by_id_for_conversation", fake_get_message)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "update_metadata", fake_update_metadata)

    client = FakeFeedbackOpenAgentClient()
    result = await OpenAgentConversationService.submit_feedback_for_session(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentFeedbackRequest(message_id=51, step_id=88, rating="like", comment="ignored"),
        open_agent_client=client,
    )

    assert client.agent_ids == [7]
    assert client.conversation_ids == [42]
    assert client.step_ids == [88]
    assert client.payloads == [{"rating": "like", "comment": None}]
    assert message.metadata_["open_agent_feedback"]["rating"] == "like"
    assert message.metadata_["open_agent_feedback"]["comment"] is None
    assert result["message"]["metadata"]["open_agent_feedback"]["updated_at"] == "2026-06-23T00:00:00+00:00"


@pytest.mark.asyncio
async def test_submit_feedback_rejects_when_open_agent_conversation_missing(monkeypatch):
    conversation = FakeConversation(
        channel=FakeChannel({
            "open_agent_enabled": True,
            "open_agent_agent_id": 7,
            "open_agent_feedback_enabled": True,
        }),
    )
    message = FakeMessage(
        id=51,
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        sender_type="bot",
        content_type="text",
        content="Hello",
        metadata_={"open_agent_feedback_step_id": 88},
    )

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_message(*_args, **_kwargs):
        return message

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(MessageRepository, "get_by_id_for_conversation", fake_get_message)

    with pytest.raises(ValidationError, match="conversation is not available"):
        await OpenAgentConversationService.submit_feedback_for_session(
            object(),
            "cv_test",
            {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
            OpenAgentFeedbackRequest(message_id=51, step_id=88, rating="like"),
            open_agent_client=FakeFeedbackOpenAgentClient(),
        )


@pytest.mark.asyncio
async def test_submit_feedback_rejects_when_channel_switch_disabled(monkeypatch):
    conversation = FakeConversation()

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)

    with pytest.raises(ValidationError, match="feedback is not enabled"):
        await OpenAgentConversationService.submit_feedback_for_session(
            object(),
            "cv_test",
            {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
            OpenAgentFeedbackRequest(message_id=51, step_id=88, rating="like"),
            open_agent_client=FakeFeedbackOpenAgentClient(),
        )


@pytest.mark.asyncio
async def test_stream_chat_saves_tool_blocks_in_bot_metadata(monkeypatch):
    conversation = FakeConversation()
    created_messages: list[dict] = []

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **_kwargs):
        return None

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_create(_db, data):
        created_messages.append(data)
        return FakeMessage(id=len(created_messages) + 10, **data)

    async def fake_noop(*_args, **_kwargs):
        return None

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(MessageRepository, "create", fake_create)
    monkeypatch.setattr(ConversationRepository, "update_last_message", fake_noop)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="price?", client_message_id="cm_tool"),
        open_agent_client=FakeToolOpenAgentClient(),
    )
    chunks = [chunk async for chunk in stream]

    assert any(b"event: tool_call" in chunk for chunk in chunks)
    assert any(b"open_desk_message_saved" in chunk for chunk in chunks)
    assert created_messages[-1]["content"] == "Let me check.\n\nPricing is available."
    text_blocks = created_messages[-1]["metadata_"]["open_agent_text_blocks"]
    tool_blocks = created_messages[-1]["metadata_"]["open_agent_tool_blocks"]
    assert [block["content"] for block in text_blocks] == ["Let me check.", "Pricing is available."]
    assert text_blocks[0]["timelineIndex"] < tool_blocks[0]["timelineIndex"] < text_blocks[1]["timelineIndex"]
    assert tool_blocks[0]["toolCallId"] == "call_1"
    assert tool_blocks[0]["toolName"] == "search"
    assert tool_blocks[0]["brief"] == "Search docs"
    assert tool_blocks[0]["arguments"] == {"query": "pricing"}
    assert tool_blocks[0]["result"] == "pricing found"
    assert tool_blocks[0]["isExecuting"] is False


@pytest.mark.asyncio
async def test_stream_chat_preserves_content_between_tool_calls(monkeypatch):
    conversation = FakeConversation()
    created_messages: list[dict] = []

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **_kwargs):
        return None

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_create(_db, data):
        created_messages.append(data)
        return FakeMessage(id=len(created_messages) + 10, **data)

    async def fake_noop(*_args, **_kwargs):
        return None

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(MessageRepository, "create", fake_create)
    monkeypatch.setattr(ConversationRepository, "update_last_message", fake_noop)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="details?", client_message_id="cm_interleaved"),
        open_agent_client=FakeInterleavedContentOpenAgentClient(),
    )
    _chunks = [chunk async for chunk in stream]

    saved = created_messages[-1]
    text_blocks = saved["metadata_"]["open_agent_text_blocks"]
    tool_blocks = saved["metadata_"]["open_agent_tool_blocks"]
    assert saved["content"] == "Detailed answer.\n\nFinal summary."
    assert [block["content"] for block in text_blocks] == ["Detailed answer.", "Final summary."]
    assert [block["brief"] for block in tool_blocks] == ["Search docs", "Search more"]
    assert tool_blocks[0]["timelineIndex"] < text_blocks[0]["timelineIndex"] < tool_blocks[1]["timelineIndex"]
    assert text_blocks[1]["timelineIndex"] > tool_blocks[1]["timelineIndex"]


@pytest.mark.asyncio
async def test_stream_chat_saves_thinking_blocks_in_bot_metadata(monkeypatch):
    conversation = FakeConversation()
    created_messages: list[dict] = []

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **_kwargs):
        return None

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_create(_db, data):
        created_messages.append(data)
        return FakeMessage(id=len(created_messages) + 10, **data)

    async def fake_noop(*_args, **_kwargs):
        return None

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(MessageRepository, "create", fake_create)
    monkeypatch.setattr(ConversationRepository, "update_last_message", fake_noop)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="think?", client_message_id="cm_think"),
        open_agent_client=FakeThinkingOpenAgentClient(),
    )
    chunks = [chunk async for chunk in stream]

    assert any(b"event: thinking_delta" in chunk for chunk in chunks)
    thinking_blocks = created_messages[-1]["metadata_"]["open_agent_thinking_blocks"]
    assert thinking_blocks[0]["content"] == "Need to inspect the doc."
    assert thinking_blocks[0]["llmStepId"] == 42
    assert thinking_blocks[0]["isStreaming"] is False


@pytest.mark.asyncio
async def test_new_chat_does_not_forward_stale_last_event_id(monkeypatch):
    conversation = FakeConversation(open_agent_last_event_id="r1-e9")
    client = CapturingOpenAgentClient()

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **_kwargs):
        return None

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="new turn", client_message_id="cm_new"),
        open_agent_client=client,
    )
    _chunks = [chunk async for chunk in stream]

    assert "last_event_id" not in client.payloads[0]
    assert conversation.open_agent_last_event_id is None


@pytest.mark.asyncio
async def test_resume_chat_uses_saved_last_event_id_when_omitted(monkeypatch):
    conversation = FakeConversation(open_agent_last_event_id="r1-e9")
    client = CapturingOpenAgentClient()

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return object()

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="resume", client_message_id="cm_new", resume=True),
        open_agent_client=client,
    )
    _chunks = [chunk async for chunk in stream]

    assert client.payloads[0]["last_event_id"] == "r1-e9"


@pytest.mark.asyncio
async def test_resume_chat_with_explicit_client_id_saves_missing_visitor_message(monkeypatch):
    conversation = FakeConversation(open_agent_last_event_id="r1-e9")
    client = CapturingOpenAgentClient()
    sent_messages: list[dict] = []

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **kwargs):
        sent_messages.append(kwargs)
        return FakeMessage(
            id=31,
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            sender_type=kwargs["sender_type"],
            sender_id=kwargs["sender_id"],
            content_type=kwargs["content_type"],
            content=kwargs["content"],
            metadata_=kwargs["metadata"],
        )

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="resume", client_message_id="cm_retry", resume=True),
        open_agent_client=client,
    )
    _chunks = [chunk async for chunk in stream]

    assert sent_messages[0]["content"] == "resume"
    assert sent_messages[0]["metadata"]["client_message_id"] == "cm_retry"
    assert sent_messages[0]["metadata"]["open_agent"] is True
    assert client.payloads[0]["resume"] is True
    assert client.payloads[0]["last_event_id"] == "r1-e9"


@pytest.mark.asyncio
async def test_stream_chat_records_handoff_event_as_system_message(monkeypatch):
    conversation = FakeConversation()
    created_messages: list[dict] = []

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **_kwargs):
        return None

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_update_status(_db, conv, status):
        conv.status = status
        return conv

    async def fake_update_handoff_state_if_unassigned(
        _db,
        conv,
        *,
        state,
        payload,
        status=None,
        allowed_previous_states=None,
    ):
        if conv.agent_id or conv.status not in {
            ConversationStatus.BOT.value,
            ConversationStatus.HANDOFF_PENDING.value,
        }:
            return conv, False
        if (
            allowed_previous_states is not None
            and conv.open_agent_handoff_state not in allowed_previous_states
        ):
            return conv, False
        conv.open_agent_handoff_state = state
        conv.open_agent_handoff_payload = payload or {}
        if status:
            conv.status = status
        return conv, True

    async def fake_create(_db, data):
        created_messages.append(data)
        return FakeMessage(id=len(created_messages) + 20, **data)

    async def fake_noop(*_args, **_kwargs):
        return None

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(ConversationRepository, "update_status", fake_update_status)
    monkeypatch.setattr(
        ConversationRepository,
        "update_handoff_state_if_unassigned",
        fake_update_handoff_state_if_unassigned,
    )
    monkeypatch.setattr(MessageRepository, "create", fake_create)
    monkeypatch.setattr(ConversationRepository, "update_last_message", fake_noop)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="help", client_message_id="cm_2"),
        open_agent_client=FakeHandoffClient(),
    )
    chunks = [chunk async for chunk in stream]

    assert any(b"open_desk_message_saved" in chunk for chunk in chunks)
    assert created_messages[0]["sender_type"] == "system"
    assert created_messages[0]["metadata_"]["event_type"] == "open_agent_handoff_event"
    assert created_messages[0]["metadata_"]["handoff_event_type"] == "confirm_requested"
    assert conversation.status == ConversationStatus.HANDOFF_PENDING.value


@pytest.mark.asyncio
async def test_handoff_event_does_not_revert_active_conversation(monkeypatch):
    conversation = FakeConversation(
        status=ConversationStatus.ACTIVE.value,
        agent_id=22,
        open_agent_handoff_state="success",
    )

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    async def fail_update(*_args, **_kwargs):
        raise AssertionError("active conversation should not be marked pending")

    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(ConversationRepository, "update_handoff_state_if_unassigned", fail_update)

    saved = await OpenAgentConversationService._save_handoff_event(
        object(),
        conversation,
        {
            "event_kind": "human_handoff",
            "schema_version": 1,
            "handoff": {"brief": "需要人工处理"},
        },
    )

    assert saved is None
    assert conversation.status == ConversationStatus.ACTIVE.value
    assert conversation.agent_id == 22


@pytest.mark.asyncio
async def test_stream_chat_records_tool_result_handoff_as_system_message(monkeypatch):
    conversation = FakeConversation()
    created_messages: list[dict] = []

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **_kwargs):
        return None

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_update_handoff_state_if_unassigned(
        _db,
        conv,
        *,
        state,
        payload,
        status=None,
        allowed_previous_states=None,
    ):
        conv.open_agent_handoff_state = state
        conv.open_agent_handoff_payload = payload or {}
        if status:
            conv.status = status
        return conv, True

    async def fake_create(_db, data):
        created_messages.append(data)
        return FakeMessage(id=len(created_messages) + 20, **data)

    async def fake_noop(*_args, **_kwargs):
        return None

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(
        ConversationRepository,
        "update_handoff_state_if_unassigned",
        fake_update_handoff_state_if_unassigned,
    )
    monkeypatch.setattr(MessageRepository, "create", fake_create)
    monkeypatch.setattr(ConversationRepository, "update_last_message", fake_noop)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="help", client_message_id="cm_tool_handoff"),
        open_agent_client=FakeToolResultHandoffClient(),
    )
    chunks = [chunk async for chunk in stream]

    assert any(b"open_desk_message_saved" in chunk for chunk in chunks)
    assert len(created_messages) == 2
    assert created_messages[0]["sender_type"] == "system"
    assert created_messages[0]["content"] == "需要人工协助"
    assert created_messages[0]["metadata_"]["event_type"] == "open_agent_handoff_event"
    assert created_messages[0]["metadata_"]["handoff_event_type"] == "confirm_requested"
    assert created_messages[0]["metadata_"]["handoff_source"] == "bot_tool"
    assert created_messages[0]["metadata_"]["tool_call_id"] == "call_handoff"
    assert created_messages[1]["sender_type"] == "bot"
    assert created_messages[1]["metadata_"]["bot_message_used_for_handoff"] is True
    tool_blocks = created_messages[1]["metadata_"]["open_agent_tool_blocks"]
    assert tool_blocks[0]["usedForHandoff"] is True


@pytest.mark.asyncio
async def test_duplicate_handoff_signals_only_create_one_system_message(monkeypatch):
    conversation = FakeConversation()
    created_messages: list[dict] = []

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **_kwargs):
        return None

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_update_handoff_state_if_unassigned(
        _db,
        conv,
        *,
        state,
        payload,
        status=None,
        allowed_previous_states=None,
    ):
        conv.open_agent_handoff_state = state
        conv.open_agent_handoff_payload = payload or {}
        if status:
            conv.status = status
        return conv, True

    async def fake_create(_db, data):
        created_messages.append(data)
        return FakeMessage(id=len(created_messages) + 20, **data)

    async def fake_noop(*_args, **_kwargs):
        return None

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(
        ConversationRepository,
        "update_handoff_state_if_unassigned",
        fake_update_handoff_state_if_unassigned,
    )
    monkeypatch.setattr(MessageRepository, "create", fake_create)
    monkeypatch.setattr(ConversationRepository, "update_last_message", fake_noop)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="help", client_message_id="cm_dup_handoff"),
        open_agent_client=FakeDuplicateHandoffClient(),
    )
    _chunks = [chunk async for chunk in stream]

    system_messages = [item for item in created_messages if item["sender_type"] == "system"]
    assert len(system_messages) == 1
    assert system_messages[0]["metadata_"]["handoff_source"] == "bot_tool"


@pytest.mark.asyncio
async def test_pending_duplicate_tool_result_updates_handoff_payload(monkeypatch):
    conversation = FakeConversation(
        status=ConversationStatus.HANDOFF_PENDING.value,
        open_agent_handoff_state="pending",
        open_agent_handoff_payload={
            "event_kind": "human_handoff",
            "schema_version": 1,
            "tool_call_id": "call_handoff",
            "handoff": {"brief": "旧话术", "reason": "old"},
        },
    )

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)

    saved = await OpenAgentConversationService._save_handoff_event(
        object(),
        conversation,
        {
            "event_kind": "human_handoff",
            "schema_version": 1,
            "tool_call_id": "call_handoff",
            "handoff": {"brief": "新话术", "reason": "new"},
        },
        handoff_source="bot_tool",
        handoff_event_type="confirm_requested",
        tool_call_id="call_handoff",
        processed_tool_call_ids={"call_handoff"},
    )

    assert saved is not None
    assert saved["event"] == "open_desk_handoff_updated"
    assert conversation.open_agent_handoff_payload["handoff"]["brief"] == "新话术"


@pytest.mark.asyncio
async def test_dismissed_tool_call_is_consumed(monkeypatch):
    conversation = FakeConversation(
        status=ConversationStatus.BOT.value,
        open_agent_handoff_state="dismissed",
        open_agent_handoff_payload={
            "event_kind": "human_handoff",
            "schema_version": 1,
            "tool_call_id": "call_handoff",
            "handoff": {"brief": "需要人工处理"},
        },
    )

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    async def fail_update(*_args, **_kwargs):
        raise AssertionError("dismissed tool_call_id should not create a new handoff event")

    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(ConversationRepository, "update_handoff_state_if_unassigned", fail_update)

    saved = await OpenAgentConversationService._save_handoff_event(
        object(),
        conversation,
        {
            "event_kind": "human_handoff",
            "schema_version": 1,
            "tool_call_id": "call_handoff",
            "handoff": {"brief": "需要人工处理"},
        },
        handoff_source="bot_tool",
        handoff_event_type="confirm_requested",
        tool_call_id="call_handoff",
    )

    assert saved is None


@pytest.mark.asyncio
async def test_new_tool_call_after_dismiss_can_prompt_again(monkeypatch):
    conversation = FakeConversation(
        status=ConversationStatus.BOT.value,
        open_agent_handoff_state="dismissed",
        open_agent_handoff_payload={
            "event_kind": "human_handoff",
            "schema_version": 1,
            "tool_call_id": "old_call",
            "handoff": {"brief": "旧话术"},
        },
    )
    created_messages: list[dict] = []

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    async def fake_update_handoff_state_if_unassigned(
        _db,
        conv,
        *,
        state,
        payload,
        status=None,
        allowed_previous_states=None,
    ):
        assert "dismissed" in allowed_previous_states
        conv.open_agent_handoff_state = state
        conv.open_agent_handoff_payload = payload or {}
        if status:
            conv.status = status
        return conv, True

    async def fake_create(_db, data):
        created_messages.append(data)
        return FakeMessage(id=len(created_messages) + 20, **data)

    async def fake_noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        ConversationRepository,
        "update_handoff_state_if_unassigned",
        fake_update_handoff_state_if_unassigned,
    )
    monkeypatch.setattr(MessageRepository, "create", fake_create)
    monkeypatch.setattr(ConversationRepository, "update_last_message", fake_noop)

    saved = await OpenAgentConversationService._save_handoff_event(
        object(),
        conversation,
        {
            "event_kind": "human_handoff",
            "schema_version": 1,
            "tool_call_id": "new_call",
            "handoff": {"brief": "新话术"},
        },
        handoff_source="bot_tool",
        handoff_event_type="confirm_requested",
        tool_call_id="new_call",
    )

    assert saved is not None
    assert created_messages[0]["metadata_"]["tool_call_id"] == "new_call"


@pytest.mark.asyncio
async def test_confirmed_by_visitor_event_is_idempotent(monkeypatch):
    conversation = FakeConversation()
    existing_message = FakeMessage(
        id=31,
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        sender_type="system",
        content_type="system",
        content="您已确认转接人工客服",
        metadata_={
            "event_type": "open_agent_handoff_event",
            "handoff_event_type": "confirmed_by_visitor",
            "handoff_source": "bot_event",
            "handoff_payload": {"tool_call_id": "call_handoff"},
            "tool_call_id": "call_handoff",
        },
    )

    async def fake_get_existing(*_args, **_kwargs):
        return existing_message

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    async def fail_create(*_args, **_kwargs):
        raise AssertionError("duplicate confirmed_by_visitor event should not be created")

    monkeypatch.setattr(MessageRepository, "get_handoff_event_by_tool_call_id", fake_get_existing)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(MessageRepository, "create", fail_create)

    saved = await ConversationService._save_confirmed_by_visitor_handoff_event(
        object(),
        conversation,
        {"tool_call_id": "call_handoff"},
        "call_handoff",
        "bot_event",
    )

    assert saved["id"] == existing_message.id
    assert saved["metadata"]["handoff_source"] == "bot_event"


@pytest.mark.asyncio
async def test_stream_chat_records_handoff_when_tool_result_omits_tool_name(monkeypatch):
    conversation = FakeConversation()
    created_messages: list[dict] = []

    async def fake_get_conversation(*_args, **_kwargs):
        return conversation

    async def fake_get_credentials(*_args, **_kwargs):
        return "https://openagent.example.com", "sk-test"

    async def fake_get_by_client_message_id(*_args, **_kwargs):
        return None

    async def fake_send_message(*_args, **_kwargs):
        return None

    async def fake_update_open_agent_state(_db, conv, data):
        for key, value in data.items():
            setattr(conv, key, value)
        return conv

    async def fake_update_handoff_state_if_unassigned(
        _db,
        conv,
        *,
        state,
        payload,
        status=None,
        allowed_previous_states=None,
    ):
        conv.open_agent_handoff_state = state
        conv.open_agent_handoff_payload = payload or {}
        if status:
            conv.status = status
        return conv, True

    async def fake_create(_db, data):
        created_messages.append(data)
        return FakeMessage(id=len(created_messages) + 20, **data)

    async def fake_noop(*_args, **_kwargs):
        return None

    async def fake_get_by_id(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", fake_get_conversation)
    monkeypatch.setattr(OpenAgentSettingsService, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(MessageRepository, "get_by_client_message_id", fake_get_by_client_message_id)
    monkeypatch.setattr(ConversationService, "send_message", fake_send_message)
    monkeypatch.setattr(ConversationRepository, "update_open_agent_state", fake_update_open_agent_state)
    monkeypatch.setattr(
        ConversationRepository,
        "update_handoff_state_if_unassigned",
        fake_update_handoff_state_if_unassigned,
    )
    monkeypatch.setattr(MessageRepository, "create", fake_create)
    monkeypatch.setattr(ConversationRepository, "update_last_message", fake_noop)
    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="help", client_message_id="cm_tool_handoff_no_name"),
        open_agent_client=FakeToolResultHandoffWithoutToolNameClient(),
    )
    chunks = [chunk async for chunk in stream]

    assert any(b"open_desk_message_saved" in chunk for chunk in chunks)
    assert len(created_messages) == 2
    assert created_messages[0]["sender_type"] == "system"
    assert created_messages[0]["metadata_"]["handoff_source"] == "bot_tool"
    assert created_messages[0]["metadata_"]["tool_call_id"] == "call_handoff"
    assert created_messages[1]["sender_type"] == "bot"
    tool_blocks = created_messages[1]["metadata_"]["open_agent_tool_blocks"]
    assert tool_blocks[0]["toolCallId"] == "call_handoff"
    assert tool_blocks[0]["usedForHandoff"] is True


@pytest.mark.asyncio
async def test_requires_action_handoff_confirm_mode_saves_pending_without_tool_result(monkeypatch):
    conversation = FakeConversation()
    created_messages: list[dict] = []
    client = FakeRequiredActionHandoffClient()
    patch_required_action_stream_dependencies(monkeypatch, conversation, created_messages)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="help", client_message_id="cm_required_confirm"),
        open_agent_client=client,
    )
    chunks = [chunk async for chunk in stream]

    assert any(b"requires_action" in chunk for chunk in chunks)
    assert client.tool_result_payloads == []
    assert conversation.open_agent_conversation_id == 42
    assert conversation.open_agent_handoff_state == "pending"
    assert conversation.status == ConversationStatus.HANDOFF_PENDING.value
    assert len(created_messages) == 1
    assert created_messages[0]["sender_type"] == "system"
    assert created_messages[0]["metadata_"]["event_type"] == "open_agent_handoff_event"
    assert created_messages[0]["metadata_"]["handoff_event_type"] == "confirm_requested"
    assert created_messages[0]["metadata_"]["tool_call_id"] == "call_handoff"


@pytest.mark.asyncio
async def test_requires_action_handoff_auto_success_submits_success_tool_result(monkeypatch):
    conversation = FakeConversation(
        channel=FakeChannel({
            "open_agent_enabled": True,
            "open_agent_agent_id": 7,
            "open_agent_agent_name": "Support Bot",
            "open_agent_handoff_behavior": "auto",
        }),
    )
    created_messages: list[dict] = []
    client = FakeRequiredActionHandoffClient()
    patch_required_action_stream_dependencies(monkeypatch, conversation, created_messages)

    async def fake_request_handoff(*_args, **_kwargs):
        conversation.status = ConversationStatus.ACTIVE.value
        conversation.agent_id = 33
        return {
            "ok": True,
            "conversation": conversation,
            "message": {
                "id": 101,
                "conversation_public_id": conversation.public_id,
                "sender_type": "system",
                "content_type": "system",
                "content": "已为您转接人工客服",
                "metadata": {"event_type": "open_agent_handoff_success"},
            },
            "messages": [],
            "agent": None,
        }

    monkeypatch.setattr(ConversationService, "request_human_handoff_for_session", fake_request_handoff)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="help", client_message_id="cm_required_auto_ok"),
        open_agent_client=client,
        redis=object(),
    )
    chunks = [chunk async for chunk in stream]

    assert any(b"open_desk_conversation_status" in chunk for chunk in chunks)
    assert client.tool_result_conversation_ids == [42]
    assert client.tool_result_payloads == [{
        "tool_call_id": "call_handoff",
        "status": "handoff_success",
        "message": "已为您转接人工客服",
    }]
    assert created_messages[0]["metadata_"]["handoff_event_type"] == "auto_triggered"
    assert conversation.status == ConversationStatus.ACTIVE.value
    assert conversation.agent_id == 33


@pytest.mark.asyncio
async def test_requires_action_handoff_auto_failure_submits_failed_and_saves_fallback(monkeypatch):
    fallback = "当前没有可用客服，我先继续帮您处理。"
    conversation = FakeConversation(
        channel=FakeChannel({
            "open_agent_enabled": True,
            "open_agent_agent_id": 7,
            "open_agent_agent_name": "Support Bot",
            "open_agent_handoff_behavior": "auto",
        }),
    )
    created_messages: list[dict] = []
    client = FakeRequiredActionHandoffClient([
        f"event: content_delta\ndata: {json.dumps({'content': fallback}, ensure_ascii=False)}\n\n".encode(),
        f"event: done\ndata: {json.dumps({'final_content': fallback, 'finish_reason': 'handoff_failed'}, ensure_ascii=False)}\n\n".encode(),
    ])
    patch_required_action_stream_dependencies(monkeypatch, conversation, created_messages)

    async def fake_request_handoff(*_args, **_kwargs):
        conversation.status = ConversationStatus.BOT.value
        conversation.open_agent_handoff_state = "failed"
        return {
            "ok": False,
            "conversation": conversation,
            "message": {
                "id": 102,
                "conversation_public_id": conversation.public_id,
                "sender_type": "system",
                "content_type": "system",
                "content": "当前人工客服不在线，您可以继续向智能助手咨询",
                "metadata": {"event_type": "open_agent_handoff_failed", "reason": "offline"},
            },
            "messages": [],
            "agent": None,
            "reason": "offline",
        }

    monkeypatch.setattr(ConversationService, "request_human_handoff_for_session", fake_request_handoff)

    stream = stream_chat_for_session_under_test(
        object(),
        "cv_test",
        {"tenant_id": 1, "channel_id": 10, "visitor_external_id": "v_1"},
        OpenAgentChatRequest(message="help", client_message_id="cm_required_auto_fail"),
        open_agent_client=client,
        redis=object(),
    )
    chunks = [chunk async for chunk in stream]

    assert any(b"open_desk_message_saved" in chunk for chunk in chunks)
    assert client.tool_result_payloads == [{
        "tool_call_id": "call_handoff",
        "status": "handoff_failed",
        "message": "当前人工客服不在线，您可以继续向智能助手咨询",
    }]
    assert created_messages[-1]["sender_type"] == "bot"
    assert created_messages[-1]["content"] == fallback
    assert created_messages[-1]["metadata_"]["open_agent_tool_result_status"] == "handoff_failed"
