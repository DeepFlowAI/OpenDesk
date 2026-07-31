"""
Tests for the live call transcript relay.

The orchestrator mirrors kernel ASR/TTS text events (`call.speech_partial`,
`call.speech_end`, `call.user_text`, `call.assistant_text`) to the bridged
agent's browser as `cc.transcript` — purely for the real-time transcript UI.
Nothing is persisted, and text only flows once the call is bridged to an agent.
"""
import pytest

from app.libs.telephony.base import CallEvent
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center import orchestrator as orch_module
from app.services.call_center.orchestrator import CallCenterOrchestrator


class _FakeTransport:
    def __init__(self) -> None:
        self.emits: list[tuple[str, dict, str | None]] = []

    async def emit(self, event, data, *, room=None, to=None, namespace=None):
        self.emits.append((event, data, room))


class _FakeWorkflow:
    def __init__(self, agent: dict | None) -> None:
        self._agent = agent

    def bridged_agent_info(self) -> dict | None:
        return self._agent


def _orch(monkeypatch, transport):
    monkeypatch.setattr(orch_module, "get_realtime_transport", lambda: transport)
    return CallCenterOrchestrator(telephony=MockTelephonyClient())


def _stub_transcript_persist(monkeypatch):
    """Final lines open AsyncSessionLocal to persist — incidental to relay tests."""

    class _FakeService:
        @staticmethod
        async def append(_db, *, tenant_id, call_id, role, text, seq=None):
            return None

    class _Session:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(orch_module, "CallTranscriptService", _FakeService)


@pytest.mark.asyncio
async def test_relays_user_and_agent_text_to_bridged_agent(monkeypatch):
    transport = _FakeTransport()
    orch = _orch(monkeypatch, transport)
    orch._workflows["call-1"] = _FakeWorkflow({"tenant_id": 7, "employee_id": 42})
    _stub_transcript_persist(monkeypatch)

    await orch._on_transcript_event(
        CallEvent("call.user_text", {"call_id": "call-1", "text": "你好"})
    )
    await orch._on_transcript_event(
        CallEvent("call.assistant_text", {"call_id": "call-1", "text": "您好，请问"})
    )

    assert transport.emits == [
        (
            "cc.transcript",
            {"call_id": "call-1", "role": "user", "text": "你好", "final": True, "seq": None},
            "agent:7:42",
        ),
        (
            "cc.transcript",
            {"call_id": "call-1", "role": "agent", "text": "您好，请问", "final": True, "seq": None},
            "agent:7:42",
        ),
    ]


@pytest.mark.asyncio
async def test_speech_partial_is_not_final_speech_end_is(monkeypatch):
    transport = _FakeTransport()
    orch = _orch(monkeypatch, transport)
    orch._workflows["call-1"] = _FakeWorkflow({"tenant_id": 1, "employee_id": 2})

    await orch._on_transcript_event(
        CallEvent("call.speech_partial", {"call_id": "call-1", "text": "我想", "seq": 3})
    )
    await orch._on_transcript_event(
        CallEvent("call.speech_end", {"call_id": "call-1", "text": "我想退款"})
    )

    partial, final = transport.emits
    assert partial[1]["final"] is False
    assert partial[1]["role"] == "user"
    assert partial[1]["seq"] == 3
    assert final[1]["final"] is True
    assert final[1]["text"] == "我想退款"


@pytest.mark.asyncio
async def test_bridge_transcript_uses_explicit_speaker_and_final(monkeypatch):
    transport = _FakeTransport()
    orch = _orch(monkeypatch, transport)
    orch._workflows["call-1"] = _FakeWorkflow({"tenant_id": 3, "employee_id": 9})
    _stub_transcript_persist(monkeypatch)

    # Agent leg, streaming partial.
    await orch._on_transcript_event(
        CallEvent(
            "call.bridge_transcript",
            {"call_id": "call-1", "speaker": "agent", "text": "您好", "final": False, "seq": 1},
        )
    )
    # User leg, final.
    await orch._on_transcript_event(
        CallEvent(
            "call.bridge_transcript",
            {"call_id": "call-1", "speaker": "user", "text": "我要退款", "final": True},
        )
    )

    assert transport.emits == [
        (
            "cc.transcript",
            {"call_id": "call-1", "role": "agent", "text": "您好", "final": False, "seq": 1},
            "agent:3:9",
        ),
        (
            "cc.transcript",
            {"call_id": "call-1", "role": "user", "text": "我要退款", "final": True, "seq": None},
            "agent:3:9",
        ),
    ]


@pytest.mark.asyncio
async def test_final_is_persisted_partial_is_not(monkeypatch):
    transport = _FakeTransport()
    orch = _orch(monkeypatch, transport)
    orch._workflows["call-1"] = _FakeWorkflow({"tenant_id": 5, "employee_id": 8})

    appended: list[dict] = []

    class _FakeService:
        @staticmethod
        async def append(_db, *, tenant_id, call_id, role, text, seq=None):
            appended.append(
                {"tenant_id": tenant_id, "call_id": call_id, "role": role, "text": text, "seq": seq}
            )

    class _Session:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(orch_module, "CallTranscriptService", _FakeService)

    # Partial → relayed but NOT persisted.
    await orch._on_transcript_event(
        CallEvent(
            "call.bridge_transcript",
            {"call_id": "call-1", "speaker": "user", "text": "我要", "final": False, "seq": 1},
        )
    )
    # Final → persisted.
    await orch._on_transcript_event(
        CallEvent(
            "call.bridge_transcript",
            {"call_id": "call-1", "speaker": "agent", "text": "好的", "final": True, "seq": 2},
        )
    )

    assert appended == [
        {"tenant_id": 5, "call_id": "call-1", "role": "agent", "text": "好的", "seq": 2}
    ]


@pytest.mark.asyncio
async def test_no_relay_before_agent_bridged(monkeypatch):
    transport = _FakeTransport()
    orch = _orch(monkeypatch, transport)
    # Workflow exists (AI phase) but no agent has joined yet.
    orch._workflows["call-1"] = _FakeWorkflow(None)

    await orch._on_transcript_event(
        CallEvent("call.user_text", {"call_id": "call-1", "text": "喂"})
    )

    assert transport.emits == []


@pytest.mark.asyncio
async def test_no_relay_for_unknown_call_or_empty_text(monkeypatch):
    transport = _FakeTransport()
    orch = _orch(monkeypatch, transport)
    orch._workflows["call-1"] = _FakeWorkflow({"tenant_id": 1, "employee_id": 2})

    # Unknown call id → no workflow.
    await orch._on_transcript_event(
        CallEvent("call.user_text", {"call_id": "ghost", "text": "hi"})
    )
    # Known call but blank text.
    await orch._on_transcript_event(
        CallEvent("call.user_text", {"call_id": "call-1", "text": "   "})
    )

    assert transport.emits == []
