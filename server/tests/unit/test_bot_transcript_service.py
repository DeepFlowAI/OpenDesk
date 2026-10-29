"""Unit tests for robot-stage transcript mapping and workspace authorization."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.libs.voice_speed.base import (
    VoiceSpeedCallTranscript,
    VoiceSpeedCallTranscriptMessage,
    VoiceSpeedClientError,
)
from app.schemas.permission import EffectivePrincipal
from app.services.bot_transcript_service import (
    BotTranscriptService,
    _PreparedBotCall,
    map_bot_messages,
)


def _msg(
    role: str,
    content: str,
    *,
    interrupted: bool = False,
    heard_content: str | None = None,
) -> VoiceSpeedCallTranscriptMessage:
    return VoiceSpeedCallTranscriptMessage(
        role=role,
        content=content,
        interrupted=interrupted,
        heard_content=heard_content,
    )


def test_map_keeps_user_and_full_bot_reply():
    visible = map_bot_messages(
        [
            _msg("assistant", "您好"),
            _msg("user", "转人工"),
            _msg("assistant", "好的"),
        ]
    )
    assert [(m.role, m.text, m.interrupted) for m in visible] == [
        ("bot", "您好", False),
        ("user", "转人工", False),
        ("bot", "好的", False),
    ]


def test_map_interrupted_with_heard_content_keeps_prefix_only():
    visible = map_bot_messages(
        [_msg("assistant", "您好，我是客服助手", interrupted=True, heard_content="您好，")]
    )
    assert visible == [
        type(visible[0])(role="bot", text="您好，", interrupted=True),
    ]


def test_map_interrupted_before_playback_hides_message():
    visible = map_bot_messages(
        [
            _msg("assistant", "这条客户没听到", interrupted=True, heard_content=""),
            _msg("user", "转人工"),
        ]
    )
    assert [(m.role, m.text) for m in visible] == [("user", "转人工")]


def test_map_interrupted_without_position_keeps_full_text():
    visible = map_bot_messages(
        [_msg("assistant", "完整回复", interrupted=True, heard_content=None)]
    )
    assert visible[0].text == "完整回复"
    assert visible[0].interrupted is True


def _principal() -> EffectivePrincipal:
    return EffectivePrincipal(user_id=7, tenant_id=1, permissions=["call.workspace.use"])


class _FakeSessionCtx:
    def __init__(self, prepared, last_serving=None):
        self.prepared = prepared
        self.last_serving = last_serving

    async def __aenter__(self):
        return object()

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_workspace_hides_when_call_never_reached_bot(monkeypatch):
    monkeypatch.setattr(
        BotTranscriptService,
        "_prepare",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.bot_transcript_service.AsyncSessionLocal",
        lambda: _FakeSessionCtx(None),
    )
    result = await BotTranscriptService.get_for_workspace_managed(_principal(), "call-1")
    assert result.available is False


@pytest.mark.asyncio
async def test_workspace_allows_last_serving_agent_without_redis(monkeypatch):
    prepared = _PreparedBotCall(
        call_id="call-1",
        agent_id="3",
        agent_name_snapshot="助手",
        credentials=None,
        last_serving_agent_id=7,
    )
    monkeypatch.setattr(BotTranscriptService, "_prepare", AsyncMock(return_value=prepared))
    monkeypatch.setattr(
        "app.services.bot_transcript_service.AsyncSessionLocal",
        lambda: _FakeSessionCtx(prepared),
    )
    monkeypatch.setattr(BotTranscriptService, "_has_live_assignment", AsyncMock(return_value=False))
    result = await BotTranscriptService.get_for_workspace_managed(_principal(), "call-1")
    assert result.available is True
    assert result.status == "error"


@pytest.mark.asyncio
async def test_workspace_hides_when_offer_withdrawn(monkeypatch):
    prepared = _PreparedBotCall(
        call_id="call-1",
        agent_id="3",
        agent_name_snapshot="助手",
        credentials=("https://vs", "key"),
    )

    async def fake_prepare(_db, *, tenant_id, call_id):
        return prepared

    monkeypatch.setattr(BotTranscriptService, "_prepare", fake_prepare)
    monkeypatch.setattr(
        "app.services.bot_transcript_service.AsyncSessionLocal",
        lambda: _FakeSessionCtx(prepared),
    )
    monkeypatch.setattr(BotTranscriptService, "_has_live_assignment", AsyncMock(return_value=False))
    result = await BotTranscriptService.get_for_workspace_managed(_principal(), "call-1")
    assert result.available is False


@pytest.mark.asyncio
async def test_workspace_fetches_when_agent_is_ringing(monkeypatch):
    prepared = _PreparedBotCall(
        call_id="call-1",
        agent_id="3",
        agent_name_snapshot="助手",
        credentials=("https://vs", "key"),
    )

    async def fake_prepare(_db, *, tenant_id, call_id):
        return prepared

    transcript = VoiceSpeedCallTranscript(
        call_id="call-1",
        agent_id="3",
        agent_name="移动客服",
        handoff_at="2026-10-22T03:01:10Z",
        messages=[_msg("user", "转人工"), _msg("assistant", "好的")],
    )
    client = SimpleNamespace(get_call_transcript=AsyncMock(return_value=transcript))

    monkeypatch.setattr(BotTranscriptService, "_prepare", fake_prepare)
    monkeypatch.setattr(
        "app.services.bot_transcript_service.AsyncSessionLocal",
        lambda: _FakeSessionCtx(prepared),
    )
    monkeypatch.setattr(BotTranscriptService, "_has_live_assignment", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "app.services.bot_transcript_service.create_voice_speed_client",
        lambda: client,
    )

    result = await BotTranscriptService.get_for_workspace_managed(_principal(), "call-1")
    assert result.available is True
    assert result.status == "ok"
    assert result.agent_name == "移动客服"
    assert result.entered_human is True
    assert result.handoff_at is not None
    assert [m.text for m in result.messages] == ["转人工", "好的"]
    client.get_call_transcript.assert_awaited_once()


@pytest.mark.asyncio
async def test_workspace_maps_voicespeed_404_to_empty(monkeypatch):
    prepared = _PreparedBotCall(
        call_id="call-1",
        agent_id="3",
        agent_name_snapshot="助手",
        credentials=("https://vs", "key"),
    )
    client = SimpleNamespace(
        get_call_transcript=AsyncMock(
            side_effect=VoiceSpeedClientError("missing", status_code=404)
        )
    )
    monkeypatch.setattr(BotTranscriptService, "_prepare", AsyncMock(return_value=prepared))
    monkeypatch.setattr(
        "app.services.bot_transcript_service.AsyncSessionLocal",
        lambda: _FakeSessionCtx(prepared),
    )
    monkeypatch.setattr(BotTranscriptService, "_has_live_assignment", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "app.services.bot_transcript_service.create_voice_speed_client",
        lambda: client,
    )
    result = await BotTranscriptService.get_for_workspace_managed(_principal(), "call-1")
    assert result.available is True
    assert result.status == "empty"


@pytest.mark.asyncio
async def test_workspace_maps_timeout_to_error(monkeypatch):
    prepared = _PreparedBotCall(
        call_id="call-1",
        agent_id="3",
        agent_name_snapshot="助手",
        credentials=("https://vs", "key"),
    )
    client = SimpleNamespace(
        get_call_transcript=AsyncMock(side_effect=VoiceSpeedClientError("timeout"))
    )
    monkeypatch.setattr(BotTranscriptService, "_prepare", AsyncMock(return_value=prepared))
    monkeypatch.setattr(
        "app.services.bot_transcript_service.AsyncSessionLocal",
        lambda: _FakeSessionCtx(prepared),
    )
    monkeypatch.setattr(BotTranscriptService, "_has_live_assignment", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "app.services.bot_transcript_service.create_voice_speed_client",
        lambda: client,
    )
    result = await BotTranscriptService.get_for_workspace_managed(_principal(), "call-1")
    assert result.available is True
    assert result.status == "error"


@pytest.mark.asyncio
async def test_history_bot_only_has_no_divider(monkeypatch):
    prepared = _PreparedBotCall(
        call_id="call-1",
        agent_id="3",
        agent_name_snapshot="助手",
        credentials=None,
    )
    row = SimpleNamespace(
        actual_reception_type="bot",
        first_agent_connected_at=None,
        bot_handoff_succeeded_at=None,
    )
    monkeypatch.setattr(
        "app.services.bot_transcript_service.CallRecordService.get_scoped_row_by_public_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(BotTranscriptService, "_prepare_row", AsyncMock(return_value=prepared))
    monkeypatch.setattr(
        "app.services.bot_transcript_service.AsyncSessionLocal",
        lambda: _FakeSessionCtx(prepared),
    )
    result = await BotTranscriptService.get_for_record_managed(_principal(), uuid4())
    assert result.available is True
    assert result.status == "error"
    assert result.entered_human is False
