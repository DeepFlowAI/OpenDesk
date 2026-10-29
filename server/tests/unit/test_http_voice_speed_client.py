import json

import httpx
import pytest

from app.libs.voice_speed.base import BaseVoiceSpeedClient, VoiceSpeedClientError
from app.libs.voice_speed.providers.http import HTTPVoiceSpeedClient


def test_build_turn_url_targets_sse_stream_endpoint():
    # flowkit's converse reader parses SSE `data:` lines, so it must hit the
    # streaming variant — the plain /turn returns JSON and yields a silent reply.
    for base in (
        "https://voicespeed.example.com",
        "https://voicespeed.example.com/api/v1",
        "https://voicespeed.example.com/api/v1/openapi",
    ):
        assert (
            BaseVoiceSpeedClient.build_turn_url(base, "1")
            == "https://voicespeed.example.com/api/v1/openapi/agents/1/turn/stream"
        )


def test_build_agents_url_from_root_base_url():
    assert (
        HTTPVoiceSpeedClient._build_agents_url("https://voicespeed.example.com")
        == "https://voicespeed.example.com/api/v1/openapi/agents"
    )


def test_build_agents_url_respects_api_v1_base_path():
    assert (
        HTTPVoiceSpeedClient._build_agents_url("https://voicespeed.example.com/api/v1")
        == "https://voicespeed.example.com/api/v1/openapi/agents"
    )


def test_build_agents_url_respects_openapi_base_path():
    assert (
        HTTPVoiceSpeedClient._build_agents_url("https://voicespeed.example.com/api/v1/openapi")
        == "https://voicespeed.example.com/api/v1/openapi/agents"
    )


def test_map_error_message_for_invalid_api_key():
    assert HTTPVoiceSpeedClient._map_error_message(401, None) == "VoiceSpeed API 密钥无效或已失效"


def test_map_error_message_for_missing_config_scope():
    assert (
        HTTPVoiceSpeedClient._map_error_message(403, "Forbidden")
        == "VoiceSpeed API 密钥缺少配置管理权限，请在 VoiceSpeed 中为该密钥勾选 config 权限范围"
    )


def test_map_error_message_for_tenant_unavailable():
    assert (
        HTTPVoiceSpeedClient._map_error_message(400, "tenant disabled")
        == "VoiceSpeed 租户不可用，请检查 VoiceSpeed 租户状态"
    )


def test_parse_agents_keeps_only_safe_fields():
    response = httpx.Response(
        200,
        json={
            "items": [
                {
                    "id": 7,
                    "name": "Sales Bot",
                    "description": "handles sales",
                    "status": "enabled",
                    # sensitive fields that must never surface
                    "engine_config": {"x": 1},
                    "voice_spk_id": "spk_1",
                    "text_llm": "gpt",
                },
            ]
        },
    )
    agents = HTTPVoiceSpeedClient._parse_agents(response)
    assert len(agents) == 1
    agent = agents[0]
    assert agent.id == "7"  # coerced to string for forward compatibility
    assert agent.name == "Sales Bot"
    assert agent.description == "handles sales"
    assert agent.status == "enabled"
    # only the 4 contract fields exist on the dataclass
    assert set(vars(agent).keys()) == {"id", "name", "description", "status"}


def test_parse_agents_skips_items_missing_id_or_name():
    response = httpx.Response(
        200,
        json={"items": [{"id": 1}, {"name": "no id"}, {"id": 2, "name": "ok", "status": "enabled"}]},
    )
    agents = HTTPVoiceSpeedClient._parse_agents(response)
    assert [a.id for a in agents] == ["2"]


def test_parse_agents_handles_non_object_payload():
    response = httpx.Response(200, json={})
    assert HTTPVoiceSpeedClient._parse_agents(response) == []


def test_build_realtime_sessions_url_from_root_base_url():
    assert (
        HTTPVoiceSpeedClient._build_realtime_sessions_url("https://vs.example.com", "ag_1")
        == "https://vs.example.com/api/v1/openapi/agents/ag_1/realtime-sessions"
    )


def test_build_realtime_sessions_url_respects_openapi_base_path():
    assert (
        HTTPVoiceSpeedClient._build_realtime_sessions_url(
            "https://vs.example.com/api/v1/openapi", "ag_2"
        )
        == "https://vs.example.com/api/v1/openapi/agents/ag_2/realtime-sessions"
    )


def test_parse_realtime_session_extracts_contract_fields():
    response = httpx.Response(
        200,
        json={
            "session_id": "sess_x",
            "ws_url": "wss://vs.example.com/rt?x=1",
            "token": "jwt-token",
            "expires_at": "2026-06-29T00:00:00Z",
            "audio_in": {"codec": "pcm16", "sample_rate": 16000, "channels": 1},
            "audio_out": {"codec": "pcm16", "sample_rate": 24000, "channels": 1},
        },
    )
    session = HTTPVoiceSpeedClient._parse_realtime_session(response)
    assert session.session_id == "sess_x"
    assert session.ws_url == "wss://vs.example.com/rt?x=1"
    assert session.token == "jwt-token"
    assert session.audio_in["sample_rate"] == 16000
    assert session.audio_out["sample_rate"] == 24000


