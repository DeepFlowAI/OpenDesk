import httpx
import pytest

from app.libs.open_agent.base import OpenAgentClientError
from app.libs.open_agent.providers.http import HTTPOpenAgentClient


def test_build_agent_detail_url_respects_api_v1_base_path():
    assert (
        HTTPOpenAgentClient._build_agent_detail_url("https://new.example.com/api/v1", 12)
        == "https://new.example.com/api/v1/agents/12"
    )


def test_build_agent_tool_url_respects_api_v1_base_path():
    assert (
        HTTPOpenAgentClient._build_agent_tool_url("https://new.example.com/api/v1", 12, 34)
        == "https://new.example.com/api/v1/agents/12/tools/34"
    )
    assert (
        HTTPOpenAgentClient._build_agent_tool_url("https://new.example.com", 12, 34)
        == "https://new.example.com/api/v1/agents/12/tools/34"
    )


def test_parse_attachment_handoff_tool_id_from_engine_config():
    assert HTTPOpenAgentClient._parse_attachment_handoff_tool_id({
        "engine_config": {"attachment_handoff_tool_id": "34"},
    }) == 34
    assert HTTPOpenAgentClient._parse_attachment_handoff_tool_id({
        "engine_config": {"attachment_handoff_tool_id": None},
    }) is None


@pytest.mark.asyncio
async def test_get_agent_tool_parses_human_handoff_tool(monkeypatch):
    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **_kwargs):
            request = httpx.Request("GET", url)
            return httpx.Response(
                200,
                json={
                    "id": 34,
                    "agent_id": 12,
                    "name": "Attachment handoff",
                    "tool_type": "human_handoff",
                    "is_enabled": True,
                },
                request=request,
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    tool = await HTTPOpenAgentClient().get_agent_tool(
        "https://new.example.com",
        "sk-test",
        12,
        34,
    )

    assert tool.id == 34
    assert tool.agent_id == 12
    assert tool.tool_type == "human_handoff"
    assert tool.is_enabled is True
    assert (
        HTTPOpenAgentClient._build_agent_detail_url("https://new.example.com", 12)
        == "https://new.example.com/api/v1/agents/12"
    )


def test_build_step_feedback_url_respects_api_v1_base_path():
    assert (
        HTTPOpenAgentClient._build_step_feedback_url("https://new.example.com/api/v1", 7, 42, 88)
        == "https://new.example.com/api/v1/agents/7/conversations/42/steps/88/feedback"
    )


def test_build_robot_qa_urls_respect_api_v1_base_path():
    assert (
        HTTPOpenAgentClient._build_knowledge_bases_url("https://new.example.com/api/v1")
        == "https://new.example.com/api/v1/knowledge-bases"
    )
    assert (
        HTTPOpenAgentClient._build_qa_directories_url("https://new.example.com", 7)
        == "https://new.example.com/api/v1/knowledge-bases/7/qa-directories"
    )
    assert (
        HTTPOpenAgentClient._build_qas_url("https://new.example.com/api/v1", 7)
        == "https://new.example.com/api/v1/knowledge-bases/7/qas"
    )


def test_parse_robot_qa_resources():
    knowledge_base = HTTPOpenAgentClient._parse_knowledge_base(
        {"id": "4", "name": "Support", "description": "Docs", "status": "active"}
    )
    directory = HTTPOpenAgentClient._parse_qa_directory(
        {
            "id": 9,
            "parent_id": None,
            "name": "未分类",
            "sort_order": 2,
            "depth": 1,
            "path": ["未分类"],
        }
    )

    assert knowledge_base is not None
    assert (knowledge_base.id, knowledge_base.name) == (4, "Support")
    assert directory is not None
    assert directory.path == ["未分类"]


@pytest.mark.asyncio
async def test_robot_qa_request_preserves_upstream_error_status(monkeypatch):
    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, url, **_kwargs):
            request = httpx.Request(method, url)
            return httpx.Response(
                403,
                json={"code": "FORBIDDEN", "message": "API key lacks required scope: config"},
                request=request,
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = HTTPOpenAgentClient()

    with pytest.raises(OpenAgentClientError) as exc_info:
        await client.list_qa_directories("https://new.example.com", "sk-test", 7)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "FORBIDDEN"
    assert (
        HTTPOpenAgentClient._build_step_feedback_url("https://new.example.com", 7, 42, 88)
        == "https://new.example.com/api/v1/agents/7/conversations/42/steps/88/feedback"
    )


def test_parse_agent_welcome_message_reads_conversation_settings():
    payload = {
        "engine_config": {
            "conversation_settings": {
                "welcome_message": {
                    "enabled": True,
                    "blocks": [
                        {"type": "markdown", "content": "Hi **there**"},
                        {"type": "embed", "embed_code": "<div>Card</div>", "height": "240"},
                    ],
                }
            }
        }
    }

    assert HTTPOpenAgentClient._parse_agent_welcome_message(payload) == {
        "enabled": True,
        "blocks": [
            {"type": "markdown", "content": "Hi **there**"},
            {"type": "embed", "embed_code": "<div>Card</div>", "height": 240},
        ],
    }


def test_parse_agent_faq_reads_valid_categories():
    payload = {
        "engine_config": {
            "conversation_settings": {
                "faq": {
                    "enabled": True,
                    "title": " FAQ ",
                    "categories": [
                        {
                            "name": " Account ",
                            "questions": [
                                {"text": " How do I reset my password? "},
                                {"text": ""},
                                {"text": "How do I update billing?"},
                            ],
                        },
                        {"name": "Empty", "questions": []},
                        {"name": "", "questions": [{"text": "Ignored"}]},
                    ],
                }
            }
        }
    }

    assert HTTPOpenAgentClient._parse_agent_faq(payload) == {
        "enabled": True,
        "title": "FAQ",
        "categories": [
            {
                "name": "Account",
                "questions": [
                    {"text": "How do I reset my password?"},
                    {"text": "How do I update billing?"},
                ],
            }
        ],
    }


def test_parse_agent_ai_disclaimer_reads_conversation_settings():
    payload = {
        "engine_config": {
            "conversation_settings": {
                "ai_disclaimer": {
                    "enabled": True,
                    "content": " 本内容由AI生成，仅供参考 ",
                }
            }
        }
    }

    assert HTTPOpenAgentClient._parse_agent_ai_disclaimer(payload) == {
        "enabled": True,
        "content": "本内容由AI生成，仅供参考",
    }
