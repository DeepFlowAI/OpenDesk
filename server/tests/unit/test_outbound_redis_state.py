"""Cross-node outbound state: originator / webrtc pair / ended live in Redis."""
from __future__ import annotations

import pytest
import fakeredis.aioredis
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager

from app.libs.telephony.base import CallEvent
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center import orchestrator as orch_module
from app.services.call_center.orchestrator import CallCenterOrchestrator


@asynccontextmanager
async def _fake_session():
    db = AsyncMock()
    yield db


def _bridge_calls(telephony):
    return [payload for method, payload in telephony.recorded if method == "call.bridge"]


async def _ready_outbound_orchestrator(monkeypatch, fake):
    from app.services.system_settings_service import SystemSettingsService

    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: fake)
    monkeypatch.setattr(orch_module, "AsyncSessionLocal", _fake_session)
    monkeypatch.setattr(orch_module.CallRecordService, "mark_answered", AsyncMock())
    monkeypatch.setattr(
        orch_module.CallRecordService, "mark_reception_started", AsyncMock()
    )
    monkeypatch.setattr(
        SystemSettingsService,
        "is_bridge_asr_enabled_managed",
        AsyncMock(return_value=False),
    )
    telephony = MockTelephonyClient()
    orch = CallCenterOrchestrator(telephony=telephony)
    monkeypatch.setattr(orch, "bind_call_trace", lambda *_args: None)
    monkeypatch.setattr(orch, "notify_agent_outbound_event", AsyncMock())
    await orch.register_outbound_call(
        call_id="out-1", tenant_id=9, employee_id=42, outbound_did="9000001"
    )
    return orch, telephony


@pytest.mark.asyncio
async def test_outbound_pair_then_answer_bridges_once(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    orch, telephony = await _ready_outbound_orchestrator(monkeypatch, fake)

    await orch.pair_outbound_webrtc(
        outbound_call_id="out-1", webrtc_call_id="rtc-1"
    )
    assert _bridge_calls(telephony) == []

    event = CallEvent(method="call.answered", data={"call_id": "out-1"})
    await orch._on_outbound_answered(event)
    await orch._on_outbound_answered(event)

    assert len(_bridge_calls(telephony)) == 1


@pytest.mark.asyncio
async def test_outbound_answer_then_pair_bridges_once(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    orch, telephony = await _ready_outbound_orchestrator(monkeypatch, fake)

    event = CallEvent(method="call.answered", data={"call_id": "out-1"})
    await orch._on_outbound_answered(event)
    assert _bridge_calls(telephony) == []

    await orch.pair_outbound_webrtc(
        outbound_call_id="out-1", webrtc_call_id="rtc-1"
    )
    await orch.pair_outbound_webrtc(
        outbound_call_id="out-1", webrtc_call_id="rtc-1"
    )

    assert len(_bridge_calls(telephony)) == 1


@pytest.mark.asyncio
async def test_outbound_originator_round_trips_via_redis(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "app.services.call_center.orchestrator._get_redis_client",
        lambda: fake,
    )
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._outbound_originators = {}
    orch._outbound_ended = {}
    orch._outbound_webrtc_pairs = {}
    orch._call_traces = {}

    await orch.register_outbound_call(
        call_id="out-1",
        tenant_id=9,
        employee_id=42,
        outbound_did="+86021",
    )
    # Simulate another node: empty local cache, hydrate from Redis.
    orch._outbound_originators.clear()
    info = await orch._peek_outbound_originator("out-1")
    assert info == (9, 42, "+86021")


@pytest.mark.asyncio
async def test_outbound_webrtc_pair_pop_from_redis(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "app.services.call_center.orchestrator._get_redis_client",
        lambda: fake,
    )
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._outbound_originators = {}
    orch._outbound_ended = {}
    orch._outbound_webrtc_pairs = {}

    await orch.pair_outbound_webrtc(
        outbound_call_id="out-1", webrtc_call_id="rtc-9"
    )
    orch._outbound_webrtc_pairs.clear()
    got = await orch._pop_outbound_webrtc("out-1")
    assert got == "rtc-9"
    assert await orch._pop_outbound_webrtc("out-1") is None


@pytest.mark.asyncio
async def test_outbound_ended_visible_across_nodes(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "app.services.call_center.orchestrator._get_redis_client",
        lambda: fake,
    )
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._outbound_originators = {}
    orch._outbound_ended = {}
    orch._outbound_webrtc_pairs = {}

    await orch._mark_outbound_ended(
        "out-1", "busy", 486, hangup_details={"sip_reason": "Busy Here"}
    )
    orch._outbound_ended.clear()
    ended = await orch.outbound_ended_reason("out-1")
    assert ended == ("busy", 486)
    assert orch._outbound_ended_details["out-1"]["sip_reason"] == "Busy Here"


@pytest.mark.asyncio
async def test_hangup_before_originator_marks_ended_for_dial_webrtc(monkeypatch):
    """Carrier 404 in <50ms must still make /dial-webrtc return 410."""

    class _NoRow:
        def scalar_one_or_none(self):
            return None

    class _DbNoRow:
        async def execute(self, _q):
            return _NoRow()

    class _SessionNoRow:
        async def __aenter__(self):
            return _DbNoRow()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _SessionNoRow())
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: None)

    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    orch._outbound_originators = {}
    orch._outbound_ended = {}
    orch._outbound_webrtc_pairs = {}

    async def _noop(_call_id):
        return None

    monkeypatch.setattr(orch, "_delayed_trace_cleanup", _noop)
    monkeypatch.setattr(orch, "_delayed_outbound_cleanup", _noop)

    await orch._on_hangup(
        CallEvent(
            method="call.hangup",
            data={
                "call_id": "out-race",
                "reason": "rejected",
                "sip_status": 404,
            },
        )
    )

    assert await orch.outbound_ended_reason("out-race") == ("rejected", 404)


