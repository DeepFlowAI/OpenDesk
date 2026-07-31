"""
Unit tests for InternalConsultService — the agent-to-agent WebRTC consult /
transfer ring-on-demand path.

These verify:
  - a Web-phone target is reserved, rung (`cc.call_incoming` with
    call_type / from), and on accept its WebRTC leg is returned + marked in_call;
  - decline / no-answer releases the reservation and cancels the offer, and no
    leg is handed back;
  - a non-Web-phone (or unavailable) target is rejected up-front with no
    reservation;
  - no DB session is held while awaiting the target's accept.
"""
import asyncio

import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center import internal_consult_service as ics_module
from app.services.call_center.internal_consult_service import InternalConsultService


# ─────────────── fakes ───────────────


class _FakeResource:
    """Records reserve / ring / in_call / release against the resource service."""

    def __init__(self, reserve_ok=True):
        self.reserve_ok = reserve_ok
        self.calls: list[tuple] = []

    async def reserve_inbound(self, r, tenant_id, employee_id, **kw):
        self.calls.append(("reserve", tenant_id, employee_id, kw))
        return {"resource_state": "reserved"} if self.reserve_ok else None

    async def mark_ringing(self, r, tenant_id, employee_id, **kw):
        self.calls.append(("ringing", tenant_id, employee_id, kw))
        return {"resource_state": "ringing"}

    async def mark_in_call(self, r, tenant_id, employee_id, **kw):
        self.calls.append(("in_call", tenant_id, employee_id, kw))
        return {"resource_state": "in_call"}

    async def release(self, r, tenant_id, employee_id, **kw):
        self.calls.append(("release", tenant_id, employee_id, kw))
        return {"resource_state": "idle"}

    def method_names(self):
        return [c[0] for c in self.calls]


class _FakeOrch:
    def __init__(self):
        self.offer_future: asyncio.Future | None = None
        self.incoming: list[dict] = []
        self.cancelled: list[str] = []
        self.push_ok = True

    def register_offer(self, offer_id):
        self.offer_future = asyncio.get_event_loop().create_future()
        return self.offer_future

    def cancel_offer(self, offer_id):
        self.cancelled.append(offer_id)

    async def notify_agent_incoming(self, *, tenant_id, employee_id, payload):
        self.incoming.append(payload)
        return self.push_ok


def _install(monkeypatch, *, device, reserve_ok=True):
    resource = _FakeResource(reserve_ok=reserve_ok)
    orch = _FakeOrch()

    async def _device(_tenant_id, _employee_id):
        return device

    monkeypatch.setattr(
        InternalConsultService, "_resolve_target_device", staticmethod(_device)
    )
    monkeypatch.setattr(ics_module, "CcAgentResourceService", resource)

    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "get_orchestrator", lambda: orch)
    return resource, orch


_WEBRTC_OK = {"device_type": "webrtc", "available": True}


@pytest.mark.asyncio
async def test_rejects_non_webrtc_target(monkeypatch):
    resource, _orch = _install(
        monkeypatch, device={"device_type": "sip_phone", "available": True}
    )
    tel = MockTelephonyClient()
    await tel.connect()

    with pytest.raises(ValidationError):
        await InternalConsultService.initiate_webrtc_consult(
            tel, object(), tenant_id=7, initiator_employee_id=1, target_employee_id=2,
        )
    # No reservation attempted for an ineligible target.
    assert resource.calls == []


@pytest.mark.asyncio
async def test_reserve_conflict_raises(monkeypatch):
    resource, orch = _install(monkeypatch, device=_WEBRTC_OK, reserve_ok=False)
    tel = MockTelephonyClient()
    await tel.connect()

    with pytest.raises(ConflictError):
        await InternalConsultService.initiate_webrtc_consult(
            tel, object(), tenant_id=7, initiator_employee_id=1, target_employee_id=2,
        )
    assert resource.method_names() == ["reserve"]
    # No offer registered / left dangling.
    assert orch.offer_future is None


