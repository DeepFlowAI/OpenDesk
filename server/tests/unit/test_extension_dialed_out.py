"""
An agent dialling on their desk phone, rather than from the workstation.

The kernel reports the handset's call as an incoming leg, so without telling it
apart from a customer calling in we would answer the agent with an IVR. The
kernel marks these legs with the extension it verified they came from; that mark
is what routes them here instead.

The handset is already off-hook, which makes this the second half of the
workstation's SIP-phone dial: the customer leg is originated straight away and
paired to the handset, and the existing answered handler bridges them.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.libs.telephony import CallEvent
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center.orchestrator import get_orchestrator, reset_orchestrator

HANDSET_LEG = "handset-leg-1"


def _ext(**kw):
    base = dict(
        id=1, tenant_id=7, sip_user_id="acme-1001", is_active=True,
        registration_status="registered", extension_number="1001",
        current_occupant_employee_id=42,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _did(**kw):
    base = dict(
        id="pn-1", phone_number="+8602112345678", call_types=["outbound"],
        trunk_id="trunk_sh", called_number_prefix=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@asynccontextmanager
async def _fake_session():
    sess = MagicMock()
    sess.commit = AsyncMock()
    sess.execute = AsyncMock()
    yield sess


@pytest.fixture(autouse=True)
def _reset_orch():
    reset_orchestrator()
    yield
    reset_orchestrator()


def _setup(monkeypatch, *, ext=_ext(), dids=None):
    """Wire an orchestrator whose extension and DID lookups are stubbed."""
    from app.repositories.sip_extension_repository import SipExtensionRepository
    from app.repositories.tenant_phone_number_repository import (
        TenantPhoneNumberRepository,
    )
    from app.services.call_center import orchestrator as orch_mod

    telephony = MockTelephonyClient()
    orch = get_orchestrator()
    orch.telephony = telephony

    monkeypatch.setattr(orch_mod, "AsyncSessionLocal", _fake_session)
    monkeypatch.setattr(
        SipExtensionRepository, "get_by_sip_user_id", AsyncMock(return_value=ext),
    )
    monkeypatch.setattr(
        TenantPhoneNumberRepository, "get_tenant",
        AsyncMock(return_value=SimpleNamespace(tenant_id="tenant-x")),
    )
    monkeypatch.setattr(
        TenantPhoneNumberRepository, "list_assigned",
        AsyncMock(return_value=[_did()] if dids is None else dids),
    )
    monkeypatch.setattr(orch_mod.CallRecordService, "create_for_outbound", AsyncMock())
    monkeypatch.setattr(orch_mod.CcAgentStatusService, "sync_pg_status", AsyncMock())
    monkeypatch.setattr(orch, "bind_call_trace", lambda *a, **kw: None)
    monkeypatch.setattr(orch, "_claim_call", AsyncMock(return_value=True))
    return orch, telephony


def _handset_call(dialed: str = "13800138000", extension: str = "acme-1001") -> CallEvent:
    return CallEvent(
        method="call.incoming",
        data={
            "call_id": HANDSET_LEG,
            "transport": "sip",
            "from": extension,
            "to": dialed,
            "caller_extension": extension,
        },
    )


def _calls(telephony: MockTelephonyClient, method: str) -> list[dict]:
    return [params for name, params in telephony.recorded if name == method]


@pytest.mark.asyncio
async def test_handset_dial_calls_the_number_the_agent_keyed_in(monkeypatch):
    """The customer is dialled with the tenant's outbound number as caller ID —
    the agent's handset has no way to offer them a choice."""
    orch, telephony = _setup(monkeypatch)

    await orch._on_incoming(_handset_call(dialed="13800138000"))

    originates = _calls(telephony, "call.originate")
    assert len(originates) == 1
    assert originates[0]["uri"] == "13800138000"
    assert originates[0]["caller_id"] == "+8602112345678"
    assert originates[0]["trunk_id"] == "trunk_sh"


@pytest.mark.asyncio
async def test_handset_dial_is_not_routed_as_an_inbound_call(monkeypatch):
    """Falling through to inbound routing would answer the agent with an IVR
    and hang up when no rule matched the number they dialled."""
    orch, telephony = _setup(monkeypatch)
    from app.services.call_center import orchestrator as orch_mod
    match = AsyncMock(return_value=None)
    monkeypatch.setattr(orch_mod, "match_routing_rule", match)

    await orch._on_incoming(_handset_call())

    match.assert_not_awaited()
    assert _calls(telephony, "call.answer") == []
    assert _calls(telephony, "call.hangup") == []


@pytest.mark.asyncio
async def test_customer_leg_is_paired_to_the_handset_for_bridging(monkeypatch):
    """Pairing is what makes the answered handler bridge the two legs; without
    it the customer picks up to silence."""
    orch, telephony = _setup(monkeypatch)
    telephony.originate_response = {"call_id": "customer-leg", "status": "originating"}

    await orch._on_incoming(_handset_call())

    assert await orch._pop_outbound_webrtc("customer-leg") == HANDSET_LEG


@pytest.mark.asyncio
async def test_a_prefix_on_the_outbound_number_is_applied(monkeypatch):
    """Some carriers require a dial-out prefix. The workstation applies it, and
    a handset that cannot know about it must get the same treatment."""
    orch, telephony = _setup(monkeypatch, dids=[_did(called_number_prefix="0")])

    await orch._on_incoming(_handset_call(dialed="13800138000"))

    assert _calls(telephony, "call.originate")[0]["uri"] == "013800138000"