@pytest.mark.asyncio
async def test_unanswered_outbound_hangup_releases_before_notify(monkeypatch):
    """Callee hangup while ringing must restore ready before cc.outbound_hangup.

    The workbench refetches agent-status on that event; notifying first left
    the poll overlay on busy.
    """
    from types import SimpleNamespace

    from app.services.cc_agent_resource_service import CcAgentResourceService
    from app.services.cc_agent_status_service import CcAgentStatusService

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await CcAgentResourceService.set_visible_status(
        fake, tenant_id=1, employee_id=42, status="ready"
    )
    await CcAgentResourceService.reserve_outbound(
        fake, 1, 42, reservation_id="outbound:token", ttl_seconds=30
    )
    await CcAgentResourceService.bind_outbound_call(
        fake, 1, 42, reservation_id="outbound:token", call_id="out-ring", ttl_seconds=30
    )

    class _Result:
        def scalar_one_or_none(self):
            return SimpleNamespace(
                tenant_id=1, call_id="out-ring", customer_connected_at=None
            )

    class _Db:
        async def execute(self, _q):
            return _Result()

    @asynccontextmanager
    async def _session():
        yield _Db()

    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: fake)
    monkeypatch.setattr(orch_module, "AsyncSessionLocal", _session)
    monkeypatch.setattr(orch_module.CallRecordService, "mark_completed", AsyncMock())
    sync_pg = AsyncMock()
    monkeypatch.setattr(CcAgentStatusService, "sync_pg_status", sync_pg)

    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    orch._outbound_originators = {}
    orch._outbound_ended = {}
    orch._outbound_webrtc_pairs = {}
    monkeypatch.setattr(orch, "bind_call_trace", lambda *_args: None)
    monkeypatch.setattr(orch, "_delayed_trace_cleanup", AsyncMock())
    monkeypatch.setattr(orch, "_delayed_outbound_cleanup", AsyncMock())
    monkeypatch.setattr(orch, "_maybe_release_sip_occupancy", AsyncMock())

    notify_visible: list[str] = []

    async def _notify(**_kwargs):
        snap = await CcAgentResourceService.get_snapshot(fake, 1, 42)
        notify_visible.append((snap or {}).get("visible_status") or "")

    monkeypatch.setattr(orch, "notify_agent_outbound_event", _notify)
    await orch.register_outbound_call(
        call_id="out-ring", tenant_id=1, employee_id=42, outbound_did="9000000"
    )

    await orch._on_hangup(
        CallEvent(
            method="call.hangup",
            data={"call_id": "out-ring", "reason": "remote_bye"},
        )
    )

    assert notify_visible == ["ready"]
    snap = await CcAgentResourceService.get_snapshot(fake, 1, 42)
    assert snap is not None
    assert snap["visible_status"] == "ready"
    assert snap["resource_state"] == "idle"
    sync_pg.assert_awaited()
    assert sync_pg.await_args.args[3] == "ready"


