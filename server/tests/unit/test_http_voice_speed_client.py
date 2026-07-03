import httpx

from app.libs.voice_speed.providers.http import HTTPVoiceSpeedClient


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
