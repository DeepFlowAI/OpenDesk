"""Unit tests for three-party conference ownership / resource cleanup fixes."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import fakeredis.aioredis
import pytest

from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
from app.services.call_center import call_control_service as ccs_module
from app.services.call_center.call_control_service import CallControlService
from app.services.cc_agent_status_service import CcAgentStatusService


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

    async def commit(self):
        return None


class _FakeSession:
    def __init__(self, row, tracker: SessionTracker):
        self.row = row
        self.tracker = tracker

    async def __aenter__(self):
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
        agent_id=42,
        state="in_progress",
        started_at=None,
        root_call_id="sip-customer",
        call_id="sip-customer",
        from_number="10086",
        to_number="400",
        user_id=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


async def _webrtc_active(_db, _tenant_id, _employee_id):
    return {"webrtc_call_id": "webrtc-1"}


def _fake_orchestrator(monkeypatch):
    class _Orch:
        def __init__(self):
            self.waiters: dict[str, asyncio.Future] = {}
            self.ended: list[tuple] = []
            self.republished: list[tuple] = []
            self.participant_left: list[tuple] = []
            self.control_results: list[tuple] = []
            self._workflows: dict = {}

        def register_leg_wait(self, call_id):
            fut = asyncio.get_event_loop().create_future()
            self.waiters[call_id] = fut
            return fut

        def cancel_leg_wait(self, call_id):
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

        async def notify_conference_participant_left(self, *, tenant_id, employee_id):
            self.participant_left.append((tenant_id, employee_id))

        async def republish_agent_call_ui(self, *, tenant_id, employee_id):
            self.republished.append((tenant_id, employee_id))

    orch = _Orch()
    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "get_orchestrator", lambda: orch)
    return orch


def _seed_workflow(orch, *, call_id: str, employee_id: int, tenant_id: int = 7):
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


class _ResourceTracker:
    def __init__(self):
        self.force_released: list[tuple[int, int, str]] = []
        self.marked_in_call: list[tuple[int, int, str]] = []
        self.after_call_work: list[tuple[int, int, str, str]] = []

    def install(self, monkeypatch):
        async def _force_release(_r, tenant_id, employee_id, *, reason):
            self.force_released.append((tenant_id, employee_id, reason))
            return {"resource_state": "idle", "visible_status": "ready"}

        async def _mark_in_call(_r, tenant_id, employee_id, *, call_id, direction, **_kw):
            self.marked_in_call.append((tenant_id, employee_id, call_id))
            return {"resource_state": "in_call"}

        async def _acw(_r, tenant_id, employee_id, *, call_id, reason):
            self.after_call_work.append((tenant_id, employee_id, call_id, reason))
            return {"resource_state": "after_call_work"}

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
            "mark_after_call_work",
            staticmethod(_acw),
        )


def _stub_asr(monkeypatch, enabled: bool = True):
    async def _asr(_tid):
        return enabled

    monkeypatch.setattr(
        "app.services.system_settings_service.SystemSettingsService"
        ".is_bridge_asr_enabled_managed",
        staticmethod(_asr),
    )


def _stub_pg_sync(monkeypatch, sink: list):
    async def _sync(_db, tenant_id, employee_id, status, reason):
        sink.append((tenant_id, employee_id, status))
        return {"employee_id": employee_id, "status": status}

    monkeypatch.setattr(CcAgentStatusService, "sync_pg_status", staticmethod(_sync))


def _seed_conference_legs(
    *,
    colleague_id: int | None = 99,
    participant_leg: str = "colleague-leg",
):
    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        agent_media_call_id="webrtc-1",
        room_id="room-9",
        room_legs=["sip-customer", "webrtc-1", participant_leg],
        conference_participant_call_id=participant_leg,
        conference_target_employee_id=colleague_id,
    )


@pytest.mark.asyncio
async def test_conference_leave_hands_over_to_colleague(monkeypatch):
    """Host leaves; colleague keeps talking and becomes the owning agent."""

    row = _active_row()
    _install_session(monkeypatch, row, SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _stub_asr(monkeypatch)
    pg_sync: list = []
    _stub_pg_sync(monkeypatch, pg_sync)

    import app.services.call_center.orchestrator as orch_mod

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: r)
    orch = _fake_orchestrator(monkeypatch)
    wf = _seed_workflow(orch, call_id="sip-customer", employee_id=42)
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)

    reassigned: list[tuple] = []

    async def _reassign(tenant_id, customer_call_id, new_agent_id):
        reassigned.append((tenant_id, customer_call_id, new_agent_id))
        row.agent_id = new_agent_id

    monkeypatch.setattr(
        CallControlService, "_reassign_call_record_to_agent", staticmethod(_reassign)
    )

    await ccs_module._register_conference_participant(7, 42, "colleague-leg")
    _seed_conference_legs()

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.conference_leave(tel, tenant_id=7, employee_id=42)

    hangups = {d["call_id"] for m, d in tel.recorded if m == "call.hangup"}
    assert hangups == {"webrtc-1"}
    assert "colleague-leg" not in hangups
    assert tracker.force_released == []
    assert (
        "call.bridge",
        {"call_id": "sip-customer", "other_call_id": "colleague-leg", "transcribe": True},
    ) in tel.recorded
    assert reassigned == [(7, "sip-customer", 99)]
    assert wf.bridged_agent_info()["employee_id"] == 99
    colleague_legs = await ccs_module._legs(7, 99)
    assert colleague_legs.agent_media_call_id == "colleague-leg"
    assert (7, 99, "sip-customer") in tracker.marked_in_call
    assert (7, 99) in orch.republished
    assert (7, 42, "sip-customer", "left_conference") in tracker.after_call_work
    assert (7, 42, "after_call_work") in pg_sync
    assert (7, 42) not in ccs_module._in_call_state
    assert any(
        e[1] == 42 and e[2] == "sip-customer" and e[3] == "left_conference"
        for e in orch.ended
    )
    assert await r.get(ccs_module._conf_host_key("colleague-leg")) is None


@pytest.mark.asyncio
async def test_conference_leave_external_skips_ownership(monkeypatch):
    """External participant stays up; host wraps up; no colleague reassignment."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _stub_asr(monkeypatch)
    _stub_pg_sync(monkeypatch, [])

    import app.services.call_center.orchestrator as orch_mod

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: r)
    orch = _fake_orchestrator(monkeypatch)
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)

    reassigned: list = []

    async def _reassign(*_a, **_kw):
        reassigned.append(True)

    monkeypatch.setattr(
        CallControlService, "_reassign_call_record_to_agent", staticmethod(_reassign)
    )

    await ccs_module._register_conference_participant(7, 42, "party-1")
    _seed_conference_legs(colleague_id=None, participant_leg="party-1")

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.conference_leave(tel, tenant_id=7, employee_id=42)

    assert not any(
        d["call_id"] == "party-1" for m, d in tel.recorded if m == "call.hangup"
    )
    assert reassigned == []
    assert tracker.marked_in_call == []
    assert orch.republished == []
    assert (7, 42, "sip-customer", "left_conference") in tracker.after_call_work
    assert await r.get(ccs_module._conf_host_key("party-1")) is None


