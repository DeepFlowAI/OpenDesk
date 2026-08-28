"""Unit tests for supervisor call-intervention (reports extension).

Covers the pure helpers (number masking, talk duration), the in-process monitor
lock, and the intervention service gate chain / mode outcomes with the
DB-touching helpers stubbed so no database or Redis is required. Telephony is a
mock; we assert both the control-plane RPCs and the operation-trail writes.
"""
import importlib
from unittest.mock import AsyncMock

import pytest

import app.extensions  # noqa: F401 — triggers private overlay path injection

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotImplementedApiError,
    ValidationError,
)
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.schemas.permission import EffectivePrincipal

active_calls = importlib.import_module("app.extensions.reports.lib.active_calls")
intervention_state = importlib.import_module("app.extensions.reports.lib.intervention_state")
svc_mod = importlib.import_module("app.extensions.reports.services.call_intervention_service")
CallInterventionService = svc_mod.CallInterventionService
call_control = importlib.import_module("app.services.call_center.call_control_service")

ALL_PERMS = [
    "call.monitor.view",
    "call.monitor.listen",
    "call.monitor.whisper",
    "call.monitor.barge",
    "call.monitor.takeover",
    "call.monitor.force_hangup",
    "call.workspace.use",
]


@pytest.mark.asyncio
async def test_intervention_trail_writes_structured_trajectory(monkeypatch):
    append = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_trajectory_service.CallTrajectoryService.append_for_call_id",
        append,
    )

    await intervention_state.append_trail_event(
        AsyncMock(),
        1,
        "call-1",
        {
            "supervisor_id": 10,
            "mode": "takeover",
            "event": "succeeded",
            "reason": "quality_risk",
        },
    )

    payload = append.await_args.kwargs
    assert payload["event_type"] == "supervisor_takeover_completed"
    assert payload["event_category"] == "supervisor"
    assert payload["actor_type"] == "supervisor"
    assert payload["reason_code"] == "quality_risk"


@pytest.fixture(autouse=True)
def clear_call_control_room_state():
    call_control._in_call_state.clear()
    yield
    call_control._in_call_state.clear()


def _principal(user_id=10, tenant_id=1, permissions=None, scope="all"):
    return EffectivePrincipal(
        user_id=user_id,
        tenant_id=tenant_id,
        permissions=permissions if permissions is not None else list(ALL_PERMS),
        data_scopes={"call_record": scope},
    )


# ───────────────────────── pure helpers ─────────────────────────


class TestActiveCallHelpers:
    def test_customer_number_inbound_is_from(self):
        assert active_calls.customer_number("inbound", "13800138000", "1001") == "13800138000"

    def test_customer_number_outbound_is_to(self):
        assert active_calls.customer_number("outbound", "1001", "13800138000") == "13800138000"

    def test_mask_number_keeps_head_and_tail(self):
        assert active_calls.mask_number("13800138000") == "138****8000"

    def test_mask_number_none_is_dash(self):
        assert active_calls.mask_number(None) == "—"

    def test_mask_number_short_extension(self):
        assert active_calls.mask_number("1001") == "1***"

    def test_talk_duration_zero_before_answer(self):
        assert active_calls.talk_duration_seconds(None) == 0


# ───────────────────────── in-process lock ─────────────────────────


@pytest.mark.asyncio
class TestMonitorLock:
    async def test_acquire_and_holder(self):
        intervention_state._local_call_locks.clear()
        intervention_state._local_supervisor_calls.clear()
        holder = intervention_state.MonitorHolder(supervisor_id=7, name="Sup", mode="listen")
        ok = await intervention_state.acquire(None, 1, "call-a", holder)
        assert ok is True
        got = await intervention_state.get_call_holder(None, 1, "call-a")
        assert got is not None and got.supervisor_id == 7 and got.mode == "listen"

    async def test_second_supervisor_blocked(self):
        intervention_state._local_call_locks.clear()
        intervention_state._local_supervisor_calls.clear()
        await intervention_state.acquire(
            None, 1, "call-a", intervention_state.MonitorHolder(7, "A", "listen")
        )
        ok = await intervention_state.acquire(
            None, 1, "call-a", intervention_state.MonitorHolder(8, "B", "listen")
        )
        assert ok is False

    async def test_same_supervisor_can_switch_mode(self):
        intervention_state._local_call_locks.clear()
        intervention_state._local_supervisor_calls.clear()
        await intervention_state.acquire(
            None, 1, "call-a", intervention_state.MonitorHolder(7, "A", "listen")
        )
        ok = await intervention_state.acquire(
            None, 1, "call-a", intervention_state.MonitorHolder(7, "A", "whisper")
        )
        assert ok is True
        got = await intervention_state.get_call_holder(None, 1, "call-a")
        assert got.mode == "whisper"

    async def test_release_frees_call(self):
        intervention_state._local_call_locks.clear()
        intervention_state._local_supervisor_calls.clear()
        await intervention_state.acquire(
            None, 1, "call-a", intervention_state.MonitorHolder(7, "A", "listen")
        )
        await intervention_state.release(None, 1, "call-a", 7)
        assert await intervention_state.get_call_holder(None, 1, "call-a") is None
        assert await intervention_state.supervisor_busy_on(None, 1, 7) is None


