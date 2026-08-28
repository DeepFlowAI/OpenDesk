"""
Unit tests for CallControlService — the current-agent in-call control layer.

These verify:
  - hold / unhold / dtmf drive the kernel primitives on the CUSTOMER leg;
  - the DB session used for leg resolution is CLOSED before any kernel RPC
    (short-session-for-long-I/O rule);
  - mute is trail-only (no kernel RPC);
  - transfer / consult are event-driven: the request originates the target and
    returns as it rings, WITHOUT holding a DB session across the answer wait;
    the bridge / restore happens off the request path;
  - three-party uses room.* and degrades to 501 when rooms are disabled, never
    disturbing the two-party call;
  - waiting tones fire on hold/consult and stop on unhold/consult-end;
  - no active call → 404.
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.core.exceptions import NotFoundError, NotImplementedApiError, ValidationError
from app.libs.telephony.base import TelephonyMethodNotFoundError, TelephonyRPCError
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
from app.services.call_center import call_control_service as ccs_module
from app.services.call_center.call_control_service import CallControlService


def _recorded_methods(tel) -> list[str]:
    return [m for m, _ in tel.recorded]


@pytest.fixture(autouse=True)
def _clean_in_call_state():
    """Keep the module-level transient leg registry isolated per test."""
    ccs_module._in_call_state.clear()
    yield
    ccs_module._in_call_state.clear()


def _bypass_tone(monkeypatch):
    """Neutralize prompt-tone playback so orchestration tests stay focused.

    Records nothing on its own; individual tone tests exercise the real path.
    """

    async def _noop_play(_telephony, **_kw):
        return None

    monkeypatch.setattr(CallControlService, "_play_scene_tone", _noop_play)


# ─────────────── fakes: DB session that also tracks open/close ───────────────


class SessionTracker:
    def __init__(self) -> None:
        self.active = False
        self.opens = 0
        self.closes = 0


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    def __init__(self, row):
        self.row = row

    async def execute(self, _query):
        return _Result(self.row)


class _FakeSession:
    def __init__(self, row, tracker: SessionTracker):
        self.row = row
        self.tracker = tracker

    async def __aenter__(self):
        assert self.tracker.active is False, "session opened while another was active"
        self.tracker.active = True
        self.tracker.opens += 1
        return _FakeDb(self.row)

    async def __aexit__(self, *_exc):
        self.tracker.active = False
        self.tracker.closes += 1
        return False


def _install_session(monkeypatch, row, tracker: SessionTracker):
    monkeypatch.setattr(
        ccs_module, "AsyncSessionLocal", lambda: _FakeSession(row, tracker)
    )


def _active_row(**overrides):
    base = dict(
        id=1,
        tenant_id=7,
        last_serving_agent_id=42,
        initiator_agent_id=None,
        lifecycle_status="active",
        direction="inbound",
        started_at=None,
        root_call_id="sip-customer",
        call_id="sip-customer",
        customer_number="10086",
        service_number="400",
        user_id=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _has_bridge(tel, call_id: str, other_call_id: str, *, keepalive: bool | None = None) -> bool:
    for method, args in tel.recorded:
        if method != "call.bridge":
            continue
        if args.get("call_id") != call_id or args.get("other_call_id") != other_call_id:
            continue
        flag = bool(args.get("keepalive_on_peer_hangup"))
        if keepalive is not None and flag is not keepalive:
            continue
        return True
    return False


async def _webrtc_active(_db, _tenant_id, _employee_id):
    return {"webrtc_call_id": "webrtc-1"}


# ───────────────────────────── hold / unhold ─────────────────────────────


@pytest.mark.asyncio
async def test_hold_calls_kernel_on_customer_leg(monkeypatch):
    tracker = SessionTracker()
    _install_session(monkeypatch, _active_row(), tracker)
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    tel = MockTelephonyClient()
    await tel.connect()

    result = await CallControlService.hold(tel, tenant_id=7, employee_id=42)

    assert result == {"ok": True, "call_id": "sip-customer"}
    # Hold unbridges the agent leg (keeps customer RTP flowing for the tone)
    # rather than issuing a SIP-level call.hold.
    assert (
        "call.unbridge",
        {"call_id": "sip-customer", "other_call_id": "webrtc-1"},
    ) in tel.recorded
    # DB session was opened and closed before returning.
    assert tracker.opens == tracker.closes == 1
    assert tracker.active is False


@pytest.mark.asyncio
async def test_unhold_calls_kernel_on_customer_leg(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    tel = MockTelephonyClient()
    await tel.connect()

    result = await CallControlService.unhold(tel, tenant_id=7, employee_id=42)

    assert result == {"ok": True, "call_id": "sip-customer"}
    # Unhold re-bridges the agent leg back to the customer.
    assert (
        "call.bridge",
        {
            "call_id": "sip-customer",
            "other_call_id": "webrtc-1",
            "transcribe": True,
            "keepalive_on_peer_hangup": True,
        },
    ) in tel.recorded


# ─────────────────────── session closed before RPC ───────────────────────


@pytest.mark.asyncio
async def test_no_db_session_held_during_kernel_rpc(monkeypatch):
    """The pooled DB connection must be released before the kernel round-trip."""

    tracker = SessionTracker()
    _install_session(monkeypatch, _active_row(), tracker)
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    # hold also plays a waiting tone via CallPromptToneService.get_settings_managed,
    # which opens its own real AsyncSessionLocal (not the patched ccs one).
    # Bypass that incidental I/O — session discipline under test is the
    # _resolve_current_call FakeSession vs kernel RPC ordering.
    _bypass_tone(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    session_active_during_rpc: list[bool] = []
    orig_unbridge = tel.call_unbridge

    async def _tracking_unbridge(call_id, other_call_id):
        session_active_during_rpc.append(tracker.active)
        return await orig_unbridge(call_id, other_call_id)

    monkeypatch.setattr(tel, "call_unbridge", _tracking_unbridge)

    await CallControlService.hold(tel, tenant_id=7, employee_id=42)

    assert session_active_during_rpc == [False]


# ───────────────────────────── DTMF ─────────────────────────────


@pytest.mark.asyncio
async def test_dtmf_sends_digits_on_customer_leg(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    tel = MockTelephonyClient()
    await tel.connect()

    result = await CallControlService.dtmf(
        tel, tenant_id=7, employee_id=42, digits="12#"
    )

    assert result["ok"] is True
    assert (
        "call.dtmf",
        {"call_id": "sip-customer", "digits": "12#", "duration_ms": None},
    ) in tel.recorded


# ───────────────────────────── mute ─────────────────────────────


@pytest.mark.asyncio
async def test_mute_gates_the_agent_leg_in_the_kernel(monkeypatch):
    """The agent's own leg is muted, not the customer's.

    An agent on a SIP handset has no local audio track, so the kernel call is
    the only thing standing between "muted" on screen and a customer who can
    still hear them.
    """

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    tel = MockTelephonyClient()
    await tel.connect()

    result = await CallControlService.mute(tel, tenant_id=7, employee_id=42, muted=True)
    assert result == {"ok": True, "call_id": "sip-customer"}
    assert ("call.mute", {"call_id": "webrtc-1"}) in tel.recorded

    await CallControlService.mute(tel, tenant_id=7, employee_id=42, muted=False)
    assert ("call.unmute", {"call_id": "webrtc-1"}) in tel.recorded


# ───────────────────────────── no active call ─────────────────────────────


@pytest.mark.asyncio
async def test_hold_without_active_call_raises_not_found(monkeypatch):
    _install_session(monkeypatch, None, SessionTracker())

    tel = MockTelephonyClient()
    await tel.connect()

    with pytest.raises(NotFoundError):
        await CallControlService.hold(tel, tenant_id=7, employee_id=42)
    # No RPC issued.
    assert tel.recorded == []


# ─────────────────────── target resolution stubs ───────────────────────


def _stub_external_target(monkeypatch):
    """Make `_resolve_target_originate` return an external-number originate."""

    async def _resolve(_tenant_id, _tt, _tid, number):
        return (
            {"uri": number, "caller_id": "1000", "trunk_id": "t1"},
            f"external:{number}",
        )

    monkeypatch.setattr(
        CallControlService, "_resolve_target_originate", _resolve
    )


def _fake_orchestrator(monkeypatch):
    """Install a fake orchestrator exposing register/cancel leg-wait.

    Returns the orchestrator; tests resolve `orch.waiters[call_id]` to simulate
    the target answering / declining.
    """

    class _Orch:
        def __init__(self):
            self.waiters: dict[str, asyncio.Future] = {}
            self.cancelled: list[str] = []
            self.control_results: list[tuple] = []
            self.ended: list[tuple] = []
            self.participant_left: list[tuple] = []
            self.republished: list[tuple] = []
            self._workflows: dict = {}
            self.discarded: list[str] = []
            self.republish_error: Exception | None = None

        def register_leg_wait(self, call_id):
            fut = asyncio.get_event_loop().create_future()
            self.waiters[call_id] = fut
            return fut

        def cancel_leg_wait(self, call_id):
            self.cancelled.append(call_id)
            self.waiters.pop(call_id, None)

        def active_workflow(self, call_id):
            return self._workflows.get(call_id)

        async def discard_call_state(self, call_id):
            self.discarded.append(call_id)
            self._workflows.pop(call_id, None)

        async def notify_agent_control_result(
            self, *, tenant_id, employee_id, method, payload
        ):
            self.control_results.append((tenant_id, employee_id, method, payload))

        async def notify_agent_call_ended(
            self, *, tenant_id, employee_id, call_id, reason
        ):
            self.ended.append((tenant_id, employee_id, call_id, reason))

        async def notify_conference_participant_left(self, *, tenant_id, employee_id):
            self.participant_left.append((tenant_id, employee_id))

        async def republish_agent_call_ui(self, *, tenant_id, employee_id):
            if self.republish_error is not None:
                raise self.republish_error
            self.republished.append((tenant_id, employee_id))

    orch = _Orch()
    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "get_orchestrator", lambda: orch)
    return orch


def _seed_bridged_workflow(orch, *, call_id: str, employee_id: int, tenant_id: int = 7):
    """Attach a minimal workflow so transfer finalize can rebind bridged agent."""

    from app.services.call_center.workflow import VoiceFlowWorkflow

    tel = MockTelephonyClient()
    wf = VoiceFlowWorkflow(
        call_id=call_id,
        tenant_id=tenant_id,
        graph={"nodes": [{"id": "start", "type": "start"}], "edges": []},
        telephony=tel,
        initial_variables={"sys._bridged_agent_id": employee_id},
    )
    orch._workflows[call_id] = wf
    return wf


# ─────────────────────── transfer (event-driven) ───────────────────────


@pytest.mark.asyncio
async def test_transfer_originates_target_and_returns_ringing(monkeypatch):
    tracker = SessionTracker()
    _install_session(monkeypatch, _active_row(), tracker)
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _stub_external_target(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "target-1"}
    await tel.connect()

    session_active_during_originate: list[bool] = []
    orig_orig = tel.call_originate

    async def _tracking_originate(*a, **kw):
        session_active_during_originate.append(tracker.active)
        return await orig_orig(*a, **kw)

    monkeypatch.setattr(tel, "call_originate", _tracking_originate)

    result = await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="external", target_id=None, number="13800138000",
    )

    assert result["ok"] is True
    assert result["note"] == "ringing_target"
    # Target was originated; customer/agent legs NOT yet bridged or dropped.
    assert "call.originate" in _recorded_methods(tel)
    assert "call.bridge" not in _recorded_methods(tel)
    assert "call.hangup" not in _recorded_methods(tel)
    # No DB session was held across the originate RPC.
    assert session_active_during_originate == [False]
    # A leg-waiter was registered off the request path.
    assert "target-1" in orch.waiters


@pytest.mark.asyncio
async def test_transfer_bridges_customer_and_drops_agent_on_answer(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _stub_external_target(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "target-1"}
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="external", target_id=None, number="13800138000",
    )

    # Simulate the target answering; the background runner bridges + drops agent.
    orch.waiters["target-1"].set_result({"answered": True})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    methods = _recorded_methods(tel)
    # The customer MUST be detached from the agent before bridging to the
    # target — else the kernel rejects the bridge (-32003 already bridged) and
    # the whole handover silently aborts.
    unbridge_idx = tel.recorded.index(
        ("call.unbridge", {"call_id": "sip-customer", "other_call_id": "webrtc-1"})
    )
    bridge_idx = tel.recorded.index(
        ("call.bridge", {
            "call_id": "sip-customer", "other_call_id": "target-1", "transcribe": True,
        })
    )
    assert unbridge_idx < bridge_idx
    # Agent's own WebRTC leg dropped after the customer is handed over.
    assert ("call.hangup", {"call_id": "webrtc-1", "reason": "transferred"}) in tel.recorded


@pytest.mark.asyncio
async def test_transfer_sip_employee_rebinds_workflow_bridged_agent(monkeypatch):
    """After SIP/extension blind transfer, live ASR targets the new agent."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, False)
    orch = _fake_orchestrator(monkeypatch)
    wf = _seed_bridged_workflow(orch, call_id="sip-customer", employee_id=42)

    async def _resolve(_tenant_id, _tt, tid, _number):
        return ({"extension": "6001"}, f"employee:{tid}")

    monkeypatch.setattr(CallControlService, "_resolve_target_originate", _resolve)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "target-sip-1"}
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    orch.waiters["target-sip-1"].set_result({"answered": True})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert wf.bridged_agent_info() == {"tenant_id": 7, "employee_id": 99}