@pytest.mark.asyncio
async def test_conference_leave_rebridge_failure_still_hands_over(monkeypatch):
    """Re-bridge failure must not drop the customer or skip ownership handover."""

    row = _active_row()
    _install_session(monkeypatch, row, SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)
    _stub_asr(monkeypatch)
    _stub_pg_sync(monkeypatch, [])

    import app.services.call_center.orchestrator as orch_mod

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: r)
    orch = _fake_orchestrator(monkeypatch)
    _seed_workflow(orch, call_id="sip-customer", employee_id=42)
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)

    reassigned: list = []

    async def _reassign(tenant_id, customer_call_id, new_agent_id):
        reassigned.append((tenant_id, customer_call_id, new_agent_id))

    monkeypatch.setattr(
        CallControlService, "_reassign_call_record_to_agent", staticmethod(_reassign)
    )

    await ccs_module._register_conference_participant(7, 42, "colleague-leg")
    _seed_conference_legs()

    tel = MockTelephonyClient()
    tel.bridge_error = RuntimeError("bridge failed")
    await tel.connect()

    await CallControlService.conference_leave(tel, tenant_id=7, employee_id=42)

    hangups = {d["call_id"] for m, d in tel.recorded if m == "call.hangup"}
    assert "sip-customer" not in hangups
    assert "colleague-leg" not in hangups
    assert reassigned == [(7, "sip-customer", 99)]
    assert tracker.force_released == []
    assert (7, 99) in orch.republished
    assert (7, 42, "sip-customer", "left_conference") in tracker.after_call_work


