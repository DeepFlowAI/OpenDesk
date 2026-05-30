"""
Unit tests for OutboundDialService — the agent dial → FlowKit originate path.

Stubs the DB layer (TenantPhoneNumberRepository) and the telephony client so
we can assert the wiring without spinning up FastAPI / Postgres.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.telephony.base import TelephonyRPCError
from app.services.call_center.outbound_dial_service import OutboundDialService
from app.services.cc_agent_resource_service import CcAgentResourceService


def _stub_tenant(tenant_string_id: str = "tenant-x"):
    return SimpleNamespace(tenant_id=tenant_string_id)


def _stub_phone_number(
    *,
    phone_id: str = "pn-1",
    phone_number: str = "+8602112345678",
    call_types: list[str] | None = None,
    trunk_id: str | None = "trunk_sh",
    called_number_prefix: str | None = None,
):
    return SimpleNamespace(
        id=phone_id,
        phone_number=phone_number,
        call_types=call_types if call_types is not None else ["outbound"],
        trunk_id=trunk_id,
        called_number_prefix=called_number_prefix,
    )


@pytest.mark.asyncio
async def test_dial_happy_path():
    telephony = MagicMock()
    telephony.call_originate = AsyncMock(return_value={
        "call_id": "out-123",
        "conversation_id": "conv-1",
        "status": "originating",
    })

    with patch(
        "app.services.call_center.outbound_dial_service.TenantPhoneNumberRepository"
    ) as repo:
        repo.get_tenant = AsyncMock(return_value=_stub_tenant())
        repo.get_assigned_by_id = AsyncMock(return_value=_stub_phone_number())

        resp = await OutboundDialService.dial(
            db=MagicMock(),
            telephony=telephony,
            tenant_pk=1,
            employee_id=42,
            outbound_phone_number_id="pn-1",
            destination="13800138000",
        )

    assert resp.call_id == "out-123"
    telephony.call_originate.assert_awaited_once_with(
        uri="13800138000",
        caller_id="+8602112345678",
        trunk_id="trunk_sh",
    )


@pytest.mark.asyncio
async def test_dial_occupies_call_center_resource():
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await CcAgentResourceService.set_visible_status(
        fake_redis, tenant_id=1, employee_id=42, status="ready"
    )
    telephony = MagicMock()
    telephony.call_originate = AsyncMock(return_value={
        "call_id": "out-123",
        "conversation_id": "conv-1",
        "status": "originating",
    })

    with patch(
        "app.services.call_center.outbound_dial_service.TenantPhoneNumberRepository"
    ) as repo:
        repo.get_tenant = AsyncMock(return_value=_stub_tenant())
        repo.get_assigned_by_id = AsyncMock(return_value=_stub_phone_number())

        await OutboundDialService.dial(
            db=MagicMock(),
            telephony=telephony,
            tenant_pk=1,
            employee_id=42,
            outbound_phone_number_id="pn-1",
            destination="13800138000",
            r=fake_redis,
        )

    snapshot = await CcAgentResourceService.get_snapshot(fake_redis, 1, 42)
    assert snapshot is not None
    assert snapshot["visible_status"] == "busy"
    assert snapshot["resource_state"] == "ringing"
    assert snapshot["direction"] == "outbound"
    assert snapshot["current_call_id"] == "out-123"


@pytest.mark.asyncio
async def test_dial_strips_whitespace_in_destination():
    telephony = MagicMock()
    telephony.call_originate = AsyncMock(return_value={"call_id": "out-x"})
    with patch(
        "app.services.call_center.outbound_dial_service.TenantPhoneNumberRepository"
    ) as repo:
        repo.get_tenant = AsyncMock(return_value=_stub_tenant())
        repo.get_assigned_by_id = AsyncMock(return_value=_stub_phone_number())
        await OutboundDialService.dial(
            db=MagicMock(),
            telephony=telephony,
            tenant_pk=1,
            employee_id=42,
            outbound_phone_number_id="pn-1",
            destination="  13800138000  ",
        )
    assert telephony.call_originate.await_args.kwargs["uri"] == "13800138000"


@pytest.mark.asyncio
async def test_dial_rejects_invalid_destination():
    telephony = MagicMock()
    with pytest.raises(ValidationError):
        await OutboundDialService.dial(
            db=MagicMock(),
            telephony=telephony,
            tenant_pk=1,
            employee_id=42,
            outbound_phone_number_id="pn-1",
            destination="; DROP TABLE",
        )


@pytest.mark.asyncio
async def test_dial_phone_number_not_assigned():
    telephony = MagicMock()
    with patch(
        "app.services.call_center.outbound_dial_service.TenantPhoneNumberRepository"
    ) as repo:
        repo.get_tenant = AsyncMock(return_value=_stub_tenant())
        repo.get_assigned_by_id = AsyncMock(return_value=None)
        with pytest.raises(NotFoundError):
            await OutboundDialService.dial(
                db=MagicMock(),
                telephony=telephony,
                tenant_pk=1,
                employee_id=42,
                outbound_phone_number_id="missing",
                destination="13800138000",
            )


@pytest.mark.asyncio
async def test_dial_phone_number_not_outbound_capable():
    telephony = MagicMock()
    with patch(
        "app.services.call_center.outbound_dial_service.TenantPhoneNumberRepository"
    ) as repo:
        repo.get_tenant = AsyncMock(return_value=_stub_tenant())
        repo.get_assigned_by_id = AsyncMock(
            return_value=_stub_phone_number(call_types=["inbound"])
        )
        with pytest.raises(ValidationError):
            await OutboundDialService.dial(
                db=MagicMock(),
                telephony=telephony,
                tenant_pk=1,
                employee_id=42,
                outbound_phone_number_id="pn-1",
                destination="13800138000",
            )


@pytest.mark.asyncio
async def test_dial_phone_number_unbound_trunk():
    telephony = MagicMock()
    with patch(
        "app.services.call_center.outbound_dial_service.TenantPhoneNumberRepository"
    ) as repo:
        repo.get_tenant = AsyncMock(return_value=_stub_tenant())
        repo.get_assigned_by_id = AsyncMock(
            return_value=_stub_phone_number(trunk_id=None)
        )
        with pytest.raises(ValidationError):
            await OutboundDialService.dial(
                db=MagicMock(),
                telephony=telephony,
                tenant_pk=1,
                employee_id=42,
                outbound_phone_number_id="pn-1",
                destination="13800138000",
            )


@pytest.mark.asyncio
async def test_dial_applies_called_number_prefix():
    """PhoneNumber.called_number_prefix prepended to destination before
    handing off to FlowKit. Idempotent: already-prefixed input not doubled."""
    telephony = MagicMock()
    telephony.call_originate = AsyncMock(return_value={"call_id": "out-1"})
    with patch(
        "app.services.call_center.outbound_dial_service.TenantPhoneNumberRepository"
    ) as repo:
        repo.get_tenant = AsyncMock(return_value=_stub_tenant())
        repo.get_assigned_by_id = AsyncMock(
            return_value=_stub_phone_number(called_number_prefix="035"),
        )
        await OutboundDialService.dial(
            db=MagicMock(),
            telephony=telephony,
            tenant_pk=1,
            employee_id=42,
            outbound_phone_number_id="pn-1",
            destination="13800138000",
        )
    assert telephony.call_originate.await_args.kwargs["uri"] == "03513800138000"


@pytest.mark.asyncio
async def test_dial_prefix_not_doubled_when_already_present():
    telephony = MagicMock()
    telephony.call_originate = AsyncMock(return_value={"call_id": "out-1"})
    with patch(
        "app.services.call_center.outbound_dial_service.TenantPhoneNumberRepository"
    ) as repo:
        repo.get_tenant = AsyncMock(return_value=_stub_tenant())
        repo.get_assigned_by_id = AsyncMock(
            return_value=_stub_phone_number(called_number_prefix="035"),
        )
        await OutboundDialService.dial(
            db=MagicMock(),
            telephony=telephony,
            tenant_pk=1,
            employee_id=42,
            outbound_phone_number_id="pn-1",
            destination="03513800138000",  # already prefixed
        )
    assert telephony.call_originate.await_args.kwargs["uri"] == "03513800138000"


@pytest.mark.asyncio
async def test_dial_no_prefix_when_phone_number_has_none():
    telephony = MagicMock()
    telephony.call_originate = AsyncMock(return_value={"call_id": "out-1"})
    with patch(
        "app.services.call_center.outbound_dial_service.TenantPhoneNumberRepository"
    ) as repo:
        repo.get_tenant = AsyncMock(return_value=_stub_tenant())
        repo.get_assigned_by_id = AsyncMock(
            return_value=_stub_phone_number(called_number_prefix=None),
        )
        await OutboundDialService.dial(
            db=MagicMock(),
            telephony=telephony,
            tenant_pk=1,
            employee_id=42,
            outbound_phone_number_id="pn-1",
            destination="13800138000",
        )
    assert telephony.call_originate.await_args.kwargs["uri"] == "13800138000"


@pytest.mark.asyncio
async def test_dial_surfaces_flowkit_trunk_not_found():
    """FlowKit -32602 'trunk_id not found' MUST become a ValidationError so
    the agent UI shows a clear reason rather than a 500."""
    telephony = MagicMock()
    telephony.call_originate = AsyncMock(
        side_effect=TelephonyRPCError(-32602, "trunk_id not found")
    )
    with patch(
        "app.services.call_center.outbound_dial_service.TenantPhoneNumberRepository"
    ) as repo:
        repo.get_tenant = AsyncMock(return_value=_stub_tenant())
        repo.get_assigned_by_id = AsyncMock(return_value=_stub_phone_number())
        with pytest.raises(ValidationError):
            await OutboundDialService.dial(
                db=MagicMock(),
                telephony=telephony,
                tenant_pk=1,
                employee_id=42,
                outbound_phone_number_id="pn-1",
                destination="13800138000",
            )
