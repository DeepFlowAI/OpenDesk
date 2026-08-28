"""
Unit tests for OutboundDialService — the agent dial → FlowKit originate path.

Stubs the DB layer (TenantPhoneNumberRepository) and the telephony client so
we can assert the wiring without spinning up FastAPI / Postgres.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.telephony.base import TelephonyRPCError
from app.services.call_center import outbound_dial_service as ods_mod
from app.services.call_center.orchestrator import get_orchestrator, reset_orchestrator
from app.services.call_center.outbound_dial_service import OutboundDialService
from app.services.cc_agent_resource_service import CcAgentResourceService


@pytest.fixture(autouse=True)
def _reset_orch():
    reset_orchestrator()
    yield
    reset_orchestrator()


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
    ) as repo, patch(
        "app.services.call_center.outbound_dial_service.CcAgentStatusService.sync_pg_status",
        new_callable=AsyncMock,
    ), patch(
        "app.services.call_center.outbound_dial_service.CallRecordService.create_for_outbound",
        new_callable=AsyncMock,
    ):
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
    assert "out-123" in get_orchestrator()._outbound_originators
    assert get_orchestrator()._outbound_originators["out-123"] == (
        1, 42, "+8602112345678",
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


@pytest.mark.asyncio
async def test_persist_skips_busy_when_outbound_already_ended(monkeypatch):
    """Hangup can beat persist; do not write PG busy after ready was restored."""
    from app.services.call_center.outbound_dial_service import _DialContext

    orch = get_orchestrator()
    await orch._mark_outbound_ended("out-ended", "rejected", 603)
    sync = AsyncMock()
    create = AsyncMock()
    finalize = AsyncMock(return_value=("rejected", 603))
    monkeypatch.setattr(
        "app.services.call_center.outbound_dial_service.CcAgentStatusService.sync_pg_status",
        sync,
    )
    monkeypatch.setattr(
        "app.services.call_center.outbound_dial_service.CallRecordService.create_for_outbound",
        create,
    )
    monkeypatch.setattr(orch, "finalize_outbound_cdr_if_already_ended", finalize)

    ctx = _DialContext(
        dest="13800138000",
        dialed="13800138000",
        caller_id="+86021",
        trunk_id="trunk_sh",
        prefix="",
        device_type="webrtc",
        device_identifier=None,
    )
    db = AsyncMock()
    await OutboundDialService._persist_webrtc_outbound(
        db,
        tenant_pk=1,
        employee_id=42,
        ctx=ctx,
        call_id="out-ended",
        result={},
        call_source="manual",
        custom_business_info=None,
        external_context=None,
    )

    sync.assert_not_awaited()
    create.assert_awaited_once()


class _FakeSessionCM:
    """Minimal async context manager standing in for AsyncSessionLocal."""

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


def _stub_managed_dial_prereqs(monkeypatch):
    """Stub everything dial_managed touches before/around the originate RPC."""
    monkeypatch.setattr(
        "app.services.call_center.outbound_dial_service.AsyncSessionLocal",
        lambda: _FakeSessionCM(AsyncMock()),
    )
    repo = MagicMock()
    repo.get_tenant = AsyncMock(return_value=_stub_tenant())
    repo.get_assigned_by_id = AsyncMock(return_value=_stub_phone_number())
    monkeypatch.setattr(
        "app.services.call_center.outbound_dial_service.TenantPhoneNumberRepository",
        repo,
    )
    monkeypatch.setattr(
        "app.services.agent_call_device_service.AgentCallDeviceService.get_current_device",
        AsyncMock(return_value={"device_type": "webrtc"}),
    )


def _stub_originate(call_id: str) -> MagicMock:
    telephony = MagicMock()
    telephony.call_originate = AsyncMock(
        return_value={
            "call_id": call_id,
            "conversation_id": "conv-1",
            "status": "originating",
        }
    )
    return telephony


@pytest.mark.asyncio
async def test_dial_managed_returns_before_persist_completes(monkeypatch):
    """/dial must respond once the originate is accepted; the CDR persist
    (seconds of DB work) continues in a background task."""
    _stub_managed_dial_prereqs(monkeypatch)
    telephony = _stub_originate("out-bg")

    persist_started = asyncio.Event()
    persist_release = asyncio.Event()
    persist_done = asyncio.Event()

    async def gated_persist(db, **kwargs):
        persist_started.set()
        await persist_release.wait()
        persist_done.set()

    monkeypatch.setattr(
        OutboundDialService, "_persist_webrtc_outbound", gated_persist
    )

    resp = await OutboundDialService.dial_managed(
        telephony,
        tenant_pk=1,
        employee_id=42,
        outbound_phone_number_id="pn-1",
        destination="13800138000",
    )

    # The response is already in hand while the persist is still gated —
    # before the change this awaited the full DB persist.
    assert resp.call_id == "out-bg"
    assert resp.status == "originating"
    await asyncio.sleep(0)
    assert persist_started.is_set()
    assert not persist_done.is_set()

    persist_release.set()
    tasks = list(ods_mod._background_persist_tasks)
    assert len(tasks) == 1
    await asyncio.gather(*tasks)
    assert persist_done.is_set()


@pytest.mark.asyncio
async def test_dial_managed_persist_failure_stays_off_response(monkeypatch, caplog):
    """A failing background persist must not break an already-accepted dial."""
    _stub_managed_dial_prereqs(monkeypatch)
    telephony = _stub_originate("out-err")
    monkeypatch.setattr(
        OutboundDialService,
        "_persist_webrtc_outbound",
        AsyncMock(side_effect=RuntimeError("db down")),
    )

    resp = await OutboundDialService.dial_managed(
        telephony,
        tenant_pk=1,
        employee_id=42,
        outbound_phone_number_id="pn-1",
        destination="13800138000",
    )

    assert resp.call_id == "out-err"
    tasks = list(ods_mod._background_persist_tasks)
    assert len(tasks) == 1
    await asyncio.gather(*tasks)  # must not re-raise the persist failure
    assert "outbound persist failed call_id=out-err" in caplog.text