@pytest.mark.asyncio
async def test_conference_remove_releases_colleague(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    import app.services.call_center.orchestrator as orch_mod

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: r)
    orch = _fake_orchestrator(monkeypatch)
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)

    await ccs_module._register_conference_participant(7, 42, "colleague-leg")
    _seed_conference_legs()

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService.conference_remove(tel, tenant_id=7, employee_id=42)

    assert (
        "call.hangup",
        {"call_id": "colleague-leg", "reason": "participant_removed"},
    ) in tel.recorded
    assert (7, 99, "conference_removed") in tracker.force_released
    assert any(
        e[1] == 99 and e[2] == "colleague-leg" and e[3] == "conference_removed"
        for e in orch.ended
    )
    legs = await ccs_module._legs(7, 42)
    assert legs.conference_participant_call_id is None
    assert legs.conference_target_employee_id is None
    assert await r.get(ccs_module._conf_host_key("colleague-leg")) is None


@pytest.mark.asyncio
async def test_participant_departed_releases_colleague(monkeypatch):
    import app.services.call_center.orchestrator as orch_mod

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: r)
    _fake_orchestrator(monkeypatch)
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)
    _install_session(monkeypatch, _active_row(), SessionTracker())

    await ccs_module._register_conference_participant(7, 42, "colleague-leg")
    _seed_conference_legs()

    await CallControlService.on_conference_participant_departed("colleague-leg")

    assert (7, 99, "conference_participant_departed") in tracker.force_released


@pytest.mark.asyncio
async def test_participant_departed_unknown_leg_is_noop(monkeypatch):
    import app.services.call_center.orchestrator as orch_mod

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: r)
    orch = _fake_orchestrator(monkeypatch)
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)

    await CallControlService.on_conference_participant_departed("never-tracked")

    assert tracker.force_released == []
    assert orch.participant_left == []


@pytest.mark.asyncio
async def test_customer_hangup_releases_conference_colleague(monkeypatch):
    import app.libs.telephony as tel_lib

    _install_session(monkeypatch, _active_row(), SessionTracker())
    orch = _fake_orchestrator(monkeypatch)
    tracker = _ResourceTracker()
    tracker.install(monkeypatch)

    import app.services.call_center.orchestrator as orch_mod

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: r)

    await ccs_module._register_conference_participant(7, 42, "colleague-leg")
    _seed_conference_legs()

    tel = MockTelephonyClient()
    await tel.connect()
    monkeypatch.setattr(tel_lib, "get_telephony_client", lambda: tel)

    ok = await CallControlService.cleanup_conference_for_host(
        7, 42, reason="caller_hangup",
    )

    assert ok is True
    assert (
        "call.hangup",
        {"call_id": "colleague-leg", "reason": "caller_hangup"},
    ) in tel.recorded
    assert (7, 99, "caller_hangup") in tracker.force_released
    assert any(e[1] == 99 and e[2] == "colleague-leg" for e in orch.ended)
    assert await r.get(ccs_module._conf_host_key("colleague-leg")) is None


@pytest.mark.asyncio
async def test_manual_merge_registers_participant_index(monkeypatch):
    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    async def _noop_play(_telephony, **_kw):
        return None

    monkeypatch.setattr(CallControlService, "_play_scene_tone", _noop_play)

    import app.services.call_center.orchestrator as orch_mod

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: r)

    ccs_module._in_call_state[(7, 42)] = ccs_module.InCallLegs(
        conference_participant_call_id="party-1"
    )

    tel = MockTelephonyClient()
    tel.room_create_response = {"room_id": "room-9", "legs": []}
    await tel.connect()

    await CallControlService.conference_merge(tel, tenant_id=7, employee_id=42)

    assert await r.get(ccs_module._conf_host_key("party-1")) == "7:42"