# ───────────────────────── service gate chain ─────────────────────────


@pytest.fixture
def stub_db(monkeypatch):
    """Stub the service's DB-touching helpers so no DB/Redis is needed.

    ``_resolve`` returns a fixed target; ``_supervisor_name`` a fixed name;
    ``_trail`` records events into an in-memory list; wrap-up status update and
    the trail append are captured for assertions.
    """

    trail: list[dict] = []
    target = svc_mod._ResolvedTarget(
        record_id=1,
        call_id="call-1",
        customer_call_id="cust-leg-1",
        agent_id=99,
        phase="single",
    )

    target.agent_call_id = "agent-leg-1"

    async def fake_resolve(principal, call_id, *, require_scope):
        return target

    async def fake_name(supervisor_id):
        return "Supervisor"

    async def fake_trail(principal, call_id, *, mode, event, reason=None, note=None, detail=None):
        trail.append(
            {"mode": mode, "event": event, "reason": reason, "note": note, "detail": detail}
        )

    async def fake_status(db, tenant_id, employee_id, status, reason=None):
        fake_status.calls.append((employee_id, status))
        return {}

    fake_status.calls = []

    async def fake_close(db, tenant_id, employee_id):
        fake_close.calls.append((tenant_id, employee_id))

    fake_close.calls = []

    async def fake_finalize(redis, principal, resolved):
        fake_finalize.calls.append((principal.tenant_id, principal.user_id, resolved.agent_id))
        fake_status.calls.append((resolved.agent_id, "after_call_work"))
        fake_close.calls.append((principal.tenant_id, resolved.agent_id))
        call_control._in_call_state.pop((principal.tenant_id, resolved.agent_id), None)

    fake_finalize.calls = []

    notified: list[dict] = []

    async def fake_notify(principal, agent_id, event, payload):
        notified.append({"agent_id": agent_id, "event": event, "payload": payload})

    monkeypatch.setattr(CallInterventionService, "_resolve", staticmethod(fake_resolve))
    monkeypatch.setattr(CallInterventionService, "_supervisor_name", staticmethod(fake_name))
    monkeypatch.setattr(CallInterventionService, "_trail", staticmethod(fake_trail))
    monkeypatch.setattr(CallInterventionService, "_notify_agent", staticmethod(fake_notify))
    monkeypatch.setattr(
        svc_mod.CcAgentStatusService, "sync_pg_status", staticmethod(fake_status)
    )
    monkeypatch.setattr(
        svc_mod.AgentWebRTCSessionService, "close", staticmethod(fake_close)
    )
    monkeypatch.setattr(
        CallInterventionService, "_finalize_takeover_state", staticmethod(fake_finalize)
    )
    intervention_state._local_call_locks.clear()
    intervention_state._local_supervisor_calls.clear()
    intervention_state._local_supervisor_legs.clear()
    return {
        "trail": trail,
        "target": target,
        "status": fake_status,
        "session_close": fake_close,
        "finalize": fake_finalize,
        "notified": notified,
    }


async def _establish_leg(mock, principal, call_id, redis=None, sdp="v=0"):
    """Helper: negotiate the supervisor media leg so speaking modes can run."""

    return await CallInterventionService.register_supervisor_leg(
        mock, redis, principal, call_id, sdp
    )


# ───────────────────────── call phase ─────────────────────────

call_control = importlib.import_module("app.services.call_center.call_control_service")


def _patch_legs(monkeypatch, legs=None, *, raises=False):
    async def fake_legs(tenant_id, employee_id):
        if raises:
            raise RuntimeError("redis unavailable")
        return legs

    monkeypatch.setattr(call_control, "_legs", fake_legs)