@pytest.mark.asyncio
async def test_transfer_sip_employee_republishes_target_call_ui(monkeypatch):
    """SIP desk-phone transfer must push the target agent's in-call workspace."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, False)
    orch = _fake_orchestrator(monkeypatch)
    _seed_bridged_workflow(orch, call_id="sip-customer", employee_id=42)

    async def _resolve(_tenant_id, _tt, tid, _number):
        return ({"extension": "6001"}, f"employee:{tid}")

    monkeypatch.setattr(CallControlService, "_resolve_target_originate", _resolve)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "target-sip-1"}
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    orch.waiters["target-sip-1"].set_result({"answered": True})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert orch.republished == [(7, 99)]


@pytest.mark.asyncio
async def test_transfer_external_does_not_republish_target_call_ui(monkeypatch):
    """External blind transfer has no employee workspace to republish."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _stub_external_target(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "target-1"}
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="external", target_id=None, number="13800138000",
    )
    orch.waiters["target-1"].set_result({"answered": True})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert orch.republished == []
    assert any(
        method == "cc.transfer_result" and employee_id == 42
        for _tenant_id, employee_id, method, _payload in orch.control_results
    )


@pytest.mark.asyncio
async def test_transfer_webrtc_employee_republishes_target_call_ui(monkeypatch):
    """After the WebRTC handover the target's UI is re-keyed onto the customer
    call (restore push), so transcript/history anchor to the customer leg."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_internal_consult(
        monkeypatch,
        result={"target_webrtc_call_id": "target-web-2", "offer_id": "offer-1"},
    )
    orch = _fake_orchestrator(monkeypatch)
    _seed_bridged_workflow(orch, call_id="sip-customer", employee_id=42)
    _ResourceTracker().install(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(5):
        await asyncio.sleep(0)

    assert orch.republished == [(7, 99)]


@pytest.mark.asyncio
async def test_transfer_sip_employee_republish_failure_is_non_fatal(monkeypatch):
    """A republish error must not undo a completed SIP handover."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, False)
    orch = _fake_orchestrator(monkeypatch)
    orch.republish_error = RuntimeError("socket down")
    _seed_bridged_workflow(orch, call_id="sip-customer", employee_id=42)

    async def _resolve(_tenant_id, _tt, tid, _number):
        return ({"extension": "6001"}, f"employee:{tid}")

    monkeypatch.setattr(CallControlService, "_resolve_target_originate", _resolve)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "target-sip-1"}
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    orch.waiters["target-sip-1"].set_result({"answered": True})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert orch.republished == []
    assert any(
        method == "cc.transfer_result"
        and employee_id == 42
        and payload.get("ok") is True
        for _tenant_id, employee_id, method, payload in orch.control_results
    )
    assert ("call.hangup", {"call_id": "webrtc-1", "reason": "transferred"}) in tel.recorded


