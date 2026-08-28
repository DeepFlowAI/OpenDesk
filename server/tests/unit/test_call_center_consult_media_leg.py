"""Consult must bridge the live agent media leg, not a stale softphone session."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NotFoundError
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center import call_control_service as ccs_mod
from app.services.call_center.call_control_service import (
    CallControlService,
    CurrentCall,
    InCallLegs,
    _clear_legs,
    _consult_target_grace_tasks,
    _in_call_state,
)


@pytest.fixture(autouse=True)
def _clear_incall(monkeypatch):
    from app.repositories.call_satisfaction_execution_repository import (
        CallSatisfactionExecutionRepository,
    )

    # Fake CDR sessions in this file answer every execute(); without this stub
    # media_reconnect's survey guard would treat that CDR row as an execution.
    monkeypatch.setattr(
        CallSatisfactionExecutionRepository,
        "get_by_call_record_id",
        AsyncMock(return_value=None),
    )
    _in_call_state.clear()
    for task in list(_consult_target_grace_tasks.values()):
        task.cancel()
    _consult_target_grace_tasks.clear()
    yield
    _in_call_state.clear()
    for task in list(_consult_target_grace_tasks.values()):
        task.cancel()
    _consult_target_grace_tasks.clear()


@pytest.mark.asyncio
async def test_resolve_current_call_prefers_bound_media_leg(monkeypatch):
    async def _fake_db():
        raise AssertionError("should not open DB when only checking preference logic")

    # Patch the DB path with a minimal fake session that returns a CDR + session.
    class _FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(
                id=9,
                root_call_id=None,
                call_id="cust-1",
            )

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, *_a, **_k):
            return _FakeResult()

    monkeypatch.setattr(ccs_mod, "AsyncSessionLocal", lambda: _FakeSession())

    async def _fake_session(_db, _tid, _eid):
        return {"webrtc_call_id": "stale-softphone"}

    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "get_active",
        staticmethod(_fake_session),
    )

    await CallControlService.bind_agent_media_leg(1, 7, "live-leg")
    call = await CallControlService._resolve_current_call(1, 7)
    assert call.customer_call_id == "cust-1"
    assert call.webrtc_call_id == "live-leg"


@pytest.mark.asyncio
async def test_resolve_current_call_rejects_cdr_owned_by_previous_call(monkeypatch):
    """A new ringing offer must not reconnect media to an old active CDR."""

    class _FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(id=9, root_call_id=None, call_id="stale-outbound")

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, *_a, **_k):
            return _FakeResult()

    fake_redis = object()
    monkeypatch.setattr(ccs_mod, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "get_active",
        staticmethod(AsyncMock(return_value={"webrtc_call_id": "stale-leg"})),
    )
    from app.services.call_center import orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(
        ccs_mod.CcAgentResourceService,
        "get_snapshot",
        classmethod(
            AsyncMock(
                return_value={
                    "resource_state": "ringing",
                    "current_call_id": "new-inbound",
                }
            )
        ),
    )

    with pytest.raises(NotFoundError, match="状态已变化"):
        await CallControlService._resolve_current_call(1, 7)


@pytest.mark.asyncio
async def test_bind_agent_media_clears_stale_consult_from_prior_call():
    """A new customer bridge must not keep a leftover 结束咨询 Redis pointer."""
    _in_call_state[(1, 7)] = InCallLegs(
        agent_media_call_id="old-leg",
        consult_call_id="stale-consult",
        consult_target_employee_id=13,
        consult_offer_id="offer-x",
    )

    await CallControlService.bind_agent_media_leg(1, 7, "new-leg")

    legs = _in_call_state[(1, 7)]
    assert legs.agent_media_call_id == "new-leg"
    assert legs.consult_call_id is None
    assert legs.consult_target_employee_id is None
    assert legs.consult_offer_id is None


@pytest.mark.asyncio
async def test_bind_agent_media_preserves_consult_when_requested():
    _in_call_state[(1, 7)] = InCallLegs(
        agent_media_call_id="old-leg",
        consult_call_id="b-leg",
        consult_target_employee_id=13,
    )

    await CallControlService.bind_agent_media_leg(
        1, 7, "new-leg", preserve_consult=True,
    )

    legs = _in_call_state[(1, 7)]
    assert legs.agent_media_call_id == "new-leg"
    assert legs.consult_call_id == "b-leg"
    assert legs.consult_target_employee_id == 13


@pytest.mark.asyncio
async def test_consult_bridge_failure_restores_customer(monkeypatch):
    tel = MockTelephonyClient()
    await tel.connect()
    tel.bridge_error = RuntimeError("bridge boom")

    call = CurrentCall(
        record_id=1,
        tenant_id=1,
        customer_call_id="cust-1",
        webrtc_call_id="agent-leg",
    )
    _in_call_state[(1, 1)] = InCallLegs(agent_media_call_id="agent-leg")

    monkeypatch.setattr(
        CallControlService,
        "_resolve_initiator_display",
        staticmethod(AsyncMock(return_value="A")),
    )
    monkeypatch.setattr(
        CallControlService,
        "_play_scene_tone",
        staticmethod(AsyncMock()),
    )
    monkeypatch.setattr(
        CallControlService,
        "_customer_context_for_call",
        staticmethod(AsyncMock(return_value={"source_call_id": "cust-1"})),
    )
    monkeypatch.setattr(
        CallControlService,
        "_notify_consult_failed",
        staticmethod(AsyncMock()),
    )
    monkeypatch.setattr(
        CallControlService,
        "_release_internal_target",
        staticmethod(AsyncMock()),
    )
    restore = AsyncMock()
    monkeypatch.setattr(
        CallControlService,
        "_restore_after_consult_failure",
        staticmethod(restore),
    )

    class _ICS:
        @staticmethod
        async def initiate_webrtc_consult(*_a, **_k):
            return {
                "ok": True,
                "target_webrtc_call_id": "target-leg",
                "offer_id": "off-1",
            }

    monkeypatch.setattr(
        "app.services.call_center.internal_consult_service.InternalConsultService",
        _ICS,
    )
    monkeypatch.setattr(
        "app.services.call_center.orchestrator._get_redis_client",
        lambda: object(),
    )

    # Drive the background ring task inline.
    import asyncio

    tasks: list[asyncio.Task] = []
    real_create = asyncio.create_task

    def _capture(coro, **kwargs):
        t = real_create(coro, **kwargs)
        tasks.append(t)
        return t

    monkeypatch.setattr(asyncio, "create_task", _capture)

    await CallControlService._consult_webrtc_employee(
        tel,
        tenant_id=1,
        employee_id=1,
        target_employee_id=13,
        call=call,
    )
    assert tasks
    await tasks[0]

    restore.assert_awaited()
    bridge_calls = [r for r in tel.recorded if r[0] == "call.bridge"]
    assert bridge_calls
    assert bridge_calls[-1][1]["keepalive_on_peer_hangup"] is True


@pytest.mark.asyncio
async def test_media_reconnect_bridges_customer_and_binds_leg(monkeypatch):
    tel = MockTelephonyClient()
    await tel.connect()
    tel.webrtc_offer_response = {"call_id": "new-leg", "sdp": "v=0-answer"}
    tel.call_list_response = [{"call_id": "cust-1"}]

    class _FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(id=1, root_call_id=None, call_id="cust-1")

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, *_a, **_k):
            return _FakeResult()

    monkeypatch.setattr(ccs_mod, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "get_active",
        staticmethod(AsyncMock(return_value={"webrtc_call_id": "dead-leg"})),
    )
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "upsert_with_real_call_id",
        staticmethod(AsyncMock()),
    )
    monkeypatch.setattr(
        CallControlService,
        "_stop_tone",
        staticmethod(AsyncMock()),
    )
    _in_call_state[(7, 42)] = InCallLegs(agent_media_call_id="dead-leg")

    result = await CallControlService.media_reconnect(
        tel, tenant_id=7, employee_id=42, sdp="v=0-offer",
    )

    assert result["call_id"] == "new-leg"
    assert result["sdp"] == "v=0-answer"
    assert result.get("consult_active") is False
    assert (
        "call.bridge",
        {
            "call_id": "cust-1",
            "other_call_id": "new-leg",
            "transcribe": True,
            "keepalive_on_peer_hangup": True,
        },
    ) in tel.recorded
    assert _in_call_state[(7, 42)].agent_media_call_id == "new-leg"


@pytest.mark.asyncio
async def test_media_reconnect_rejoins_existing_room_after_refresh(monkeypatch):
    """Refreshing an agent under whisper/barge must rejoin the room, not bridge
    an already-roomed customer a second time (bridged -> bridged)."""
    tel = MockTelephonyClient()
    await tel.connect()
    tel.webrtc_offer_response = {"call_id": "new-leg", "sdp": "v=0-answer"}
    tel.call_list_response = [{"call_id": "cust-1"}]

    class _FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(id=1, root_call_id=None, call_id="cust-1")

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, *_a, **_k):
            return _FakeResult()

    monkeypatch.setattr(ccs_mod, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "get_active",
        staticmethod(AsyncMock(return_value={"webrtc_call_id": "old-leg"})),
    )
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "upsert_with_real_call_id",
        staticmethod(AsyncMock()),
    )
    monkeypatch.setattr(
        CallControlService,
        "_stop_tone",
        staticmethod(AsyncMock()),
    )
    _in_call_state[(7, 42)] = InCallLegs(
        agent_media_call_id="old-leg",
        room_id="room-1",
        room_legs=["cust-1", "old-leg", "supervisor-leg"],
    )

    result = await CallControlService.media_reconnect(
        tel, tenant_id=7, employee_id=42, sdp="v=0-offer",
    )

    assert result["call_id"] == "new-leg"
    assert (
        "room.replace_leg",
        {"room_id": "room-1", "old_call_id": "old-leg", "new_call_id": "new-leg"},
    ) in tel.recorded
    assert not any(method == "call.bridge" for method, _params in tel.recorded)
    legs = _in_call_state[(7, 42)]
    assert legs.agent_media_call_id == "new-leg"
    assert legs.room_legs == ["cust-1", "new-leg", "supervisor-leg"]


@pytest.mark.asyncio
async def test_media_reconnect_adds_leg_when_room_already_detached_old_leg(monkeypatch):
    """FlowKit removes a media_eof leg from its room before HTTP reconnect."""
    tel = MockTelephonyClient()
    await tel.connect()
    tel.webrtc_offer_response = {"call_id": "new-leg", "sdp": "v=0-answer"}
    tel.call_list_response = [{"call_id": "cust-1"}]
    tel.room_replace_leg = AsyncMock(side_effect=RuntimeError("room: leg not found"))

    class _FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(id=1, root_call_id=None, call_id="cust-1")

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, *_a, **_k):
            return _FakeResult()

    monkeypatch.setattr(ccs_mod, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "get_active",
        staticmethod(AsyncMock(return_value={"webrtc_call_id": "old-leg"})),
    )
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "upsert_with_real_call_id",
        staticmethod(AsyncMock()),
    )
    _in_call_state[(7, 42)] = InCallLegs(
        agent_media_call_id="old-leg",
        room_id="room-1",
        room_legs=["cust-1", "old-leg", "supervisor-leg"],
    )

    await CallControlService.media_reconnect(
        tel, tenant_id=7, employee_id=42, sdp="v=0-offer",
    )

    assert (
        "room.add_leg",
        {"room_id": "room-1", "call_id": "new-leg"},
    ) in tel.recorded
    assert not any(method == "call.bridge" for method, _params in tel.recorded)


@pytest.mark.asyncio
async def test_media_reconnect_preserves_active_consult(monkeypatch):
    """Initiator browser refresh mid-consult must keep A↔B and consult UI state."""
    tel = MockTelephonyClient()
    await tel.connect()
    tel.webrtc_offer_response = {"call_id": "new-leg", "sdp": "v=0-answer"}
    tel.call_list_response = [{"call_id": "cust-1"}]

    class _FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(id=1, root_call_id=None, call_id="cust-1")

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, *_a, **_k):
            return _FakeResult()

    monkeypatch.setattr(ccs_mod, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "get_active",
        staticmethod(AsyncMock(return_value={"webrtc_call_id": "dead-leg"})),
    )
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "upsert_with_real_call_id",
        staticmethod(AsyncMock()),
    )
    stop_tone = AsyncMock()
    monkeypatch.setattr(
        CallControlService,
        "_stop_tone",
        staticmethod(stop_tone),
    )
    release = AsyncMock()
    ended = AsyncMock()
    monkeypatch.setattr(
        CallControlService, "_release_internal_target", staticmethod(release)
    )
    monkeypatch.setattr(
        CallControlService, "_notify_browser_call_ended", staticmethod(ended)
    )
    _in_call_state[(7, 42)] = InCallLegs(
        agent_media_call_id="dead-leg",
        consult_call_id="consult-leg",
        consult_target_employee_id=13,
        consult_offer_id="offer-1",
    )

    result = await CallControlService.media_reconnect(
        tel, tenant_id=7, employee_id=42, sdp="v=0-offer",
    )

    assert result["call_id"] == "new-leg"
    assert result["consult_active"] is True
    assert result["consult_target_employee_id"] == 13
    legs = _in_call_state[(7, 42)]
    assert legs.consult_call_id == "consult-leg"
    assert legs.consult_target_employee_id == 13
    assert legs.agent_media_call_id == "new-leg"
    release.assert_not_awaited()
    ended.assert_not_awaited()
    stop_tone.assert_not_awaited()
    hangups = [r for r in tel.recorded if r[0] == "call.hangup"]
    assert not any(r[1].get("call_id") == "consult-leg" for r in hangups)
    # Re-bridge initiator ↔ consult target (not customer).
    bridges = [r for r in tel.recorded if r[0] == "call.bridge"]
    assert any(
        r[1].get("call_id") == "new-leg" and r[1].get("other_call_id") == "consult-leg"
        for r in bridges
    )
    assert not any(
        r[1].get("call_id") == "cust-1" and r[1].get("other_call_id") == "new-leg"
        for r in bridges
    )


@pytest.mark.asyncio
async def test_consult_target_departed_requests_media_reconnect_on_bridge_fail(
    monkeypatch,
):
    import fakeredis.aioredis

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    tel = MockTelephonyClient()
    await tel.connect()
    tel.bridge_error = RuntimeError("call not found")

    legs = InCallLegs(
        agent_media_call_id="dead-leg",
        consult_call_id="target-leg",
        consult_target_employee_id=13,
    )
    await r.set("cc:agent:incall:7:42", json.dumps(legs.to_dict()))

    monkeypatch.setattr(
        "app.services.call_center.orchestrator._get_redis_client",
        lambda: r,
    )
    monkeypatch.setattr(
        "app.libs.telephony.get_telephony_client",
        lambda: tel,
    )
    monkeypatch.setattr(
        CallControlService,
        "_resolve_current_call",
        staticmethod(
            AsyncMock(
                return_value=CurrentCall(
                    record_id=1,
                    tenant_id=7,
                    customer_call_id="cust-1",
                    webrtc_call_id="dead-leg",
                )
            )
        ),
    )
    monkeypatch.setattr(
        CallControlService,
        "_release_internal_target",
        staticmethod(AsyncMock()),
    )
    monkeypatch.setattr(
        CallControlService,
        "_agent_uses_sip_phone",
        staticmethod(AsyncMock(return_value=False)),
    )
    monkeypatch.setattr(ccs_mod.asyncio, "sleep", AsyncMock())
    ended = AsyncMock()
    monkeypatch.setattr(
        CallControlService,
        "_notify_browser_call_ended",
        staticmethod(ended),
    )
    play_tone = AsyncMock()
    monkeypatch.setattr(
        CallControlService,
        "_play_scene_tone",
        staticmethod(play_tone),
    )
    monkeypatch.setattr(
        CallControlService,
        "_stop_tone",
        staticmethod(AsyncMock()),
    )
    notified: list[tuple] = []

    async def _notify(*, tenant_id, initiator_employee_id, method, payload):
        notified.append((tenant_id, initiator_employee_id, method, payload))

    monkeypatch.setattr(
        CallControlService,
        "_notify_control_result",
        staticmethod(_notify),
    )

    ok = await CallControlService.on_consult_target_departed(
        "target-leg", reason="agent_hangup",
    )
    assert ok is True
    play_tone.assert_awaited()
    ended.assert_awaited_once()
    assert ended.await_args.args[:3] == (7, 13, "target-leg")
    reconnect = [
        n for n in notified if n[2] == "cc.media_reconnect_required"
    ]
    assert len(reconnect) == 1
    assert reconnect[0][3]["customer_call_id"] == "cust-1"
    # Must unbridge A↔B before retrying customer↔A.
    assert any(r[0] == "call.unbridge" for r in tel.recorded)
    consult = [n for n in notified if n[2] == "cc.consult_result"]
    assert consult
    assert consult[0][3]["ok"] is True
    assert consult[0][3]["ended"] is True
    assert consult[0][3]["resumed"] is False


@pytest.mark.asyncio
async def test_consult_target_departed_sip_host_skips_browser_reconnect(
    monkeypatch,
):
    """SIP A must not get media_reconnect_required — that steals the handset bridge."""
    import fakeredis.aioredis

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    tel = MockTelephonyClient()
    await tel.connect()
    tel.bridge_error = RuntimeError("call already bridged")

    legs = InCallLegs(
        agent_media_call_id="a-sip-leg",
        consult_call_id="target-leg",
        consult_target_employee_id=13,
    )
    await r.set("cc:agent:incall:7:1", json.dumps(legs.to_dict()))

    monkeypatch.setattr(
        "app.services.call_center.orchestrator._get_redis_client",
        lambda: r,
    )
    monkeypatch.setattr(
        "app.libs.telephony.get_telephony_client",
        lambda: tel,
    )
    monkeypatch.setattr(
        CallControlService,
        "_resolve_current_call",
        staticmethod(
            AsyncMock(
                return_value=CurrentCall(
                    record_id=1,
                    tenant_id=7,
                    customer_call_id="cust-1",
                    webrtc_call_id="a-sip-leg",
                )
            )
        ),
    )
    monkeypatch.setattr(
        CallControlService,
        "_release_internal_target",
        staticmethod(AsyncMock()),
    )
    monkeypatch.setattr(
        CallControlService,
        "_agent_uses_sip_phone",
        staticmethod(AsyncMock(return_value=True)),
    )
    monkeypatch.setattr(ccs_mod.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(
        CallControlService,
        "_notify_browser_call_ended",
        staticmethod(AsyncMock()),
    )
    monkeypatch.setattr(
        CallControlService,
        "_play_scene_tone",
        staticmethod(AsyncMock()),
    )
    monkeypatch.setattr(
        CallControlService,
        "_stop_tone",
        staticmethod(AsyncMock()),
    )
    notified: list[tuple] = []

    async def _notify(*, tenant_id, initiator_employee_id, method, payload):
        notified.append((tenant_id, initiator_employee_id, method, payload))

    monkeypatch.setattr(
        CallControlService,
        "_notify_control_result",
        staticmethod(_notify),
    )

    ok = await CallControlService.on_consult_target_departed(
        "target-leg", reason="agent_hangup",
    )
    assert ok is True
    reconnect = [
        n for n in notified if n[2] == "cc.media_reconnect_required"
    ]
    assert reconnect == []
    assert any(r[0] == "call.unbridge" for r in tel.recorded)


@pytest.mark.asyncio
async def test_media_reconnect_consult_target_rebridges_to_host(monkeypatch):
    """B (Web consult target) refresh rebuilds media against A's host leg."""
    tel = MockTelephonyClient()
    await tel.connect()
    tel.webrtc_offer_response = {"call_id": "b-new-leg", "sdp": "v=0-answer"}

    class _FakeSessionCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    _in_call_state[(7, 1)] = InCallLegs(
        agent_media_call_id="a-sip-leg",
        consult_call_id="b-old-leg",
        consult_target_employee_id=13,
    )

    monkeypatch.setattr(
        CallControlService,
        "_resolve_current_call",
        staticmethod(
            AsyncMock(
                return_value=CurrentCall(
                    record_id=1,
                    tenant_id=7,
                    customer_call_id="cust-1",
                    webrtc_call_id="a-sip-leg",
                )
            )
        ),
    )
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "upsert_with_real_call_id",
        staticmethod(AsyncMock()),
    )
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "set_busy",
        staticmethod(AsyncMock()),
    )
    monkeypatch.setattr(ccs_mod, "AsyncSessionLocal", lambda: _FakeSessionCtx())
    mark_in_call = AsyncMock()
    monkeypatch.setattr(
        ccs_mod.CcAgentResourceService,
        "mark_in_call",
        staticmethod(mark_in_call),
    )
    monkeypatch.setattr(
        "app.services.call_center.orchestrator._get_redis_client",
        lambda: object(),
    )

    result = await CallControlService.media_reconnect(
        tel, tenant_id=7, employee_id=13, sdp="v=0-offer",
    )

    assert result["call_id"] == "b-new-leg"
    assert result["consult_active"] is True
    legs = _in_call_state[(7, 1)]
    assert legs.consult_call_id == "b-new-leg"
    bridges = [r for r in tel.recorded if r[0] == "call.bridge"]
    assert any(
        r[1].get("call_id") == "a-sip-leg"
        and r[1].get("other_call_id") == "b-new-leg"
        for r in bridges
    )
    hangups = [r for r in tel.recorded if r[0] == "call.hangup"]
    assert any(r[1].get("call_id") == "b-old-leg" for r in hangups)