@pytest.mark.asyncio
class TestPhaseDerivation:
    """Barging into a consultation, or taking over one leg of a three-party
    call, drops the supervisor into the wrong conversation. The phase driving
    that check is read from the agent's persisted call legs.
    """

    async def test_plain_two_party_call_is_single(self, monkeypatch):
        _patch_legs(monkeypatch, call_control.InCallLegs())
        assert await CallInterventionService._derive_phase(1, 99) == "single"

    async def test_live_consult_is_consulting(self, monkeypatch):
        _patch_legs(
            monkeypatch,
            call_control.InCallLegs(consult_state="active", consult_call_id="consult-1"),
        )
        assert await CallInterventionService._derive_phase(1, 99) == "consulting"

    async def test_ringing_consult_counts_too(self, monkeypatch):
        _patch_legs(
            monkeypatch,
            call_control.InCallLegs(consult_state="ringing", consult_offer_id="offer-1"),
        )
        assert await CallInterventionService._derive_phase(1, 99) == "consulting"

    async def test_intervention_room_alone_remains_single(self, monkeypatch):
        _patch_legs(monkeypatch, call_control.InCallLegs(room_id="room-1"))
        assert await CallInterventionService._derive_phase(1, 99) == "single"

    async def test_ringing_participant_is_three_way(self, monkeypatch):
        _patch_legs(
            monkeypatch,
            call_control.InCallLegs(conference_participant_call_id="party-1"),
        )
        assert await CallInterventionService._derive_phase(1, 99) == "three_way"

    async def test_call_without_an_agent_has_no_legs_to_read(self, monkeypatch):
        _patch_legs(monkeypatch, call_control.InCallLegs())
        assert await CallInterventionService._derive_phase(1, 0) == "single"

    async def test_unreadable_state_does_not_block_monitoring(self, monkeypatch):
        _patch_legs(monkeypatch, raises=True)
        assert await CallInterventionService._derive_phase(1, 99) == "single"


@pytest.mark.asyncio
class TestPhaseMatrix:
    async def test_barge_rejected_mid_consult(self, stub_db):
        stub_db["target"].phase = "consulting"
        with pytest.raises(ConflictError):
            await CallInterventionService.barge(
                MockTelephonyClient(), None, _principal(), "call-1"
            )

    async def test_takeover_rejected_in_three_way(self, stub_db):
        stub_db["target"].phase = "three_way"
        with pytest.raises(ConflictError):
            await CallInterventionService.takeover(
                MockTelephonyClient(), None, _principal(), "call-1",
                "customer_escalation", None,
            )

    async def test_listening_in_stays_allowed(self, stub_db):
        stub_db["target"].phase = "consulting"
        result = await CallInterventionService.listen(
            MockTelephonyClient(), None, _principal(), "call-1"
        )
        assert result["ok"] is True


@pytest.mark.asyncio
class TestListen:
    async def test_listen_calls_kernel_and_records_trail(self, stub_db):
        mock = MockTelephonyClient()
        result = await CallInterventionService.listen(mock, None, _principal(), "call-1")

        assert result == {"ok": True, "call_id": "call-1", "mode": "listen", "supervisor_id": 10}
        assert ("call.listen", {"call_id": "cust-leg-1", "timeout_ms": None}) in mock.recorded
        holder = await intervention_state.get_call_holder(None, 1, "call-1")
        assert holder is not None and holder.supervisor_id == 10
        assert any(e["event"] == "started" for e in stub_db["trail"])

    async def test_listen_denied_without_permission(self, stub_db):
        mock = MockTelephonyClient()
        with pytest.raises(ForbiddenError):
            await CallInterventionService.listen(
                mock, None, _principal(permissions=["call.monitor.view"]), "call-1"
            )

    async def test_listen_blocked_when_other_supervisor_holds(self, stub_db):
        await intervention_state.acquire(
            None, 1, "call-1", intervention_state.MonitorHolder(999, "Other", "listen")
        )
        mock = MockTelephonyClient()
        with pytest.raises(ConflictError):
            await CallInterventionService.listen(mock, None, _principal(), "call-1")

    async def test_listen_blocked_when_supervisor_busy_elsewhere(self, stub_db):
        await intervention_state.acquire(
            None, 1, "call-other", intervention_state.MonitorHolder(10, "Me", "listen")
        )
        mock = MockTelephonyClient()
        with pytest.raises(ConflictError):
            await CallInterventionService.listen(mock, None, _principal(), "call-1")