@pytest.mark.asyncio
async def test_transfer_webrtc_employee_rebinds_workflow_bridged_agent(monkeypatch):
    """After internal WebRTC blind transfer, live ASR targets the new agent."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_internal_consult(
        monkeypatch,
        result={"target_webrtc_call_id": "target-web-2", "offer_id": "offer-1"},
    )
    orch = _fake_orchestrator(monkeypatch)
    wf = _seed_bridged_workflow(orch, call_id="sip-customer", employee_id=42)
    _ResourceTracker().install(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(5):
        await asyncio.sleep(0)

    assert wf.bridged_agent_info() == {"tenant_id": 7, "employee_id": 99}


@pytest.mark.asyncio
async def test_transfer_no_answer_keeps_customer(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _stub_external_target(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "target-1"}
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="external", target_id=None, number="13800138000",
    )
    # Target declines → restore path runs; customer leg never bridged/dropped.
    orch.waiters["target-1"].set_result({"answered": False, "reason": "declined"})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert ("call.bridge", {
        "call_id": "sip-customer", "other_call_id": "target-1", "transcribe": True,
    }) not in tel.recorded
    # Customer leg was never hung up.
    assert ("call.hangup", {"call_id": "sip-customer", "reason": None}) not in tel.recorded


# ─────────────────────── consult (event-driven) ───────────────────────


@pytest.mark.asyncio
async def test_consult_start_holds_customer_and_originates(monkeypatch):
    tracker = SessionTracker()
    _install_session(monkeypatch, _active_row(), tracker)
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _stub_external_target(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "consult-1"}
    await tel.connect()

    session_active_during_originate: list[bool] = []
    orig_orig = tel.call_originate

    async def _tracking_originate(*a, **kw):
        session_active_during_originate.append(tracker.active)
        return await orig_orig(*a, **kw)

    monkeypatch.setattr(tel, "call_originate", _tracking_originate)

    result = await CallControlService.consult_start(
        tel, tenant_id=7, employee_id=42,
        target_type="external", target_id=None, number="13800138000",
    )

    assert result["note"] == "ringing_target"
    methods = _recorded_methods(tel)
    # Customer held; consult leg originated; agent not yet bridged.
    assert (
        "call.unbridge",
        {"call_id": "sip-customer", "other_call_id": "webrtc-1"},
    ) in tel.recorded
    assert "call.originate" in methods
    assert "call.bridge" not in methods
    assert session_active_during_originate == [False]
    assert ccs_module._in_call_state[(7, 42)].consult_call_id == "consult-1"

    # Answer → agent bridged to consult leg.
    orch.waiters["consult-1"].set_result({"answered": True})
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert ("call.bridge", {
        "call_id": "webrtc-1", "other_call_id": "consult-1", "transcribe": True,
    }) in tel.recorded


@pytest.mark.asyncio
async def test_consult_end_drops_third_party_and_resumes(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    tel = MockTelephonyClient()
    await tel.connect()

    # Seed an active consult leg.
    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(consult_call_id="consult-1")

    result = await CallControlService.consult_end(tel, tenant_id=7, employee_id=42)

    assert result == {"ok": True, "call_id": "sip-customer"}
    assert ("call.unbridge", {"call_id": "webrtc-1", "other_call_id": "consult-1"}) in tel.recorded
    assert ("call.hangup", {"call_id": "consult-1", "reason": "consult_ended"}) in tel.recorded
    assert ("call.stop", {"call_id": "sip-customer", "target": "play"}) in tel.recorded
    assert (
        "call.bridge",
        {
            "call_id": "sip-customer",
            "other_call_id": "webrtc-1",
            "transcribe": True,
            "keepalive_on_peer_hangup": True,
        },
    ) in tel.recorded
    assert ccs_module._in_call_state[(7, 42)].consult_call_id is None


@pytest.mark.asyncio
async def test_consult_end_notifies_internal_target_browser(monkeypatch):
    """Ending a browser-ring consult pushes cc.call_hangup to the colleague so
    their WebRTC leg closes cleanly (no stuck "通话中" / spurious ICE error)."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    # Don't touch Redis for the resource release in this unit test.
    async def _noop_release(_tenant_id, _target_id, *, reason):
        return None

    monkeypatch.setattr(
        CallControlService, "_release_internal_target", staticmethod(_noop_release)
    )

    ended: list[dict] = []

    class _Orch:
        async def notify_agent_call_ended(self, *, tenant_id, employee_id, call_id, reason):
            ended.append(
                {"tenant_id": tenant_id, "employee_id": employee_id,
                 "call_id": call_id, "reason": reason}
            )

    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "get_orchestrator", lambda: _Orch())

    tel = MockTelephonyClient()
    await tel.connect()

    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        consult_call_id="consult-1", consult_target_employee_id=36
    )

    await CallControlService.consult_end(tel, tenant_id=7, employee_id=42)

    assert ended == [
        {"tenant_id": 7, "employee_id": 36,
         "call_id": "consult-1", "reason": "consult_ended"}
    ]


# ─────────────────────── three-party (room) ───────────────────────


@pytest.mark.asyncio
async def test_conference_merge_creates_room(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)

    tel = MockTelephonyClient()
    tel.room_create_response = {"room_id": "room-9", "legs": []}
    await tel.connect()

    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        conference_participant_call_id="party-1"
    )

    result = await CallControlService.conference_merge(tel, tenant_id=7, employee_id=42)

    assert result["note"] == "room-9"
    assert ("room.create", {
        "leg_call_ids": ["sip-customer", "webrtc-1", "party-1"],
    }) in tel.recorded
    assert ccs_module._in_call_state[(7, 42)].room_id == "room-9"


@pytest.mark.asyncio
async def test_conference_merge_degrades_when_rooms_disabled(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)

    tel = MockTelephonyClient()
    tel.room_error = TelephonyMethodNotFoundError(-32601, "method not found")
    await tel.connect()

    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        conference_participant_call_id="party-1"
    )

    with pytest.raises(NotImplementedApiError):
        await CallControlService.conference_merge(tel, tenant_id=7, employee_id=42)

    # No customer/agent leg was disturbed — only the (rejected) room.create and
    # the tone-stop after degrade.
    assert "call.hangup" not in _recorded_methods(tel)
    assert "call.unbridge" not in _recorded_methods(tel)