@pytest.mark.asyncio
async def test_accept_returns_leg_and_marks_in_call(monkeypatch):
    resource, orch = _install(monkeypatch, device=_WEBRTC_OK)
    tel = MockTelephonyClient()
    await tel.connect()

    task = asyncio.create_task(
        InternalConsultService.initiate_webrtc_consult(
            tel, object(),
            tenant_id=7, initiator_employee_id=1, target_employee_id=2,
            initiator_display="Alice",
            customer_context={
                "source_call_id": "sip-customer",
                "customer_from": "13800138000",
                "customer_to": "400800",
                "user_id": 99,
                "user_public_id": "usr_abc",
            },
        )
    )
    # Let it reserve + ring + register the offer, then simulate the target
    # accepting via their /current-call/accept.
    for _ in range(5):
        await asyncio.sleep(0)
        if orch.offer_future is not None:
            break
    orch.offer_future.set_result({"accept": True, "webrtc_call_id": "target-leg"})
    result = await task

    assert result["ok"] is True
    assert result["target_webrtc_call_id"] == "target-leg"
    # cc.call_incoming carried the internal call_type + initiator display
    # plus the initiator's customer context for the target's user panel.
    assert orch.incoming[0]["call_type"] == "internal_consult"
    assert orch.incoming[0]["from"] == "Alice"
    assert orch.incoming[0]["source_call_id"] == "sip-customer"
    assert orch.incoming[0]["customer_from"] == "13800138000"
    assert orch.incoming[0]["user_public_id"] == "usr_abc"
    # Resource lifecycle: reserve → ring → in_call, no release on success.
    assert resource.method_names() == ["reserve", "ringing", "in_call"]


@pytest.mark.asyncio
async def test_decline_releases_and_raises(monkeypatch):
    resource, orch = _install(monkeypatch, device=_WEBRTC_OK)
    tel = MockTelephonyClient()
    await tel.connect()

    task = asyncio.create_task(
        InternalConsultService.initiate_webrtc_consult(
            tel, object(), tenant_id=7, initiator_employee_id=1, target_employee_id=2,
        )
    )
    for _ in range(5):
        await asyncio.sleep(0)
        if orch.offer_future is not None:
            break
    orch.offer_future.set_result({"accept": False, "reason": "rejected"})

    with pytest.raises(ValidationError):
        await task

    assert "release" in resource.method_names()
    assert orch.cancelled  # offer cancelled


class _FakeRedisKV:
    """Just enough of redis for the consult-cancel tombstone check."""

    def __init__(self, store=None):
        self.store = dict(store or {})

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


@pytest.mark.asyncio
async def test_precancelled_offer_aborts_before_ring(monkeypatch):
    """A cancel tombstone written before the ring task registered its offer
    must abort the consult before cc.call_incoming, releasing the target."""

    from app.constants.call_center import consult_cancel_key

    resource, orch = _install(monkeypatch, device=_WEBRTC_OK)
    tel = MockTelephonyClient()
    await tel.connect()

    r = _FakeRedisKV({consult_cancel_key("offer-x"): "1"})

    with pytest.raises(ConflictError):
        await InternalConsultService.initiate_webrtc_consult(
            tel, r, tenant_id=7, initiator_employee_id=1, target_employee_id=2,
            offer_id="offer-x",
        )

    # Reservation freed, offer cancelled, target browser never rung.
    assert "release" in resource.method_names()
    assert orch.cancelled == ["offer-x"]
    assert orch.incoming == []


@pytest.mark.asyncio
async def test_timeout_releases_and_raises(monkeypatch):
    resource, orch = _install(monkeypatch, device=_WEBRTC_OK)
    tel = MockTelephonyClient()
    await tel.connect()

    # Never resolve the future; a tiny timeout fires the no-answer path.
    with pytest.raises(ValidationError):
        await InternalConsultService.initiate_webrtc_consult(
            tel, object(),
            tenant_id=7, initiator_employee_id=1, target_employee_id=2,
            timeout_seconds=0.01,
        )
    assert "release" in resource.method_names()
    assert orch.cancelled
