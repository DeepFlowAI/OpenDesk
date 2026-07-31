"""
Unit tests for SIP extension service, occupancy, and agent call-device service.
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
from app.services.agent_status_service import AgentStatusService
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.sip_extension_occupancy_service import SipExtensionOccupancyService
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
        current_occupant_employee_id=None,
        bound_employee_ids=[],
        bound_employees=[],
        current_occupant=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_reconcile_registrations_flips_only_absent(monkeypatch):
    a = _extension(sip_user_id="t-1", current_occupant_employee_id=1)
    b = _extension(sip_user_id="t-2", current_occupant_employee_id=2)
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
    assert a.registration_status == "registered"


@pytest.mark.asyncio
async def test_reconcile_registrations_upgrades_unregistered_in_live(monkeypatch):
    from datetime import datetime, timezone

    a = _extension(
        sip_user_id="t-1",
        registration_status="unregistered",
        last_registered_at=None,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [a]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    async def fake_update(_db, record, updates):
        for k, v in updates.items():
            setattr(record, k, v)
        return record

    monkeypatch.setattr(SipExtensionRepository, "update", fake_update)

    flipped = await SipExtensionService.reconcile_registrations(db, {"t-1"})

    assert [e.sip_user_id for e in flipped] == ["t-1"]
    assert a.registration_status == "registered"
    assert isinstance(a.last_registered_at, datetime)
    assert a.last_registered_at.tzinfo is not None
    assert a.last_registered_at.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_reconcile_registrations_bidirectional_in_one_call(monkeypatch):
    downgrade = _extension(
        id=1, sip_user_id="t-stale", registration_status="registered"
    )
    upgrade = _extension(
        id=2,
        sip_user_id="t-live",
        registration_status="unregistered",
        last_registered_at=None,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [downgrade, upgrade]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    async def fake_update(_db, record, updates):
        for k, v in updates.items():
            setattr(record, k, v)
        return record

    monkeypatch.setattr(SipExtensionRepository, "update", fake_update)

    flipped = await SipExtensionService.reconcile_registrations(db, {"t-live"})

    assert {e.sip_user_id for e in flipped} == {"t-stale", "t-live"}
    assert downgrade.registration_status == "unregistered"
    assert upgrade.registration_status == "registered"
    assert upgrade.last_registered_at is not None


def test_hash_password_is_stable_and_not_plaintext():
    first = SipExtensionService.hash_password("s3cret-value")
    second = SipExtensionService.hash_password("s3cret-value")
    assert first == second
    assert first != "s3cret-value"
    assert len(first) == 64


def test_mask_password_keeps_only_prefix():
    assert SipExtensionService.mask_password("abcdefghijkl") == "abcd********"


@pytest.mark.asyncio
async def test_create_returns_one_time_registration_info(monkeypatch):
    created: dict = {}

    monkeypatch.setattr(SipExtensionRepository, "get_by_extension_number", AsyncMock(return_value=None))
    monkeypatch.setattr(SipExtensionRepository, "get_tenant_slug", AsyncMock(return_value="acme"))
    monkeypatch.setattr(SipExtensionRepository, "get_by_sip_user_id", AsyncMock(return_value=None))
    monkeypatch.setattr(SipExtensionRepository, "replace_bindings", AsyncMock())
    monkeypatch.setattr(SipExtensionService, "_attach_binding_views", AsyncMock())

    async def fake_create(_db, data):
        created.update(data)
        return _extension(**{
            k: v for k, v in data.items()
            if k in {
                "tenant_id", "name", "extension_number", "sip_user_id",
                "auth_account", "auth_password_masked",
            }
        }, registration_status="unregistered")

    monkeypatch.setattr(SipExtensionRepository, "create", fake_create)

    result = await SipExtensionService.create(
        object(), _principal(), SipExtensionCreate(name="客服张三", extension_number="1001")
    )

    info = result["registration_info"]
    assert info.sip_user_id == "acme-1001"
    assert info.auth_account == "acme-1001"
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


@pytest.mark.asyncio
async def test_bind_conflicts_when_employee_already_bound(monkeypatch):
    monkeypatch.setattr(EmployeeRepository, "get_by_id", AsyncMock(
        return_value=SimpleNamespace(id=22, tenant_id=7, is_active=True)))
    monkeypatch.setattr(EmployeeRepository, "has_effective_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(SipExtensionRepository, "get_by_employee", AsyncMock(
        return_value=_extension(id=99, extension_number="1099")))

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


class _FakeRedis:
    pass


@pytest.mark.asyncio
async def test_reset_password_blocked_while_bound_agent_in_call(monkeypatch):
    item = _extension(current_occupant_employee_id=22)
    monkeypatch.setattr(SipExtensionService, "get_scoped", AsyncMock(return_value=item))
    monkeypatch.setattr(
        SipExtensionRepository, "list_bound_employee_ids", AsyncMock(return_value=[22])
    )
    monkeypatch.setattr(CcAgentResourceService, "get_snapshot",
                        AsyncMock(return_value={"resource_state": "in_call"}))

    with pytest.raises(ConflictError):
        await SipExtensionService.reset_password(object(), _principal(), 1, _FakeRedis())


@pytest.mark.asyncio
async def test_disable_blocked_when_occupant_online(monkeypatch):
    item = _extension(current_occupant_employee_id=22, is_active=True)
    monkeypatch.setattr(SipExtensionService, "get_scoped", AsyncMock(return_value=item))
    monkeypatch.setattr(
        SipExtensionRepository, "list_bound_employee_ids", AsyncMock(return_value=[22])
    )
    monkeypatch.setattr(CcAgentResourceService, "get_snapshot",
                        AsyncMock(return_value={"resource_state": "idle"}))
    monkeypatch.setattr(AgentStatusService, "is_connected", AsyncMock(return_value=True))

    with pytest.raises(ConflictError):
        await SipExtensionService.disable(object(), _principal(), 1, _FakeRedis())


@pytest.mark.asyncio
async def test_reset_password_masks_and_resets_registration(monkeypatch):
    item = _extension(registration_status="registered")
    monkeypatch.setattr(SipExtensionService, "get_scoped", AsyncMock(return_value=item))
    monkeypatch.setattr(
        SipExtensionRepository, "list_bound_employee_ids", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(SipExtensionService, "_attach_binding_views", AsyncMock())
    saved: dict = {}

    async def fake_update(_db, _item, data):
        saved.update(data)
        return _extension(**{"registration_status": data["registration_status"],
                             "auth_password_masked": data["auth_password_masked"]})

    monkeypatch.setattr(SipExtensionRepository, "update", fake_update)

    result = await SipExtensionService.reset_password(object(), _principal(), 1, None)

    assert result["registration_info"].auth_password is not None
    assert saved["registration_status"] == "unregistered"
    assert saved["last_registered_at"] is None
    assert saved["auth_password_masked"].endswith("********")


@pytest.mark.asyncio
async def test_update_bindings_removes_offline_occupant(monkeypatch):
    item = _extension(current_occupant_employee_id=22)
    monkeypatch.setattr(SipExtensionService, "get_scoped", AsyncMock(return_value=item))
    monkeypatch.setattr(
        SipExtensionRepository, "list_bound_employee_ids", AsyncMock(return_value=[22, 23])
    )
    monkeypatch.setattr(CcAgentResourceService, "get_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr(AgentStatusService, "is_connected", AsyncMock(return_value=False))
    monkeypatch.setattr(
        SipExtensionOccupancyService,
        "_employee_display_name",
        AsyncMock(return_value="Alice"),
    )
    monkeypatch.setattr(EmployeeRepository, "get_by_id", AsyncMock(
        return_value=SimpleNamespace(id=23, tenant_id=7, is_active=True)))
    monkeypatch.setattr(EmployeeRepository, "has_effective_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(SipExtensionRepository, "get_by_employee", AsyncMock(return_value=None))
    update = AsyncMock(return_value=item)
    monkeypatch.setattr(SipExtensionRepository, "update", update)
    replace = AsyncMock()
    monkeypatch.setattr(SipExtensionRepository, "replace_bindings", replace)
    monkeypatch.setattr(SipExtensionService, "_clear_agent_sip_device", AsyncMock())
    monkeypatch.setattr(SipExtensionService, "_attach_binding_views", AsyncMock())

    body = SipExtensionUpdate(bound_employee_ids=[23])
    await SipExtensionService.update(
        object(), _principal(), 1, body, {"bound_employee_ids"}, _FakeRedis()
    )
    assert update.await_args.args[2]["current_occupant_employee_id"] is None
    replace.assert_awaited_once()


@pytest.mark.asyncio
async def test_sip_device_unbound_is_unavailable(monkeypatch):
    view = await SipExtensionOccupancyService.describe_sip_availability(
        object(), None, 7, 10, None
    )
    assert view["available"] is False
    assert view["unavailable_reason"] == "未绑定 SIP 分机"


@pytest.mark.asyncio
async def test_sip_device_registered_available_when_free(monkeypatch):
    monkeypatch.setattr(
        SipExtensionOccupancyService,
        "list_online_bound_blockers",
        AsyncMock(return_value=[]),
    )
    view = await SipExtensionOccupancyService.describe_sip_availability(
        object(), _FakeRedis(), 7, 10,
        _extension(is_active=True, registration_status="registered"),
    )
    assert view["available"] is True
    assert view["extension_number"] == "1001"


@pytest.mark.asyncio
async def test_sip_device_blocked_when_other_bound_online(monkeypatch):
    monkeypatch.setattr(
        SipExtensionOccupancyService,
        "list_online_bound_blockers",
        AsyncMock(return_value=[22]),
    )
    monkeypatch.setattr(
        SipExtensionOccupancyService,
        "_employee_display_name",
        AsyncMock(return_value="Bob"),
    )
    view = await SipExtensionOccupancyService.describe_sip_availability(
        object(), _FakeRedis(), 7, 10,
        _extension(is_active=True, registration_status="registered"),
    )
    assert view["available"] is False
    assert "Bob" in view["unavailable_reason"]


@pytest.mark.asyncio
async def test_acquire_idempotent_for_current_occupant(monkeypatch):
    ext = _extension(current_occupant_employee_id=10)
    monkeypatch.setattr(
        SipExtensionRepository, "get_by_employee_for_update", AsyncMock(return_value=ext)
    )
    result = await SipExtensionOccupancyService.acquire_for_employee(
        object(), _FakeRedis(), 7, 10
    )
    assert result.current_occupant_employee_id == 10


@pytest.mark.asyncio
async def test_acquire_rejected_when_redis_missing():
    with pytest.raises(ConflictError):
        await SipExtensionOccupancyService.acquire_for_employee(object(), None, 7, 10)


@pytest.mark.asyncio
async def test_acquire_rejected_when_other_occupant_holds(monkeypatch):
    ext = _extension(current_occupant_employee_id=22)
    monkeypatch.setattr(
        SipExtensionRepository, "get_by_employee_for_update", AsyncMock(return_value=ext)
    )
    monkeypatch.setattr(
        SipExtensionOccupancyService, "occupant_still_holds", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        SipExtensionOccupancyService,
        "_employee_display_name",
        AsyncMock(return_value="Alice"),
    )
    with pytest.raises(ConflictError) as exc:
        await SipExtensionOccupancyService.acquire_for_employee(
            object(), _FakeRedis(), 7, 10
        )
    assert "Alice" in str(exc.value)


def test_webrtc_device_always_available():
    assert AgentCallDeviceService._webrtc_device()["available"] is True


@pytest.mark.asyncio
async def test_list_available_devices_has_both_types(monkeypatch):
    monkeypatch.setattr(SipExtensionRepository, "get_by_employee", AsyncMock(return_value=None))
    result = await AgentCallDeviceService.list_available_devices(object(), 7, 10)
    types = {d["device_type"] for d in result["items"]}
    assert types == {"webrtc", "sip_phone"}


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
    monkeypatch.setattr(
        SipExtensionOccupancyService,
        "acquire_for_employee",
        AsyncMock(side_effect=ConflictError("未绑定 SIP 分机")),
    )
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


@pytest.mark.asyncio
async def test_ready_rejected_without_selected_device(monkeypatch):
    monkeypatch.setattr(AgentCallDeviceRepository, "get_for_employee", AsyncMock(return_value=None))
    with pytest.raises(ConflictError):
        await AgentCallDeviceService.ensure_ready_allowed(object(), 7, 10)


@pytest.mark.asyncio
async def test_ready_rejected_when_selected_device_unavailable(monkeypatch):
    monkeypatch.setattr(AgentCallDeviceRepository, "get_for_employee", AsyncMock(
        return_value=SimpleNamespace(device_type="sip_phone")))
    monkeypatch.setattr(SipExtensionRepository, "get_by_employee", AsyncMock(return_value=None))
    monkeypatch.setattr(AgentCallDeviceRepository, "clear_for_employee", AsyncMock())
    with pytest.raises(ConflictError):
        await AgentCallDeviceService.ensure_ready_allowed(object(), 7, 10)


@pytest.mark.asyncio
async def test_get_current_device_clears_sip_when_occupancy_released(monkeypatch):
    """Offline release clears occupant; stale sip_phone selection must not stay ready."""
    clear = AsyncMock()
    monkeypatch.setattr(
        AgentCallDeviceRepository,
        "get_for_employee",
        AsyncMock(return_value=SimpleNamespace(device_type="sip_phone")),
    )
    monkeypatch.setattr(AgentCallDeviceRepository, "clear_for_employee", clear)
    monkeypatch.setattr(
        SipExtensionRepository,
        "get_by_employee",
        AsyncMock(
            return_value=_extension(
                current_occupant_employee_id=None,
                is_active=True,
                registration_status="registered",
            )
        ),
    )
    monkeypatch.setattr(
        SipExtensionOccupancyService,
        "list_online_bound_blockers",
        AsyncMock(return_value=[]),
    )

    result = await AgentCallDeviceService.get_current_device(
        object(), 7, 10, _FakeRedis()
    )
    assert result["device_type"] is None
    assert result["available"] is False
    assert "占用已释放" in result["unavailable_reason"]
    clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_ready_rejected_when_sip_selected_but_not_occupant(monkeypatch):
    monkeypatch.setattr(
        AgentCallDeviceRepository,
        "get_for_employee",
        AsyncMock(return_value=SimpleNamespace(device_type="sip_phone")),
    )
    monkeypatch.setattr(AgentCallDeviceRepository, "clear_for_employee", AsyncMock())
    monkeypatch.setattr(
        SipExtensionRepository,
        "get_by_employee",
        AsyncMock(
            return_value=_extension(
                current_occupant_employee_id=None,
                is_active=True,
                registration_status="registered",
            )
        ),
    )
    monkeypatch.setattr(
        SipExtensionOccupancyService,
        "list_online_bound_blockers",
        AsyncMock(return_value=[]),
    )
    with pytest.raises(ConflictError):
        await AgentCallDeviceService.ensure_ready_allowed(object(), 7, 10, _FakeRedis())


@pytest.mark.asyncio
async def test_set_sip_device_releases_occupancy_if_view_unavailable(monkeypatch):
    ext = _extension(
        current_occupant_employee_id=10,
        is_active=True,
        registration_status="registered",
    )
    monkeypatch.setattr(
        CcAgentResourceService, "get_snapshot", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        SipExtensionOccupancyService,
        "acquire_for_employee",
        AsyncMock(return_value=ext),
    )
    monkeypatch.setattr(
        AgentCallDeviceService,
        "_device_view",
        AsyncMock(
            return_value={
                "device_type": "sip_phone",
                "available": False,
                "unavailable_reason": "分机未注册",
            }
        ),
    )
    clear = AsyncMock(return_value=ext)
    monkeypatch.setattr(SipExtensionOccupancyService, "clear_occupant", clear)

    with pytest.raises(ConflictError):
        await AgentCallDeviceService.set_current_device(
            object(), 7, 10, "sip_phone", _FakeRedis()
        )
    clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_ready_allowed_with_available_webrtc(monkeypatch):
    monkeypatch.setattr(AgentCallDeviceRepository, "get_for_employee", AsyncMock(
        return_value=SimpleNamespace(device_type="webrtc")))
    await AgentCallDeviceService.ensure_ready_allowed(object(), 7, 10)


@pytest.mark.asyncio
async def test_resolve_endpoint_uses_webrtc_even_when_bound_sip(monkeypatch):
    monkeypatch.setattr(
        AgentCallDeviceService,
        "get_current_device",
        AsyncMock(return_value={"device_type": "webrtc", "available": True}),
    )
    endpoint = await AgentCallDeviceService.resolve_employee_call_endpoint(
        object(), 7, 10, _FakeRedis()
    )
    assert endpoint["kind"] == "webrtc"


@pytest.mark.asyncio
async def test_resolve_endpoint_sip_requires_occupant(monkeypatch):
    monkeypatch.setattr(
        AgentCallDeviceService,
        "get_current_device",
        AsyncMock(return_value={"device_type": "sip_phone", "available": True}),
    )
    monkeypatch.setattr(
        SipExtensionRepository,
        "get_by_employee",
        AsyncMock(return_value=_extension(
            current_occupant_employee_id=99,
            is_active=True,
            registration_status="registered",
        )),
    )
    endpoint = await AgentCallDeviceService.resolve_employee_call_endpoint(
        object(), 7, 10, _FakeRedis()
    )
    assert endpoint["kind"] == "unavailable"