@pytest.mark.asyncio
class TestSupervisorLeg:
    async def test_register_leg_negotiates_and_records(self, stub_db):
        mock = MockTelephonyClient()
        res = await CallInterventionService.register_supervisor_leg(
            mock, None, _principal(), "call-1", "v=0"
        )
        assert res["supervisor_call_id"] == "mock-webrtc-call"
        assert ("webrtc.offer", {"sdp": "v=0", "call_id": None}) in mock.recorded
        holder = await intervention_state.get_call_holder(None, 1, "call-1")
        assert holder is not None and holder.supervisor_call_id == "mock-webrtc-call"

    async def test_register_leg_sets_reverse_index(self, stub_db):
        mock = MockTelephonyClient()
        await CallInterventionService.register_supervisor_leg(
            mock, None, _principal(), "call-1", "v=0"
        )
        target = await intervention_state.get_supervisor_leg_target(
            None, "mock-webrtc-call"
        )
        assert target == (1, "call-1")

    async def test_register_leg_after_refresh_replaces_stale_supervisor_leg(self, stub_db):
        mock = MockTelephonyClient()
        p = _principal()
        await _establish_leg(mock, p, "call-1")
        await CallInterventionService.whisper(mock, None, p, "call-1")

        mock.webrtc_offer_response = {
            "call_id": "refreshed-supervisor-leg",
            "sdp": "v=0\r\nmock-answer",
        }
        mock.recorded.clear()
        await CallInterventionService.register_supervisor_leg(
            mock, None, p, "call-1", "v=0-refreshed"
        )

        assert (
            "room.replace_leg",
            {
                "room_id": "mock-room",
                "old_call_id": "mock-webrtc-call",
                "new_call_id": "refreshed-supervisor-leg",
            },
        ) in mock.recorded
        assert (
            "call.hangup",
            {"call_id": "mock-webrtc-call", "reason": "supervisor_media_replaced"},
        ) in mock.recorded
        holder = await intervention_state.get_call_holder(None, 1, "call-1")
        assert holder is not None
        assert holder.supervisor_call_id == "refreshed-supervisor-leg"


@pytest.mark.asyncio
class TestSupervisorIce:
    async def test_add_ice_forwards_to_stored_leg(self, stub_db):
        mock = MockTelephonyClient()
        p = _principal()
        await _establish_leg(mock, p, "call-1")
        mock.recorded.clear()
        candidate = {"candidate": "candidate:1 1 udp ...", "sdpMid": "0"}
        result = await CallInterventionService.add_supervisor_ice(
            mock, None, p, "call-1", candidate
        )
        assert result == {"ok": True}
        # Forwarded against the negotiated supervisor leg id, not the target call.
        assert (
            "webrtc.ice",
            {"call_id": "mock-webrtc-call", "candidate": candidate},
        ) in mock.recorded

    async def test_add_ice_no_leg_raises_not_found(self, stub_db):
        from app.core.exceptions import NotFoundError

        mock = MockTelephonyClient()
        with pytest.raises(NotFoundError):
            await CallInterventionService.add_supervisor_ice(
                mock, None, _principal(), "call-1", {"candidate": "x"}
            )


@pytest.mark.asyncio
class TestKernelIceRouting:
    async def test_kernel_ice_for_supervisor_leg_emits_to_supervisor(self, stub_db, monkeypatch):
        emitted: list[dict] = []

        class FakeTransport:
            async def emit(self, event, payload, room=None, namespace=None):
                emitted.append({"event": event, "payload": payload, "room": room, "namespace": namespace})

        monkeypatch.setattr(svc_mod, "get_realtime_transport", lambda: FakeTransport())

        mock = MockTelephonyClient()
        await _establish_leg(mock, _principal(user_id=10), "call-1")
        candidate = {"candidate": "candidate:2 1 udp ..."}
        await CallInterventionService.handle_kernel_ice(None, "mock-webrtc-call", candidate)

        assert len(emitted) == 1
        e = emitted[0]
        assert e["event"] == "cc.supervisor.ice"
        assert e["payload"] == {"candidate": candidate}
        assert e["room"] == "agent:1:10"
        assert e["namespace"] == "/chat"

    async def test_kernel_ice_for_unknown_leg_is_noop(self, stub_db, monkeypatch):
        emitted: list[dict] = []

        class FakeTransport:
            async def emit(self, *a, **k):
                emitted.append({})

        monkeypatch.setattr(svc_mod, "get_realtime_transport", lambda: FakeTransport())
        # No leg indexed → nothing routed.
        await CallInterventionService.handle_kernel_ice(None, "not-a-supervisor-leg", {"candidate": "x"})
        assert emitted == []

    async def test_stop_clears_reverse_index(self, stub_db):
        mock = MockTelephonyClient()
        p = _principal()
        await _establish_leg(mock, p, "call-1")
        assert await intervention_state.get_supervisor_leg_target(None, "mock-webrtc-call") is not None
        await CallInterventionService.stop(mock, None, p, "call-1")
        assert await intervention_state.get_supervisor_leg_target(None, "mock-webrtc-call") is None