@pytest.mark.asyncio
async def test_late_outbound_cdr_is_immediately_finalized(monkeypatch):
    """A CDR created after carrier rejection must never remain ringing."""

    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._outbound_ended = {"out-race": ("rejected", 404)}
    mark_completed = AsyncMock()
    monkeypatch.setattr(
        orch_module.CallRecordService, "mark_completed", mark_completed
    )
    db = AsyncMock()

    ended = await orch.finalize_outbound_cdr_if_already_ended(
        db, tenant_id=1, call_id="out-race"
    )

    assert ended == ("rejected", 404)
    mark_completed.assert_awaited_once_with(
        db,
        1,
        "out-race",
        hangup_reason="rejected",
        end_state="failed",
        hangup_details=None,
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_outbound_auto_bridge_treats_missing_call_as_skip(monkeypatch):
    """Remote BYE before call.bridge must not raise an ERROR-level failure."""
    from app.libs.telephony.base import TelephonyRPCError

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    orch, telephony = await _ready_outbound_orchestrator(monkeypatch, fake)
    telephony.bridge_error = TelephonyRPCError(-32002, "call not found: out-1")

    await orch.pair_outbound_webrtc(
        outbound_call_id="out-1", webrtc_call_id="rtc-1"
    )
    event = CallEvent(method="call.answered", data={"call_id": "out-1"})
    await orch._on_outbound_answered(event)

    assert _bridge_calls(telephony) == [
        {
            "call_id": "out-1",
            "other_call_id": "rtc-1",
            "transcribe": False,
            "keepalive_on_peer_hangup": True,
            "user_call_id": "out-1",
        }
    ]
    # Claim released so a later pairing/event can retry if the SIP is still up.
    assert await fake.get(orch._outbound_bridged_key("out-1")) is None


@pytest.mark.asyncio
async def test_outbound_auto_bridge_binds_agent_media_leg(monkeypatch):
    """After outbound auto-bridge, mute/transfer must see the live WebRTC leg."""
    from app.services.call_center.call_control_service import _in_call_state

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    orch, telephony = await _ready_outbound_orchestrator(monkeypatch, fake)
    _in_call_state.clear()

    await orch.pair_outbound_webrtc(
        outbound_call_id="out-1", webrtc_call_id="rtc-1"
    )
    event = CallEvent(method="call.answered", data={"call_id": "out-1"})
    await orch._on_outbound_answered(event)

    assert len(_bridge_calls(telephony)) == 1
    legs = _in_call_state[(9, 42)]
    assert legs.agent_media_call_id == "rtc-1"
    _in_call_state.clear()


def test_outbound_early_fail_covers_flowkit_reasons_and_final_sip() -> None:
    from app.services.call_center.orchestration.outbound import OutboundMixin

    assert OutboundMixin._is_outbound_early_fail("busy")
    assert OutboundMixin._is_outbound_early_fail("originate_rejected")
    assert OutboundMixin._is_outbound_early_fail("timeout")
    assert OutboundMixin._is_outbound_early_fail("ack_failed")
    assert OutboundMixin._is_outbound_early_fail("unknown_bucket", 486)
    assert OutboundMixin._is_outbound_early_fail("remote_bye") is False
    assert OutboundMixin._is_outbound_early_fail("remote_bye", 183) is False


@pytest.mark.asyncio
async def test_reassign_outbound_originator_moves_call_to_new_agent(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: fake)
    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    await orch.register_outbound_call(
        call_id="out-1", tenant_id=9, employee_id=42, outbound_did="9000001"
    )

    await orch.reassign_outbound_originator("out-1", 77)
    await orch.reassign_outbound_originator("not-outbound", 77)

    other_node = CallCenterOrchestrator(telephony=MockTelephonyClient())
    assert await other_node._peek_outbound_originator("out-1") == (9, 77, "9000001")
    assert await other_node._peek_outbound_originator("not-outbound") is None
