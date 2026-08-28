"""
Unit tests for the VoiceSpeed external-agent node executor (v2 flowkit-中枢架构).

These cover the runtime orchestration (P5): the happy handoff path, the
failure/normal-end terminations, handoff idempotency, and — most importantly —
that NO database session is held while the kernel runs the conversation
(CLAUDE.md rule #8). In v2 the kernel owns ASR/TTS/barge-in and calls the
agent's turn endpoint; OpenDesk only kicks it off and routes the events.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center.nodes import (
    ExecutionContext,
    Goto,
    VoiceSpeedExecutor,
    WaitForEvent,
    build_voicespeed_direct_graph,
)
from app.services.call_center.workflow import VoiceFlowWorkflow
from app.services.open_agent_settings_service import OpenAgentSettingsService


class _FakeVSClient:
    """Stands in for the VoiceSpeed client; only the turn-URL builder is used."""

    TURN_URL = "http://vs/api/v1/openapi/agents/ag_1/turn"

    def __init__(self):
        self.calls: list[dict] = []

    def build_turn_url(self, base_url, agent_id):
        self.calls.append({"base_url": base_url, "agent_id": agent_id})
        return self.TURN_URL


class _FakeSessionCtx:
    """Stand-in for `async with AsyncSessionLocal() as db`."""

    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_exc):
        return False


def _graph(handoff_target: str = "h") -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "s", "type": "start", "data": {}, "position": {"x": 0, "y": 0}},
            {
                "id": "vs", "type": "voicespeed", "position": {"x": 1, "y": 0},
                "data": {
                    "agent_id": "ag_1",
                    "agent_name": "Bot",
                    "unavailable_prompt_text": "UNAVAILABLE",
                    "connect_failed_prompt_text": "CONNECT_FAILED",
                },
            },
            {"id": "h", "type": "hangup", "position": {"x": 2, "y": 0}, "data": {"pre_play": None}},
        ],
        "edges": [
            {"id": "e1", "source": "s", "target": "vs", "source_handle": "next"},
            {"id": "e2", "source": "vs", "target": handoff_target, "source_handle": "handoff"},
        ],
        "variables": [],
    }


def _patch_runtime(monkeypatch, *, client, credentials=("http://vs", "key")):
    monkeypatch.setattr("app.db.session.AsyncSessionLocal", lambda: _FakeSessionCtx())

    async def _fake_creds(_db, _tenant_id):
        return credentials

    monkeypatch.setattr(
        OpenAgentSettingsService, "get_voice_speed_credentials", _fake_creds,
    )
    monkeypatch.setattr(
        "app.libs.voice_speed.create_voice_speed_client", lambda: client,
    )


async def _start_bridged_workflow(monkeypatch, *, handoff_target="h"):
    client = _FakeVSClient()
    _patch_runtime(monkeypatch, client=client)
    tel = MockTelephonyClient()
    await tel.connect()
    wf = VoiceFlowWorkflow(
        call_id="call-1",
        tenant_id=1,
        graph=_graph(handoff_target),
        telephony=tel,
        initial_variables={"sys._traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01",
                           "sys._trace_id": "a" * 32},
    )
    await wf.start()
    return wf, tel, client


def _methods(tel: MockTelephonyClient) -> list[str]:
    return [m for m, _ in tel.recorded]


def _says(tel: MockTelephonyClient) -> list[str]:
    return [p["text"] for m, p in tel.recorded if m == "call.say"]


class TestVoiceSpeedExecutor:
    @pytest.mark.asyncio
    async def test_happy_path_handoff_goes_to_outlet(self, monkeypatch):
        wf, tel, client = await _start_bridged_workflow(monkeypatch)

        # After start: conversation requested in the kernel, still waiting.
        assert wf.done.is_set() is False
        assert "call.converse_external_agent" in _methods(tel)
        conv = next(p for m, p in tel.recorded if m == "call.converse_external_agent")
        assert conv["provider"] == "voicespeed"
        assert conv["turn_url"] == _FakeVSClient.TURN_URL
        assert conv["token"] == "key"
        # A fixed greeting is spoken on entry.
        assert conv["greeting"]
        # traceparent propagated downstream to the kernel RPC (and on to each turn).
        assert conv["traceparent"].startswith("00-")
        assert client.calls[0]["agent_id"] == "ag_1"

        # connected → keep waiting (not done).
        await wf.handle_event("call.external_agent.connected", {"call_id": "call-1"})
        assert wf.done.is_set() is False

        # handoff → routed out the "handoff" outlet (hangup node) → done.
        await wf.handle_event(
            "call.external_agent.handoff",
            {"call_id": "call-1", "payload": {"suggested_target": "complaint"}},
        )
        assert wf.done.is_set() is True
        assert wf.ctx.variables["sys._handoff_handled"] is True
        # Routed via the graph (plain hangup, reason=None) — not a fail prompt.
        assert "CONNECT_FAILED" not in _says(tel)

    @pytest.mark.asyncio
    async def test_failed_plays_connect_failed_prompt(self, monkeypatch):
        wf, tel, _client = await _start_bridged_workflow(monkeypatch)

        await wf.handle_event(
            "call.external_agent.failed",
            {"call_id": "call-1", "code": "ws_error", "message": "boom"},
        )
        assert wf.done.is_set() is True
        assert "CONNECT_FAILED" in _says(tel)
        hangup = next(p for m, p in tel.recorded if m == "call.hangup")
        assert hangup["reason"] == "voicespeed_connect_failed"

    @pytest.mark.asyncio
    async def test_ended_without_handoff_ends_call(self, monkeypatch):
        wf, tel, _client = await _start_bridged_workflow(monkeypatch)

        await wf.handle_event(
            "call.external_agent.ended", {"call_id": "call-1", "reason": "completed"},
        )
        assert wf.done.is_set() is True
        # Normal end: no fail/unavailable prompt, but the call is hung up.
        assert _says(tel) == []
        hangup = next(p for m, p in tel.recorded if m == "call.hangup")
        assert hangup["reason"] == "voicespeed_ended"

    @pytest.mark.asyncio
    async def test_unavailable_when_no_credentials(self, monkeypatch):
        client = _FakeVSClient()
        _patch_runtime(monkeypatch, client=client, credentials=None)
        tel = MockTelephonyClient()
        await tel.connect()
        wf = VoiceFlowWorkflow(
            call_id="call-x", tenant_id=1, graph=_graph(), telephony=tel,
        )
        await wf.start()
        assert wf.done.is_set() is True
        assert "UNAVAILABLE" in _says(tel)
        # Never built a turn URL or asked the kernel to converse.
        assert client.calls == []
        assert "call.converse_external_agent" not in _methods(tel)

    @pytest.mark.asyncio
    async def test_converse_rpc_failure_plays_connect_failed_prompt(self, monkeypatch):
        client = _FakeVSClient()
        _patch_runtime(monkeypatch, client=client)
        tel = MockTelephonyClient()
        await tel.connect()
        tel.bridge_error = RuntimeError("kernel rejected converse")
        wf = VoiceFlowWorkflow(
            call_id="call-y", tenant_id=1, graph=_graph(), telephony=tel,
        )
        await wf.start()
        assert wf.done.is_set() is True
        assert "CONNECT_FAILED" in _says(tel)
        hangup = next(p for m, p in tel.recorded if m == "call.hangup")
        assert hangup["reason"] == "voicespeed_connect_failed"

    @pytest.mark.asyncio
    async def test_handoff_is_idempotent(self):
        ex = VoiceSpeedExecutor()
        tel = MockTelephonyClient()
        await tel.connect()
        ctx = ExecutionContext(
            call_id="c",
            tenant_id=1,
            edges_by_source={"vs": {"handoff": "target"}},
            telephony=tel,
        )
        node = {"id": "vs", "data": {}}

        first = await ex._handle_handoff(ctx, node, {"payload": {"reason": "x"}})
        assert isinstance(first, Goto)
        assert first.node_id == "target"
        assert ctx.variables["sys._handoff_handled"] is True

        # Duplicate handoff → ignored (keeps waiting), not a second Goto.
        second = await ex._handle_handoff(ctx, node, {"payload": {}})
        assert isinstance(second, WaitForEvent)

    @pytest.mark.asyncio
    async def test_handoff_ignored_after_bridged(self):
        ex = VoiceSpeedExecutor()
        tel = MockTelephonyClient()
        await tel.connect()
        ctx = ExecutionContext(
            call_id="c",
            tenant_id=1,
            edges_by_source={"vs": {"handoff": "target"}},
            telephony=tel,
            variables={"sys._bridged_agent_id": 5},
        )
        node = {"id": "vs", "data": {}}
        step = await ex._handle_handoff(ctx, node, {"payload": {}})
        assert isinstance(step, WaitForEvent)
        assert "sys._handoff_handled" not in ctx.variables


class TestVoiceSpeedManagedSession:
    @pytest.mark.asyncio
    async def test_no_db_session_held_while_converse_in_flight(self, monkeypatch):
        """Assert the db session is closed BEFORE the kernel converse RPC
        (CLAUDE.md rule #8)."""

        class SessionTracker:
            active = False
            opens = 0
            closes = 0

        class TrackingSessionCtx:
            async def __aenter__(self):
                assert SessionTracker.active is False
                SessionTracker.active = True
                SessionTracker.opens += 1
                return SimpleNamespace(commit=AsyncMock())

            async def __aexit__(self, *_exc):
                SessionTracker.active = False
                SessionTracker.closes += 1
                return False

        monkeypatch.setattr(
            "app.db.session.AsyncSessionLocal", lambda: TrackingSessionCtx(),
        )

        # The bot-served CDR mark is exercised separately; here it must simply
        # run inside its own short session, not leak into the converse wait.
        async def _mark_bot_served(db, *_a, **_k):
            assert SessionTracker.active is True

        monkeypatch.setattr(
            "app.services.call_record_service.CallRecordService.mark_bot_served",
            _mark_bot_served,
        )

        async def _creds(_db, _tenant_id):
            # Reading credentials happens INSIDE the short session.
            assert SessionTracker.active is True
            return ("http://vs", "key")

        monkeypatch.setattr(
            OpenAgentSettingsService, "get_voice_speed_credentials", _creds,
        )

        client = _FakeVSClient()
        monkeypatch.setattr(
            "app.libs.voice_speed.create_voice_speed_client", lambda: client,
        )

        class ConverseTrackingTelephony(MockTelephonyClient):
            def __init__(self):
                super().__init__()
                self.active_at_converse = None

            async def call_converse_external_agent(self, *a, **k):
                self.active_at_converse = SessionTracker.active
                await super().call_converse_external_agent(*a, **k)

        tel = ConverseTrackingTelephony()
        await tel.connect()

        node = {
            "id": "vs", "type": "voicespeed",
            "data": {"agent_id": "ag_1", "connect_failed_prompt_text": "X"},
        }
        ctx = ExecutionContext(call_id="call-1", tenant_id=1, telephony=tel)

        step = await VoiceSpeedExecutor().execute(ctx, node)

        # Conversing → we end on a WaitForEvent holding no db session.
        assert isinstance(step, WaitForEvent)
        assert tel.active_at_converse is False
        # Two short sessions: credentials read + bot-served CDR mark. Both must
        # be closed before the wait begins.
        assert SessionTracker.opens == 2
        assert SessionTracker.opens == SessionTracker.closes
        assert SessionTracker.active is False


class TestVoiceSpeedEventOrderingRace:
    """An external-agent control event can arrive in the gap between the
    converse_external_agent RPC and the workflow registering its WaitForEvent.
    Such an event must be buffered and consumed, not dropped (a lost handoff
    silently breaks transfer-to-human)."""

    @pytest.mark.asyncio
    async def test_handoff_before_wait_is_consumed(self, monkeypatch):
        client = _FakeVSClient()
        _patch_runtime(monkeypatch, client=client)
        tel = MockTelephonyClient()
        await tel.connect()
        wf = VoiceFlowWorkflow(
            call_id="call-1", tenant_id=1, graph=_graph("h"), telephony=tel,
            initial_variables={"sys._trace_id": "a" * 32},
        )
        # Race: handoff arrives BEFORE the voicespeed node registers its wait.
        await wf.handle_event(
            "call.external_agent.handoff",
            {"call_id": "call-1", "payload": {"reason": "user_request"}},
        )
        # Buffered — nothing consumed yet (executor hasn't run).
        assert wf.done.is_set() is False

        await wf.start()
        # The wait registers, drains the buffered handoff, routes the outlet.
        assert wf.done.is_set() is True
        assert wf.ctx.variables["sys._handoff_handled"] is True

    @pytest.mark.asyncio
    async def test_failed_before_wait_is_handled(self, monkeypatch):
        client = _FakeVSClient()
        _patch_runtime(monkeypatch, client=client)
        tel = MockTelephonyClient()
        await tel.connect()
        wf = VoiceFlowWorkflow(
            call_id="call-1", tenant_id=1, graph=_graph("h"), telephony=tel,
        )
        # Race: failed arrives BEFORE the voicespeed node registers its wait.
        await wf.handle_event(
            "call.external_agent.failed",
            {"call_id": "call-1", "code": "ws_error", "message": "boom"},
        )
        assert wf.done.is_set() is False

        await wf.start()
        # Buffered failure is consumed → connect-failed prompt + hangup.
        assert wf.done.is_set() is True
        assert "CONNECT_FAILED" in _says(tel)
        hangup = next(p for m, p in tel.recorded if m == "call.hangup")
        assert hangup["reason"] == "voicespeed_connect_failed"


class TestDirectConnectGraph:
    def test_build_voicespeed_direct_graph_structure(self):
        graph = build_voicespeed_direct_graph(
            agent_id="ag_9",
            agent_name="Bot",
            transfer_target={"queue_type": "employee_group", "queue_id": 3},
        )
        nodes = {n["id"]: n for n in graph["nodes"]}
        assert nodes["voicespeed"]["data"]["agent_id"] == "ag_9"
        # handoff routes into assign_queue (reusing the queue executor).
        handoff_edge = next(e for e in graph["edges"] if e["source_handle"] == "handoff")
        assert handoff_edge["source"] == "voicespeed"
        assert handoff_edge["target"] == "assign_queue"
        # The single transfer target is fed to assign_queue as a queue_target.
        assert nodes["assign_queue"]["data"]["queue_targets"] == [
            {"queue_type": "employee_group", "queue_id": 3}
        ]
        # assign_queue failure/timeout falls through to hangup.
        assert any(
            e["source"] == "assign_queue" and e["target"] == "hangup"
            for e in graph["edges"]
        )

    def test_build_voicespeed_direct_graph_without_transfer_target(self):
        graph = build_voicespeed_direct_graph(
            agent_id="ag_1", agent_name=None, transfer_target=None,
        )
        nodes = {n["id"]: n for n in graph["nodes"]}
        assert nodes["assign_queue"]["data"]["queue_targets"] == []