@pytest.mark.asyncio
class TestWhisper:
    async def test_whisper_builds_room_and_agent_only_gain(self, stub_db):
        mock = MockTelephonyClient()
        p = _principal()
        await _establish_leg(mock, p, "call-1")
        result = await CallInterventionService.whisper(mock, None, p, "call-1")
        assert result["mode"] == "whisper"
        # Room created with all three legs.
        assert (
            "room.create",
            {"leg_call_ids": ["cust-leg-1", "agent-leg-1", "mock-webrtc-call"]},
        ) in mock.recorded
        # Agent hears supervisor (1.0); customer does NOT (0.0).
        assert (
            "room.set_mix_gain",
            {"room_id": "mock-room", "listener_call_id": "agent-leg-1",
             "speaker_call_id": "mock-webrtc-call", "gain": 1.0},
        ) in mock.recorded
        assert (
            "room.set_mix_gain",
            {"room_id": "mock-room", "listener_call_id": "cust-leg-1",
             "speaker_call_id": "mock-webrtc-call", "gain": 0.0},
        ) in mock.recorded
        assert any(n["event"] == "cc.supervisor_whisper" for n in stub_db["notified"])
        legs = call_control._in_call_state[(1, 99)]
        assert legs.room_id == "mock-room"
        assert legs.agent_media_call_id == "agent-leg-1"
        assert legs.room_legs == ["cust-leg-1", "agent-leg-1", "mock-webrtc-call"]

    async def test_whisper_without_leg_rejected(self, stub_db):
        mock = MockTelephonyClient()
        with pytest.raises(ConflictError):
            await CallInterventionService.whisper(mock, None, _principal(), "call-1")


@pytest.mark.asyncio
class TestBarge:
    async def test_barge_both_parties_hear_supervisor(self, stub_db):
        mock = MockTelephonyClient()
        p = _principal()
        await _establish_leg(mock, p, "call-1")
        await CallInterventionService.barge(mock, None, p, "call-1")
        # Customer hears supervisor (1.0) in barge, unlike whisper.
        assert (
            "room.set_mix_gain",
            {"room_id": "mock-room", "listener_call_id": "cust-leg-1",
             "speaker_call_id": "mock-webrtc-call", "gain": 1.0},
        ) in mock.recorded

    async def test_switch_whisper_to_barge_reuses_room(self, stub_db):
        mock = MockTelephonyClient()
        p = _principal()
        await _establish_leg(mock, p, "call-1")
        await CallInterventionService.whisper(mock, None, p, "call-1")
        mock.recorded.clear()
        await CallInterventionService.barge(mock, None, p, "call-1")
        # No second room.create — the existing room is reused.
        assert not any(r[0] == "room.create" for r in mock.recorded)

    async def test_new_supervisor_reuses_room_left_by_previous_monitor(self, stub_db):
        mock = MockTelephonyClient()
        first = _principal(user_id=10)
        await _establish_leg(mock, first, "call-1")
        await CallInterventionService.whisper(mock, None, first, "call-1")
        await CallInterventionService.stop(mock, None, first, "call-1")

        second = _principal(user_id=11)
        mock.webrtc_offer_response = {
            "call_id": "second-supervisor-leg",
            "sdp": "v=0\r\nmock-answer",
        }
        await _establish_leg(mock, second, "call-1")
        mock.recorded.clear()
        await CallInterventionService.barge(mock, None, second, "call-1")

        assert not any(r[0] == "room.create" for r in mock.recorded)
        assert (
            "room.add_leg",
            {"room_id": "mock-room", "call_id": "second-supervisor-leg"},
        ) in mock.recorded