@pytest.mark.asyncio
async def test_conference_add_merges_on_answer(monkeypatch):
    """Participant answers → room auto-created and browser told it's live."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _stub_external_target(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "party-1"}
    tel.room_create_response = {"room_id": "room-9", "legs": []}
    await tel.connect()

    result = await CallControlService.conference_add(
        tel, tenant_id=7, employee_id=42,
        target_type="external", target_id=None, number="13800138000",
    )
    assert result["note"] == "ringing_participant"
    # Customer is held (unbridged from the agent) while the participant rings.
    assert (
        "call.unbridge",
        {"call_id": "sip-customer", "other_call_id": "webrtc-1"},
    ) in tel.recorded

    orch.waiters["party-1"].set_result({"answered": True})
    for _ in range(5):
        await asyncio.sleep(0)

    assert ("room.create", {
        "leg_call_ids": ["sip-customer", "webrtc-1", "party-1"],
    }) in tel.recorded
    # The three-party waiting tone is stopped before the room is created.
    stop_idx = tel.recorded.index(
        ("call.stop", {"call_id": "sip-customer", "target": "play"})
    )
    room_idx = tel.recorded.index((
        "room.create", {"leg_call_ids": ["sip-customer", "webrtc-1", "party-1"]},
    ))
    assert stop_idx < room_idx
    assert ccs_module._in_call_state[(7, 42)].room_id == "room-9"
    conf = [r for r in orch.control_results if r[2] == "cc.conference_result"]
    assert conf and conf[-1][3]["ok"] is True


@pytest.mark.asyncio
async def test_conference_add_aborts_on_no_answer(monkeypatch):
    """Participant declines → leg cleaned up, browser told it failed, no room."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _stub_external_target(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "party-1"}
    await tel.connect()

    await CallControlService.conference_add(
        tel, tenant_id=7, employee_id=42,
        target_type="external", target_id=None, number="13800138000",
    )

    orch.waiters["party-1"].set_result({"answered": False, "reason": "declined"})
    for _ in range(5):
        await asyncio.sleep(0)

    assert ("call.hangup", {
        "call_id": "party-1", "reason": "participant_aborted",
    }) in tel.recorded
    assert ccs_module._in_call_state[(7, 42)].conference_participant_call_id is None
    assert "room.create" not in _recorded_methods(tel)
    # Held customer is restored: tone stopped + re-bridged back to the agent.
    assert ("call.stop", {"call_id": "sip-customer", "target": "play"}) in tel.recorded
    assert (
        "call.bridge",
        {
            "call_id": "sip-customer",
            "other_call_id": "webrtc-1",
            "transcribe": True,
            "keepalive_on_peer_hangup": True,
        },
    ) in tel.recorded
    conf = [r for r in orch.control_results if r[2] == "cc.conference_result"]
    assert conf and conf[-1][3]["ok"] is False
    assert conf[-1][3]["reason"] == "参与人已拒接"


@pytest.mark.asyncio
async def test_conference_add_plays_three_party_tone_and_stops_on_merge(monkeypatch):
    """The configured three-party waiting tone plays to the customer while the
    participant rings, and is stopped when the participant merges."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _stub_external_target(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)

    # Real tone path: TTS three_party scene.
    async def _tone(_tenant_id, scene):
        return ("请稍候，正在为您邀请。", None, None) if scene == "three_party" else None

    monkeypatch.setattr(CallControlService, "_load_scene_tone", _tone)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "party-1"}
    tel.room_create_response = {"room_id": "room-9", "legs": []}
    await tel.connect()

    await CallControlService.conference_add(
        tel, tenant_id=7, employee_id=42,
        target_type="external", target_id=None, number="13800138000",
    )

    # Tone plays off the request path while the participant rings.
    for _ in range(5):
        await asyncio.sleep(0)
    play = next(d for m, d in tel.recorded if m == "call.play")
    assert play["call_id"] == "sip-customer"
    assert play["text"] == "请稍候，正在为您邀请。"
    assert play["loop"] is True
    assert play["interval_ms"] == 15000

    orch.waiters["party-1"].set_result({"answered": True})
    for _ in range(5):
        await asyncio.sleep(0)

    # Tone stopped once the participant merges into the room.
    assert ("call.stop", {"call_id": "sip-customer", "target": "play"}) in tel.recorded


@pytest.mark.asyncio
async def test_conference_add_webrtc_rings_and_merges_on_answer(monkeypatch):
    """A Web-phone colleague added to a conference is rung then merged into the
    room on answer (not routed to the SIP-originate path)."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_internal_consult(
        monkeypatch, result={"target_webrtc_call_id": "colleague-leg"}
    )
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    tel.room_create_response = {"room_id": "room-7", "legs": []}
    await tel.connect()

    result = await CallControlService.conference_add(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    assert result["note"] == "ringing_participant"
    # No SIP originate for a browser colleague.
    assert "call.originate" not in _recorded_methods(tel)
    # Customer held (unbridged) synchronously while the browser rings.
    assert (
        "call.unbridge",
        {"call_id": "sip-customer", "other_call_id": "webrtc-1"},
    ) in tel.recorded

    for _ in range(6):
        await asyncio.sleep(0)

    assert ("room.create", {
        "leg_call_ids": ["sip-customer", "webrtc-1", "colleague-leg"],
    }) in tel.recorded
    # Three-party tone stopped before the room is created.
    assert ("call.stop", {"call_id": "sip-customer", "target": "play"}) in tel.recorded
    legs = ccs_module._in_call_state[(7, 42)]
    assert legs.room_id == "room-7"
    assert legs.conference_target_employee_id == 99
    conf = [r for r in orch.control_results if r[2] == "cc.conference_result"]
    assert conf and conf[-1][3]["ok"] is True


@pytest.mark.asyncio
async def test_conference_add_webrtc_notifies_on_failure(monkeypatch):
    """A browser colleague who declines → no room, and the initiator is told
    with the real reason (not a generic fallback)."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_internal_consult(monkeypatch, error=ValidationError("目标坐席拒接"))
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.conference_add(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(6):
        await asyncio.sleep(0)

    assert "room.create" not in _recorded_methods(tel)
    # Held customer is restored on the browser-ring failure: tone stopped +
    # re-bridged back to the agent.
    assert ("call.stop", {"call_id": "sip-customer", "target": "play"}) in tel.recorded
    assert (
        "call.bridge",
        {
            "call_id": "sip-customer",
            "other_call_id": "webrtc-1",
            "transcribe": True,
            "keepalive_on_peer_hangup": True,
        },
    ) in tel.recorded
    conf = [r for r in orch.control_results if r[2] == "cc.conference_result"]
    assert conf and conf[-1][3]["ok"] is False
    assert conf[-1][3]["reason"] == "目标坐席拒接"


@pytest.mark.asyncio
async def test_conference_end_all_without_room_still_hangs_up(monkeypatch):
    """A participant that is still ringing (no room yet) must not 404 on end-all
    — the agent can always tear everything down."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        conference_participant_call_id="party-1"
    )

    await CallControlService.conference_end_all(tel, tenant_id=7, employee_id=42)

    assert "room.close" not in _recorded_methods(tel)
    hangups = {d["call_id"] for m, d in tel.recorded if m == "call.hangup"}
    assert hangups == {"sip-customer", "webrtc-1", "party-1"}
    assert (7, 42) not in ccs_module._in_call_state
    # Agent's own browser leg is told to close cleanly (no ICE-failure stall).
    assert any(e[1] == 42 and e[2] == "webrtc-1" for e in orch.ended)


@pytest.mark.asyncio
async def test_conference_leave_notifies_agent_browser(monkeypatch):
    """Leaving a conference with an external participant: host wraps up, the
    customer is re-bridged to the participant, and the participant is not hung up."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    async def _asr(_tid):
        return True

    monkeypatch.setattr(
        "app.services.system_settings_service.SystemSettingsService"
        ".is_bridge_asr_enabled_managed",
        staticmethod(_asr),
    )
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        room_id="room-9",
        room_legs=["sip-customer", "webrtc-1", "party-1"],
        conference_participant_call_id="party-1",
    )

    await CallControlService.conference_leave(tel, tenant_id=7, employee_id=42)

    # Host media hung up; customer/participant kept alive and re-bridged.
    assert ("call.hangup", {"call_id": "webrtc-1", "reason": "agent_left"}) in tel.recorded
    assert not any(
        d["call_id"] in {"sip-customer", "party-1"}
        for m, d in tel.recorded if m == "call.hangup"
    )
    assert (
        "call.bridge",
        {"call_id": "sip-customer", "other_call_id": "party-1", "transcribe": True},
    ) in tel.recorded
    # Browser hangup uses the customer call id (what the UI stores), not the media leg.
    assert any(e[1] == 42 and e[2] == "sip-customer" for e in orch.ended)
    assert (7, 42) not in ccs_module._in_call_state


@pytest.mark.asyncio
async def test_conference_end_all_closes_room_and_hangs_up(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        conference_participant_call_id="party-1",
        room_id="room-9",
        room_legs=["sip-customer", "webrtc-1", "party-1"],
    )

    await CallControlService.conference_end_all(tel, tenant_id=7, employee_id=42)

    assert ("room.close", {"room_id": "room-9", "reason": "ended_by_agent"}) in tel.recorded
    hangups = [d["call_id"] for m, d in tel.recorded if m == "call.hangup"]
    assert set(hangups) == {"sip-customer", "webrtc-1", "party-1"}
    # Transient state cleared.
    assert (7, 42) not in ccs_module._in_call_state


@pytest.mark.asyncio
async def test_conference_end_all_drops_state_for_already_gone_leg(monkeypatch):
    """A leg the kernel has already forgotten (-32002) gets no call.hangup, so
    end-all must drop the orchestrator's state for it. Left behind, the
    workflow pins the call for the life of the process and stalls the
    blue/green shutdown drain."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    orch = _fake_orchestrator(monkeypatch)
    orch._workflows["sip-customer"] = SimpleNamespace()

    tel = MockTelephonyClient()
    await tel.connect()
    tel.hangup_errors["sip-customer"] = TelephonyRPCError(
        -32002, "call not found: sip-customer"
    )

    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        conference_participant_call_id="party-1",
        room_id="room-9",
        room_legs=["sip-customer", "webrtc-1", "party-1"],
    )

    await CallControlService.conference_end_all(tel, tenant_id=7, employee_id=42)

    assert orch.discarded == ["sip-customer"]
    assert "sip-customer" not in orch._workflows
    # The other legs still hang up normally.
    hangups = {d["call_id"] for m, d in tel.recorded if m == "call.hangup"}
    assert {"webrtc-1", "party-1"} <= hangups


