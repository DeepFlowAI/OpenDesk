"""
Ownership tracking for blind transfer: bridged-agent routing and Redis in_call.

Covers the two gaps left on the SIP / external transfer paths:
  - external handover must clear sys._bridged_agent_id (no agent owns the call);
  - queue enqueue must leave the bridged agent alone for the later handover rebind;
  - SIP desk-phone target must be marked in_call on the customer call id;
  - Redis failures on that mark must not undo a completed SIP handover;
  - Web-phone transfer still re-keys exactly once via the existing helper.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
from app.services.call_center import call_control_service as ccs_module
from app.services.call_center.call_control_service import CallControlService


@pytest.fixture(autouse=True)
def _clean_in_call_state():
    ccs_module._in_call_state.clear()
    yield
    ccs_module._in_call_state.clear()


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


async def _webrtc_active(_db, _tenant_id, _employee_id):
    return {"webrtc_call_id": "webrtc-1"}


def _bypass_tone(monkeypatch):
    async def _noop_play(_telephony, **_kw):
        return None

    monkeypatch.setattr(CallControlService, "_play_scene_tone", _noop_play)


def _stub_external_target(monkeypatch):
    async def _resolve(_tenant_id, _tt, _tid, number):
        return (
            {"uri": number, "caller_id": "1000", "trunk_id": "t1"},
            f"external:{number}",
        )

    monkeypatch.setattr(CallControlService, "_resolve_target_originate", _resolve)


def _route_employee_webrtc(monkeypatch, is_webrtc: bool):
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


def _fake_orchestrator(monkeypatch):
    class _Orch:
        def __init__(self):
            self.waiters: dict[str, asyncio.Future] = {}
            self.cancelled: list[str] = []
            self.control_results: list[tuple] = []
            self.ended: list[tuple] = []
            self.republished: list[tuple] = []
            self._workflows: dict = {}

        def register_leg_wait(self, call_id):
            fut = asyncio.get_event_loop().create_future()
            self.waiters[call_id] = fut
            return fut

        def cancel_leg_wait(self, call_id):
            self.cancelled.append(call_id)
            self.waiters.pop(call_id, None)

        def active_workflow(self, call_id):
            return self._workflows.get(call_id)

        async def notify_agent_control_result(
            self, *, tenant_id, employee_id, method, payload
        ):
            self.control_results.append((tenant_id, employee_id, method, payload))

        async def notify_agent_call_ended(
            self, *, tenant_id, employee_id, call_id, reason
        ):
            self.ended.append((tenant_id, employee_id, call_id, reason))

        async def republish_agent_call_ui(self, *, tenant_id, employee_id):
            self.republished.append((tenant_id, employee_id))

    orch = _Orch()
    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "get_orchestrator", lambda: orch)
    return orch


def _seed_bridged_workflow(orch, *, call_id: str, employee_id: int, tenant_id: int = 7):
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


def _stub_internal_consult(monkeypatch, *, result=None, error=None):
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
    def __init__(self):
        self.force_released: list[tuple[int, int, str]] = []
        self.marked_in_call: list[tuple] = []
        self.reserved: list[tuple] = []

    def install(self, monkeypatch, *, mark_error: Exception | None = None):
        async def _force_release(_r, tenant_id, employee_id, *, reason):
            self.force_released.append((tenant_id, employee_id, reason))
            return {"resource_state": "idle"}

        async def _mark_in_call(
            _r, tenant_id, employee_id, *, call_id, direction, offer_id=None, **_kw
        ):
            if mark_error is not None:
                raise mark_error
            self.marked_in_call.append(
                (tenant_id, employee_id, call_id, direction, offer_id)
            )
            return {"resource_state": "in_call", "current_call_id": call_id}

        async def _reserve_inbound(
            _r, tenant_id, employee_id, *, call_id, offer_id, queue_id=None, **_kw
        ):
            self.reserved.append(
                (tenant_id, employee_id, call_id, offer_id, queue_id)
            )
            return {
                "resource_state": "reserved",
                "current_call_id": call_id,
                "offer_id": offer_id,
            }

        async def _get_snapshot(_r, _tenant_id, _employee_id):
            return {"visible_status": "ready", "resource_state": "idle"}

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
            "reserve_inbound",
            staticmethod(_reserve_inbound),
        )
        monkeypatch.setattr(
            ccs_module.CcAgentResourceService,
            "get_snapshot",
            staticmethod(_get_snapshot),
        )


# ───────────────────────── Fix 1: bridged agent ─────────────────────────


@pytest.mark.asyncio
async def test_transfer_external_clears_bridged_agent(monkeypatch):
    """External blind transfer must stop routing transcript to the initiator."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _stub_external_target(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)
    wf = _seed_bridged_workflow(orch, call_id="sip-customer", employee_id=42)

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

    assert wf.bridged_agent_info() is None
    assert "sys._bridged_agent_id" not in wf.ctx.variables