@pytest.mark.asyncio
class TestTakeover:
    async def test_takeover_requires_workspace_use(self, stub_db):
        mock = MockTelephonyClient()
        perms = [p for p in ALL_PERMS if p != "call.workspace.use"]
        with pytest.raises(ForbiddenError):
            await CallInterventionService.takeover(
                mock, None, _principal(permissions=perms), "call-1", "customer_escalation", None
            )

    async def test_takeover_drops_agent_and_wraps_agent(self, stub_db):
        mock = MockTelephonyClient()
        p = _principal()
        await _establish_leg(mock, p, "call-1")
        # A room must exist; whisper first to build it (which also puts the
        # supervisor leg into the room — so takeover must NOT re-add it).
        await CallInterventionService.whisper(mock, None, p, "call-1")
        result = await CallInterventionService.takeover(
            mock, None, p, "call-1", "customer_escalation", None
        )
        assert result["mode"] == "takeover"
        # Agent is dropped from the room (not swapped in via replace_leg, which
        # would fail because the supervisor leg is already in the room).
        assert (
            "room.remove_leg",
            {"room_id": "mock-room", "call_id": "agent-leg-1"},
        ) in mock.recorded
        # Customer now hears the supervisor at full volume (whisper had pinned it to 0).
        assert (
            "room.set_mix_gain",
            {"room_id": "mock-room", "listener_call_id": "cust-leg-1",
             "speaker_call_id": "mock-webrtc-call", "gain": 1.0},
        ) in mock.recorded
        # Agent's own WebRTC leg is hung up so their kernel call ends.
        assert (
            "call.hangup",
            {"call_id": "agent-leg-1", "reason": "supervisor_takeover"},
        ) in mock.recorded
        # Agent's browser gets a clean cc.call_hangup so its call bar closes and
        # the WebRTC teardown doesn't surface as an ICE error.
        assert any(n["event"] == "cc.call_hangup" for n in stub_db["notified"])
        assert (99, "after_call_work") in stub_db["status"].calls
        assert stub_db["finalize"].calls == [(1, 10, 99)]
        assert (1, 99) not in call_control._in_call_state
        events = [e["event"] for e in stub_db["trail"]]
        assert "reception_segment_intent" in events and "succeeded" in events
        assert any(n["event"] == "cc.supervisor_takeover" for n in stub_db["notified"])

    async def test_takeover_without_leg_rejected(self, stub_db):
        mock = MockTelephonyClient()
        with pytest.raises(ConflictError):
            await CallInterventionService.takeover(
                mock, None, _principal(), "call-1", "customer_escalation", None
            )

    async def test_end_takeover_closes_room_and_releases(self, stub_db):
        mock = MockTelephonyClient()
        p = _principal()
        await _establish_leg(mock, p, "call-1")
        await CallInterventionService.whisper(mock, None, p, "call-1")
        await CallInterventionService.takeover(
            mock, None, p, "call-1", "customer_escalation", None
        )
        result = await CallInterventionService.end_takeover(mock, None, p, "call-1")
        assert result["mode"] == "takeover"
        # The room is closed in one shot (drops customer + supervisor legs).
        assert (
            "room.close",
            {"room_id": "mock-room", "reason": "supervisor_takeover_end"},
        ) in mock.recorded
        # Monitor lock released and the leg reverse-index cleared.
        assert await intervention_state.get_call_holder(None, p.tenant_id, "call-1") is None
        assert (
            await intervention_state.get_supervisor_leg_target(None, "mock-webrtc-call")
            is None
        )

    async def test_end_takeover_without_holder_is_noop(self, stub_db):
        mock = MockTelephonyClient()
        result = await CallInterventionService.end_takeover(
            mock, None, _principal(), "call-1"
        )
        assert result["mode"] == "takeover"
        assert not any(r[0] == "room.close" for r in mock.recorded)


@pytest.mark.asyncio
class TestTakeoverStateFinalization:
    async def test_reassigns_owner_and_clears_original_agent_reconnect_state(
        self, monkeypatch
    ):
        row = type("CallRow", (), {"last_serving_agent_id": 99})()
        calls: list[tuple] = []

        class Result:
            def scalar_one_or_none(self):
                return row

        class FakeDb:
            async def execute(self, statement):
                return Result()

            async def commit(self):
                calls.append(("commit",))

        class FakeSessionContext:
            async def __aenter__(self):
                return FakeDb()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        async def fake_close(db, tenant_id, employee_id):
            calls.append(("close_session", tenant_id, employee_id))

        async def fake_status(db, tenant_id, employee_id, status, reason=None):
            calls.append(("status", tenant_id, employee_id, status, reason))

        async def fake_clear(tenant_id, employee_id):
            calls.append(("clear_legs", tenant_id, employee_id))

        monkeypatch.setattr(svc_mod, "AsyncSessionLocal", FakeSessionContext)
        monkeypatch.setattr(
            svc_mod.AgentWebRTCSessionService, "close", staticmethod(fake_close)
        )
        monkeypatch.setattr(
            svc_mod.CcAgentStatusService, "sync_pg_status", staticmethod(fake_status)
        )
        monkeypatch.setattr(call_control, "_clear_legs", fake_clear)

        target = svc_mod._ResolvedTarget(
            record_id=1,
            call_id="call-1",
            customer_call_id="customer-1",
            agent_id=99,
            agent_call_id="agent-leg-1",
            phase="single",
        )
        await CallInterventionService._finalize_takeover_state(
            None, _principal(), target
        )

        assert row.last_serving_agent_id == 10
        assert ("close_session", 1, 99) in calls
        assert ("status", 1, 99, "after_call_work", "supervisor_takeover") in calls
        assert ("clear_legs", 1, 99) in calls


@pytest.mark.asyncio
class TestRoomDegradation:
    async def test_whisper_degrades_when_rooms_disabled(self, stub_db):
        from app.libs.telephony.base import TelephonyMethodNotFoundError
        mock = MockTelephonyClient()
        p = _principal()
        await _establish_leg(mock, p, "call-1")
        mock.room_error = TelephonyMethodNotFoundError(-32601, "method not found")
        with pytest.raises(NotImplementedApiError):
            await CallInterventionService.whisper(mock, None, p, "call-1")
        # Agent/customer call untouched: no hangup was issued.
        assert not any(r[0] == "call.hangup" for r in mock.recorded)
        # Mode downgraded back to listen so the supervisor is not stuck.
        holder = await intervention_state.get_call_holder(None, 1, "call-1")
        assert holder is not None and holder.mode == "listen"