def test_parse_realtime_session_rejects_missing_token():
    import pytest

    from app.libs.voice_speed.base import VoiceSpeedClientError

    response = httpx.Response(200, json={"ws_url": "wss://x"})
    with pytest.raises(VoiceSpeedClientError):
        HTTPVoiceSpeedClient._parse_realtime_session(response)


def test_build_call_variables_url_respects_base_paths():
    for base in (
        "https://voicespeed.example.com",
        "https://voicespeed.example.com/api/v1",
        "https://voicespeed.example.com/api/v1/openapi",
    ):
        assert (
            HTTPVoiceSpeedClient._build_call_variables_url(base, "7", "call-1")
            == "https://voicespeed.example.com/api/v1/openapi/agents/7/calls/call-1/variables"
        )


def _patch_async_client(monkeypatch, handler):
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_preset_call_variables_puts_variables(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"call_id": "call-1", "expires_at": "2026-10-19T00:00:00Z"})

    _patch_async_client(monkeypatch, handler)
    await HTTPVoiceSpeedClient().preset_call_variables(
        "https://vs.example.com", "key", "7", "call-1", {"customer_name": "张三"}
    )
    assert seen == {
        "method": "PUT",
        "url": "https://vs.example.com/api/v1/openapi/agents/7/calls/call-1/variables",
        "auth": "Bearer key",
        "body": {"variables": {"customer_name": "张三"}},
    }


@pytest.mark.asyncio
async def test_preset_call_variables_raises_on_rejection(monkeypatch):
    _patch_async_client(
        monkeypatch,
        lambda _request: httpx.Response(409, json={"message": "Call already started"}),
    )
    with pytest.raises(VoiceSpeedClientError) as exc_info:
        await HTTPVoiceSpeedClient().preset_call_variables(
            "https://vs.example.com", "key", "7", "call-1", {"a": "b"}
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_get_call_opening_posts_session_and_fallback(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"greeting": "", "opening": "model", "voice_spk_id": "general"})

    _patch_async_client(monkeypatch, handler)
    opening = await HTTPVoiceSpeedClient().get_call_opening(
        "https://vs.example.com", "key", "3", session_id="call-1", fallback_greeting="您好"
    )

    assert opening == {"greeting": "", "opening": "model", "voice_spk_id": "general"}
    assert seen["url"] == "https://vs.example.com/api/v1/openapi/agents/3/call-opening"
    assert seen["auth"] == "Bearer key"
    assert seen["body"] == {"session_id": "call-1", "fallback_greeting": "您好"}

    await HTTPVoiceSpeedClient().get_call_opening(
        "https://vs.example.com", "key", "3", session_id="call-1", fallback_greeting="您好",
        user_identifier="13800000000",
    )
    assert seen["body"]["user_identifier"] == "13800000000"


@pytest.mark.asyncio
async def test_get_call_opening_falls_back_when_endpoint_missing(monkeypatch):
    _patch_async_client(monkeypatch, lambda _req: httpx.Response(404, json={"detail": "Not Found"}))
    opening = await HTTPVoiceSpeedClient().get_call_opening(
        "https://vs.example.com", "key", "3", session_id="call-1", fallback_greeting="您好"
    )
    assert opening == {"greeting": "您好", "opening": ""}


@pytest.mark.asyncio
async def test_get_call_transcript_parses_handoff_and_interrupt(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "call_id": "call-1",
                "agent": {"id": 3, "name": "移动客服"},
                "handoff": {"handoff_at": "2026-10-22T03:01:10Z"},
                "messages": [
                    {
                        "role": "assistant",
                        "content": "您好，我是移动客服",
                        "interrupted": True,
                        "heard_content": "您好，",
                    },
                    {"role": "user", "content": "转人工", "interrupted": False},
                ],
            },
        )

    _patch_async_client(monkeypatch, handler)
    transcript = await HTTPVoiceSpeedClient().get_call_transcript(
        "https://vs.example.com", "key", "3", "call-1"
    )
    assert seen["url"] == "https://vs.example.com/api/v1/openapi/agents/3/calls/call-1/transcript"
    assert seen["auth"] == "Bearer key"
    assert transcript.agent_name == "移动客服"
    assert transcript.handoff_at == "2026-10-22T03:01:10Z"
    assert transcript.messages[0].heard_content == "您好，"
    assert transcript.messages[1].role == "user"


@pytest.mark.asyncio
async def test_get_call_transcript_raises_on_404(monkeypatch):
    _patch_async_client(monkeypatch, lambda _req: httpx.Response(404, json={"detail": "not found"}))
    with pytest.raises(VoiceSpeedClientError) as exc_info:
        await HTTPVoiceSpeedClient().get_call_transcript(
            "https://vs.example.com", "key", "3", "missing"
        )
    assert exc_info.value.status_code == 404