@pytest.mark.asyncio
async def test_handset_is_hung_up_when_nobody_holds_the_extension(monkeypatch):
    """A shared phone with no current occupant has no agent to bill the call to
    or hand it back to. Leaving the leg up would sound like dead air."""
    orch, telephony = _setup(monkeypatch, ext=_ext(current_occupant_employee_id=None))

    await orch._on_incoming(_handset_call())

    assert _calls(telephony, "call.originate") == []
    assert _calls(telephony, "call.hangup")[0]["call_id"] == HANDSET_LEG


@pytest.mark.asyncio
async def test_handset_is_hung_up_when_the_tenant_cannot_dial_out(monkeypatch):
    orch, telephony = _setup(monkeypatch, dids=[_did(call_types=["inbound"])])

    await orch._on_incoming(_handset_call())

    assert _calls(telephony, "call.originate") == []
    assert _calls(telephony, "call.hangup")[0]["call_id"] == HANDSET_LEG


@pytest.mark.asyncio
async def test_handset_is_hung_up_when_the_agent_is_already_on_a_call(monkeypatch):
    """The workstation dial refuses a second concurrent call; a handset that
    bypasses it must not be able to start one either."""
    from app.core.exceptions import ConflictError
    from app.services.call_center import orchestrator as orch_mod

    orch, telephony = _setup(monkeypatch)
    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: MagicMock())
    monkeypatch.setattr(
        orch_mod.CcAgentResourceService, "reserve_outbound",
        AsyncMock(side_effect=ConflictError("occupied")),
    )

    await orch._on_incoming(_handset_call())

    assert _calls(telephony, "call.originate") == []
    assert _calls(telephony, "call.hangup")[0]["call_id"] == HANDSET_LEG


@pytest.mark.asyncio
async def test_the_agent_hears_ringback_while_the_customer_is_called(monkeypatch):
    """The kernel answers the handset as soon as it is lifted, but the customer
    may ring for ten seconds after that. Without a tone the agent holds a
    connected line that is completely silent: no sign the call is being placed,
    and no way to hear the moment the customer picks up."""
    orch, telephony = _setup(monkeypatch)

    await orch._on_incoming(_handset_call())

    plays = _calls(telephony, "call.play")
    assert len(plays) == 1
    assert plays[0]["call_id"] == HANDSET_LEG
    assert plays[0]["loop"] is True, "one beep then silence is not ringback"
    # Carried inline rather than as a URL or TTS: a tone that needed an uploaded
    # asset or a tenant setting would leave most handsets silent.
    assert plays[0]["audio"]
    assert plays[0]["audio_url"] is None and plays[0]["text"] is None


def test_the_ringback_tone_is_a_playable_wav():
    """The kernel decodes WAV only, and rejects the play outright otherwise —
    which would be silence again, discovered on a live call."""
    import base64
    import io
    import wave

    from app.services.call_center.orchestration.extension_dial import _ringback_wav_b64

    with wave.open(io.BytesIO(base64.b64decode(_ringback_wav_b64()))) as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16000
        assert wav.getnframes() > 0


@pytest.mark.asyncio
async def test_ringback_stops_before_the_customer_is_bridged(monkeypatch):
    """The tone loops until told to stop, so leaving it running would beep over
    the customer for the whole conversation."""
    from app.services.call_center import orchestrator as orch_mod
    from app.services.system_settings_service import SystemSettingsService

    orch, telephony = _setup(monkeypatch)
    telephony.originate_response = {"call_id": "customer-leg", "status": "originating"}
    monkeypatch.setattr(orch_mod.CallRecordService, "mark_answered", AsyncMock())
    monkeypatch.setattr(
        SystemSettingsService, "is_bridge_asr_enabled_managed",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(orch, "notify_agent_outbound_event", AsyncMock())

    await orch._on_incoming(_handset_call())
    await orch._on_outbound_answered(
        CallEvent(method="call.answered", data={"call_id": "customer-leg"})
    )

    methods = [name for name, _ in telephony.recorded]
    assert "call.bridge" in methods, "the customer answered but was never joined"
    assert methods.index("call.stop") < methods.index("call.bridge")
    stop = _calls(telephony, "call.stop")[0]
    assert stop["call_id"] == HANDSET_LEG
    assert stop["target"] == "play", "stopping 'all' would also kill the audio path"


@pytest.mark.asyncio
async def test_a_customer_calling_in_still_routes_as_inbound(monkeypatch):
    """The mark is what distinguishes the two; a call without it must reach
    inbound routing exactly as before."""
    orch, telephony = _setup(monkeypatch)
    from app.services.call_center import orchestrator as orch_mod
    match = AsyncMock(return_value=None)
    monkeypatch.setattr(orch_mod, "match_routing_rule", match)
    monkeypatch.setattr(orch, "_resolve_tenant_id_for_did", AsyncMock(return_value=7))

    await orch._on_incoming(
        CallEvent(
            method="call.incoming",
            data={
                "call_id": "customer-1", "transport": "sip",
                "from": "13800138000", "to": "+8602112345678",
            },
        )
    )

    match.assert_awaited()
    assert _calls(telephony, "call.originate") == []