@pytest.mark.asyncio
class TestForceHangup:
    async def test_force_hangup_ends_all_legs_and_wraps_agent(self, stub_db):
        mock = MockTelephonyClient()
        result = await CallInterventionService.force_hangup(
            mock, None, _principal(), "call-1", "violation", None
        )
        assert result["ok"] is True and result["mode"] == "force_hangup"
        # No room: every enumerated leg (customer + agent) is hung up.
        assert (
            "call.hangup",
            {"call_id": "cust-leg-1", "reason": "supervisor_force_hangup"},
        ) in mock.recorded
        assert (
            "call.hangup",
            {"call_id": "agent-leg-1", "reason": "supervisor_force_hangup"},
        ) in mock.recorded
        assert (99, "after_call_work") in stub_db["status"].calls
        events = [e["event"] for e in stub_db["trail"]]
        assert "initiated" in events and "succeeded" in events

    async def test_force_hangup_closes_room_when_present(self, stub_db):
        mock = MockTelephonyClient()
        p = _principal()
        await _establish_leg(mock, p, "call-1")
        await CallInterventionService.whisper(mock, None, p, "call-1")
        mock.recorded.clear()
        await CallInterventionService.force_hangup(mock, None, p, "call-1", "violation", None)
        # One-shot room teardown instead of per-leg hangup.
        assert (
            "room.close",
            {"room_id": "mock-room", "reason": "supervisor_force_hangup"},
        ) in mock.recorded
        assert not any(r[0] == "call.hangup" for r in mock.recorded)


@pytest.mark.asyncio
class TestNoSessionDuringKernelIO:
    """Assert no DB session is held while the supervisor WebRTC leg negotiates.

    ``register_supervisor_leg`` does a kernel round-trip (webrtc.offer +
    call.answer). Per the short-session rule, no pooled DB connection may be
    checked out across that wait. We track session open/close and record whether
    a session is active on each kernel call.
    """

    async def test_register_leg_holds_no_session_during_offer(self, monkeypatch):
        class SessionTracker:
            active = False
            opens = 0
            closes = 0

        class FakeSessionContext:
            async def __aenter__(self):
                assert SessionTracker.active is False
                SessionTracker.active = True
                SessionTracker.opens += 1
                return object()

            async def __aexit__(self, *_):
                SessionTracker.active = False
                SessionTracker.closes += 1
                return False

        def fake_session_local():
            return FakeSessionContext()

        # Any short session the service opens goes through the tracker.
        monkeypatch.setattr(svc_mod, "AsyncSessionLocal", fake_session_local)

        # Stub the DB-touching helpers to open a tracked short session, mirroring
        # the real ones (open → read → close), but with no real DB.
        async def fake_resolve(principal, call_id, *, require_scope):
            async with svc_mod.AsyncSessionLocal():
                pass
            t = svc_mod._ResolvedTarget(
                record_id=1, call_id="call-1", customer_call_id="cust-leg-1",
                agent_id=99, phase="single", agent_call_id="agent-leg-1",
            )
            return t

        async def fake_name(supervisor_id):
            async with svc_mod.AsyncSessionLocal():
                return "Sup"

        async def fake_trail(principal, call_id, *, mode, event, reason=None, note=None, detail=None):
            async with svc_mod.AsyncSessionLocal():
                pass

        monkeypatch.setattr(CallInterventionService, "_resolve", staticmethod(fake_resolve))
        monkeypatch.setattr(CallInterventionService, "_supervisor_name", staticmethod(fake_name))
        monkeypatch.setattr(CallInterventionService, "_trail", staticmethod(fake_trail))
        intervention_state._local_call_locks.clear()
        intervention_state._local_supervisor_calls.clear()

        active_during_kernel: list[bool] = []

        class TrackingTelephony(MockTelephonyClient):
            async def webrtc_offer(self, sdp, call_id=None):
                active_during_kernel.append(SessionTracker.active)
                return await super().webrtc_offer(sdp, call_id)

            async def call_answer(self, call_id):
                active_during_kernel.append(SessionTracker.active)
                return await super().call_answer(call_id)

        mock = TrackingTelephony()
        await CallInterventionService.register_supervisor_leg(
            mock, None, _principal(), "call-1", "v=0"
        )
        # No session was active during any kernel round-trip.
        assert active_during_kernel == [False, False]
        # Every opened session was closed.
        assert SessionTracker.opens == SessionTracker.closes and SessionTracker.opens > 0


class TestReasonValidation:
    def test_other_requires_note(self):
        with pytest.raises(ValidationError):
            CallInterventionService.validate_reason("other", None)

    def test_other_with_note_ok(self):
        CallInterventionService.validate_reason("other", "explained")

    def test_known_reason_no_note_ok(self):
        CallInterventionService.validate_reason("customer_escalation", None)

    def test_empty_reason_rejected(self):
        with pytest.raises(ValidationError):
            CallInterventionService.validate_reason("", None)


