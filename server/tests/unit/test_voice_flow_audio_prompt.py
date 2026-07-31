"""Play/collect/hangup audio prompts must call_play(audio_url), not TTS placeholders."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center.nodes import (
    HangupExecutor,
    PlayExecutor,
    _utter_prompt,
)
from app.services.call_center.workflow import VoiceFlowWorkflow


class _FakeSessionCtx:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *args):
        return False


def _graph_audio_play(asset_id: int = 7) -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "s", "type": "start", "data": {}, "position": {"x": 0, "y": 0}},
            {
                "id": "p",
                "type": "play",
                "position": {"x": 100, "y": 0},
                "data": {"prompt": {"kind": "audio", "asset_id": asset_id}},
            },
            {
                "id": "h",
                "type": "hangup",
                "position": {"x": 200, "y": 0},
                "data": {"pre_play": None},
            },
        ],
        "edges": [
            {"id": "e1", "source": "s", "target": "p", "source_handle": "next"},
            {"id": "e2", "source": "p", "target": "h", "source_handle": "next"},
        ],
        "variables": [],
    }


def _patch_audio_resolve(monkeypatch, *, url: str | None, mime: str = "audio/mpeg"):
    from app.db import session as session_mod
    from app.repositories.audio_asset_repository import AudioAssetRepository
    from app.libs import storage as storage_mod

    asset = None
    if url is not None:
        asset = SimpleNamespace(
            id=7,
            mime_type=mime,
            storage_key="voice-flow/audio/1/demo.mp3",
        )

    monkeypatch.setattr(
        session_mod, "AsyncSessionLocal", lambda: _FakeSessionCtx(MagicMock())
    )
    monkeypatch.setattr(
        AudioAssetRepository,
        "get_by_id",
        AsyncMock(return_value=asset),
    )

    storage = MagicMock()
    storage.get_temporary_url = AsyncMock(return_value=url)

    monkeypatch.setattr(storage_mod, "create_storage_client", lambda: storage)
    return storage


@pytest.mark.asyncio
async def test_utter_prompt_audio_uses_call_play(monkeypatch):
    tel = MockTelephonyClient()
    await tel.connect()
    _patch_audio_resolve(
        monkeypatch, url="https://example.com/tmp/demo.mp3"
    )

    from app.services.call_center.nodes import ExecutionContext

    ctx = ExecutionContext(call_id="c1", tenant_id=1, telephony=tel)
    started = await _utter_prompt(
        ctx, {"kind": "audio", "asset_id": 7}
    )
    assert started is True
    assert tel.recorded[0][0] == "call.play"
    assert tel.recorded[0][1]["audio_url"] == "https://example.com/tmp/demo.mp3"
    assert not any(m == "call.say" for m, _ in tel.recorded)


@pytest.mark.asyncio
async def test_utter_prompt_tts_still_uses_call_say():
    tel = MockTelephonyClient()
    await tel.connect()
    from app.services.call_center.nodes import ExecutionContext

    ctx = ExecutionContext(call_id="c1", tenant_id=1, telephony=tel)
    started = await _utter_prompt(
        ctx, {"kind": "tts", "text": "欢迎致电"}
    )
    assert started is True
    assert tel.recorded[0][0] == "call.say"
    assert tel.recorded[0][1]["text"] == "欢迎致电"


@pytest.mark.asyncio
async def test_play_node_audio_via_workflow(monkeypatch):
    tel = MockTelephonyClient()
    await tel.connect()
    _patch_audio_resolve(
        monkeypatch, url="https://cdn.example/a.mp3"
    )

    wf = VoiceFlowWorkflow(
        call_id="call-1",
        tenant_id=1,
        graph=_graph_audio_play(),
        telephony=tel,
    )
    await wf.start()
    assert any(m == "call.play" for m, _ in tel.recorded)
    assert not any(
        m == "call.say" and "[audio #" in (p.get("text") or "")
        for m, p in tel.recorded
    )
    await wf.handle_event("call.play_end", {"call_id": "call-1"})
    assert wf.done.is_set() is True
    assert any(m == "call.hangup" for m, _ in tel.recorded)


@pytest.mark.asyncio
async def test_play_node_skips_missing_audio(monkeypatch):
    tel = MockTelephonyClient()
    await tel.connect()
    _patch_audio_resolve(monkeypatch, url=None)

    # get_by_id returns None when url is None in helper — also cover missing asset
    from app.repositories.audio_asset_repository import AudioAssetRepository

    monkeypatch.setattr(
        AudioAssetRepository, "get_by_id", AsyncMock(return_value=None)
    )

    exe = PlayExecutor()
    from app.services.call_center.nodes import ExecutionContext

    ctx = ExecutionContext(
        call_id="c1",
        tenant_id=1,
        telephony=tel,
        edges_by_source={"p": {"next": "h"}},
    )
    step = await exe.execute(
        ctx,
        {
            "id": "p",
            "type": "play",
            "data": {"prompt": {"kind": "audio", "asset_id": 99}},
        },
    )
    # Missing asset → skip wait, jump to next
    assert step.node_id == "h"
    assert tel.recorded == []


@pytest.mark.asyncio
async def test_hangup_pre_play_audio(monkeypatch):
    tel = MockTelephonyClient()
    await tel.connect()
    _patch_audio_resolve(
        monkeypatch, url="https://cdn.example/bye.wav", mime="audio/wav"
    )

    exe = HangupExecutor()
    from app.services.call_center.nodes import ExecutionContext, WaitForEvent

    ctx = ExecutionContext(call_id="c1", tenant_id=1, telephony=tel)
    step = await exe.execute(
        ctx,
        {
            "id": "h",
            "type": "hangup",
            "data": {"pre_play": {"kind": "audio", "asset_id": 7}},
        },
    )
    assert isinstance(step, WaitForEvent)
    assert tel.recorded[0][0] == "call.play"
    assert tel.recorded[0][1]["audio_url"] == "https://cdn.example/bye.wav"
