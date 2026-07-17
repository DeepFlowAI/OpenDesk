"""
Unit tests for SIP extension service and agent call-device service.

Telephony / Redis resource state is mocked; only service-layer business rules
are exercised (binding uniqueness, busy-state guards, device availability,
readiness gating, password masking).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.repositories.agent_call_device_repository import AgentCallDeviceRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.sip_extension_repository import SipExtensionRepository
from app.schemas.permission import EffectivePrincipal
from app.schemas.sip_extension import SipExtensionCreate, SipExtensionUpdate
from app.services.agent_call_device_service import AgentCallDeviceService
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.sip_extension_service import SipExtensionService


def _principal() -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=10,
        tenant_id=7,
        is_super_admin=True,
        permissions=["admin.access", "call.admin.extension.manage"],
    )


def _extension(**overrides):
    base = dict(
        id=1,
        tenant_id=7,
        name="客服张三",
        extension_number="1001",
        sip_user_id="acme-1001",
        auth_account="acme-1001",
        auth_password_hash="hash",
        auth_password_masked="abcd********",
        registration_status="registered",
        last_registered_at=None,
        is_active=True,
        disabled_at=None,
        bound_employee_id=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_reconcile_registrations_flips_only_absent(monkeypatch):
    # DB believes both are registered; the kernel only still knows t-1.
    a = _extension(sip_user_id="t-1", bound_employee_id=1)
    b = _extension(sip_user_id="t-2", bound_employee_id=2)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [a, b]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    async def fake_update(_db, record, updates):
        for k, v in updates.items():
            setattr(record, k, v)
        return record

    monkeypatch.setattr(SipExtensionRepository, "update", fake_update)

    flipped = await SipExtensionService.reconcile_registrations(db, {"t-1"})

    assert [e.sip_user_id for e in flipped] == ["t-2"]
    assert b.registration_status == "unregistered"
    assert a.registration_status == "registered"  # still live — untouched


# ─────────── credential helpers ───────────


def test_hash_password_is_stable_and_not_plaintext():
    first = SipExtensionService.hash_password("s3cret-value")
    second = SipExtensionService.hash_password("s3cret-value")
    assert first == second
    assert first != "s3cret-value"
    assert len(first) == 64


def test_mask_password_keeps_only_prefix():
    assert SipExtensionService.mask_password("abcdefghijkl") == "abcd********"


# ─────────── create ───────────


@pytest.mark.asyncio
async def test_create_returns_one_time_registration_info(monkeypatch):
    created: dict = {}

    monkeypatch.setattr(SipExtensionRepository, "get_by_extension_number", AsyncMock(return_value=None))
    monkeypatch.setattr(SipExtensionRepository, "get_tenant_slug", AsyncMock(return_value="acme"))
    monkeypatch.setattr(SipExtensionRepository, "get_by_sip_user_id", AsyncMock(return_value=None))

    async def fake_create(_db, data):
        created.update(data)
        return _extension(**{k: v for k, v in data.items() if k in {
            "tenant_id", "name", "extension_number", "sip_user_id",
            "auth_account", "auth_password_masked", "bound_employee_id",
        }}, registration_status="unregistered")

    monkeypatch.setattr(SipExtensionRepository, "create", fake_create)

    result = await SipExtensionService.create(
        object(), _principal(), SipExtensionCreate(name="客服张三", extension_number="1001")
    )

    info = result["registration_info"]
    assert info.sip_user_id == "acme-1001"
    assert info.auth_account == "acme-1001"
    # Plaintext password present exactly once; storage only has hash + mask.
    assert info.auth_password is not None
    assert created["auth_password_hash"] != info.auth_password
    assert created["auth_password_masked"].endswith("********")


@pytest.mark.asyncio
async def test_create_rejects_duplicate_extension_number(monkeypatch):
    monkeypatch.setattr(
        SipExtensionRepository, "get_by_extension_number",
        AsyncMock(return_value=_extension()),
    )
    with pytest.raises(ConflictError):
        await SipExtensionService.create(
            object(), _principal(),
            SipExtensionCreate(name="dup", extension_number="1001"),
        )


def test_create_schema_rejects_non_numeric_extension():
    with pytest.raises(ValueError):
        SipExtensionCreate(name="x", extension_number="10a1")


# ─────────── binding uniqueness ───────────


@pytest.mark.asyncio
async def test_bind_conflicts_when_employee_already_bound(monkeypatch):
    monkeypatch.setattr(EmployeeRepository, "get_by_id", AsyncMock(
        return_value=SimpleNamespace(id=22, tenant_id=7, is_active=True)))
    monkeypatch.setattr(EmployeeRepository, "has_effective_permission", AsyncMock(return_value=True))
    # Employee 22 already bound to a *different* extension (id=99, number 1099).
    monkeypatch.setattr(SipExtensionRepository, "get_by_employee", AsyncMock(
        return_value=_extension(id=99, extension_number="1099", bound_employee_id=22)))

    with pytest.raises(ConflictError) as exc:
        await SipExtensionService._validate_binding_target(object(), 7, 22, current_extension_id=1)
    assert "1099" in str(exc.value)


@pytest.mark.asyncio
async def test_bind_rejects_employee_without_call_permission(monkeypatch):
    monkeypatch.setattr(EmployeeRepository, "get_by_id", AsyncMock(
        return_value=SimpleNamespace(id=22, tenant_id=7, is_active=True)))
    monkeypatch.setattr(EmployeeRepository, "has_effective_permission", AsyncMock(return_value=False))

    with pytest.raises(ValidationError):
        await SipExtensionService._validate_binding_target(object(), 7, 22, current_extension_id=None)


# ─────────── busy-state guards ───────────


class _FakeRedis:
    pass


@pytest.mark.asyncio
async def test_reset_password_blocked_while_agent_in_call(monkeypatch):
    item = _extension(bound_employee_id=22)
    monkeypatch.setattr(SipExtensionService, "get_scoped", AsyncMock(return_value=item))
    monkeypatch.setattr(CcAgentResourceService, "get_snapshot",
                        AsyncMock(return_value={"resource_state": "in_call"}))

    with pytest.raises(ConflictError):
        await SipExtensionService.reset_password(object(), _principal(), 1, _FakeRedis())


@pytest.mark.asyncio
async def test_disable_blocked_when_extension_is_current_device(monkeypatch):
    item = _extension(bound_employee_id=22, is_active=True)
    monkeypatch.setattr(SipExtensionService, "get_scoped", AsyncMock(return_value=item))
    # Agent idle...
    monkeypatch.setattr(CcAgentResourceService, "get_snapshot",
                        AsyncMock(return_value={"resource_state": "idle"}))
    # ...but the extension is their current selected SIP device.
    monkeypatch.setattr(AgentCallDeviceRepository, "get_for_employee", AsyncMock(
        return_value=SimpleNamespace(device_type="sip_phone")))

    with pytest.raises(ConflictError):
        await SipExtensionService.disable(object(), _principal(), 1, _FakeRedis())


@pytest.mark.asyncio
async def test_reset_password_masks_and_resets_registration(monkeypatch):
    item = _extension(bound_employee_id=None, registration_status="registered")
    monkeypatch.setattr(SipExtensionService, "get_scoped", AsyncMock(return_value=item))
    saved: dict = {}

    async def fake_update(_db, _item, data):
        saved.update(data)
        return _extension(**{"registration_status": data["registration_status"],
                             "auth_password_masked": data["auth_password_masked"]})

    monkeypatch.setattr(SipExtensionRepository, "update", fake_update)
    monkeypatch.setattr(SipExtensionRepository, "get_by_employee", AsyncMock(return_value=None))

    result = await SipExtensionService.reset_password(object(), _principal(), 1, None)

    assert result["registration_info"].auth_password is not None
    assert saved["registration_status"] == "unregistered"
    assert saved["last_registered_at"] is None
    assert saved["auth_password_masked"].endswith("********")


# ─────────── device availability ───────────


def test_sip_device_unbound_is_unavailable():
    view = AgentCallDeviceService._sip_device_from_extension(None)
    assert view["available"] is False
    assert view["unavailable_reason"] == "未绑定 SIP 分机"
    assert view["device_type"] == "sip_phone"


def test_sip_device_unregistered_is_unavailable():
    view = AgentCallDeviceService._sip_device_from_extension(
        _extension(is_active=True, registration_status="unregistered"))
    assert view["available"] is False
    assert view["unavailable_reason"] == "分机未注册"


def test_sip_device_registered_is_available():
    view = AgentCallDeviceService._sip_device_from_extension(
        _extension(is_active=True, registration_status="registered"))
    assert view["available"] is True
    assert view["extension_number"] == "1001"


def test_webrtc_device_always_available():
    assert AgentCallDeviceService._webrtc_device()["available"] is True


@pytest.mark.asyncio
async def test_list_available_devices_has_both_types(monkeypatch):
    monkeypatch.setattr(SipExtensionRepository, "get_by_employee", AsyncMock(return_value=None))
    result = await AgentCallDeviceService.list_available_devices(object(), 7, 10)
    types = {d["device_type"] for d in result["items"]}
    assert types == {"webrtc", "sip_phone"}


# ─────────── device switching ───────────


@pytest.mark.asyncio
async def test_switch_device_rejected_while_in_call(monkeypatch):
    monkeypatch.setattr(CcAgentResourceService, "get_snapshot",
                        AsyncMock(return_value={"resource_state": "in_call"}))
    with pytest.raises(ConflictError):
        await AgentCallDeviceService.set_current_device(object(), 7, 10, "webrtc", _FakeRedis())


@pytest.mark.asyncio
async def test_switch_to_unavailable_sip_device_rejected(monkeypatch):
    monkeypatch.setattr(CcAgentResourceService, "get_snapshot",
                        AsyncMock(return_value={"resource_state": "idle"}))
    monkeypatch.setattr(SipExtensionRepository, "get_by_employee", AsyncMock(return_value=None))
    with pytest.raises(ConflictError):
        await AgentCallDeviceService.set_current_device(object(), 7, 10, "sip_phone", _FakeRedis())


@pytest.mark.asyncio
async def test_switch_to_webrtc_persists(monkeypatch):
    monkeypatch.setattr(CcAgentResourceService, "get_snapshot", AsyncMock(return_value=None))
    upsert = AsyncMock()
    monkeypatch.setattr(AgentCallDeviceRepository, "upsert", upsert)
    result = await AgentCallDeviceService.set_current_device(object(), 7, 10, "webrtc", _FakeRedis())
    assert result["device_type"] == "webrtc"
    upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_switch_rejects_unknown_device_type():
    with pytest.raises(ValidationError):
        await AgentCallDeviceService.set_current_device(object(), 7, 10, "carrier_pigeon", None)


# ─────────── readiness gating ───────────


@pytest.mark.asyncio
async def test_ready_rejected_without_selected_device(monkeypatch):
    monkeypatch.setattr(AgentCallDeviceRepository, "get_for_employee", AsyncMock(return_value=None))
    with pytest.raises(ConflictError):
        await AgentCallDeviceService.ensure_ready_allowed(object(), 7, 10)


@pytest.mark.asyncio
async def test_ready_rejected_when_selected_device_unavailable(monkeypatch):
    # Selected sip_phone but the bound extension is gone → unavailable.
    monkeypatch.setattr(AgentCallDeviceRepository, "get_for_employee", AsyncMock(
        return_value=SimpleNamespace(device_type="sip_phone")))
    monkeypatch.setattr(SipExtensionRepository, "get_by_employee", AsyncMock(return_value=None))
    with pytest.raises(ConflictError):
        await AgentCallDeviceService.ensure_ready_allowed(object(), 7, 10)


@pytest.mark.asyncio
async def test_ready_allowed_with_available_webrtc(monkeypatch):
    monkeypatch.setattr(AgentCallDeviceRepository, "get_for_employee", AsyncMock(
        return_value=SimpleNamespace(device_type="webrtc")))
    # Should not raise.
    await AgentCallDeviceService.ensure_ready_allowed(object(), 7, 10)
