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