@pytest.mark.asyncio
async def test_conference_end_all_finalizes_cdr(monkeypatch):
    """Ending the whole conference must close the CDR itself.

    Closing the room drops its legs inside the kernel without a ``call.hangup``
    notification, so nothing else will finalize the record — it would sit in
    ``active`` until an unrelated hangup swept it up.
    """

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _fake_orchestrator(monkeypatch)

    completed: list[dict] = []

    async def _mark_completed(_db, tenant_id, call_id, **kwargs):
        completed.append({"tenant_id": tenant_id, "call_id": call_id, **kwargs})

    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.mark_completed",
        _mark_completed,
    )

    tel = MockTelephonyClient()
    await tel.connect()

    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        conference_participant_call_id="party-1",
        room_id="room-9",
        room_legs=["sip-customer", "webrtc-1", "party-1"],
    )

    await CallControlService.conference_end_all(tel, tenant_id=7, employee_id=42)

    assert completed == [
        {
            "tenant_id": 7,
            "call_id": "sip-customer",
            "hangup_reason": "conference_ended",
            "hangup_party": "agent",
        }
    ]


# ─────────────────────── prompt tones (hold/consult) ───────────────────────


@pytest.mark.asyncio
async def test_hold_plays_looping_tone(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    # Real tone path: TTS hold scene.
    async def _tone(_tenant_id, scene):
        return ("通话已保持，请稍候。", None, None) if scene == "hold" else None

    monkeypatch.setattr(CallControlService, "_load_scene_tone", _tone)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.hold(tel, tenant_id=7, employee_id=42)

    play = next(d for m, d in tel.recorded if m == "call.play")
    assert play["call_id"] == "sip-customer"
    assert play["text"] == "通话已保持，请稍候。"
    assert play["loop"] is True
    assert play["interval_ms"] == 15000


@pytest.mark.asyncio
async def test_hold_tone_failure_does_not_break_hold(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    async def _tone(_tenant_id, scene):
        return ("x", None, None)

    monkeypatch.setattr(CallControlService, "_load_scene_tone", _tone)

    tel = MockTelephonyClient()
    tel.play_error = RuntimeError("kernel rejected play")
    await tel.connect()

    # Hold still succeeds despite the play failing.
    result = await CallControlService.hold(tel, tenant_id=7, employee_id=42)
    assert result["ok"] is True
    assert (
        "call.unbridge",
        {"call_id": "sip-customer", "other_call_id": "webrtc-1"},
    ) in tel.recorded


@pytest.mark.asyncio
async def test_unhold_stops_tone(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.unhold(tel, tenant_id=7, employee_id=42)

    assert ("call.stop", {"call_id": "sip-customer", "target": "play"}) in tel.recorded
    assert (
        "call.bridge",
        {
            "call_id": "sip-customer",
            "other_call_id": "webrtc-1",
            "transcribe": True,
            "keepalive_on_peer_hangup": True,
        },
    ) in tel.recorded


# ───────────────────────────── target validation ─────────────────────────────


# ─────────────── internal WebRTC employee consult / transfer ───────────────


def _route_employee_webrtc(monkeypatch, is_webrtc: bool):
    """Force the employee-target device-routing decision."""

    async def _is_webrtc(_tenant_id, _target_id):
        return is_webrtc

    async def _display(_tenant_id, _employee_id):
        return "Alice"

    monkeypatch.setattr(
        CallControlService, "_employee_target_is_webrtc", staticmethod(_is_webrtc)
    )
    monkeypatch.setattr(
        CallControlService, "_resolve_initiator_display", staticmethod(_display)
    )


def _stub_internal_consult(monkeypatch, *, result=None, error=None):
    """Stub InternalConsultService.initiate_webrtc_consult + redis accessor.

    Also makes the synchronous WebRTC pre-check pass (target ready + idle) so
    tests exercising the background ring reach it; individual pre-check tests
    override the snapshot themselves.
    """

    import app.services.call_center.orchestrator as orch_mod
    from app.services.call_center import internal_consult_service as ics_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: object())

    async def _ready_snapshot(_r, _tenant_id, _employee_id):
        return {"visible_status": "ready", "resource_state": "idle"}

    monkeypatch.setattr(
        ccs_module.CcAgentResourceService,
        "get_snapshot",
        staticmethod(_ready_snapshot),
    )

    async def _init(_tel, _r, **_kw):
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(
        ics_mod.InternalConsultService,
        "initiate_webrtc_consult",
        staticmethod(_init),
    )


class _ResourceTracker:
    """Records force_release / mark_in_call / rekey against the resource service."""

    def __init__(self):
        self.force_released: list[tuple[int, int, str]] = []
        self.marked_in_call: list[tuple[int, int, str]] = []
        self.rekeyed: list[tuple[int, int, str]] = []

    def install(self, monkeypatch):
        async def _force_release(_r, tenant_id, employee_id, *, reason):
            self.force_released.append((tenant_id, employee_id, reason))
            return {"resource_state": "idle"}

        async def _mark_in_call(_r, tenant_id, employee_id, *, call_id, direction, **_kw):
            self.marked_in_call.append((tenant_id, employee_id, call_id))
            return {"resource_state": "in_call"}

        async def _rekey_current_call(_r, tenant_id, employee_id, *, call_id):
            self.rekeyed.append((tenant_id, employee_id, call_id))
            return {"resource_state": "in_call", "current_call_id": call_id}

        monkeypatch.setattr(
            ccs_module.CcAgentResourceService,
            "force_release",
            staticmethod(_force_release),
        )
        monkeypatch.setattr(
            ccs_module.CcAgentResourceService,
            "mark_in_call",
            staticmethod(_mark_in_call),
        )
        monkeypatch.setattr(
            ccs_module.CcAgentResourceService,
            "rekey_current_call",
            staticmethod(_rekey_current_call),
        )


@pytest.mark.asyncio
async def test_consult_webrtc_employee_rings_and_bridges(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_internal_consult(
        monkeypatch,
        result={"target_webrtc_call_id": "target-web-2", "offer_id": "offer-1"},
    )

    tel = MockTelephonyClient()
    await tel.connect()

    result = await CallControlService.consult_start(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )

    assert result["note"] == "ringing_webrtc_target"
    # Customer held immediately; no SIP originate on the WebRTC path.
    assert (
        "call.unbridge",
        {"call_id": "sip-customer", "other_call_id": "webrtc-1"},
    ) in tel.recorded
    assert "call.originate" not in _recorded_methods(tel)

    # Let the background ring-and-bridge task run to completion.
    for _ in range(5):
        await asyncio.sleep(0)

    # Initiator's WebRTC leg bridged to the target's WebRTC leg.
    assert _has_bridge(tel, "webrtc-1", "target-web-2", keepalive=True)
    legs = ccs_module._in_call_state[(7, 42)]
    assert legs.consult_call_id == "target-web-2"
    # The occupied colleague is tracked so consult_end can free them.
    assert legs.consult_target_employee_id == 99
    # offer_id is generated before the browser wait and kept through ACTIVE.
    assert legs.consult_offer_id
    assert legs.consult_state == "active"


@pytest.mark.asyncio
async def test_consult_webrtc_employee_decline_resumes_customer(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_internal_consult(monkeypatch, error=ValidationError("目标坐席拒接"))

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.consult_start(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(5):
        await asyncio.sleep(0)

    # Customer resumed (re-bridged to the initiator); no consult bridge happened.
    assert (
        "call.bridge",
        {
            "call_id": "sip-customer",
            "other_call_id": "webrtc-1",
            "transcribe": True,
            "keepalive_on_peer_hangup": True,
        },
    ) in tel.recorded
    assert (
        "call.bridge",
        {"call_id": "webrtc-1", "other_call_id": "", "transcribe": True},
    ) not in tel.recorded


@pytest.mark.asyncio
async def test_consult_webrtc_end_during_ringing_ignores_late_accept(monkeypatch):
    """Race: consult_end while RINGING must not let a late accept bridge the host.

    Regression for the bug where early RINGING persistence let consult_end clear
    Redis + resume the customer, then the background waiter still transitioned
    to ACTIVE and bridged the initiator onto the colleague.
    """

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)

    import app.services.call_center.orchestrator as orch_mod
    from app.services.call_center import internal_consult_service as ics_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: object())

    async def _ready_snapshot(_r, _tenant_id, _employee_id):
        return {"visible_status": "ready", "resource_state": "idle"}

    monkeypatch.setattr(
        ccs_module.CcAgentResourceService,
        "get_snapshot",
        staticmethod(_ready_snapshot),
    )

    gate = asyncio.Event()
    resolved_offers: list[tuple[str, dict]] = []

    async def _slow_accept(_tel, _r, **kw):
        await gate.wait()
        return {
            "ok": True,
            "target_webrtc_call_id": "target-web-late",
            "offer_id": kw.get("offer_id"),
        }

    monkeypatch.setattr(
        ics_mod.InternalConsultService,
        "initiate_webrtc_consult",
        staticmethod(_slow_accept),
    )

    class _Orch:
        def resolve_offer(self, offer_id, decision):
            resolved_offers.append((offer_id, decision))
            return True

    monkeypatch.setattr(orch_mod, "get_orchestrator", lambda: _Orch())

    released: list[tuple] = []

    async def _release(tenant_id, target_id, *, reason):
        released.append((tenant_id, target_id, reason))

    monkeypatch.setattr(
        CallControlService, "_release_internal_target", staticmethod(_release)
    )

    ended: list[dict] = []

    async def _ended(tenant_id, employee_id, call_id, *, reason):
        ended.append(
            {
                "tenant_id": tenant_id,
                "employee_id": employee_id,
                "call_id": call_id,
                "reason": reason,
            }
        )

    monkeypatch.setattr(
        CallControlService, "_notify_browser_call_ended", staticmethod(_ended)
    )

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.consult_start(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    # Yield so the background task reaches the gate wait.
    for _ in range(5):
        await asyncio.sleep(0)

    legs = ccs_module._in_call_state[(7, 42)]
    assert legs.consult_state == "ringing"
    assert legs.consult_target_employee_id == 99
    offer_id = legs.consult_offer_id
    assert offer_id

    result = await CallControlService.consult_end(tel, tenant_id=7, employee_id=42)
    assert result == {"ok": True, "call_id": "sip-customer"}
    assert legs.consult_state == "none"
    assert legs.consult_call_id is None
    assert resolved_offers == [
        (offer_id, {"accept": False, "reason": "consult_ended"})
    ]
    assert (7, 99, "internal_consult_ended") in released
    assert {
        "tenant_id": 7,
        "employee_id": 99,
        "call_id": f"internal:{offer_id}",
        "reason": "consult_ended",
    } in ended
    assert (
        "call.bridge",
        {
            "call_id": "sip-customer",
            "other_call_id": "webrtc-1",
            "transcribe": True,
            "keepalive_on_peer_hangup": True,
        },
    ) in tel.recorded

    # Late accept: background task continues after cancel.
    gate.set()
    for _ in range(10):
        await asyncio.sleep(0)

    assert not _has_bridge(tel, "webrtc-1", "target-web-late", keepalive=True)
    assert (
        "call.hangup",
        {"call_id": "target-web-late", "reason": "consult_cancelled"},
    ) in tel.recorded
    assert (7, 99, "consult_cancelled") in released
    # Host consult must stay cleared — no resurrection to ACTIVE.
    assert legs.consult_state == "none"
    assert legs.consult_call_id is None


@pytest.mark.asyncio
async def test_cleanup_consult_for_host_ringing_cancels_pending_offer(monkeypatch):
    """Tearing down a RINGING consult (e.g. host hangup) must cancel the
    pending browser offer and notify the target on the synthetic internal
    offer call_id (no media leg exists yet)."""

    import app.libs.telephony as tel_lib
    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: None)

    tel = MockTelephonyClient()
    await tel.connect()
    monkeypatch.setattr(tel_lib, "get_telephony_client", lambda: tel)

    resolved: list[tuple[str, dict]] = []

    class _Orch:
        def resolve_offer(self, offer_id, decision):
            resolved.append((offer_id, decision))
            return True

    monkeypatch.setattr(orch_mod, "get_orchestrator", lambda: _Orch())

    released: list[tuple] = []

    async def _release(tenant_id, target_id, *, reason):
        released.append((tenant_id, target_id, reason))

    monkeypatch.setattr(
        CallControlService, "_release_internal_target", staticmethod(_release)
    )

    ended: list[tuple] = []

    async def _ended(tenant_id, employee_id, call_id, *, reason):
        ended.append((tenant_id, employee_id, call_id, reason))

    monkeypatch.setattr(
        CallControlService, "_notify_browser_call_ended", staticmethod(_ended)
    )

    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        consult_state="ringing",
        consult_target_employee_id=99,
        consult_offer_id="offer-ring",
    )

    ok = await CallControlService.cleanup_consult_for_host(
        7, 42, reason="host_hangup",
    )

    assert ok is True
    assert resolved == [("offer-ring", {"accept": False, "reason": "host_hangup"})]
    assert (7, 99, "host_hangup") in released
    assert (7, 99, "internal:offer-ring", "consult_ended") in ended
    # Legs fully cleared for the host.
    assert (7, 42) not in ccs_module._in_call_state


@pytest.mark.asyncio
async def test_transfer_webrtc_employee_hands_over_customer(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_internal_consult(
        monkeypatch, result={"target_webrtc_call_id": "target-web-2"}
    )

    tel = MockTelephonyClient()
    await tel.connect()

    result = await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )

    assert result["note"] == "ringing_webrtc_target"
    assert "call.originate" not in _recorded_methods(tel)

    for _ in range(5):
        await asyncio.sleep(0)

    # Customer bridged to the target's WebRTC leg; initiator's own leg dropped.
    # keepalive: a target-side browser refresh must not drop the customer.
    assert _has_bridge(tel, "sip-customer", "target-web-2", keepalive=True)
    assert ("call.hangup", {"call_id": "webrtc-1", "reason": "transferred"}) in tel.recorded


@pytest.mark.asyncio
async def test_consult_sip_phone_employee_still_originates(monkeypatch):
    """Regression: a SIP-extension employee target keeps the originate path."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    # Not a WebRTC target → fall through to _resolve_target_originate.
    _route_employee_webrtc(monkeypatch, False)
    orch = _fake_orchestrator(monkeypatch)

    async def _resolve(_tenant_id, _tt, tid, _number):
        return ({"extension": "6001"}, f"employee:{tid}")

    monkeypatch.setattr(CallControlService, "_resolve_target_originate", _resolve)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "consult-sip"}
    await tel.connect()

    result = await CallControlService.consult_start(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )

    assert result["note"] == "ringing_target"
    # SIP extension originate happened; leg-waiter registered.
    assert "call.originate" in _recorded_methods(tel)
    assert "consult-sip" in orch.waiters


@pytest.mark.asyncio
async def test_transfer_validates_target_payload(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    tel = MockTelephonyClient()
    await tel.connect()

    # external target without number → validation error (before 501).
    with pytest.raises(ValidationError):
        await CallControlService.transfer(
            tel, tenant_id=7, employee_id=42,
            target_type="external", target_id=None, number=None,
        )
    # employee target without id → validation error.
    with pytest.raises(ValidationError):
        await CallControlService.transfer(
            tel, tenant_id=7, employee_id=42,
            target_type="employee", target_id=None, number=None,
        )


@pytest.mark.asyncio
async def test_transfer_queue_routes_to_queue_branch_not_501(monkeypatch):
    """target_type=queue must enter transfer_to_queue, not raise 501."""

    called: list[dict] = []

    async def _queue_branch(telephony, *, tenant_id, employee_id, queue_id):
        called.append(
            {
                "tenant_id": tenant_id,
                "employee_id": employee_id,
                "queue_id": queue_id,
            }
        )
        return {"ok": True, "call_id": "sip-customer", "note": "queued_target"}

    monkeypatch.setattr(CallControlService, "transfer_to_queue", _queue_branch)

    tel = MockTelephonyClient()
    await tel.connect()

    result = await CallControlService.transfer(
        tel,
        tenant_id=7,
        employee_id=42,
        target_type="queue",
        target_id=5,
        number=None,
    )

    assert result["note"] == "queued_target"
    assert called == [{"tenant_id": 7, "employee_id": 42, "queue_id": 5}]


# ─────────────── internal target resource release / re-key ───────────────


def _patch_redis_accessor(monkeypatch):
    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: object())


@pytest.mark.asyncio
async def test_consult_end_releases_internal_webrtc_target(monkeypatch):
    """consult_end frees the colleague we occupied for a browser-ring consult.

    Regression for the resource-leak bug: without the force_release the target
    stays stuck in_call and a SECOND consult to the same colleague is refused.
    """

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _patch_redis_accessor(monkeypatch)
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    # Seed an active internal consult (target colleague 99 occupied).
    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        consult_call_id="target-web-2",
        consult_target_employee_id=99,
        consult_offer_id="offer-1",
    )

    result = await CallControlService.consult_end(tel, tenant_id=7, employee_id=42)

    assert result == {"ok": True, "call_id": "sip-customer"}
    # Target leg dropped, customer resumed.
    assert ("call.hangup", {"call_id": "target-web-2", "reason": "consult_ended"}) in tel.recorded
    # The colleague's resource was force-released (frees a stuck in_call).
    assert tracker.force_released == [(7, 99, "internal_consult_ended")]
    # Tracking cleared so a stale target can't be double-released.
    legs = ccs_module._in_call_state[(7, 42)]
    assert legs.consult_call_id is None
    assert legs.consult_target_employee_id is None
    assert legs.consult_offer_id is None


@pytest.mark.asyncio
async def test_consult_end_sip_target_does_not_touch_resource(monkeypatch):
    """A SIP (non-internal) consult end must NOT force-release anyone."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _patch_redis_accessor(monkeypatch)
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(consult_call_id="consult-sip")
    await CallControlService.consult_end(tel, tenant_id=7, employee_id=42)

    assert tracker.force_released == []


@pytest.mark.asyncio
async def test_second_consult_same_target_succeeds_after_end(monkeypatch):
    """End-to-end: consult B → consult_end frees B → second consult B succeeds.

    Proves the leak is gone: the first consult's force_release lets the target
    be occupied again, so the second consult reaches the bridge instead of
    failing at reserve with `目标坐席正在通话或不可用`.
    """

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_internal_consult(
        monkeypatch,
        result={"target_webrtc_call_id": "target-web-2", "offer_id": "offer-1"},
    )
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    # First consult to colleague 99.
    await CallControlService.consult_start(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(5):
        await asyncio.sleep(0)
    assert ccs_module._in_call_state[(7, 42)].consult_target_employee_id == 99

    # End it — colleague 99 released.
    await CallControlService.consult_end(tel, tenant_id=7, employee_id=42)
    assert (7, 99, "internal_consult_ended") in tracker.force_released

    # Second consult to the SAME colleague 99 — must reach the bridge again.
    await CallControlService.consult_start(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(5):
        await asyncio.sleep(0)

    assert ccs_module._in_call_state[(7, 42)].consult_target_employee_id == 99
    assert _has_bridge(tel, "webrtc-1", "target-web-2", keepalive=True)


# ─────────────── WebRTC target pre-check + result events ───────────────


def _stub_target_snapshot(monkeypatch, snapshot, *, connected=False):
    """Force the WebRTC pre-check's resource-snapshot read + provide redis.

    ``connected`` controls the socket-liveness probe used by the stale-presence
    reconcile: default False keeps an "offline" snapshot genuinely offline.
    """

    import app.services.agent_status_service as ass_mod
    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: object())

    async def _snap(_r, _tenant_id, _employee_id):
        return snapshot

    monkeypatch.setattr(
        ccs_module.CcAgentResourceService, "get_snapshot", staticmethod(_snap)
    )

    async def _is_connected(_r, _tenant_id, _employee_id):
        return connected

    monkeypatch.setattr(
        ass_mod.AgentStatusService, "is_connected", staticmethod(_is_connected)
    )


class _ControlResultTracker:
    """Records cc.consult_result / cc.transfer_result pushes to the initiator."""

    def __init__(self):
        self.events: list[tuple[int, int, str, dict]] = []

    def install(self, monkeypatch):
        tracker = self

        class _Orch:
            async def notify_agent_control_result(
                self, *, tenant_id, employee_id, method, payload
            ):
                tracker.events.append((tenant_id, employee_id, method, payload))

        import app.services.call_center.orchestrator as orch_mod

        monkeypatch.setattr(orch_mod, "get_orchestrator", lambda: _Orch())


@pytest.mark.asyncio
async def test_consult_webrtc_offline_target_fails_sync_without_unbridge(monkeypatch):
    """Offline colleague → 400 before any kernel RPC; customer never disturbed."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _route_employee_webrtc(monkeypatch, True)
    _stub_target_snapshot(monkeypatch, {"visible_status": "offline", "resource_state": "unavailable"})

    tel = MockTelephonyClient()
    await tel.connect()

    with pytest.raises(ValidationError, match="不在线"):
        await CallControlService.consult_start(
            tel, tenant_id=7, employee_id=42,
            target_type="employee", target_id=99, number=None,
        )

    # The customer was NOT unbridged/held and no target was originated.
    assert "call.unbridge" not in _recorded_methods(tel)
    assert "call.originate" not in _recorded_methods(tel)


@pytest.mark.asyncio
async def test_precheck_heals_stale_offline_from_db_when_connected(monkeypatch):
    """A ready, still-connected colleague whose Redis presence drifted to
    "offline" is reconciled from the durable DB status and passes the
    pre-check instead of being wrongly rejected as offline."""

    import app.repositories.agent_status_repository as asr_mod

    # Redis view is stale-offline, but the agent's browser socket is live.
    _stub_target_snapshot(
        monkeypatch,
        {"visible_status": "offline", "resource_state": "unavailable"},
        connected=True,
    )
    # The durable record of the agent's chosen status is "ready".
    async def _db_row(_db, _tenant_id, _employee_id):
        return SimpleNamespace(status="ready")

    monkeypatch.setattr(
        asr_mod.AgentStatusRepository, "get_for_employee", staticmethod(_db_row)
    )
    # Healing writes ready back to Redis and returns the fresh snapshot.
    async def _set_visible(_r, _tenant_id, _employee_id, _status):
        return {"visible_status": "ready", "resource_state": "idle"}

    monkeypatch.setattr(
        ccs_module.CcAgentResourceService,
        "set_visible_status",
        staticmethod(_set_visible),
    )
    _install_session(monkeypatch, None, SessionTracker())

    # Must NOT raise: the stale-offline target is reconciled to ready.
    await CallControlService._precheck_webrtc_target_available(
        7, 99, action="转接"
    )


@pytest.mark.asyncio
async def test_transfer_webrtc_busy_target_fails_sync_without_unbridge(monkeypatch):
    """Busy colleague → 400 before any kernel RPC; customer never disturbed."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _route_employee_webrtc(monkeypatch, True)
    _stub_target_snapshot(monkeypatch, {"visible_status": "busy", "resource_state": "in_call"})

    tel = MockTelephonyClient()
    await tel.connect()

    with pytest.raises(ValidationError, match="正在通话"):
        await CallControlService.transfer(
            tel, tenant_id=7, employee_id=42,
            target_type="employee", target_id=99, number=None,
        )

    assert "call.unbridge" not in _recorded_methods(tel)
    assert "call.originate" not in _recorded_methods(tel)


@pytest.mark.asyncio
async def test_consult_webrtc_decline_pushes_failed_result(monkeypatch):
    """Background decline → cc.consult_result {ok:false} to the initiator."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_target_snapshot(monkeypatch, {"visible_status": "ready", "resource_state": "idle"})
    _stub_internal_consult(monkeypatch, error=ValidationError("目标坐席拒接"))
    results = _ControlResultTracker()
    results.install(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.consult_start(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(5):
        await asyncio.sleep(0)

    consult_events = [e for e in results.events if e[2] == "cc.consult_result"]
    assert consult_events, "expected a cc.consult_result push"
    _tenant, initiator, _method, payload = consult_events[-1]
    assert initiator == 42
    assert payload["ok"] is False
    assert payload["kind"] == "consult"
    assert payload["reason"] == "目标坐席拒接"


@pytest.mark.asyncio
async def test_consult_webrtc_accept_pushes_success_result(monkeypatch):
    """Background accept + bridge → cc.consult_result {ok:true} to the initiator."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_target_snapshot(monkeypatch, {"visible_status": "ready", "resource_state": "idle"})
    _stub_internal_consult(
        monkeypatch,
        result={"target_webrtc_call_id": "target-web-2", "offer_id": "offer-1"},
    )
    results = _ControlResultTracker()
    results.install(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.consult_start(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(5):
        await asyncio.sleep(0)

    ok_events = [
        e for e in results.events
        if e[2] == "cc.consult_result" and e[3].get("ok") is True
    ]
    assert ok_events, "expected an ok cc.consult_result push"


@pytest.mark.asyncio
async def test_transfer_webrtc_success_pushes_result_event(monkeypatch):
    """Background handover complete → cc.transfer_result {ok:true} to initiator."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_target_snapshot(monkeypatch, {"visible_status": "ready", "resource_state": "idle"})
    _stub_internal_consult(
        monkeypatch,
        result={"target_webrtc_call_id": "target-web-2", "offer_id": "offer-1"},
    )
    _ResourceTracker().install(monkeypatch)
    results = _ControlResultTracker()
    results.install(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(5):
        await asyncio.sleep(0)

    ok_events = [
        e for e in results.events
        if e[2] == "cc.transfer_result" and e[3].get("ok") is True
    ]
    assert ok_events, "expected an ok cc.transfer_result push"


@pytest.mark.asyncio
async def test_transfer_webrtc_decline_pushes_failed_result(monkeypatch):
    """Background ring failure → cc.transfer_result {ok:false}; customer kept."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_target_snapshot(monkeypatch, {"visible_status": "ready", "resource_state": "idle"})
    _stub_internal_consult(monkeypatch, error=ValidationError("目标坐席未接听"))
    results = _ControlResultTracker()
    results.install(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(5):
        await asyncio.sleep(0)

    fail_events = [
        e for e in results.events
        if e[2] == "cc.transfer_result" and e[3].get("ok") is False
    ]
    assert fail_events, "expected a failed cc.transfer_result push"
    assert fail_events[-1][3]["reason"] == "目标坐席未接听"
    # Customer never bridged to a target / never hung up.
    assert ("call.hangup", {"call_id": "sip-customer", "reason": None}) not in tel.recorded


@pytest.mark.asyncio
async def test_transfer_webrtc_employee_rekeys_target_and_releases_initiator(monkeypatch):
    """Blind transfer to a browser-ring colleague re-keys them onto the customer.

    After handover the colleague owns the customer call, so their resource is
    marked in_call on the CUSTOMER call_id (not the internal leg) — this is what
    lets the customer's own hangup finalize them without
    `Call resource belongs to another call`. The initiator's own leg is dropped.
    """

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, True)
    _stub_internal_consult(
        monkeypatch,
        result={"target_webrtc_call_id": "target-web-2", "offer_id": "offer-1"},
    )
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(5):
        await asyncio.sleep(0)

    # Colleague 99's resource re-keyed onto the customer call.
    assert (7, 99, "sip-customer") in tracker.rekeyed
    # The transfer target keeps the (now customer) call. The initiator may use
    # force_release as a fallback if its after-call-work transition fails.
    assert not any(employee_id == 99 for _, employee_id, _ in tracker.force_released)
    # Customer bridged to the colleague; initiator's own leg dropped.
    assert _has_bridge(tel, "sip-customer", "target-web-2", keepalive=True)
    assert ("call.hangup", {"call_id": "webrtc-1", "reason": "transferred"}) in tel.recorded


@pytest.mark.asyncio
async def test_conference_participant_departed_collapses_host(monkeypatch):
    """When a conference participant's leg ends, the host is told to collapse
    and their in-call legs are cleaned; a Web-phone colleague is released."""
    import fakeredis.aioredis
    import app.services.call_center.orchestrator as orch_mod

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: r)
    orch = _fake_orchestrator(monkeypatch)
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)
    _install_session(monkeypatch, _active_row(), SessionTracker())

    await ccs_module._register_conference_participant(7, 42, "party-leg")
    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        room_id="room-1",
        room_legs=["sip-customer", "webrtc-1", "party-leg"],
        conference_participant_call_id="party-leg",
        conference_target_employee_id=99,
    )

    await CallControlService.on_conference_participant_departed("party-leg")

    legs = await ccs_module._legs(7, 42)
    assert legs.conference_participant_call_id is None
    assert legs.conference_target_employee_id is None
    assert "party-leg" not in legs.room_legs
    assert (7, 42) in orch.participant_left
    assert await r.get(ccs_module._conf_host_key("party-leg")) is None
    assert (7, 99, "conference_participant_departed") in tracker.force_released


@pytest.mark.asyncio
async def test_conference_participant_departed_ignores_unknown_leg(monkeypatch):
    """A hangup for a non-participant leg is a harmless no-op (no notify)."""
    import fakeredis.aioredis
    import app.services.call_center.orchestrator as orch_mod

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: r)
    orch = _fake_orchestrator(monkeypatch)

    await CallControlService.on_conference_participant_departed("some-customer-leg")

    assert orch.participant_left == []


@pytest.mark.asyncio
async def test_transfer_reassigns_call_record_to_target(monkeypatch):
    """After a successful transfer the CDR is re-pointed to the target agent, so
    the initiator's hangup can't target/kill the customer and the customer's
    hangup notifies the target (who otherwise stays stuck "通话中")."""
    row = SimpleNamespace(
        last_serving_agent_id=36,
        tenant_id=8,
        call_id="cust-1",
        root_call_id="cust-1",
    )
    committed: list[bool] = []

    class _Db:
        async def execute(self, _q):
            return _Result(row)

        async def commit(self):
            committed.append(True)

    class _Sess:
        async def __aenter__(self):
            return _Db()

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr(ccs_module, "AsyncSessionLocal", lambda: _Sess())

    await CallControlService._reassign_call_record_to_agent(8, "cust-1", 37)

    assert row.last_serving_agent_id == 37
    assert committed == [True]