@pytest.mark.asyncio
async def test_consult_target_media_loss_waits_for_reconnect(monkeypatch):
    """B refresh must not immediately end consult for A."""
    _in_call_state[(7, 1)] = InCallLegs(
        agent_media_call_id="a-leg",
        consult_call_id="b-leg",
        consult_target_employee_id=13,
    )
    reconnect_notify = AsyncMock()
    monkeypatch.setattr(
        CallControlService,
        "_notify_media_reconnect_required",
        staticmethod(reconnect_notify),
    )
    finalize = AsyncMock(return_value=True)
    monkeypatch.setattr(
        CallControlService,
        "_finalize_consult_target_departed",
        staticmethod(finalize),
    )

    ok = await CallControlService.on_consult_target_departed(
        "b-leg", reason="media_eof",
    )
    assert ok is True
    reconnect_notify.assert_awaited_once()
    finalize.assert_not_awaited()
    assert _in_call_state[(7, 1)].consult_call_id == "b-leg"
    assert _consult_target_grace_tasks


@pytest.mark.asyncio
async def test_consult_host_media_departed_notifies_target(monkeypatch):
    """A SIP hangup during consult must clear B's 通话中 UI."""
    tel = MockTelephonyClient()
    await tel.connect()
    _in_call_state[(7, 1)] = InCallLegs(
        agent_media_call_id="a-sip-leg",
        consult_call_id="b-leg",
        consult_target_employee_id=13,
    )
    monkeypatch.setattr(
        "app.libs.telephony.get_telephony_client",
        lambda: tel,
    )
    release = AsyncMock()
    ended = AsyncMock()
    monkeypatch.setattr(
        CallControlService, "_release_internal_target", staticmethod(release)
    )
    monkeypatch.setattr(
        CallControlService, "_notify_browser_call_ended", staticmethod(ended)
    )
    monkeypatch.setattr(
        CallControlService,
        "_resolve_current_call",
        staticmethod(
            AsyncMock(
                return_value=CurrentCall(
                    record_id=1,
                    tenant_id=7,
                    customer_call_id="cust-1",
                    webrtc_call_id="a-sip-leg",
                )
            )
        ),
    )
    monkeypatch.setattr(
        CallControlService, "_stop_tone", staticmethod(AsyncMock())
    )

    ok = await CallControlService.on_consult_host_media_departed(
        "a-sip-leg", reason="remote_bye",
    )
    assert ok is True
    release.assert_awaited_once()
    ended.assert_awaited_once()
    assert ended.await_args.args[:3] == (7, 13, "b-leg")
    assert (7, 1) not in _in_call_state or _in_call_state[(7, 1)].consult_call_id is None


