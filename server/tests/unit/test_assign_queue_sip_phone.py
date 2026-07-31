"""
Unit tests for the inbound SIP-phone branch of assign_queue.

`_try_ring_sip_phone_agent` rings the picked agent's physical extension and
bridges the caller to it on off-hook. WebRTC agents must fall through to the
unchanged browser-offer path (returns the _NOT_SIP_PHONE sentinel).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.call_center.nodes import (
    _NOT_SIP_PHONE,
    AssignQueueExecutor,
    ExecutionContext,
)
from app.services.call_center.orchestrator import get_orchestrator, reset_orchestrator
from app.libs.telephony.providers.mock.client import MockTelephonyClient


@pytest.fixture(autouse=True)
def _reset_orch():
    reset_orchestrator()
    yield
    reset_orchestrator()


def _ctx(telephony) -> ExecutionContext:
    ctx = ExecutionContext(call_id="cust-call", tenant_id=7)
    ctx.telephony = telephony
    ctx.variables["__orchestrator__"] = get_orchestrator()
    ctx.edges_by_source = {"n1": {"timeout": "hangup_node"}}
    return ctx


def _node():
    return {"id": "n1", "data": {}}


@asynccontextmanager
async def _fake_session():
    yield MagicMock()


def _patch_common(monkeypatch, *, device_type, ext):
    from app.services.call_center import nodes as nodes_mod
    from app.services.agent_call_device_service import AgentCallDeviceService
    from app.repositories.sip_extension_repository import SipExtensionRepository

    monkeypatch.setattr(nodes_mod, "AsyncSessionLocal", _fake_session, raising=False)
    # nodes.py imports AsyncSessionLocal locally inside methods, so patch the
    # source module it imports from.
    from app.db import session as session_mod
    monkeypatch.setattr(session_mod, "AsyncSessionLocal", _fake_session)

    async def fake_current_device(_db, _t, _e, _r=None):
        return {"device_type": device_type}

    monkeypatch.setattr(
        AgentCallDeviceService, "get_current_device", fake_current_device,
    )
    monkeypatch.setattr(
        SipExtensionRepository, "get_by_employee", AsyncMock(return_value=ext),
    )


@pytest.mark.asyncio
async def test_webrtc_agent_returns_sentinel(monkeypatch):
    telephony = MockTelephonyClient()
    await telephony.connect()
    _patch_common(monkeypatch, device_type="webrtc", ext=None)

    exe = AssignQueueExecutor()
    result = await exe._try_ring_sip_phone_agent(
        _ctx(telephony), {}, _node(), {"employee_id": 42},
        "offer-1", 30.0, None, get_orchestrator(), MagicMock(),
    )
    assert result is _NOT_SIP_PHONE
    # No extension was rung — the WebRTC path is fully preserved.
    assert not [m for m, _ in telephony.recorded if m == "call.originate"]


@pytest.mark.asyncio
async def test_sip_phone_agent_rings_and_bridges_on_answer(monkeypatch):
    telephony = MockTelephonyClient()
    await telephony.connect()
    telephony.originate_response = {"call_id": "ext-leg", "status": "originating"}
    ext = SimpleNamespace(
        sip_user_id="acme-1001",
        is_active=True,
        registration_status="registered",
        current_occupant_employee_id=42,
    )
    _patch_common(monkeypatch, device_type="sip_phone", ext=ext)

    # Stub out the DB-write services used after off-hook.
    from app.services import call_record_service
    from app.services.cc_agent_status_service import CcAgentStatusService
    from app.services.cc_agent_resource_service import CcAgentResourceService
    from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
    from app.services.system_settings_service import SystemSettingsService

    monkeypatch.setattr(call_record_service.CallRecordService, "mark_answered", AsyncMock())
    monkeypatch.setattr(CcAgentStatusService, "set_status", AsyncMock())
    monkeypatch.setattr(AgentWebRTCSessionService, "set_busy", AsyncMock())
    monkeypatch.setattr(CcAgentResourceService, "mark_ringing", AsyncMock(return_value=None))
    mark_in_call = AsyncMock(return_value=None)
    monkeypatch.setattr(CcAgentResourceService, "mark_in_call", mark_in_call)
    monkeypatch.setattr(
        SystemSettingsService, "is_bridge_asr_enabled_managed", AsyncMock(return_value=True),
    )

    ctx = _ctx(telephony)
    exe = AssignQueueExecutor()

    orch = get_orchestrator()
    orch.notify_agent_incoming = AsyncMock()
    orch.notify_agent_call_answered = AsyncMock()

    async def answer_soon():
        await asyncio.sleep(0.05)
        # Prompt finished (call.play_end) — lets the bridge proceed without
        # waiting out the bounded prompt-finish timeout.
        orch._resolve_play_wait("cust-call", {})
        orch._resolve_leg_wait("ext-leg", {"answered": True})

    answer_task = asyncio.create_task(answer_soon())
    redis = MagicMock()
    result = await exe._try_ring_sip_phone_agent(
        ctx, {}, _node(), {"employee_id": 42},
        "offer-1", 30.0, redis, orch, MagicMock(),
    )
    await answer_task

    assert result is not _NOT_SIP_PHONE
    originates = [a for m, a in telephony.recorded if m == "call.originate"]
    assert originates == [{"extension": "acme-1001"}]
    # Caller SIP leg bridged to the physical extension leg.
    bridges = [a for m, a in telephony.recorded if m == "call.bridge"]
    assert bridges and bridges[0]["call_id"] == "cust-call"
    assert bridges[0]["other_call_id"] == "ext-leg"
    assert ctx.variables["sys._bridged_agent_id"] == 42
    assert ctx.variables["sys._bridged_webrtc_call_id"] == "ext-leg"
    # Off-hook on the handset moves the agent's browser to 通话中 (no click).
    orch.notify_agent_call_answered.assert_awaited_once()
    assert orch.notify_agent_call_answered.await_args.kwargs["call_id"] == "cust-call"
    assert orch.notify_agent_call_answered.await_args.kwargs["employee_id"] == 42
    # Redis must leave ringing so a page refresh restores 通话中, not 来电.
    mark_in_call.assert_awaited_once()
    assert mark_in_call.await_args.args[0] is redis
    assert mark_in_call.await_args.kwargs["call_id"] == "cust-call"
    assert mark_in_call.await_args.kwargs["offer_id"] == "offer-1"


@pytest.mark.asyncio
async def test_sip_phone_no_answer_fails_without_bridge(monkeypatch):
    telephony = MockTelephonyClient()
    await telephony.connect()
    telephony.originate_response = {"call_id": "ext-leg", "status": "originating"}
    ext = SimpleNamespace(
        sip_user_id="acme-1001",
        is_active=True,
        registration_status="registered",
        current_occupant_employee_id=42,
    )
    _patch_common(monkeypatch, device_type="sip_phone", ext=ext)

    ctx = _ctx(telephony)
    exe = AssignQueueExecutor()

    orch = get_orchestrator()
    orch.notify_agent_incoming = AsyncMock()
    orch.notify_agent_call_ended = AsyncMock()

    # timeout_s tiny → no answer → fail branch (goto timeout handle).
    result = await exe._try_ring_sip_phone_agent(
        ctx, {}, _node(), {"employee_id": 42},
        "offer-1", 0.05, None, orch, MagicMock(),
    )
    assert result is not _NOT_SIP_PHONE
    bridges = [m for m, _ in telephony.recorded if m == "call.bridge"]
    assert not bridges  # customer never bridged
    hangups = [a for m, a in telephony.recorded if m == "call.hangup"]
    assert any(h["call_id"] == "ext-leg" for h in hangups)
    assert "sys._bridged_agent_id" not in ctx.variables
    # The ringing incoming shown in the browser is cleared on no-answer.
    orch.notify_agent_call_ended.assert_awaited_once()
    assert orch.notify_agent_call_ended.await_args.kwargs["call_id"] == "cust-call"


@pytest.mark.asyncio
async def test_sip_phone_caller_hangup_cancels_ring(monkeypatch):
    """Caller hangs up while the handset is still ringing → the ring is torn
    down immediately (not left ringing until the assign timeout)."""
    telephony = MockTelephonyClient()
    await telephony.connect()
    telephony.originate_response = {"call_id": "ext-leg", "status": "originating"}
    ext = SimpleNamespace(
        sip_user_id="acme-1001",
        is_active=True,
        registration_status="registered",
        current_occupant_employee_id=42,
    )
    _patch_common(monkeypatch, device_type="sip_phone", ext=ext)

    ctx = _ctx(telephony)
    exe = AssignQueueExecutor()
    orch = get_orchestrator()
    orch.notify_agent_incoming = AsyncMock()
    orch.notify_agent_call_ended = AsyncMock()

    async def caller_hangs_up_soon():
        await asyncio.sleep(0.05)
        # What orchestrator._on_hangup(customer) does: find the ringing handset,
        # tear it down, and resolve the assign wait.
        pending = orch.pop_pending_sip_originate("cust-call")
        assert pending == "ext-leg", "the ringing handset must be tracked"
        await telephony.call_hangup(pending, reason="caller_hangup")
        orch._resolve_leg_wait(pending, {"answered": False, "reason": "caller_hangup"})

    task = asyncio.create_task(caller_hangs_up_soon())
    # timeout 30s — the caller hangup must abort well before it, not ring it out.
    result = await exe._try_ring_sip_phone_agent(
        ctx, {}, _node(), {"employee_id": 42},
        "offer-1", 30.0, None, orch, MagicMock(),
    )
    await task

    assert result is not _NOT_SIP_PHONE
    hangups = [a for m, a in telephony.recorded if m == "call.hangup"]
    assert any(h["call_id"] == "ext-leg" for h in hangups), "handset ring stopped"
    bridges = [m for m, _ in telephony.recorded if m == "call.bridge"]
    assert not bridges  # customer never bridged
