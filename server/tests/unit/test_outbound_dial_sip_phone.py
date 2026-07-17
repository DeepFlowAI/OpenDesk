"""
Unit tests for the SIP-phone two-stage outbound originate (event-driven).

The SIP-phone dial is split so the HTTP request never waits for the agent's
physical phone to go off-hook — no pooled DB connection is held across the long
ring wait, which would otherwise starve the connection pool under load:

  * `/dial` rings the agent's extension and returns immediately with status
    ``ringing_extension`` — the customer is NOT dialed in the request;
  * the orchestrator waits for the extension leg's ``call.answered`` off the
    request path, THEN originates the customer leg and pairs it for bridging;
  * if the extension never answers (hangup / timeout), the orchestrator tears
    the extension leg down and the customer is never dialed.

Also verifies the WebRTC (Web-phone) path is unchanged — the extension is
never rung and the customer is dialed synchronously in the request.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ValidationError
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center.orchestrator import get_orchestrator, reset_orchestrator
from app.services.call_center.outbound_dial_service import OutboundDialService


def _tenant(tid: str = "tenant-x"):
    return SimpleNamespace(tenant_id=tid)


def _phone(**kw):
    base = dict(
        id="pn-1", phone_number="+8602112345678", call_types=["outbound"],
        trunk_id="trunk_sh", called_number_prefix=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _ext(**kw):
    base = dict(
        id=1, sip_user_id="acme-1001", is_active=True,
        registration_status="registered", extension_number="1001",
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _reset_orch():
    reset_orchestrator()
    yield
    reset_orchestrator()


def _patch_repos(monkeypatch, *, device_type, ext=None):
    """Patch phone-number repo, device lookup and extension lookup."""
    from app.services.call_center import outbound_dial_service as mod
    from app.repositories.sip_extension_repository import SipExtensionRepository

    repo = MagicMock()
    repo.get_tenant = AsyncMock(return_value=_tenant())
    repo.get_assigned_by_id = AsyncMock(return_value=_phone())
    monkeypatch.setattr(mod, "TenantPhoneNumberRepository", repo)
    monkeypatch.setattr(
        SipExtensionRepository, "get_by_employee", AsyncMock(return_value=ext),
    )

    async def fake_current_device(_db, _t, _e):
        return {"device_type": device_type, "extension_number": "1001"}

    from app.services.agent_call_device_service import AgentCallDeviceService
    monkeypatch.setattr(
        AgentCallDeviceService, "get_current_device", fake_current_device,
    )
    # CDR + status writes are side effects we don't assert here.
    monkeypatch.setattr(
        mod.CallRecordService, "create_for_outbound", AsyncMock(),
    )
    monkeypatch.setattr(
        mod.CcAgentStatusService, "sync_pg_status", AsyncMock(),
    )


@asynccontextmanager
async def _fake_session():
    sess = MagicMock()
    sess.commit = AsyncMock()
    sess.execute = AsyncMock()
    yield sess


def _patch_orchestrator_side_effects(monkeypatch, telephony):
    """Neutralize the orchestrator-side DB/status writes that run off the
    request path so the event-driven customer originate can be tested without a
    live DB, and point the orchestrator's telephony at the test client (in
    production both are the same singleton; in tests the request passes its own
    client while the customer leg is originated via the orchestrator's).
    Redis is already absent in unit tests (`_get_redis_client` → None).
    """
    from app.services.call_center import orchestrator as orch_mod

    get_orchestrator().telephony = telephony
    monkeypatch.setattr(orch_mod, "AsyncSessionLocal", _fake_session)
    monkeypatch.setattr(
        orch_mod.CallRecordService, "create_for_outbound", AsyncMock(),
    )
    monkeypatch.setattr(
        orch_mod.CcAgentStatusService, "sync_pg_status", AsyncMock(),
    )
    # Never carry trace/session across the async hop; keep it a no-op.
    monkeypatch.setattr(
        get_orchestrator(), "bind_call_trace", lambda *a, **kw: None,
    )


@pytest.mark.asyncio
async def test_sip_phone_dial_returns_before_extension_answers(monkeypatch):
    """The request rings the extension and returns immediately — it does NOT
    wait for off-hook and does NOT dial the customer. The extension leg never
    answers here (mock a phone that stays ringing)."""
    telephony = MockTelephonyClient()
    await telephony.connect()
    telephony.originate_response = {"call_id": "ext-leg", "status": "originating"}
    _patch_repos(monkeypatch, device_type="sip_phone", ext=_ext())
    _patch_orchestrator_side_effects(monkeypatch, telephony)

    db = AsyncMock()
    # No answered event is ever fired for ext-leg → if dial() waited, it would
    # block. asyncio.wait_for(..., 0.5s) proves it returns fast regardless.
    resp = await asyncio.wait_for(
        OutboundDialService.dial(
            db=db, telephony=telephony,
            tenant_pk=1, employee_id=42,
            outbound_phone_number_id="pn-1", destination="13800138000",
        ),
        timeout=0.5,
    )

    # Returned the extension leg, in the ringing state, without dialing anyone.
    assert resp.call_id == "ext-leg"
    assert resp.status == "ringing_extension"
    originates = [a for m, a in telephony.recorded if m == "call.originate"]
    assert originates == [{"extension": "acme-1001"}]  # only the extension rung


@pytest.mark.asyncio
async def test_sip_phone_does_not_hold_db_session_while_ringing(monkeypatch):
    """Connection-pool regression: the request-scoped db session must NOT be
    used/held between originating the extension leg and returning. We track the
    session's activity and assert nothing touches it after the extension leg is
    originated (i.e. no long wait runs on the request coroutine)."""
    telephony = MockTelephonyClient()
    await telephony.connect()
    _patch_repos(monkeypatch, device_type="sip_phone", ext=_ext())
    _patch_orchestrator_side_effects(monkeypatch, telephony)

    used_after_originate: list[str] = []
    originated = {"done": False}

    real_orig = telephony.call_originate

    async def orig(*a, **kw):
        r = await real_orig(*a, **kw)
        originated["done"] = True
        return {"call_id": "ext-leg", "status": "originating"}

    telephony.call_originate = orig

    class TrackingSession:
        async def execute(self, *a, **kw):
            if originated["done"]:
                used_after_originate.append("execute")
            return MagicMock()

        async def commit(self):
            if originated["done"]:
                used_after_originate.append("commit")

    resp = await asyncio.wait_for(
        OutboundDialService.dial(
            db=TrackingSession(), telephony=telephony,
            tenant_pk=1, employee_id=42,
            outbound_phone_number_id="pn-1", destination="13800138000",
        ),
        timeout=0.5,
    )
    assert resp.status == "ringing_extension"
    # No DB work happened after the extension leg was originated → the request
    # returns without holding the session across any wait.
    assert used_after_originate == []


@pytest.mark.asyncio
async def test_customer_dialed_only_after_extension_answered(monkeypatch):
    """After the extension leg's answered event arrives (off the request path),
    the orchestrator originates the customer and pairs it to the extension leg
    for auto-bridge."""
    telephony = MockTelephonyClient()
    await telephony.connect()
    responses = iter([
        {"call_id": "ext-leg", "status": "originating"},
        {"call_id": "cust-leg", "conversation_id": "c1", "status": "originating"},
    ])
    real_orig = telephony.call_originate

    async def orig(*a, **kw):
        await real_orig(*a, **kw)
        return next(responses)

    telephony.call_originate = orig
    _patch_repos(monkeypatch, device_type="sip_phone", ext=_ext())
    _patch_orchestrator_side_effects(monkeypatch, telephony)

    resp = await OutboundDialService.dial(
        db=AsyncMock(), telephony=telephony,
        tenant_pk=1, employee_id=42,
        outbound_phone_number_id="pn-1", destination="13800138000",
    )
    assert resp.call_id == "ext-leg"

    # Customer not dialed yet — only the extension.
    originates = [a for m, a in telephony.recorded if m == "call.originate"]
    assert originates == [{"extension": "acme-1001"}]

    # Fire the extension-answered event; the orchestrator's background dial task
    # now originates the customer.
    get_orchestrator()._resolve_leg_wait("ext-leg", {"answered": True})
    await asyncio.sleep(0.05)

    originates = [a for m, a in telephony.recorded if m == "call.originate"]
    assert originates[0] == {"extension": "acme-1001"}
    assert originates[1]["uri"] == "13800138000"     # customer dialed after answer
    # Customer leg paired to the extension leg + registered as originator so the
    # shared _on_outbound_answered path bridges them when the customer picks up.
    assert get_orchestrator()._outbound_webrtc_pairs["cust-leg"] == "ext-leg"
    assert "cust-leg" in get_orchestrator()._outbound_originators


@pytest.mark.asyncio
async def test_extension_no_answer_never_dials_customer(monkeypatch):
    """When the extension never answers, the orchestrator's timeout aborts the
    dial (tears down the extension leg) and the customer is NEVER dialed. The
    request itself has long since returned — the abort is timer-driven, holding
    no DB session."""
    telephony = MockTelephonyClient()
    await telephony.connect()
    telephony.originate_response = {"call_id": "ext-leg", "status": "originating"}
    _patch_repos(monkeypatch, device_type="sip_phone", ext=_ext())
    _patch_orchestrator_side_effects(monkeypatch, telephony)

    # Shrink the answer timeout so the orchestrator aborts fast.
    monkeypatch.setattr(
        OutboundDialService, "_EXTENSION_ANSWER_TIMEOUT_SEC", 0.05,
    )

    resp = await OutboundDialService.dial(
        db=AsyncMock(), telephony=telephony,
        tenant_pk=1, employee_id=42,
        outbound_phone_number_id="pn-1", destination="13800138000",
    )
    assert resp.status == "ringing_extension"

    # Let the timeout fire in the orchestrator's background task.
    await asyncio.sleep(0.2)

    originates = [a for m, a in telephony.recorded if m == "call.originate"]
    assert originates == [{"extension": "acme-1001"}]  # customer never dialed
    hangups = [a for m, a in telephony.recorded if m == "call.hangup"]
    assert any(h["call_id"] == "ext-leg" for h in hangups)  # extension torn down


@pytest.mark.asyncio
async def test_extension_declined_never_dials_customer(monkeypatch):
    """Extension hung up / declined before answering (answered=False event) →
    customer never dialed; leg already gone so no extra teardown needed."""
    telephony = MockTelephonyClient()
    await telephony.connect()
    telephony.originate_response = {"call_id": "ext-leg", "status": "originating"}
    _patch_repos(monkeypatch, device_type="sip_phone", ext=_ext())
    _patch_orchestrator_side_effects(monkeypatch, telephony)

    resp = await OutboundDialService.dial(
        db=AsyncMock(), telephony=telephony,
        tenant_pk=1, employee_id=42,
        outbound_phone_number_id="pn-1", destination="13800138000",
    )
    assert resp.status == "ringing_extension"

    get_orchestrator()._resolve_leg_wait(
        "ext-leg", {"answered": False, "reason": "declined"}
    )
    await asyncio.sleep(0.05)

    originates = [a for m, a in telephony.recorded if m == "call.originate"]
    assert originates == [{"extension": "acme-1001"}]  # customer never dialed


@pytest.mark.asyncio
async def test_sip_phone_unregistered_extension_rejected(monkeypatch):
    """Unregistered extension is rejected synchronously in the request (400)
    before anything is dialed."""
    telephony = MockTelephonyClient()
    await telephony.connect()
    _patch_repos(
        monkeypatch, device_type="sip_phone",
        ext=_ext(registration_status="unregistered"),
    )
    with pytest.raises(ValidationError, match="未注册"):
        await OutboundDialService.dial(
            db=AsyncMock(), telephony=telephony,
            tenant_pk=1, employee_id=42,
            outbound_phone_number_id="pn-1", destination="13800138000",
        )
    # Nothing dialed at all.
    assert not [m for m, _ in telephony.recorded if m == "call.originate"]


@pytest.mark.asyncio
async def test_webrtc_path_never_rings_extension(monkeypatch):
    """A Web-phone agent must keep the single-stage originate — the extension
    RPC is never invoked, protecting the existing WebRTC outbound path."""
    telephony = MockTelephonyClient()
    await telephony.connect()
    telephony.originate_response = {"call_id": "cust-leg", "status": "originating"}
    _patch_repos(monkeypatch, device_type="webrtc", ext=None)

    resp = await OutboundDialService.dial(
        db=AsyncMock(), telephony=telephony,
        tenant_pk=1, employee_id=42,
        outbound_phone_number_id="pn-1", destination="13800138000",
    )
    originates = [a for m, a in telephony.recorded if m == "call.originate"]
    assert originates == [{"uri": "13800138000", "caller_id": "+8602112345678", "trunk_id": "trunk_sh"}]
    assert resp.call_id == "cust-leg"
    # No pairing created for a WebRTC dial (that happens later via /dial-webrtc).
    assert "cust-leg" not in get_orchestrator()._outbound_webrtc_pairs