@pytest.mark.asyncio
async def test_media_reconnect_rejects_while_satisfaction_survey_runs(monkeypatch):
    from app.core.exceptions import ConflictError
    from app.repositories.call_satisfaction_execution_repository import (
        CallSatisfactionExecutionRepository,
    )

    tel = MockTelephonyClient()
    await tel.connect()
    tel.webrtc_offer_response = {"call_id": "new-leg", "sdp": "v=0-answer"}
    tel.call_list_response = [{"call_id": "cust-1"}]

    class _FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(id=1, root_call_id=None, call_id="cust-1")

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, _query):
            return _FakeResult()

    monkeypatch.setattr(ccs_mod, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "get_active",
        staticmethod(AsyncMock(return_value={"webrtc_call_id": "dead-leg"})),
    )
    monkeypatch.setattr(
        CallSatisfactionExecutionRepository,
        "get_by_call_record_id",
        AsyncMock(return_value=SimpleNamespace(id=4, status="in_progress")),
    )
    _in_call_state[(7, 42)] = InCallLegs(agent_media_call_id="dead-leg")

    with pytest.raises(ConflictError, match="满意度调查"):
        await CallControlService.media_reconnect(
            tel, tenant_id=7, employee_id=42, sdp="v=0-offer",
        )
    assert not any(method == "call.bridge" for method, _ in tel.recorded)


