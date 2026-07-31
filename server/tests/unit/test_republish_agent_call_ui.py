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
):
    from app.db import redis as redis_mod
    from app.db import session as session_mod
    from app.services.cc_agent_resource_service import CcAgentResourceService
    from app.services.cc_agent_status_service import CcAgentStatusService
    from app.repositories.call_record_repository import CallRecordRepository
    from app.services.agent_call_device_service import AgentCallDeviceService
    from app.services.call_center.call_control_service import CallControlService

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
        AgentCallDeviceService,
        "get_current_device",
        AsyncMock(return_value={"device_type": device_type}),
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
        record=SimpleNamespace(
            from_number="15200001111",
            to_number="4001889250",
            device_type="webrtc",
            state="ringing",
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
        record=SimpleNamespace(
            from_number="1", to_number="2", device_type="webrtc", state="ringing"
        ),
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
        record=SimpleNamespace(
            from_number="1", to_number="2", device_type="webrtc", state="ringing"
        ),
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
        record=SimpleNamespace(
            from_number="100",
            to_number="400",
            device_type="webrtc",
            state="in_progress",
        ),
    )

    await orch.republish_agent_call_ui(tenant_id=1, employee_id=7)

    orch.notify_agent_incoming.assert_awaited_once()
    payload = orch.notify_agent_incoming.await_args.kwargs["payload"]
    assert payload["restore"] is True
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
        record=SimpleNamespace(
            from_number="19310542271",
            to_number="4001889250",
            device_type="sip_phone",
            state="in_progress",
            answered_at=datetime(2026, 7, 24, 9, 0, tzinfo=timezone.utc),
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
        record=SimpleNamespace(
            from_number="100",
            to_number="17695479404",
            device_type="webrtc",
            state="completed",
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
                SimpleNamespace(
                    from_number="15200001111",
                    to_number="4001889250",
                    device_type="webrtc",
                    state="in_progress",
                    answered_at=since,
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
        active_cdr=SimpleNamespace(
            call_id="leg-consult",
            root_call_id="call-customer",
            from_number="15200001111",
            to_number="4001889250",
            device_type="sip_phone",
            direction="inbound",
            state="in_progress",
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
        active_cdr=SimpleNamespace(
            call_id="stuck-ring",
            root_call_id=None,
            state="ringing",
            direction="outbound",
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
