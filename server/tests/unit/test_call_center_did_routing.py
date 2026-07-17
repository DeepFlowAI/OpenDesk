"""
Per-DID tenant routing for inbound calls.

An inbound call must be bound to the tenant that owns the dialed number (DID),
not to a single fixed default tenant. `_resolve_tenant_id_for_did` looks the
`to` number up in the phone-number catalog and resolves its owning tenant;
unknown/unassigned numbers return None so the caller falls back to the default.
"""
import pytest

from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.repositories.phone_number_repository import PhoneNumberRepository
from app.services.call_center import orchestrator as orch_module
from app.services.call_center.orchestrator import CallCenterOrchestrator


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeSession:
    def __init__(self, tenant_row):
        self._tenant_row = tenant_row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._tenant_row)


class _Phone:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


class _Tenant:
    def __init__(self, id):
        self.id = id


@pytest.mark.asyncio
async def test_did_maps_to_owning_tenant(monkeypatch):
    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _FakeSession(_Tenant(id=7)))

    async def fake_get(_db, number):
        assert number == "4001681715"
        return _Phone(tenant_id="repair-demo-slug")

    monkeypatch.setattr(PhoneNumberRepository, "get_by_phone_number", fake_get)

    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    assert await orch._resolve_tenant_id_for_did("4001681715") == 7


@pytest.mark.asyncio
async def test_unknown_did_returns_none(monkeypatch):
    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _FakeSession(None))

    async def fake_get(_db, _number):
        return None

    monkeypatch.setattr(PhoneNumberRepository, "get_by_phone_number", fake_get)

    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    assert await orch._resolve_tenant_id_for_did("9999") is None
    # Empty DID short-circuits before any lookup.
    assert await orch._resolve_tenant_id_for_did("") is None


@pytest.mark.asyncio
async def test_unassigned_number_returns_none(monkeypatch):
    # Number exists in the catalog but has no tenant assigned.
    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _FakeSession(None))

    async def fake_get(_db, _number):
        return _Phone(tenant_id=None)

    monkeypatch.setattr(PhoneNumberRepository, "get_by_phone_number", fake_get)

    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    assert await orch._resolve_tenant_id_for_did("4001681715") is None