@pytest.mark.asyncio
async def test_media_reconnect_skips_when_customer_leg_gone(monkeypatch):
    tel = MockTelephonyClient()
    await tel.connect()
    tel.webrtc_offer_response = {"call_id": "new-leg", "sdp": "v=0-answer"}
    tel.call_list_response = [{"call_id": "other-leg"}]

    class _FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(id=1, root_call_id=None, call_id="cust-1")

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, *_a, **_k):
            return _FakeResult()

    monkeypatch.setattr(ccs_mod, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "get_active",
        staticmethod(AsyncMock(return_value={"webrtc_call_id": "dead-leg"})),
    )
    _in_call_state[(7, 42)] = InCallLegs(agent_media_call_id="dead-leg")

    finalize = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator",
        lambda: SimpleNamespace(finalize_agent_call=finalize),
    )

    with pytest.raises(NotFoundError, match="客户通话已结束"):
        await CallControlService.media_reconnect(
            tel, tenant_id=7, employee_id=42, sdp="v=0-offer",
        )

    assert not any(method == "webrtc.offer" for method, _ in tel.recorded)
    finalize.assert_awaited_once()
    assert finalize.await_args.kwargs["call_id"] == "cust-1"
    assert finalize.await_args.kwargs["reason"] == "media_timeout"
    assert (7, 42) not in _in_call_state