@pytest.mark.asyncio
async def test_conference_invite_defers_tone_playback(monkeypatch):
    """HTTP response returns before waiting-tone playback starts."""

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    play_started = asyncio.Event()
    play_gate = asyncio.Event()
    play_order: list[str] = []

    async def _slow_play(_telephony, **_kw):
        play_order.append("tone_start")
        play_started.set()
        await play_gate.wait()
        play_order.append("tone_done")

    monkeypatch.setattr(CallControlService, "_play_scene_tone", _slow_play)

    async def _resolve(_tenant_id, _tt, _tid, number):
        return (
            {"uri": number, "caller_id": "1000", "trunk_id": "t1"},
            f"external:{number}",
        )

    monkeypatch.setattr(CallControlService, "_resolve_target_originate", _resolve)
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "party-1"}
    await tel.connect()

    result = await CallControlService.conference_add(
        tel,
        tenant_id=7,
        employee_id=42,
        target_type="external",
        target_id=None,
        number="13800138000",
    )

    assert result["note"] == "ringing_participant"
    assert "tone_start" not in play_order
    assert (
        "call.unbridge",
        {"call_id": "sip-customer", "other_call_id": "webrtc-1"},
    ) in tel.recorded

    await asyncio.wait_for(play_started.wait(), timeout=1.0)
    assert play_order == ["tone_start"]
    play_gate.set()
    for _ in range(5):
        await asyncio.sleep(0)
    assert "tone_done" in play_order

    # Clean up the background waiter so it doesn't leak into other tests.
    if "party-1" in orch.waiters:
        orch.waiters["party-1"].set_result({"answered": False, "reason": "declined"})
        for _ in range(5):
            await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_conference_invite_cancels_tone_before_fast_answer(monkeypatch):
    """Fast answer must cancel a still-pending invite tone before stop/merge.

    Otherwise a late call_play (after tone settings / object-storage work)
    can land after call_stop and leave the customer hearing a looping tone
    for the rest of the conference.
    """

    _install_session(monkeypatch, _active_row(), SessionTracker())
    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _webrtc_active)

    play_entered = asyncio.Event()
    play_gate = asyncio.Event()
    play_calls: list[str] = []

    async def _slow_play(telephony, *, tenant_id, customer_call_id, scene):
        play_entered.set()
        await play_gate.wait()
        play_calls.append("play")
        await telephony.call_play(
            customer_call_id, text="waiting", audio_url=None, loop=True
        )

    monkeypatch.setattr(CallControlService, "_play_scene_tone", _slow_play)

    async def _resolve(_tenant_id, _tt, _tid, number):
        return (
            {"uri": number, "caller_id": "1000", "trunk_id": "t1"},
            f"external:{number}",
        )

    monkeypatch.setattr(CallControlService, "_resolve_target_originate", _resolve)
    orch = _fake_orchestrator(monkeypatch)

    tel = MockTelephonyClient()
    tel.originate_response = {"call_id": "party-1"}
    tel.room_create_response = {
        "room_id": "room-9",
        "legs": ["sip-customer", "webrtc-1", "party-1"],
    }
    await tel.connect()

    result = await CallControlService.conference_add(
        tel,
        tenant_id=7,
        employee_id=42,
        target_type="external",
        target_id=None,
        number="13800138000",
    )
    assert result["note"] == "ringing_participant"
    await asyncio.wait_for(play_entered.wait(), timeout=1.0)

    # Participant answers while tone setup is still gated (before call_play).
    assert "party-1" in orch.waiters
    orch.waiters["party-1"].set_result({"answered": True, "reason": None})
    for _ in range(20):
        await asyncio.sleep(0)
        if any(m == "call.stop" for m, _ in tel.recorded):
            break

    stop_idxs = [i for i, (m, _) in enumerate(tel.recorded) if m == "call.stop"]
    assert stop_idxs, "expected tone stop on answer/merge"
    first_stop = stop_idxs[0]

    # Releasing the gate after stop must not produce a late call_play.
    play_gate.set()
    for _ in range(10):
        await asyncio.sleep(0)

    play_idxs = [i for i, (m, _) in enumerate(tel.recorded) if m == "call.play"]
    assert play_calls == []
    assert not any(i > first_stop for i in play_idxs)
    assert any(
        m == "room.create" for m, _ in tel.recorded
    ), "fast answer should still merge the room"