@pytest.mark.asyncio
async def test_transfer_to_queue_leaves_bridged_agent_at_enqueue(monkeypatch):
    """Queue transfer must not clear bridged agent before a queue agent answers."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)
    wf = _seed_bridged_workflow(orch, call_id="sip-customer", employee_id=42)

    async def _validate(*_a, **_k):
        return None

    async def _bind_queue(_db, _tenant_id, _call_id, _queue_type, _queue_id):
        return None

    async def _noop_wait(*_a, **_k):
        await asyncio.sleep(0)

    monkeypatch.setattr(
        CallControlService, "_validate_queue_transfer_target", _validate
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.bind_queue",
        _bind_queue,
    )
    monkeypatch.setattr(
        CallControlService, "_run_queue_transfer_wait", _noop_wait
    )

    # Avoid Redis status transitions in finalize so this test stays focused.
    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: None)

    # transfer_to_queue registers the wait task on the real orchestrator helper.
    orch.set_pending_queue_transfer = lambda *_a, **_k: None

    tel = MockTelephonyClient()
    await tel.connect()

    result = await CallControlService.transfer_to_queue(
        tel, tenant_id=7, employee_id=42, queue_id=5
    )

    assert result["note"] == "queued_target"
    # Still the initiator — later queue handover rebinds when someone answers.
    assert wf.bridged_agent_info() == {"tenant_id": 7, "employee_id": 42}


# ───────────────────────── Fix 2: SIP in_call ─────────────────────────


@pytest.mark.asyncio
async def test_transfer_sip_employee_marks_target_in_call(monkeypatch):
    """SIP desk-phone transfer must occupy the target on the customer call."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, False)
    orch = _fake_orchestrator(monkeypatch)
    _seed_bridged_workflow(orch, call_id="sip-customer", employee_id=42)

    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: object())
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)

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

    assert len(tracker.reserved) == 1
    r_tenant, r_emp, r_call, r_offer, r_queue = tracker.reserved[0]
    assert (r_tenant, r_emp, r_call, r_queue) == (7, 99, "sip-customer", None)
    assert r_offer  # fresh offer id for the reserve → mark_in_call pair

    assert len(tracker.marked_in_call) == 1
    m_tenant, m_emp, m_call, m_dir, m_offer = tracker.marked_in_call[0]
    assert (m_tenant, m_emp, m_call, m_dir) == (7, 99, "sip-customer", "inbound")
    assert m_offer == r_offer
    assert orch.republished == [(7, 99)]