@pytest.mark.asyncio
async def test_media_reconnect_fail_open_when_call_list_errors(monkeypatch):
    tel = MockTelephonyClient()
    await tel.connect()
    tel.webrtc_offer_response = {"call_id": "new-leg", "sdp": "v=0-answer"}
    tel.call_list_response = [{"call_id": "cust-1"}]

    async def _boom():
        raise RuntimeError("kernel down")

    tel.call_list = _boom  # type: ignore[method-assign]

    class _FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(id=1, root_call_id=None, call_id="cust-1")

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, *_a, **_k):
            return _FakeResult()

    monkeypatch.setattr(ccs_mod, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "get_active",
        staticmethod(AsyncMock(return_value={"webrtc_call_id": "dead-leg"})),
    )
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "upsert_with_real_call_id",
        staticmethod(AsyncMock()),
    )
    monkeypatch.setattr(
        CallControlService,
        "_stop_tone",
        staticmethod(AsyncMock()),
    )
    _in_call_state[(7, 42)] = InCallLegs(agent_media_call_id="dead-leg")

    result = await CallControlService.media_reconnect(
        tel, tenant_id=7, employee_id=42, sdp="v=0-offer",
    )

    assert result["call_id"] == "new-leg"
    assert any(method == "webrtc.offer" for method, _ in tel.recorded)


