"""
Regression tests for the "stuck agent" call-center concurrency bug.

Scenario (from production): a caller reaches an `assign_queue` node which rings
an agent, then the CALLER hangs up. Three races used to leave the agent stuck on
忙碌 (busy) forever:

  (a) caller hangs up while the offer is still ringing → offer must be withdrawn
      (agent browser stops ringing) and the reserved agent freed;
  (b) caller hangs up after the agent accepted, so the bridge target is gone →
      `call.bridge` -32002 must abort cleanly (tear down the agent's WebRTC leg,
      reset status), not leave the agent bridged to a dead leg;
  (c) agent-initiated hangup when the customer leg is already gone (-32002) →
      the agent's own WebRTC leg must still be torn down and status reset, with
      no exception, so the agent can always hang up.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from app.libs import realtime as realtime_module
from app.libs.telephony.base import CallEvent, TelephonyRPCError
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
from app.services.call_center import orchestrator as orch_module
from app.services.call_center.nodes import AssignQueueExecutor, End, ExecutionContext
from app.services.call_center.orchestrator import CallCenterOrchestrator
from app.services.call_record_service import CallRecordService
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService
from app.services.system_settings_service import SystemSettingsService


class _FakeTransport:
    def __init__(self) -> None:
        self.emits: list[tuple[str, dict, str | None]] = []

    async def emit(self, event, data, *, room=None, to=None, namespace=None):
        self.emits.append((event, data, room))


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
    def __init__(self, row):
        self.row = row

    async def __aenter__(self):
        return _FakeDb(self.row)

    async def __aexit__(self, *_exc):
        return False


async def _prepare_ringing(fake_redis, *, tenant_id=7, employee_id=42, call_id="call-1", offer_id="offer-1"):
    await CcAgentResourceService.set_visible_status(fake_redis, tenant_id, employee_id, "ready")
    await CcAgentResourceService.reserve_inbound(
        fake_redis, tenant_id, employee_id,
        call_id=call_id, offer_id=offer_id, queue_id=9, ttl_seconds=30,
    )
    await CcAgentResourceService.mark_ringing(
        fake_redis, tenant_id, employee_id,
        offer_id=offer_id, call_id=call_id, ttl_seconds=30,
    )


# ─────────────────── (a) caller hangs up while offer ringing ───────────────────


@pytest.mark.asyncio
async def test_withdraw_pending_offer_frees_agent_and_stops_ringing(monkeypatch):
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    transport = _FakeTransport()
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(orch_module, "get_realtime_transport", lambda: transport)
    monkeypatch.setattr(realtime_module, "get_realtime_transport", lambda: transport)
    await _prepare_ringing(fake_redis)

    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    future = orch.register_offer("offer-1")

    await orch._withdraw_pending_offer(
        tenant_id=7,
        call_id="call-1",
        pending_offer={"offer_id": "offer-1", "employee_id": 42},
        reason="caller_hangup",
    )

    # Workflow executor is woken with a non-accept decision so it exits promptly.
    assert future.done() is True
    assert future.result() == {"accept": False, "reason": "caller_hangup"}

    # Reserved agent is freed.
    snapshot = await CcAgentResourceService.get_snapshot(fake_redis, 7, 42)
    assert snapshot is not None
    assert snapshot["resource_state"] == "idle"
    assert snapshot["last_release_reason"] == "caller_hangup"

    # Agent browser is told to stop ringing.
    assert any(
        event == "cc.call_hangup" and room == "agent:7:42"
        for event, _data, room in transport.emits
    )


# ─────────────────── (b) bridge when peer call missing ───────────────────


class _CapturingOrchestrator:
    def __init__(self) -> None:
        self.finalized: list[dict] = []

    async def finalize_agent_call(self, *, tenant_id, employee_id, call_id, reason, mark_cdr_completed=False):
        self.finalized.append({
            "tenant_id": tenant_id,
            "employee_id": employee_id,
            "call_id": call_id,
            "reason": reason,
            "mark_cdr_completed": mark_cdr_completed,
        })


@pytest.mark.asyncio
async def test_bridge_aborts_when_peer_call_missing(monkeypatch):
    async def _bridge_asr_enabled(_tenant_id):
        return True

    monkeypatch.setattr(
        SystemSettingsService,
        "is_bridge_asr_enabled_managed",
        _bridge_asr_enabled,
    )

    tel = MockTelephonyClient()
    await tel.connect()
    tel.bridge_error = TelephonyRPCError(-32002, "call not found: call-1")

    capturing = _CapturingOrchestrator()
    ctx = ExecutionContext(
        call_id="call-1",
        tenant_id=7,
        telephony=tel,
        variables={"__orchestrator__": capturing},
    )

    step = await AssignQueueExecutor()._bridge_to_agent(
        ctx, webrtc_call_id="webrtc-1", employee_id=42, redis=None,
    )

    assert isinstance(step, End)
    assert step.reason == "bridge_aborted"

    methods = [(m, p.get("call_id")) for m, p in tel.recorded]
    # Bridge was attempted (and rejected), then the agent's OWN webrtc leg torn down.
    assert ("call.bridge", "call-1") in methods
    assert ("call.hangup", "webrtc-1") in methods

    # Agent status reset is delegated to the orchestrator with CDR finalization.
    assert capturing.finalized == [{
        "tenant_id": 7,
        "employee_id": 42,
        "call_id": "call-1",
        "reason": "caller_gone",
        "mark_cdr_completed": True,
    }]


# ─────────────────── (c) agent hangup when customer call already gone ──────────


@pytest.mark.asyncio
async def test_agent_hangup_when_customer_gone_resets_status(monkeypatch):
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    transport = _FakeTransport()

    row = SimpleNamespace(
        id=1,
        tenant_id=7,
        agent_id=42,
        state="in_progress",
        started_at=None,
        root_call_id="sip-customer",
        call_id="sip-customer",
    )
    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _FakeSession(row))
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(orch_module, "get_realtime_transport", lambda: transport)
    monkeypatch.setattr(realtime_module, "get_realtime_transport", lambda: transport)

    async def _get_active(_db, _tenant_id, _employee_id):
        return {"webrtc_call_id": "webrtc-1"}

    pg_calls: list[tuple] = []

    async def _sync_pg(_db, tenant_id, employee_id, status, reason=None):
        pg_calls.append((tenant_id, employee_id, status))
        return {}

    set_busy_calls: list[tuple] = []

    async def _set_busy(_db, tenant_id, employee_id, busy):
        set_busy_calls.append((tenant_id, employee_id, busy))
        return None

    mark_completed_calls: list[str] = []

    async def _mark_completed(_db, _tenant_id, _call_id, *, hangup_reason=None, end_state="completed"):
        mark_completed_calls.append(_call_id)
        return None

    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _get_active)
    monkeypatch.setattr(CcAgentStatusService, "sync_pg_status", _sync_pg)
    monkeypatch.setattr(AgentWebRTCSessionService, "set_busy", _set_busy)
    monkeypatch.setattr(CallRecordService, "mark_completed", _mark_completed)

    # Agent is mid-call on the (now-gone) customer leg.
    await CcAgentResourceService.set_visible_status(fake_redis, 7, 42, "ready")
    await CcAgentResourceService.reserve_inbound(
        fake_redis, 7, 42, call_id="sip-customer", offer_id="o1", queue_id=9, ttl_seconds=30,
    )
    await CcAgentResourceService.mark_in_call(
        fake_redis, 7, 42, call_id="sip-customer", direction="inbound", offer_id="o1",
    )

    tel = MockTelephonyClient()
    await tel.connect()
    # Customer SIP leg is already gone; agent's own webrtc leg hangs up fine.
    tel.hangup_errors["sip-customer"] = TelephonyRPCError(-32002, "call not found: sip-customer")

    orch = CallCenterOrchestrator(telephony=tel)
    orch._workflows["sip-customer"] = SimpleNamespace()
    await orch._claim_call("sip-customer")
    result = await orch.hangup_agent_current_call(tenant_id=7, employee_id=42)

    assert result == {"ok": True, "note": "already_ended", "call_id": "sip-customer"}

    # No kernel call.hangup will arrive for a leg the kernel has forgotten, so
    # the orchestrator must drop its own state here. Leaving it behind pins the
    # workflow for the life of the process and stalls blue/green drain.
    assert "sip-customer" not in orch._workflows
    assert await fake_redis.exists(orch._call_owner_key("sip-customer")) == 0

    methods = [(m, p.get("call_id")) for m, p in tel.recorded]
    # Agent's own webrtc leg is torn down (so the browser can hang up)...
    assert ("call.hangup", "webrtc-1") in methods
    # ...and the customer leg was attempted (rejected -32002, treated as success).
    assert ("call.hangup", "sip-customer") in methods

    # Agent status is reset out of busy.
    assert (7, 42, "after_call_work") in pg_calls
    assert (7, 42, False) in set_busy_calls
    snapshot = await CcAgentResourceService.get_snapshot(fake_redis, 7, 42)
    assert snapshot is not None
    assert snapshot["visible_status"] == "after_call_work"
    assert any(event == "cc.call_hangup" for event, _data, _room in transport.emits)
    # CDR finalization belongs to the in-flight call.hangup event, not this path.
    assert mark_completed_calls == []


@pytest.mark.asyncio
async def test_agent_hangup_no_active_call_returns_error(monkeypatch):
    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _FakeSession(None))

    async def _no_session(_db, _tenant_id, _employee_id):
        return None

    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _no_session)
    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    result = await orch.hangup_agent_current_call(tenant_id=7, employee_id=42)
    assert result == {"ok": False, "error": "no_active_call"}


@pytest.mark.asyncio
async def test_agent_hangup_internal_participant_tears_down_leg(monkeypatch):
    """An internal-ring participant (consult / conference target) has a WebRTC
    leg but no CDR — hanging up tears down their leg and resets them, rather
    than returning 'no_active_call' and leaving them stuck 通话中."""

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    transport = _FakeTransport()

    # No CDR for this agent (row=None), but they hold an internal WebRTC leg.
    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _FakeSession(None))
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(orch_module, "get_realtime_transport", lambda: transport)
    monkeypatch.setattr(realtime_module, "get_realtime_transport", lambda: transport)

    async def _get_active(_db, _tenant_id, _employee_id):
        return {"webrtc_call_id": "internal-web-1"}

    async def _sync_pg(_db, tenant_id, employee_id, status, reason=None):
        return {}

    async def _set_busy(_db, tenant_id, employee_id, busy):
        return None

    monkeypatch.setattr(AgentWebRTCSessionService, "get_active", _get_active)
    monkeypatch.setattr(CcAgentStatusService, "sync_pg_status", _sync_pg)
    monkeypatch.setattr(AgentWebRTCSessionService, "set_busy", _set_busy)

    # The participant is occupied in_call on their internal leg.
    await CcAgentResourceService.set_visible_status(fake_redis, 7, 42, "ready")
    await CcAgentResourceService.reserve_inbound(
        fake_redis, 7, 42, call_id="internal-offer", offer_id="io1", queue_id=9, ttl_seconds=30,
    )
    await CcAgentResourceService.mark_in_call(
        fake_redis, 7, 42, call_id="internal-offer", direction="inbound", offer_id="io1",
    )

    tel = MockTelephonyClient()
    await tel.connect()
    orch = CallCenterOrchestrator(telephony=tel)
    result = await orch.hangup_agent_current_call(tenant_id=7, employee_id=42)

    assert result == {"ok": True, "note": "left_internal_call", "call_id": "internal-web-1"}
    methods = [(m, p.get("call_id")) for m, p in tel.recorded]
    assert ("call.hangup", "internal-web-1") in methods
    # Their browser is told to close; their occupied resource is freed.
    assert any(event == "cc.call_hangup" for event, _data, _room in transport.emits)
    snapshot = await CcAgentResourceService.get_snapshot(fake_redis, 7, 42)
    assert snapshot is None or snapshot["resource_state"] != "in_call"


@pytest.mark.asyncio
async def test_finalize_agent_call_keeps_live_satisfaction_workflow(monkeypatch):
    """Satisfaction handoff ends the agent's participation but leaves the
    customer on the survey. Discarding that workflow would freeze the survey
    after the first prompt (no play_end / DTMF / hangup delivery)."""

    from app.services.call_center.satisfaction_workflow import SatisfactionWorkflow

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    transport = _FakeTransport()
    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _FakeSession(None))
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(orch_module, "get_realtime_transport", lambda: transport)
    monkeypatch.setattr(realtime_module, "get_realtime_transport", lambda: transport)
    monkeypatch.setattr(CcAgentStatusService, "sync_pg_status", AsyncMock(return_value={}))
    monkeypatch.setattr(AgentWebRTCSessionService, "set_busy", AsyncMock(return_value=None))

    await CcAgentResourceService.set_visible_status(fake_redis, 7, 42, "ready")
    await CcAgentResourceService.reserve_inbound(
        fake_redis, 7, 42, call_id="cust-1", offer_id="o1", queue_id=9, ttl_seconds=30,
    )
    await CcAgentResourceService.mark_in_call(
        fake_redis, 7, 42, call_id="cust-1", direction="inbound", offer_id="o1",
    )

    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    survey = SatisfactionWorkflow.__new__(SatisfactionWorkflow)
    survey.done = __import__("asyncio").Event()
    survey.execution_id = 81
    orch._workflows["cust-1"] = survey
    await orch._claim_call("cust-1")

    await orch.finalize_agent_call(
        tenant_id=7,
        employee_id=42,
        call_id="cust-1",
        reason="satisfaction_started",
        mark_cdr_completed=False,
    )

    assert orch._workflows.get("cust-1") is survey
    assert await fake_redis.exists(orch._call_owner_key("cust-1")) == 1
    snap = await CcAgentResourceService.get_snapshot(fake_redis, 7, 42)
    assert snap["visible_status"] == "after_call_work"


@pytest.mark.asyncio
async def test_hangup_without_workflow_settles_agent_from_cdr(monkeypatch):
    """Auto-outbound bridged the agent, then its reception popped the workflow
    (or the process restarted mid-call). The customer-leg hangup finds no
    workflow and no outbound originator, so it must fall back to the CDR's
    last_serving_agent_id to move the agent busy → after_call_work."""
    tenant_id, employee_id, call_id = 1, 42, "call-1"
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await CcAgentResourceService.set_visible_status(redis, tenant_id, employee_id, "ready")
    await CcAgentResourceService.reserve_inbound(
        redis, tenant_id, employee_id, call_id=call_id, offer_id="o1", queue_id=9,
        ttl_seconds=30,
    )
    await CcAgentResourceService.mark_in_call(
        redis, tenant_id, employee_id, call_id=call_id, direction="outbound"
    )

    row = SimpleNamespace(
        call_id=call_id,
        root_call_id=call_id,
        tenant_id=tenant_id,
        lifecycle_status="answered",
        customer_connected_at=datetime.now(timezone.utc),
        last_serving_agent_id=employee_id,
    )

    class _Result:
        def scalar_one_or_none(self):
            return row

    class _FakeDb:
        async def execute(self, _q):
            return _Result()

        async def scalar(self, _q):
            return None  # no auto-outbound task wrap-up override

    class _Session:
        async def __aenter__(self):
            return _FakeDb()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: redis)
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.mark_completed",
        AsyncMock(),
    )
    set_busy = AsyncMock()
    monkeypatch.setattr(AgentWebRTCSessionService, "set_busy", set_busy)
    sync_pg = AsyncMock()
    monkeypatch.setattr(
        "app.services.cc_agent_status_service.CcAgentStatusService.sync_pg_status",
        sync_pg,
    )
    monkeypatch.setattr(
        "app.services.system_settings_service.SystemSettingsService.get_settings",
        AsyncMock(return_value=SimpleNamespace(call_wrapup_seconds=60)),
    )
    transport = _FakeTransport()
    monkeypatch.setattr(realtime_module, "get_realtime_transport", lambda: transport)

    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    monkeypatch.setattr(orch, "_maybe_release_sip_occupancy", AsyncMock())

    async def _noop_cleanup(_call_id):
        return None

    monkeypatch.setattr(orch, "_delayed_trace_cleanup", _noop_cleanup)

    await orch._on_hangup(
        CallEvent(method="call.hangup", data={"call_id": call_id, "reason": "bye"})
    )

    snapshot = await CcAgentResourceService.get_snapshot(redis, tenant_id, employee_id)
    assert snapshot["resource_state"] == "after_call_work"
    assert snapshot["visible_status"] == "after_call_work"
    set_busy.assert_awaited_once()
    assert set_busy.await_args.kwargs["busy"] is False
    sync_pg.assert_awaited_once()
    assert sync_pg.await_args.args[3] == "after_call_work"
    methods = [m for m, _, _ in transport.emits]
    assert "cc.call_hangup" in methods


@pytest.mark.asyncio
async def test_hangup_fallback_skips_agent_who_moved_on(monkeypatch):
    """The CDR fallback must not touch an agent whose resource already left
    this call (e.g. they took a new call after a stale workflow cleanup)."""
    tenant_id, employee_id, call_id = 1, 42, "call-1"
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await CcAgentResourceService.set_visible_status(redis, tenant_id, employee_id, "ready")
    await CcAgentResourceService.reserve_inbound(
        redis, tenant_id, employee_id, call_id="call-2", offer_id="o2", queue_id=9,
        ttl_seconds=30,
    )
    await CcAgentResourceService.mark_in_call(
        redis, tenant_id, employee_id, call_id="call-2", direction="outbound"
    )

    row = SimpleNamespace(
        call_id=call_id,
        root_call_id=call_id,
        tenant_id=tenant_id,
        lifecycle_status="answered",
        customer_connected_at=datetime.now(timezone.utc),
        last_serving_agent_id=employee_id,
    )

    class _Result:
        def scalar_one_or_none(self):
            return row

    class _FakeDb:
        async def execute(self, _q):
            return _Result()

        async def scalar(self, _q):
            return None

    class _Session:
        async def __aenter__(self):
            return _FakeDb()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: redis)
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.mark_completed",
        AsyncMock(),
    )
    set_busy = AsyncMock()
    monkeypatch.setattr(AgentWebRTCSessionService, "set_busy", set_busy)
    sync_pg = AsyncMock()
    monkeypatch.setattr(
        "app.services.cc_agent_status_service.CcAgentStatusService.sync_pg_status",
        sync_pg,
    )
    transport = _FakeTransport()
    monkeypatch.setattr(realtime_module, "get_realtime_transport", lambda: transport)

    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    monkeypatch.setattr(orch, "_maybe_release_sip_occupancy", AsyncMock())

    async def _noop_cleanup(_call_id):
        return None

    monkeypatch.setattr(orch, "_delayed_trace_cleanup", _noop_cleanup)

    await orch._on_hangup(
        CallEvent(method="call.hangup", data={"call_id": call_id, "reason": "bye"})
    )

    snapshot = await CcAgentResourceService.get_snapshot(redis, tenant_id, employee_id)
    assert snapshot["resource_state"] == "in_call"
    assert snapshot["current_call_id"] == "call-2"
    set_busy.assert_not_awaited()
    sync_pg.assert_not_awaited()
