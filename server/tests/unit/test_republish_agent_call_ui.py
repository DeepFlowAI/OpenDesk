"""Page-refresh restore: re-push ringing / in-call UI on agent reconnect."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.call_center.orchestrator import CallCenterOrchestrator


class _FakeSessionCtx:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *args):
        return False


def _call_record(
    *,
    id: int = 1,
    customer_number: str = "",
    service_number: str = "",
    direction: str = "inbound",
    lifecycle_status: str = "active",
    first_agent_connected_at=None,
    customer_connected_at=None,
    started_at=None,
    call_id: str | None = None,
    root_call_id: str | None = None,
):
    return SimpleNamespace(
        id=id,
        customer_number=customer_number,
        service_number=service_number,
        direction=direction,
        lifecycle_status=lifecycle_status,
        first_agent_connected_at=first_agent_connected_at,
        customer_connected_at=customer_connected_at,
        started_at=started_at,
        call_id=call_id,
        root_call_id=root_call_id,
    )


def _patch_deps(
    monkeypatch,
    *,
    snapshot,
    record,
    device_type="webrtc",
    active_cdr=None,
    recover=None,
    force_release=None,
    mark_in_call=None,
    consult_host=None,
    satisfaction_execution=None,
    workspace_context=None,
):
    from app.db import redis as redis_mod
    from app.db import session as session_mod
    from app.services.cc_agent_resource_service import CcAgentResourceService
    from app.services.cc_agent_status_service import CcAgentStatusService
    from app.repositories.call_record_repository import CallRecordRepository
    from app.repositories.call_satisfaction_execution_repository import (
        CallSatisfactionExecutionRepository,
    )
    from app.services.agent_call_device_service import AgentCallDeviceService
    from app.services.call_center.call_control_service import CallControlService
    from app.services.call_workspace_context_service import CallWorkspaceContextService

    monkeypatch.setattr(
        redis_mod,
        "redis_client",
        SimpleNamespace(client=MagicMock()),
    )
    monkeypatch.setattr(
        CcAgentStatusService,
        "reconcile_agent",
        AsyncMock(return_value=snapshot),
    )
    monkeypatch.setattr(
        CcAgentResourceService,
        "get_snapshot",
        AsyncMock(return_value=snapshot),
    )
    monkeypatch.setattr(
        CcAgentResourceService,
        "recover_from_sources",
        recover or AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        CcAgentResourceService,
        "force_release",
        force_release or AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        CcAgentResourceService,
        "mark_in_call",
        mark_in_call or AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        CallControlService,
        "_find_consult_host_for_target",
        AsyncMock(return_value=consult_host),
    )
    monkeypatch.setattr(
        CallControlService,
        "_customer_leg_alive_in_kernel",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        CallControlService,
        "_resolve_current_call",
        AsyncMock(
            return_value=SimpleNamespace(customer_call_id="cust-root")
        ),
    )
    monkeypatch.setattr(
        session_mod, "AsyncSessionLocal", lambda: _FakeSessionCtx(MagicMock())
    )
    monkeypatch.setattr(
        CallRecordRepository,
        "get_by_call_id",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        CallRecordRepository,
        "get_latest_active_for_agent",
        AsyncMock(return_value=active_cdr),
    )
    monkeypatch.setattr(
        CallSatisfactionExecutionRepository,
        "get_by_call_record_id",
        AsyncMock(return_value=satisfaction_execution),
    )
    monkeypatch.setattr(
        AgentCallDeviceService,
        "get_current_device",
        AsyncMock(return_value={"device_type": device_type}),
    )
    monkeypatch.setattr(
        CallWorkspaceContextService,
        "get_auto_outbound_context",
        AsyncMock(return_value=workspace_context or {}),
    )


@pytest.mark.asyncio
async def test_republish_ringing_emits_call_incoming(monkeypatch):
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {"offer-1": MagicMock()}
    orch.notify_agent_incoming = AsyncMock(return_value=True)
    orch.notify_agent_call_answered = AsyncMock()

    _patch_deps(
        monkeypatch,
        snapshot={
            "resource_state": "ringing",
            "current_call_id": "call-1",
            "offer_id": "offer-1",
            "queue_id": 9,
            "direction": "inbound",
        },
        record=_call_record(
            customer_number="15200001111",
            service_number="4001889250",
        ),
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=7)

    orch.notify_agent_incoming.assert_awaited_once()
    payload = orch.notify_agent_incoming.await_args.kwargs["payload"]
    assert payload["offer_id"] == "offer-1"
    assert payload["call_id"] == "call-1"
    assert payload["from"] == "15200001111"
    orch.notify_agent_call_answered.assert_not_awaited()


@pytest.mark.asyncio
async def test_republish_skips_webrtc_ringing_without_pending_offer(monkeypatch):
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {}
    orch.notify_agent_incoming = AsyncMock(return_value=True)

    _patch_deps(
        monkeypatch,
        snapshot={
            "resource_state": "ringing",
            "current_call_id": "call-1",
            "offer_id": "offer-gone",
            "queue_id": None,
            "direction": "inbound",
        },
        record=_call_record(customer_number="1", service_number="2"),
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=7)
    orch.notify_agent_incoming.assert_not_awaited()


@pytest.mark.asyncio
async def test_republish_skips_webrtc_ringing_with_empty_offer_id(monkeypatch):
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {}
    orch.notify_agent_incoming = AsyncMock(return_value=True)

    _patch_deps(
        monkeypatch,
        snapshot={
            "resource_state": "ringing",
            "current_call_id": "call-1",
            "offer_id": "",
            "queue_id": None,
            "direction": "outbound",
        },
        record=_call_record(customer_number="2", service_number="1", direction="outbound"),
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=7)
    orch.notify_agent_incoming.assert_not_awaited()


@pytest.mark.asyncio
async def test_republish_in_call_emits_incoming_then_answered(monkeypatch):
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {}
    orch.notify_agent_incoming = AsyncMock(return_value=True)
    orch.notify_agent_call_answered = AsyncMock()

    _patch_deps(
        monkeypatch,
        snapshot={
            "resource_state": "in_call",
            "current_call_id": "call-9",
            "offer_id": "",
            "queue_id": None,
            "direction": "inbound",
        },
        record=_call_record(customer_number="100", service_number="400"),
        workspace_context={
            "source": "auto_outbound",
            "task_id": 12,
            "record_id": 34,
        },
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=7)

    orch.notify_agent_incoming.assert_awaited_once()
    payload = orch.notify_agent_incoming.await_args.kwargs["payload"]
    assert payload["restore"] is True
    assert payload["source"] == "auto_outbound"
    assert payload["task_id"] == 12
    assert payload["record_id"] == 34
    orch.notify_agent_call_answered.assert_awaited_once()
    assert orch.notify_agent_call_answered.await_args.kwargs["call_id"] == "call-9"


@pytest.mark.asyncio
async def test_republish_promotes_ringing_to_in_call_when_cdr_answered(monkeypatch):
    """SIP handset answered but Redis still ringing — refresh must restore 通话中."""
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {"offer-sip": MagicMock()}
    orch.notify_agent_incoming = AsyncMock(return_value=True)
    orch.notify_agent_call_answered = AsyncMock()
    mark_in_call = AsyncMock(return_value=None)
    from datetime import datetime, timezone

    _patch_deps(
        monkeypatch,
        snapshot={
            "resource_state": "ringing",
            "current_call_id": "call-sip",
            "offer_id": "offer-sip",
            "queue_id": 3,
            "direction": "inbound",
        },
        record=_call_record(
            customer_number="19310542271",
            service_number="4001889250",
            first_agent_connected_at=datetime(2026, 7, 24, 9, 0, tzinfo=timezone.utc),
        ),
        device_type="sip_phone",
        mark_in_call=mark_in_call,
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=7)

    mark_in_call.assert_awaited_once()
    orch.notify_agent_incoming.assert_awaited_once()
    payload = orch.notify_agent_incoming.await_args.kwargs["payload"]
    assert payload["restore"] is True
    assert payload["call_id"] == "call-sip"
    orch.notify_agent_call_answered.assert_awaited_once()


@pytest.mark.asyncio
async def test_republish_drops_redis_pointer_when_cdr_already_ended(monkeypatch):
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {}
    orch.notify_agent_incoming = AsyncMock(return_value=True)
    orch.notify_agent_call_answered = AsyncMock()
    release = AsyncMock(return_value=None)

    _patch_deps(
        monkeypatch,
        snapshot={
            "resource_state": "in_call",
            "current_call_id": "dead-call",
            "offer_id": "",
            "queue_id": None,
            "direction": "outbound",
        },
        record=_call_record(
            customer_number="17695479404",
            service_number="100",
            direction="outbound",
            lifecycle_status="ended",
        ),
        force_release=release,
        consult_host=None,
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=1)

    release.assert_awaited_once()
    orch.notify_agent_incoming.assert_not_awaited()
    orch.notify_agent_call_answered.assert_not_awaited()


@pytest.mark.asyncio
async def test_republish_consult_target_without_cdr_keeps_timer(monkeypatch):
    """B has no CallRecord; refresh must restore UI + answered_at from Redis."""
    from datetime import datetime, timezone

    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {}
    orch.notify_agent_incoming = AsyncMock(return_value=True)
    orch.notify_agent_call_answered = AsyncMock()
    since = datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc)

    _patch_deps(
        monkeypatch,
        snapshot={
            "resource_state": "in_call",
            "current_call_id": "b-webrtc-leg",
            "offer_id": "",
            "queue_id": None,
            "direction": "inbound",
            "in_call_since": since,
        },
        record=None,
        consult_host={"employee_id": 7, "tenant_id": 1, "legs": SimpleNamespace()},
    )
    # Host customer CDR for ANI/DNIS on B's restore payload.
    from app.repositories.call_record_repository import CallRecordRepository

    monkeypatch.setattr(
        CallRecordRepository,
        "get_by_call_id",
        AsyncMock(
            side_effect=lambda _db, call_id, _tid: (
                _call_record(
                    customer_number="15200001111",
                    service_number="4001889250",
                    first_agent_connected_at=since,
                    started_at=since,
                )
                if call_id == "cust-root"
                else None
            )
        ),
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=99)

    orch.notify_agent_incoming.assert_awaited_once()
    payload = orch.notify_agent_incoming.await_args.kwargs["payload"]
    assert payload["restore"] is True
    assert payload["call_id"] == "b-webrtc-leg"
    assert payload["call_type"] == "internal_consult"
    assert payload["source_call_id"] == "cust-root"
    assert payload["answered_at"] == since.isoformat()
    assert payload["from"] == "15200001111"
    orch.notify_agent_call_answered.assert_awaited_once()


@pytest.mark.asyncio
async def test_republish_recovers_from_active_cdr_when_redis_drifted(monkeypatch):
    """SIP consult + browser refresh: Redis may lose in_call while CDR lives."""
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {}
    orch.notify_agent_incoming = AsyncMock(return_value=True)
    orch.notify_agent_call_answered = AsyncMock()
    recover = AsyncMock(return_value=None)

    _patch_deps(
        monkeypatch,
        snapshot={
            "resource_state": "idle",
            "current_call_id": None,
            "offer_id": "",
            "queue_id": None,
            "direction": None,
        },
        record=None,
        device_type="sip_phone",
        active_cdr=_call_record(
            call_id="leg-consult",
            root_call_id="call-customer",
            customer_number="15200001111",
            service_number="4001889250",
            direction="inbound",
            first_agent_connected_at=object(),
        ),
        recover=recover,
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=7)

    recover.assert_awaited_once()
    assert recover.await_args.kwargs["active_call_id"] == "call-customer"
    orch.notify_agent_incoming.assert_awaited_once()
    payload = orch.notify_agent_incoming.await_args.kwargs["payload"]
    assert payload["call_id"] == "call-customer"
    assert payload["device_type"] == "sip_phone"
    assert payload["from"] == "15200001111"
    orch.notify_agent_call_answered.assert_awaited_once()
    assert (
        orch.notify_agent_call_answered.await_args.kwargs["call_id"]
        == "call-customer"
    )


@pytest.mark.asyncio
async def test_republish_skips_stuck_ringing_cdr_when_redis_idle(monkeypatch):
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {}
    orch.notify_agent_incoming = AsyncMock(return_value=True)
    orch.notify_agent_call_answered = AsyncMock()

    _patch_deps(
        monkeypatch,
        snapshot={"resource_state": "idle", "current_call_id": None},
        record=None,
        active_cdr=_call_record(
            call_id="stuck-ring",
            root_call_id=None,
            direction="outbound",
            first_agent_connected_at=None,
        ),
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=7)

    orch.notify_agent_incoming.assert_not_awaited()
    orch.notify_agent_call_answered.assert_not_awaited()


@pytest.mark.asyncio
async def test_republish_skips_when_no_redis_in_call_and_no_active_cdr(monkeypatch):
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {}
    orch.notify_agent_incoming = AsyncMock(return_value=True)
    orch.notify_agent_call_answered = AsyncMock()

    _patch_deps(
        monkeypatch,
        snapshot={"resource_state": "idle", "current_call_id": None},
        record=None,
        active_cdr=None,
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=7)

    orch.notify_agent_incoming.assert_not_awaited()
    orch.notify_agent_call_answered.assert_not_awaited()


@pytest.mark.asyncio
async def test_republish_skips_recover_while_satisfaction_survey_runs(monkeypatch):
    """After invite, the CDR stays active for the customer survey. Recovering the
    agent to in_call would media-reconnect and steal the IVR audio path."""

    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {}
    orch.notify_agent_incoming = AsyncMock(return_value=True)
    orch.notify_agent_call_answered = AsyncMock()
    recover = AsyncMock(return_value=None)

    _patch_deps(
        monkeypatch,
        snapshot={
            "resource_state": "after_call_work",
            "current_call_id": None,
            "offer_id": "",
            "queue_id": None,
            "direction": None,
        },
        record=None,
        active_cdr=_call_record(
            id=203,
            call_id="cust-1",
            root_call_id="cust-1",
            customer_number="15200001111",
            service_number="4001889250",
            direction="inbound",
            first_agent_connected_at=object(),
        ),
        recover=recover,
        satisfaction_execution=SimpleNamespace(id=4, status="in_progress"),
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=7)

    recover.assert_not_awaited()
    orch.notify_agent_incoming.assert_not_awaited()
    orch.notify_agent_call_answered.assert_not_awaited()


@pytest.mark.asyncio
async def test_republish_skips_in_call_when_customer_leg_gone(monkeypatch):
    from app.services.call_center.call_control_service import CallControlService

    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {}
    orch.telephony = MagicMock()
    orch.notify_agent_incoming = AsyncMock(return_value=True)
    orch.notify_agent_call_answered = AsyncMock()
    orch.finalize_agent_call = AsyncMock()

    _patch_deps(
        monkeypatch,
        snapshot={
            "resource_state": "in_call",
            "current_call_id": "cust-gone",
            "offer_id": "",
            "queue_id": None,
            "direction": "inbound",
        },
        record=_call_record(
            call_id="cust-gone",
            customer_number="100",
            service_number="400",
        ),
    )
    monkeypatch.setattr(
        CallControlService,
        "_customer_leg_alive_in_kernel",
        AsyncMock(return_value=False),
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=7)

    orch.notify_agent_incoming.assert_not_awaited()
    orch.notify_agent_call_answered.assert_not_awaited()
    orch.finalize_agent_call.assert_awaited_once()
    assert orch.finalize_agent_call.await_args.kwargs["call_id"] == "cust-gone"
    assert orch.finalize_agent_call.await_args.kwargs["reason"] == "media_timeout"

@pytest.mark.asyncio
async def test_republish_re_rings_live_internal_transfer_offer(monkeypatch):
    """A colleague's transfer ring has no CDR; reconnect must re-ring, not release."""
    from app.services.call_center import internal_consult_service

    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {}
    orch.notify_agent_incoming = AsyncMock(return_value=True)
    release = AsyncMock(return_value=None)
    ring = {
        "offer_id": "off-1",
        "call_id": "internal:off-1",
        "call_type": "internal_transfer",
        "from": "A",
        "from_employee_id": 13,
    }

    _patch_deps(
        monkeypatch,
        snapshot={
            "resource_state": "ringing",
            "current_call_id": "internal:off-1",
            "offer_id": "off-1",
            "queue_id": None,
            "direction": "inbound",
        },
        record=None,
        force_release=release,
    )
    monkeypatch.setattr(
        internal_consult_service,
        "load_internal_offer_payload",
        AsyncMock(return_value=ring),
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=1)

    release.assert_not_awaited()
    orch.notify_agent_incoming.assert_awaited_once()
    assert orch.notify_agent_incoming.await_args.kwargs["payload"] == ring


@pytest.mark.asyncio
async def test_republish_releases_internal_ring_whose_offer_ended(monkeypatch):
    from app.services.call_center import internal_consult_service

    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._pending_offers = {}
    orch.notify_agent_incoming = AsyncMock(return_value=True)
    release = AsyncMock(return_value=None)

    _patch_deps(
        monkeypatch,
        snapshot={
            "resource_state": "ringing",
            "current_call_id": "internal:off-gone",
            "offer_id": "off-gone",
            "queue_id": None,
            "direction": "inbound",
        },
        record=None,
        force_release=release,
    )
    monkeypatch.setattr(
        internal_consult_service,
        "load_internal_offer_payload",
        AsyncMock(return_value=None),
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=1)

    release.assert_awaited_once()
    orch.notify_agent_incoming.assert_not_awaited()