@pytest.mark.asyncio
async def test_media_reconnect_empty_list_is_authoritative_gone(monkeypatch):
    """Single-kernel empty call.list means the customer leg is gone."""
    tel = MockTelephonyClient()
    await tel.connect()
    tel.webrtc_offer_response = {"call_id": "new-leg", "sdp": "v=0-answer"}
    tel.call_list_response = []

    class _FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(id=1, root_call_id=None, call_id="cust-1")

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, *_a, **_k):
            return _FakeResult()

    monkeypatch.setattr(ccs_mod, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "get_active",
        staticmethod(AsyncMock(return_value={"webrtc_call_id": "dead-leg"})),
    )
    _in_call_state[(7, 42)] = InCallLegs(agent_media_call_id="dead-leg")
    finalize = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator",
        lambda: SimpleNamespace(finalize_agent_call=finalize),
    )

    with pytest.raises(NotFoundError, match="客户通话已结束"):
        await CallControlService.media_reconnect(
            tel, tenant_id=7, employee_id=42, sdp="v=0-offer",
        )
    assert not any(method == "webrtc.offer" for method, _ in tel.recorded)
    finalize.assert_awaited_once()


@pytest.mark.asyncio
async def test_media_reconnect_fail_open_when_owner_kernel_not_ready(monkeypatch):
    """Blue/green: owner kernel down must not look like customer gone."""
    from app.libs.telephony.providers.flowkit.multi_client import (
        MultiKernelTelephonyClient,
    )

    multi = MultiKernelTelephonyClient(
        ws_urls=["ws://k0/ws", "ws://k1/ws"],
        sdk_name="test",
        sdk_version="0",
    )
    k0 = MockTelephonyClient()
    k1 = MockTelephonyClient()
    multi._clients = [k0, k1]  # type: ignore[assignment]
    multi._wired = True
    await k0.connect()
    await k1.connect()
    await k0.disconnect()  # owner down
    multi._call_kernel["cust-1"] = 0
    monkeypatch.setattr(
        "app.libs.telephony.providers.flowkit.multi_client._get_redis",
        lambda: None,
    )

    class _FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(id=1, root_call_id=None, call_id="cust-1")

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, *_a, **_k):
            return _FakeResult()

    monkeypatch.setattr(ccs_mod, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "get_active",
        staticmethod(AsyncMock(return_value={"webrtc_call_id": "dead-leg"})),
    )
    monkeypatch.setattr(
        ccs_mod.AgentWebRTCSessionService,
        "upsert_with_real_call_id",
        staticmethod(AsyncMock()),
    )
    monkeypatch.setattr(
        CallControlService,
        "_stop_tone",
        staticmethod(AsyncMock()),
    )
    _in_call_state[(7, 42)] = InCallLegs(agent_media_call_id="dead-leg")

    assert await multi.call_alive("cust-1") is None

    async def _offer(sdp, call_id=None):
        return {"call_id": "new-leg", "sdp": "v=0-answer"}

    multi.webrtc_offer = _offer  # type: ignore[method-assign]
    multi.call_answer = AsyncMock()  # type: ignore[method-assign]
    multi.call_bridge = AsyncMock()  # type: ignore[method-assign]
    multi.call_hangup = AsyncMock()  # type: ignore[method-assign]

    result = await CallControlService.media_reconnect(
        multi, tenant_id=7, employee_id=42, sdp="v=0-offer",
    )
    assert result["call_id"] == "new-leg"