@pytest.mark.asyncio
async def test_transfer_sip_employee_mark_in_call_failure_is_non_fatal(monkeypatch):
    """Redis mark_in_call failure must not undo a completed SIP handover."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, False)
    orch = _fake_orchestrator(monkeypatch)
    wf = _seed_bridged_workflow(orch, call_id="sip-customer", employee_id=42)

    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: object())
    tracker = _ResourceTracker()
    tracker.install(monkeypatch, mark_error=RuntimeError("redis down"))

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
    assert any(
        method == "cc.transfer_result"
        and employee_id == 42
        and payload.get("ok") is True
        for _tenant_id, employee_id, method, payload in orch.control_results
    )
    assert ("call.hangup", {"call_id": "webrtc-1", "reason": "transferred"}) in tel.recorded
    assert orch.republished == [(7, 99)]


@pytest.mark.asyncio
async def test_transfer_webrtc_employee_rekeys_exactly_once(monkeypatch):
    """Web-phone blind transfer still re-keys the target onto the customer once."""

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

    # Track only rekey (WebRTC path does not go through SIP reserve helper).
    rekeyed: list[tuple] = []

    async def _rekey_current_call(_r, tenant_id, employee_id, *, call_id):
        rekeyed.append((tenant_id, employee_id, call_id))
        return {"resource_state": "in_call", "current_call_id": call_id}

    monkeypatch.setattr(
        ccs_module.CcAgentResourceService,
        "rekey_current_call",
        staticmethod(_rekey_current_call),
    )

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(5):
        await asyncio.sleep(0)

    assert rekeyed == [(7, 99, "sip-customer")]


# ───────────────────────── Fix: wrap-up busy + legs ─────────────────────────


def _track_wrapup(monkeypatch):
    """Stub ACW / set_busy / clear_legs and return call trackers."""

    busy_flips: list[tuple] = []
    cleared: list[tuple[int, int]] = []

    async def _sync_pg(_db, tenant_id, employee_id, status, reason):
        return {
            "employee_id": employee_id,
            "status": status,
            "reason": reason,
        }

    async def _set_busy(_db, tenant_id, employee_id, busy):
        busy_flips.append((tenant_id, employee_id, busy))
        return {"state": "online_idle" if not busy else "busy"}

    async def _mark_acw(*_a, **_k):
        return {"resource_state": "after_call_work"}

    async def _clear(tenant_id, employee_id):
        cleared.append((tenant_id, employee_id))

    monkeypatch.setattr(
        "app.services.cc_agent_status_service.CcAgentStatusService.sync_pg_status",
        _sync_pg,
    )
    monkeypatch.setattr(AgentWebRTCSessionService, "set_busy", _set_busy)
    monkeypatch.setattr(
        ccs_module.CcAgentResourceService,
        "mark_after_call_work",
        staticmethod(_mark_acw),
    )
    monkeypatch.setattr(ccs_module, "_clear_legs", _clear)
    return busy_flips, cleared


def _seed_initiator_legs(*, room_id: str = "stale-room"):
    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        agent_media_call_id="webrtc-1",
        room_id=room_id,
        consult_call_id="consult-stale",
    )
    # Target must keep its own legs if present — clearing initiator is keyed.
    ccs_module._in_call_state[(7, 99)] = ccs_module.InCallLegs(
        agent_media_call_id="target-leg",
        room_id="target-room",
    )


@pytest.mark.asyncio
async def test_transfer_external_clears_initiator_busy_and_legs(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _stub_external_target(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)
    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: object())
    busy_flips, cleared = _track_wrapup(monkeypatch)
    _seed_initiator_legs()

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "target-1"}
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="external", target_id=None, number="13800138000",
    )
    orch.waiters["target-1"].set_result({"answered": True})
    for _ in range(5):
        await asyncio.sleep(0)

    assert busy_flips == [(7, 42, False)]
    assert cleared == [(7, 42)]
    # Target's legs untouched (clear is per-employee; we stubbed clear so
    # verify only initiator was requested).
    assert (7, 99) not in cleared
    hangups = [
        p for m, p in tel.recorded
        if m == "call.hangup" and p.get("call_id") == "webrtc-1"
    ]
    assert hangups == [{"call_id": "webrtc-1", "reason": "transferred"}]


@pytest.mark.asyncio
async def test_transfer_sip_employee_clears_initiator_busy_and_legs(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    _route_employee_webrtc(monkeypatch, False)
    orch = _fake_orchestrator(monkeypatch)
    _seed_bridged_workflow(orch, call_id="sip-customer", employee_id=42)

    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: object())
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)
    busy_flips, cleared = _track_wrapup(monkeypatch)
    _seed_initiator_legs()

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
    for _ in range(5):
        await asyncio.sleep(0)

    assert busy_flips == [(7, 42, False)]
    assert cleared == [(7, 42)]
    hangups = [
        p for m, p in tel.recorded
        if m == "call.hangup" and p.get("call_id") == "webrtc-1"
    ]
    assert hangups == [{"call_id": "webrtc-1", "reason": "transferred"}]


@pytest.mark.asyncio
async def test_transfer_webrtc_employee_clears_initiator_busy_and_legs(monkeypatch):
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
    busy_flips, cleared = _track_wrapup(monkeypatch)
    _seed_initiator_legs()

    async def _mark_in_call(*_a, **_k):
        return {"resource_state": "in_call"}

    monkeypatch.setattr(
        ccs_module.CcAgentResourceService,
        "mark_in_call",
        staticmethod(_mark_in_call),
    )

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.transfer(
        tel, tenant_id=7, employee_id=42,
        target_type="employee", target_id=99, number=None,
    )
    for _ in range(5):
        await asyncio.sleep(0)

    assert busy_flips == [(7, 42, False)]
    assert cleared == [(7, 42)]
    hangups = [
        p for m, p in tel.recorded
        if m == "call.hangup" and p.get("call_id") == "webrtc-1"
    ]
    assert hangups == [{"call_id": "webrtc-1", "reason": "transferred"}]


@pytest.mark.asyncio
async def test_transfer_to_queue_clears_initiator_busy_and_legs(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _bypass_tone(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)
    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: object())
    busy_flips, cleared = _track_wrapup(monkeypatch)
    _seed_initiator_legs()

    async def _validate(*_a, **_k):
        return None

    async def _bind_queue(_db, _tenant_id, _call_id, _queue_type, _queue_id):
        return None

    async def _noop_wait(*_a, **_k):
        await asyncio.sleep(0)

    monkeypatch.setattr(
        CallControlService, "_validate_queue_transfer_target", _validate
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.bind_queue",
        _bind_queue,
    )
    monkeypatch.setattr(
        CallControlService, "_run_queue_transfer_wait", _noop_wait
    )
    orch.set_pending_queue_transfer = lambda *_a, **_k: None

    tel = MockTelephonyClient()
    await tel.connect()

    result = await CallControlService.transfer_to_queue(
        tel, tenant_id=7, employee_id=42, queue_id=5
    )

    assert result["note"] == "queued_target"
    assert busy_flips == [(7, 42, False)]
    assert cleared == [(7, 42)]
    hangups = [
        p for m, p in tel.recorded
        if m == "call.hangup" and p.get("call_id") == "webrtc-1"
    ]
    # Queue path hangs up once in transfer_to_queue (not via shared finalize).
    assert hangups == [{"call_id": "webrtc-1", "reason": "transferred"}]