# ─────────────────── call.hangup → monitor-lock release ───────────────────

reports_ext = importlib.import_module("app.extensions.reports")


class _HangupEvent:
    def __init__(self, call_id):
        self.data = {"call_id": call_id}


class TestCallHangupMonitorRelease:
    """The reports ``call.hangup`` handler frees monitor locks for both event
    shapes: the whole call ending, and a supervisor media leg dying on its own
    (e.g. the supervisor's browser closed mid-whisper)."""

    @pytest.fixture(autouse=True)
    def clean_locks(self):
        intervention_state._local_call_locks.clear()
        intervention_state._local_supervisor_calls.clear()
        intervention_state._local_supervisor_legs.clear()
        yield
        intervention_state._local_call_locks.clear()
        intervention_state._local_supervisor_calls.clear()
        intervention_state._local_supervisor_legs.clear()

    @pytest.fixture
    def handler_env(self, monkeypatch):
        """In-process locks (no Redis); trail appends captured; no real DB."""

        async def no_redis():
            return None

        trail: list[dict] = []

        async def fake_append(db, tenant_id, call_id, entry):
            trail.append({"tenant_id": tenant_id, "call_id": call_id, **entry})

        class FakeResult:
            def __init__(self, row=None):
                self._row = row

            def scalar_one_or_none(self):
                return self._row

        class FakeSession:
            row = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def execute(self, *args, **kwargs):
                return FakeResult(self.row)

            async def commit(self):
                pass

        monkeypatch.setattr(reports_ext, "_optional_redis", no_redis)
        monkeypatch.setattr(intervention_state, "append_trail_event", fake_append)
        monkeypatch.setattr("app.db.session.AsyncSessionLocal", lambda: FakeSession())
        return {"trail": trail, "session_cls": FakeSession}

    async def test_supervisor_leg_hangup_releases_monitor_lock(self, handler_env):
        await intervention_state.acquire(
            None, 1, "call-1",
            intervention_state.MonitorHolder(
                supervisor_id=10, name="Sup", mode="whisper",
                supervisor_call_id="sup-leg-1", room_id="room-1",
            ),
        )
        await intervention_state.set_supervisor_leg_index(None, 1, "call-1", "sup-leg-1")

        await reports_ext._on_call_hangup_release_monitor(_HangupEvent("sup-leg-1"))

        assert await intervention_state.get_call_holder(None, 1, "call-1") is None
        assert await intervention_state.supervisor_busy_on(None, 1, 10) is None
        assert await intervention_state.get_supervisor_leg_target(None, "sup-leg-1") is None
        assert handler_env["trail"] == [
            {
                "tenant_id": 1,
                "call_id": "call-1",
                "supervisor_id": 10,
                "mode": "whisper",
                "event": "ended",
                "detail": "supervisor_leg_hangup",
            }
        ]

    async def test_stale_leg_index_does_not_free_new_holders_lock(self, handler_env):
        # A refresh re-negotiated the supervisor leg: the holder moved on to
        # "new-leg" while the old leg's index entry is still around. The old
        # leg's late hangup must not release the refreshed session's lock.
        await intervention_state.acquire(
            None, 1, "call-1",
            intervention_state.MonitorHolder(
                supervisor_id=10, name="Sup", mode="whisper",
                supervisor_call_id="new-leg", room_id="room-1",
            ),
        )
        await intervention_state.set_supervisor_leg_index(None, 1, "call-1", "old-leg")

        await reports_ext._on_call_hangup_release_monitor(_HangupEvent("old-leg"))

        holder = await intervention_state.get_call_holder(None, 1, "call-1")
        assert holder is not None and holder.supervisor_call_id == "new-leg"
        assert handler_env["trail"] == []

    async def test_customer_call_hangup_releases_holder(self, handler_env):
        from types import SimpleNamespace

        handler_env["session_cls"].row = SimpleNamespace(tenant_id=1)
        await intervention_state.acquire(
            None, 1, "call-1",
            intervention_state.MonitorHolder(
                supervisor_id=10, name="Sup", mode="listen",
                supervisor_call_id="sup-leg-9",
            ),
        )
        await intervention_state.set_supervisor_leg_index(None, 1, "call-1", "sup-leg-9")

        await reports_ext._on_call_hangup_release_monitor(_HangupEvent("call-1"))

        assert await intervention_state.get_call_holder(None, 1, "call-1") is None
        assert await intervention_state.get_supervisor_leg_target(None, "sup-leg-9") is None
        assert handler_env["trail"] == [
            {
                "tenant_id": 1,
                "call_id": "call-1",
                "supervisor_id": 10,
                "mode": "listen",
                "event": "ended",
            }
        ]
