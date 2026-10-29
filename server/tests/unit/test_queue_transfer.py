"""Unit tests for blind-transfer into an employee-group queue."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core.exceptions import BusinessError, NotFoundError
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center import call_control_service as ccs_module
from app.services.call_center.call_control_service import CallControlService
from app.services.queue_strategy import QueueCandidate


class SessionTracker:
    def __init__(self) -> None:
        self.active = False
        self.opens = 0
        self.closes = 0


class _FakeSession:
    def __init__(self, tracker: SessionTracker, payload=None):
        self.tracker = tracker
        self.payload = payload

    async def __aenter__(self):
        assert self.tracker.active is False, "session opened while another was active"
        self.tracker.active = True
        self.tracker.opens += 1
        return self.payload if self.payload is not None else object()

    async def __aexit__(self, *_exc):
        self.tracker.active = False
        self.tracker.closes += 1
        return False


def _install_tracked_session(monkeypatch, tracker: SessionTracker, payload=None):
    monkeypatch.setattr(
        ccs_module, "AsyncSessionLocal", lambda: _FakeSession(tracker, payload)
    )


def _current_call() -> ccs_module.CurrentCall:
    return ccs_module.CurrentCall(
        record_id=1,
        tenant_id=7,
        customer_call_id="sip-customer",
        webrtc_call_id="webrtc-1",
    )


def _stub_resolve_current_call(monkeypatch):
    async def _resolve(*_a, **_k):
        return _current_call()

    monkeypatch.setattr(CallControlService, "_resolve_current_call", _resolve)


def _bypass_tone(monkeypatch):
    async def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr(CallControlService, "_play_scene_tone", _noop)
    monkeypatch.setattr(CallControlService, "_stop_tone", _noop)


def _fake_orchestrator(monkeypatch):
    class _Orch:
        def __init__(self):
            self.waiters: dict[str, asyncio.Future] = {}
            self.offers: dict[str, asyncio.Future] = {}
            self.cancelled_offers: list[str] = []
            self.control_results: list[tuple] = []
            self.ended: list[tuple] = []
            self.incoming: list[tuple] = []
            self.answered: list[tuple] = []
            self.republished: list[tuple] = []
            self._workflows: dict = {}
            self._pending_queue_transfer: dict = {}
            self._pending_sip_originate: dict = {}
            self.telephony = None

        def register_leg_wait(self, call_id):
            fut = asyncio.get_event_loop().create_future()
            self.waiters[call_id] = fut
            return fut

        def cancel_leg_wait(self, call_id):
            self.waiters.pop(call_id, None)

        def register_offer(self, offer_id):
            fut = asyncio.get_event_loop().create_future()
            self.offers[offer_id] = fut
            return fut

        def cancel_offer(self, offer_id):
            self.cancelled_offers.append(offer_id)
            self.offers.pop(offer_id, None)

        def resolve_offer(self, offer_id, decision):
            fut = self.offers.pop(offer_id, None)
            if fut is None or fut.done():
                return False
            fut.set_result(decision)
            return True

        def active_workflow(self, call_id):
            return self._workflows.get(call_id)

        def set_pending_queue_transfer(self, call_id, task):
            self._pending_queue_transfer[call_id] = task

        def pop_pending_queue_transfer(self, call_id):
            return self._pending_queue_transfer.pop(call_id, None)

        def set_pending_sip_originate(self, call_id, agent_leg):
            self._pending_sip_originate[call_id] = agent_leg

        def pop_pending_sip_originate(self, call_id):
            return self._pending_sip_originate.pop(call_id, None)

        async def notify_agent_control_result(
            self, *, tenant_id, employee_id, method, payload
        ):
            self.control_results.append((tenant_id, employee_id, method, payload))

        async def notify_agent_call_ended(
            self, *, tenant_id, employee_id, call_id, reason
        ):
            self.ended.append((tenant_id, employee_id, call_id, reason))

        async def notify_agent_incoming(self, *, tenant_id, employee_id, payload):
            self.incoming.append((tenant_id, employee_id, payload))
            return True

        async def notify_agent_call_answered(
            self, *, tenant_id, employee_id, call_id
        ):
            self.answered.append((tenant_id, employee_id, call_id))

        async def republish_agent_call_ui(self, *, tenant_id, employee_id):
            self.republished.append((tenant_id, employee_id))

    orch = _Orch()
    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "get_orchestrator", lambda: orch)
    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: object())
    return orch


async def _stub_finalize(monkeypatch, events: list):
    async def _finalize(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(
        CallControlService, "_finalize_initiator_after_transfer", _finalize
    )


def _stub_group_exists(monkeypatch, *, exists: bool = True, tenant_id: int = 7):
    async def _get_by_id(_db, group_id):
        if not exists:
            return None
        return SimpleNamespace(id=group_id, tenant_id=tenant_id, name="Q")

    monkeypatch.setattr(
        "app.repositories.employee_group_repository.EmployeeGroupRepository.get_by_id",
        _get_by_id,
    )


def _stub_candidates(monkeypatch, *, available_count: int, waitable: bool | None):
    candidates = [
        QueueCandidate(employee_id=i + 1, name=f"a{i}", available=True)
        for i in range(available_count)
    ]
    if available_count == 0:
        candidates = [
            QueueCandidate(employee_id=9, name="busy", available=False),
        ]

    async def _list(_self, _db, _r, _tenant_id, _qt, _qid, task_context=None):
        return candidates

    async def _waitable(_self, _db, _tenant_id, _qt, _qid, _r=None):
        return waitable

    async def _ringable(_r, _tenant_id, cands):
        return [c for c in cands if c.available]

    monkeypatch.setattr(
        "app.services.queue_resource_provider.CallCenterResourceProvider.list_candidates",
        _list,
    )
    monkeypatch.setattr(
        "app.services.call_center.queue.QueuePicker.has_agent_on_call_for_queue",
        _waitable,
    )
    monkeypatch.setattr(
        "app.services.queue_resource_provider.filter_ringable_call_center_candidates",
        _ringable,
    )


# ───────────────────────── precheck / enqueue ─────────────────────────


@pytest.mark.asyncio
async def test_queue_missing_raises_404_without_telephony(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)
    _stub_resolve_current_call(monkeypatch)
    _stub_group_exists(monkeypatch, exists=False)

    tel = MockTelephonyClient()
    await tel.connect()

    with pytest.raises(NotFoundError):
        await CallControlService.transfer_to_queue(
            tel, tenant_id=7, employee_id=42, queue_id=99
        )

    assert tel.recorded == []
    assert orch._pending_queue_transfer == {}


@pytest.mark.asyncio
async def test_queue_empty_raises_409_without_unbridge(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    _fake_orchestrator(monkeypatch)
    _stub_resolve_current_call(monkeypatch)
    _stub_group_exists(monkeypatch, exists=True)
    _stub_candidates(monkeypatch, available_count=0, waitable=False)

    tel = MockTelephonyClient()
    await tel.connect()

    with pytest.raises(BusinessError) as ei:
        await CallControlService.transfer_to_queue(
            tel, tenant_id=7, employee_id=42, queue_id=5
        )

    assert ei.value.status_code == 409
    assert "call.unbridge" not in [m for m, _ in tel.recorded]
    assert tel.recorded == []


@pytest.mark.asyncio
async def test_ghost_ready_agent_raises_409_without_unbridge(monkeypatch):
    """ready+idle but browser offline must fail sync validation (no unbridge)."""

    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    _fake_orchestrator(monkeypatch)
    _stub_resolve_current_call(monkeypatch)
    _stub_group_exists(monkeypatch, exists=True)

    async def _list(_self, _db, _r, _tenant_id, _qt, _qid, task_context=None):
        return [QueueCandidate(employee_id=13, name="ghost", available=True)]

    async def _waitable(_self, _db, _tenant_id, _qt, _qid, _r=None):
        return False

    async def _is_connected(_r, _tenant_id, _employee_id):
        return False

    monkeypatch.setattr(
        "app.services.queue_resource_provider.CallCenterResourceProvider.list_candidates",
        _list,
    )
    monkeypatch.setattr(
        "app.services.call_center.queue.QueuePicker.has_agent_on_call_for_queue",
        _waitable,
    )
    monkeypatch.setattr(
        "app.services.agent_status_service.AgentStatusService.is_connected",
        _is_connected,
    )

    tel = MockTelephonyClient()
    await tel.connect()

    with pytest.raises(BusinessError) as ei:
        await CallControlService.transfer_to_queue(
            tel, tenant_id=7, employee_id=42, queue_id=5
        )

    assert ei.value.status_code == 409
    assert "call.unbridge" not in [m for m, _ in tel.recorded]
    assert tel.recorded == []


@pytest.mark.asyncio
async def test_queue_no_redis_raises_409(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    import app.services.call_center.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "_get_redis_client", lambda: None)
    _stub_resolve_current_call(monkeypatch)
    _stub_group_exists(monkeypatch, exists=True)

    tel = MockTelephonyClient()
    await tel.connect()

    with pytest.raises(BusinessError) as ei:
        await CallControlService.transfer_to_queue(
            tel, tenant_id=7, employee_id=42, queue_id=5
        )
    assert ei.value.status_code == 409
    assert tel.recorded == []


@pytest.mark.asyncio
async def test_queue_ready_agent_enqueues_and_finalizes_initiator(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)
    finalize_events: list = []
    await _stub_finalize(monkeypatch, finalize_events)

    _stub_resolve_current_call(monkeypatch)
    _stub_group_exists(monkeypatch, exists=True)
    _stub_candidates(monkeypatch, available_count=1, waitable=False)

    bind_calls: list = []

    async def _bind_queue(db, tenant_id, call_id, queue_type, queue_id):
        bind_calls.append((tenant_id, call_id, queue_type, queue_id))

    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.bind_queue",
        _bind_queue,
    )

    async def _noop_wait(*_a, **_kw):
        await asyncio.sleep(0)

    monkeypatch.setattr(CallControlService, "_run_queue_transfer_wait", _noop_wait)

    tel = MockTelephonyClient()
    await tel.connect()

    result = await CallControlService.transfer_to_queue(
        tel, tenant_id=7, employee_id=42, queue_id=5
    )

    assert result == {
        "ok": True,
        "call_id": "sip-customer",
        "note": "queued_target",
    }
    assert (
        "call.unbridge",
        {"call_id": "sip-customer", "other_call_id": "webrtc-1"},
    ) in tel.recorded
    assert bind_calls == [(7, "sip-customer", "employee_group", 5)]
    assert finalize_events and finalize_events[0]["new_agent_id"] is None
    assert finalize_events[0]["employee_id"] == 42
    assert "sip-customer" in orch._pending_queue_transfer
    # Initiator media leg released after enqueue (desk-phone off-hook fix).
    assert (
        "call.hangup",
        {"call_id": "webrtc-1", "reason": "transferred"},
    ) in tel.recorded
    assert sum(
        1
        for m, p in tel.recorded
        if m == "call.hangup" and p.get("call_id") == "webrtc-1"
    ) == 1
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_queue_transfer_skips_initiator_hangup_when_unbridge_fails(monkeypatch):
    """Pre-enqueue unbridge failure must leave the initiator leg alone."""

    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)
    finalize_events: list = []
    await _stub_finalize(monkeypatch, finalize_events)

    _stub_resolve_current_call(monkeypatch)
    _stub_group_exists(monkeypatch, exists=True)
    _stub_candidates(monkeypatch, available_count=1, waitable=False)

    tel = MockTelephonyClient()
    await tel.connect()

    async def _unbridge_fail(call_id, other_call_id):
        tel.recorded.append(
            ("call.unbridge", {"call_id": call_id, "other_call_id": other_call_id})
        )
        raise RuntimeError("unbridge failed")

    monkeypatch.setattr(tel, "call_unbridge", _unbridge_fail)

    with pytest.raises(RuntimeError, match="unbridge failed"):
        await CallControlService.transfer_to_queue(
            tel, tenant_id=7, employee_id=42, queue_id=5
        )

    assert "call.hangup" not in [m for m, _ in tel.recorded]
    assert finalize_events == []
    assert orch._pending_queue_transfer == {}


@pytest.mark.asyncio
async def test_queue_transfer_initiator_hangup_failure_is_non_fatal(monkeypatch):
    """Hangup failure after enqueue must not undo a successful queue transfer."""

    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)
    finalize_events: list = []
    await _stub_finalize(monkeypatch, finalize_events)

    _stub_resolve_current_call(monkeypatch)
    _stub_group_exists(monkeypatch, exists=True)
    _stub_candidates(monkeypatch, available_count=1, waitable=False)

    async def _bind_queue(*_a, **_k):
        return None

    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.bind_queue",
        _bind_queue,
    )

    async def _noop_wait(*_a, **_kw):
        await asyncio.sleep(0)

    monkeypatch.setattr(CallControlService, "_run_queue_transfer_wait", _noop_wait)

    tel = MockTelephonyClient()
    await tel.connect()
    tel.hangup_errors["webrtc-1"] = RuntimeError("hangup boom")

    result = await CallControlService.transfer_to_queue(
        tel, tenant_id=7, employee_id=42, queue_id=5
    )

    assert result["note"] == "queued_target"
    assert finalize_events and finalize_events[0]["employee_id"] == 42
    assert "sip-customer" in orch._pending_queue_transfer
    assert (
        "call.hangup",
        {"call_id": "webrtc-1", "reason": "transferred"},
    ) in tel.recorded


@pytest.mark.asyncio
async def test_queue_wait_handover_works_after_initiator_leg_gone(monkeypatch):
    """Background wait/handover must not depend on the initiator's media leg."""

    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)
    finalize_events: list = []
    await _stub_finalize(monkeypatch, finalize_events)

    _stub_resolve_current_call(monkeypatch)
    _stub_group_exists(monkeypatch, exists=True)
    _stub_candidates(monkeypatch, available_count=1, waitable=False)

    async def _bind_queue(*_a, **_k):
        return None

    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.bind_queue",
        _bind_queue,
    )

    async def _noop_wait(*_a, **_kw):
        await asyncio.sleep(0)

    monkeypatch.setattr(CallControlService, "_run_queue_transfer_wait", _noop_wait)

    tel = MockTelephonyClient()
    await tel.connect()

    result = await CallControlService.transfer_to_queue(
        tel, tenant_id=7, employee_id=42, queue_id=5
    )
    assert result["note"] == "queued_target"
    assert (
        "call.hangup",
        {"call_id": "webrtc-1", "reason": "transferred"},
    ) in tel.recorded
    await asyncio.sleep(0)

    # Now run the real wait loop with the initiator leg already gone.
    async def _budget(*_a, **_k):
        return 30.0

    async def _alive(*_a, **_k):
        return True

    async def _numbers(*_a, **_k):
        return "13800000000", "4008000000"

    monkeypatch.setattr(CallControlService, "_queue_transfer_wait_budget", _budget)
    monkeypatch.setattr(CallControlService, "_queue_transfer_call_alive", _alive)
    monkeypatch.setattr(
        CallControlService, "_queue_transfer_customer_numbers", _numbers
    )

    async def _pick(**_kw):
        return {"employee_id": 77, "name": "B"}

    monkeypatch.setattr(CallControlService, "_queue_transfer_pick_agent", _pick)

    async def _ring(*_a, **_kw):
        return True, "agent-leg-new", True, True

    monkeypatch.setattr(CallControlService, "_queue_transfer_ring_agent", _ring)

    async def _asr(_tenant_id):
        return True

    monkeypatch.setattr(
        "app.services.system_settings_service.SystemSettingsService"
        ".is_bridge_asr_enabled_managed",
        _asr,
    )

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(
        CallControlService, "_queue_transfer_restore_in_progress", _noop
    )
    monkeypatch.setattr(
        "app.services.cc_agent_status_service.CcAgentStatusService.set_status",
        _noop,
    )
    monkeypatch.setattr(
        "app.services.agent_webrtc_session_service.AgentWebRTCSessionService.set_busy",
        _noop,
    )
    monkeypatch.setattr(CallControlService, "_reassign_call_record_to_agent", _noop)
    monkeypatch.setattr(
        "app.services.cc_agent_resource_service.CcAgentResourceService.mark_in_call",
        _noop,
    )
    monkeypatch.setattr(CallControlService, "bind_agent_media_leg", _noop)

    import app.services.call_center.call_control.queue_transfer as qt_mod

    # Call the mixin implementation directly — transfer_to_queue stubbed wait.
    await qt_mod.QueueTransferMixin._run_queue_transfer_wait(
        tel,
        tenant_id=7,
        queue_id=5,
        customer_call_id="sip-customer",
    )

    assert (
        "call.bridge",
        {
            "call_id": "sip-customer",
            "user_call_id": "sip-customer",
            "other_call_id": "agent-leg-new",
            "transcribe": True,
            "keepalive_on_peer_hangup": True,
        },
    ) in tel.recorded
    assert sum(
        1
        for m, p in tel.recorded
        if m == "call.hangup" and p.get("call_id") == "webrtc-1"
    ) == 1


# ───────────────────────── background wait loop ─────────────────────────


@pytest.mark.asyncio
async def test_first_pick_answers_and_handover(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)

    async def _budget(*_a, **_k):
        return 30.0

    async def _alive(*_a, **_k):
        return True

    async def _numbers(*_a, **_k):
        return "13800000000", "4008000000"

    monkeypatch.setattr(CallControlService, "_queue_transfer_wait_budget", _budget)
    monkeypatch.setattr(CallControlService, "_queue_transfer_call_alive", _alive)
    monkeypatch.setattr(
        CallControlService, "_queue_transfer_customer_numbers", _numbers
    )

    async def _pick(**_kw):
        return {"employee_id": 77, "name": "B"}

    monkeypatch.setattr(CallControlService, "_queue_transfer_pick_agent", _pick)

    async def _ring(*_a, **_kw):
        return True, "agent-leg-1", True, True

    monkeypatch.setattr(CallControlService, "_queue_transfer_ring_agent", _ring)

    reassigned: list = []
    rebound: list = []
    releases: list = []
    restored: list = []

    class _Wf:
        def rebind_bridged_agent(self, agent_id):
            rebound.append(agent_id)

    orch._workflows["sip-customer"] = _Wf()

    async def _release(**kw):
        releases.append(kw)

    monkeypatch.setattr(CallControlService, "_queue_transfer_release_agent", _release)

    async def _asr(_tenant_id):
        return True

    monkeypatch.setattr(
        "app.services.system_settings_service.SystemSettingsService"
        ".is_bridge_asr_enabled_managed",
        _asr,
    )

    async def _restore(tenant_id, call_id):
        restored.append((tenant_id, call_id))

    async def _set_status(*_a, **_k):
        return None

    async def _set_busy(*_a, **_k):
        return None

    monkeypatch.setattr(
        CallControlService, "_queue_transfer_restore_in_progress", _restore
    )
    monkeypatch.setattr(
        "app.services.cc_agent_status_service.CcAgentStatusService.set_status",
        _set_status,
    )
    monkeypatch.setattr(
        "app.services.agent_webrtc_session_service.AgentWebRTCSessionService.set_busy",
        _set_busy,
    )

    async def _reassign(tenant_id, call_id, agent_id):
        reassigned.append((tenant_id, call_id, agent_id))

    monkeypatch.setattr(
        CallControlService, "_reassign_call_record_to_agent", _reassign
    )

    async def _mark_in_call(*_a, **_k):
        return None

    monkeypatch.setattr(
        "app.services.cc_agent_resource_service.CcAgentResourceService.mark_in_call",
        _mark_in_call,
    )

    async def _bind_media(*_a, **_k):
        return None

    monkeypatch.setattr(CallControlService, "bind_agent_media_leg", _bind_media)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService._run_queue_transfer_wait(
        tel,
        tenant_id=7,
        queue_id=5,
        customer_call_id="sip-customer",
    )

    assert (
        "call.bridge",
        {
            "call_id": "sip-customer",
            "user_call_id": "sip-customer",
            "other_call_id": "agent-leg-1",
            "transcribe": True,
            "keepalive_on_peer_hangup": True,
        },
    ) in tel.recorded
    assert restored == [(7, "sip-customer")]
    assert reassigned == [(7, "sip-customer", 77)]
    assert rebound == [77]
    assert orch.republished == [(7, 77)]
    assert releases == []


def _stub_customer_numbers(monkeypatch, frm: str = "10086", to: str = "400"):
    async def _numbers(*_a, **_k):
        return frm, to

    monkeypatch.setattr(
        CallControlService, "_queue_transfer_customer_numbers", _numbers
    )


@pytest.mark.asyncio
async def test_first_agent_no_answer_second_answers(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    _fake_orchestrator(monkeypatch)

    async def _budget(*_a, **_k):
        return 60.0

    async def _alive(*_a, **_k):
        return True

    monkeypatch.setattr(CallControlService, "_queue_transfer_wait_budget", _budget)
    monkeypatch.setattr(CallControlService, "_queue_transfer_call_alive", _alive)
    _stub_customer_numbers(monkeypatch)

    pick_kwargs: list[dict] = []

    async def _pick(**kw):
        pick_kwargs.append(kw)
        exclude = set(kw.get("exclude_employee_ids") or set())
        # Prefer agent 11 unless excluded — proves the wait loop advances.
        if 11 not in exclude:
            return {"employee_id": 11, "name": "ghost"}
        if 12 not in exclude:
            return {"employee_id": 12, "name": "live"}
        return None

    monkeypatch.setattr(CallControlService, "_queue_transfer_pick_agent", _pick)

    ring_targets: list[int] = []

    async def _ring(*_a, **kw):
        ring_targets.append(kw["employee_id"])
        if kw["employee_id"] == 11:
            return False, None, True, True
        return True, "leg-12", True, True

    monkeypatch.setattr(CallControlService, "_queue_transfer_ring_agent", _ring)

    releases: list[int] = []

    async def _release(**kw):
        releases.append(kw["employee_id"])

    monkeypatch.setattr(CallControlService, "_queue_transfer_release_agent", _release)

    handovers: list[int] = []

    async def _handover(*_a, **kw):
        handovers.append(kw["employee_id"])
        return True

    monkeypatch.setattr(CallControlService, "_queue_transfer_handover", _handover)

    hangups: list = []

    tel = MockTelephonyClient()
    await tel.connect()
    orig_hangup = tel.call_hangup

    async def _hangup(call_id, reason=None):
        hangups.append((call_id, reason))
        return await orig_hangup(call_id, reason=reason)

    monkeypatch.setattr(tel, "call_hangup", _hangup)

    await CallControlService._run_queue_transfer_wait(
        tel,
        tenant_id=7,
        queue_id=5,
        customer_call_id="sip-customer",
    )

    assert ring_targets == [11, 12]
    assert releases == [11]
    assert handovers == [12]
    assert hangups == []
    assert 11 in set(pick_kwargs[1].get("exclude_employee_ids") or set())


@pytest.mark.asyncio
async def test_budget_exhausted_hangs_up_customer(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    _fake_orchestrator(monkeypatch)

    async def _budget(*_a, **_k):
        return 1.0

    async def _alive(*_a, **_k):
        return True

    monkeypatch.setattr(CallControlService, "_queue_transfer_wait_budget", _budget)
    monkeypatch.setattr(CallControlService, "_queue_transfer_call_alive", _alive)
    _stub_customer_numbers(monkeypatch)

    async def _pick(**_kw):
        return None

    monkeypatch.setattr(CallControlService, "_queue_transfer_pick_agent", _pick)

    import app.services.call_center.call_control.queue_transfer as qt_mod

    monkeypatch.setattr(qt_mod, "_RETRY_INTERVAL_S", 1.0)

    # waited starts 0; after one sleep of 1.0s of wall clock via monotonic, exit.
    monotonic_values = iter([100.0, 101.0, 102.0, 103.0])

    def _mono():
        try:
            return next(monotonic_values)
        except StopIteration:
            return 200.0

    monkeypatch.setattr(qt_mod.time, "monotonic", _mono)

    async def _sleep(_s):
        return None

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    releases: list = []

    async def _release(**kw):
        releases.append(kw)

    monkeypatch.setattr(CallControlService, "_queue_transfer_release_agent", _release)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService._run_queue_transfer_wait(
        tel,
        tenant_id=7,
        queue_id=5,
        customer_call_id="sip-customer",
    )

    assert (
        "call.hangup",
        {"call_id": "sip-customer", "reason": "queue_transfer_timeout"},
    ) in tel.recorded
    assert releases == []


@pytest.mark.asyncio
async def test_customer_gone_stops_without_ringing(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    _fake_orchestrator(monkeypatch)

    async def _budget(*_a, **_k):
        return 30.0

    async def _alive(*_a, **_k):
        return False

    monkeypatch.setattr(CallControlService, "_queue_transfer_wait_budget", _budget)
    monkeypatch.setattr(CallControlService, "_queue_transfer_call_alive", _alive)
    _stub_customer_numbers(monkeypatch)

    rings: list = []

    async def _ring(*_a, **_kw):
        rings.append(1)
        return False, None, False, False

    monkeypatch.setattr(CallControlService, "_queue_transfer_ring_agent", _ring)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService._run_queue_transfer_wait(
        tel,
        tenant_id=7,
        queue_id=5,
        customer_call_id="sip-customer",
    )

    assert rings == []
    assert "call.hangup" not in [m for m, _ in tel.recorded]


@pytest.mark.asyncio
async def test_cancel_releases_reserved_agent(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    orch = _fake_orchestrator(monkeypatch)

    async def _budget(*_a, **_k):
        return 60.0

    async def _alive(*_a, **_k):
        return True

    monkeypatch.setattr(CallControlService, "_queue_transfer_wait_budget", _budget)
    monkeypatch.setattr(CallControlService, "_queue_transfer_call_alive", _alive)
    _stub_customer_numbers(monkeypatch)

    async def _pick(**_kw):
        return {"employee_id": 55, "name": "C"}

    monkeypatch.setattr(CallControlService, "_queue_transfer_pick_agent", _pick)

    started = asyncio.Event()

    async def _ring(*_a, **_kw):
        started.set()
        await asyncio.sleep(60)
        return False, None, True, True

    monkeypatch.setattr(CallControlService, "_queue_transfer_ring_agent", _ring)

    releases: list = []

    async def _release(**kw):
        releases.append(kw)

    monkeypatch.setattr(CallControlService, "_queue_transfer_release_agent", _release)

    tel = MockTelephonyClient()
    await tel.connect()

    task = asyncio.create_task(
        CallControlService._run_queue_transfer_wait(
            tel,
            tenant_id=7,
            queue_id=5,
            customer_call_id="sip-customer",
        )
    )
    orch.set_pending_queue_transfer("sip-customer", task)
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert releases
    assert releases[0]["employee_id"] == 55
    assert releases[0]["reason"] == "queue_transfer_cancelled"


@pytest.mark.asyncio
async def test_bridge_failure_releases_and_continues(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    _fake_orchestrator(monkeypatch)

    async def _budget(*_a, **_k):
        return 60.0

    async def _alive(*_a, **_k):
        return True

    monkeypatch.setattr(CallControlService, "_queue_transfer_wait_budget", _budget)
    monkeypatch.setattr(CallControlService, "_queue_transfer_call_alive", _alive)
    _stub_customer_numbers(monkeypatch)

    pick_ids = [21, 22]

    async def _pick(**_kw):
        if not pick_ids:
            return None
        return {"employee_id": pick_ids.pop(0), "name": "x"}

    monkeypatch.setattr(CallControlService, "_queue_transfer_pick_agent", _pick)

    async def _ring(*_a, **kw):
        return True, f"leg-{kw['employee_id']}", True, True

    monkeypatch.setattr(CallControlService, "_queue_transfer_ring_agent", _ring)

    releases: list[tuple] = []

    async def _release(**kw):
        releases.append((kw["employee_id"], kw["reason"]))

    monkeypatch.setattr(CallControlService, "_queue_transfer_release_agent", _release)

    async def _handover(*_a, **kw):
        if kw["employee_id"] == 21:
            return False
        return True

    monkeypatch.setattr(CallControlService, "_queue_transfer_handover", _handover)

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService._run_queue_transfer_wait(
        tel,
        tenant_id=7,
        queue_id=5,
        customer_call_id="sip-customer",
    )

    assert (21, "queue_transfer_bridge_failed") in releases
    assert "call.hangup" not in [m for m, _ in tel.recorded]


@pytest.mark.asyncio
async def test_no_db_session_held_during_ring_wait_or_sleep(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    _fake_orchestrator(monkeypatch)

    async def _budget(*_a, **_k):
        return 5.0

    monkeypatch.setattr(CallControlService, "_queue_transfer_wait_budget", _budget)
    _stub_customer_numbers(monkeypatch)

    alive_calls = {"n": 0}

    async def _alive(*_a, **_k):
        alive_calls["n"] += 1
        # Open+close a session like the real helper, then return.
        async with ccs_module.AsyncSessionLocal():
            pass
        return alive_calls["n"] < 3

    monkeypatch.setattr(CallControlService, "_queue_transfer_call_alive", _alive)

    async def _pick(**_kw):
        async with ccs_module.AsyncSessionLocal():
            pass
        return None

    monkeypatch.setattr(CallControlService, "_queue_transfer_pick_agent", _pick)

    session_during_sleep: list[bool] = []

    async def _sleep(seconds):
        session_during_sleep.append(tracker.active)
        return None

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    import app.services.call_center.call_control.queue_transfer as qt_mod

    monkeypatch.setattr(qt_mod, "_RETRY_INTERVAL_S", 1.0)
    # After two sleeps, force budget exhausted via waited inflation.
    mono = iter([0.0, 0.0, 1.0, 1.0, 2.0, 2.0, 20.0])

    def _mono():
        try:
            return next(mono)
        except StopIteration:
            return 99.0

    monkeypatch.setattr(qt_mod.time, "monotonic", _mono)

    async def _timeout(*_a, **_kw):
        return None

    monkeypatch.setattr(
        CallControlService, "_queue_transfer_timeout_hangup", _timeout
    )

    tel = MockTelephonyClient()
    await tel.connect()

    await CallControlService._run_queue_transfer_wait(
        tel,
        tenant_id=7,
        queue_id=5,
        customer_call_id="sip-customer",
    )

    assert session_during_sleep
    assert all(active is False for active in session_during_sleep)
    assert tracker.active is False
    assert tracker.opens == tracker.closes


@pytest.mark.asyncio
async def test_handover_bridge_failure_returns_false_without_reassign(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    _fake_orchestrator(monkeypatch)

    async def _asr(_t):
        return False

    monkeypatch.setattr(
        "app.services.system_settings_service.SystemSettingsService"
        ".is_bridge_asr_enabled_managed",
        _asr,
    )

    reassigned: list = []

    async def _reassign(*_a, **_k):
        reassigned.append(1)

    monkeypatch.setattr(
        CallControlService, "_reassign_call_record_to_agent", _reassign
    )

    tel = MockTelephonyClient()
    await tel.connect()

    async def _fail_bridge(*_a, **_k):
        raise RuntimeError("bridge boom")

    monkeypatch.setattr(tel, "call_bridge", _fail_bridge)

    ok = await CallControlService._queue_transfer_handover(
        tel,
        tenant_id=7,
        queue_id=5,
        customer_call_id="sip-customer",
        employee_id=77,
        agent_leg_call_id="leg-1",
        offer_id="offer-1",
        redis=object(),
    )

    assert ok is False
    assert reassigned == []


# ───────────────────────── review fixes ─────────────────────────


@pytest.mark.asyncio
async def test_enqueue_marks_queue_without_rewriting_lifecycle(monkeypatch):
    """Queue handoff appends queue facts without changing CDR lifecycle."""

    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    _fake_orchestrator(monkeypatch)
    finalize_events: list = []
    await _stub_finalize(monkeypatch, finalize_events)
    _stub_resolve_current_call(monkeypatch)
    _stub_group_exists(monkeypatch, exists=True)
    _stub_candidates(monkeypatch, available_count=1, waitable=False)

    bind_calls: list = []
    update_patches: list = []

    async def _bind_queue(db, tenant_id, call_id, queue_type, queue_id):
        bind_calls.append((tenant_id, call_id, queue_type, queue_id, "queued"))

    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.bind_queue",
        _bind_queue,
    )

    async def _noop_wait(*_a, **_kw):
        return None

    monkeypatch.setattr(CallControlService, "_run_queue_transfer_wait", _noop_wait)

    tel = MockTelephonyClient()
    await tel.connect()
    await CallControlService.transfer_to_queue(
        tel, tenant_id=7, employee_id=42, queue_id=5
    )
    assert bind_calls == [(7, "sip-customer", "employee_group", 5, "queued")]

    row = SimpleNamespace(call_id="sip-customer", lifecycle_status="active")

    async def _get_by_call_id(_db, call_id, tenant_id):
        assert call_id == "sip-customer"
        assert tenant_id == 7
        return row

    async def _update(_db, record, patch):
        update_patches.append(dict(patch))
        for k, v in patch.items():
            setattr(record, k, v)
        return record

    monkeypatch.setattr(
        "app.repositories.call_record_repository.CallRecordRepository.get_by_call_id",
        _get_by_call_id,
    )
    monkeypatch.setattr(
        "app.repositories.call_record_repository.CallRecordRepository.update",
        _update,
    )

    await CallControlService._queue_transfer_restore_in_progress(7, "sip-customer")

    assert update_patches == []


@pytest.mark.asyncio
async def test_hold_tone_not_started_when_first_pick_succeeds(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    orch = _fake_orchestrator(monkeypatch)

    tones: list[str] = []

    async def _play(*_a, **kw):
        tones.append(kw.get("scene", ""))

    async def _stop(*_a, **_kw):
        return None

    monkeypatch.setattr(CallControlService, "_play_scene_tone", _play)
    monkeypatch.setattr(CallControlService, "_stop_tone", _stop)

    async def _budget(*_a, **_k):
        return 30.0

    async def _alive(*_a, **_k):
        return True

    monkeypatch.setattr(CallControlService, "_queue_transfer_wait_budget", _budget)
    monkeypatch.setattr(CallControlService, "_queue_transfer_call_alive", _alive)
    _stub_customer_numbers(monkeypatch)

    async def _pick(**_kw):
        return {"employee_id": 77, "name": "B"}

    monkeypatch.setattr(CallControlService, "_queue_transfer_pick_agent", _pick)

    async def _ring(*_a, **_kw):
        return True, "leg-1", True, True

    monkeypatch.setattr(CallControlService, "_queue_transfer_ring_agent", _ring)

    async def _handover(*_a, **_kw):
        return True

    monkeypatch.setattr(CallControlService, "_queue_transfer_handover", _handover)

    tel = MockTelephonyClient()
    await tel.connect()
    await CallControlService._run_queue_transfer_wait(
        tel, tenant_id=7, queue_id=5, customer_call_id="sip-customer"
    )

    assert "hold" not in tones
    assert orch.ended == []


@pytest.mark.asyncio
async def test_hold_tone_started_once_after_failed_pick(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _fake_orchestrator(monkeypatch)

    tones: list[str] = []

    async def _play(*_a, **kw):
        tones.append(kw.get("scene", ""))

    monkeypatch.setattr(CallControlService, "_play_scene_tone", _play)
    monkeypatch.setattr(CallControlService, "_stop_tone", _play)

    async def _budget(*_a, **_k):
        return 3.0

    async def _alive(*_a, **_k):
        return True

    monkeypatch.setattr(CallControlService, "_queue_transfer_wait_budget", _budget)
    monkeypatch.setattr(CallControlService, "_queue_transfer_call_alive", _alive)
    _stub_customer_numbers(monkeypatch)

    async def _pick(**_kw):
        return None

    monkeypatch.setattr(CallControlService, "_queue_transfer_pick_agent", _pick)

    import app.services.call_center.call_control.queue_transfer as qt_mod

    monkeypatch.setattr(qt_mod, "_RETRY_INTERVAL_S", 1.0)
    mono = iter([0.0, 1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0])

    def _mono():
        try:
            return next(mono)
        except StopIteration:
            return 99.0

    monkeypatch.setattr(qt_mod.time, "monotonic", _mono)

    async def _sleep(_s):
        return None

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    async def _timeout(*_a, **_kw):
        return None

    monkeypatch.setattr(
        CallControlService, "_queue_transfer_timeout_hangup", _timeout
    )

    tel = MockTelephonyClient()
    await tel.connect()
    await CallControlService._run_queue_transfer_wait(
        tel, tenant_id=7, queue_id=5, customer_call_id="sip-customer"
    )

    assert tones.count("hold") == 1


@pytest.mark.asyncio
async def test_sip_unavailable_releases_without_call_ended_notify(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    orch = _fake_orchestrator(monkeypatch)

    async def _get_device(*_a, **_k):
        return {"device_type": "sip_phone"}

    monkeypatch.setattr(
        "app.services.agent_call_device_service.AgentCallDeviceService"
        ".get_current_device",
        _get_device,
    )

    async def _get_ext(*_a, **_k):
        return None

    monkeypatch.setattr(
        "app.repositories.sip_extension_repository.SipExtensionRepository"
        ".get_by_employee",
        _get_ext,
    )

    releases: list = []

    async def _release(redis, tenant_id, employee_id, **kw):
        releases.append((tenant_id, employee_id, kw.get("reason"), kw.get("expected_offer_id")))

    monkeypatch.setattr(
        "app.services.cc_agent_resource_service.CcAgentResourceService.release",
        _release,
    )

    answered, leg, pushed, is_webrtc = await CallControlService._queue_transfer_ring_sip(
        MockTelephonyClient(),
        tenant_id=7,
        queue_id=5,
        customer_call_id="sip-customer",
        employee_id=88,
        offer_id="offer-x",
        redis=object(),
        caller_number="13800000000",
        called_number="400",
    )
    assert is_webrtc is False
    assert (answered, leg, pushed) == (False, None, False)

    await CallControlService._queue_transfer_release_agent(
        redis=object(),
        tenant_id=7,
        employee_id=88,
        offer_id="offer-x",
        reason="queue_transfer_no_answer",
        customer_call_id="sip-customer",
        incoming_pushed=pushed,
    )

    assert releases == [(7, 88, "queue_transfer_no_answer", "offer-x")]
    assert orch.ended == []
    assert orch.incoming == []


@pytest.mark.asyncio
async def test_incoming_payload_includes_customer_numbers(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    orch = _fake_orchestrator(monkeypatch)

    async def _get_device(*_a, **_k):
        return {"device_type": "webrtc"}

    monkeypatch.setattr(
        "app.services.agent_call_device_service.AgentCallDeviceService"
        ".get_current_device",
        _get_device,
    )

    async def _is_connected(*_a, **_k):
        return True

    monkeypatch.setattr(
        "app.services.agent_status_service.AgentStatusService.is_connected",
        _is_connected,
    )

    async def _mark_ringing(*_a, **_k):
        return None

    monkeypatch.setattr(
        "app.services.cc_agent_resource_service.CcAgentResourceService.mark_ringing",
        _mark_ringing,
    )

    async def _accept_soon():
        await asyncio.sleep(0)
        for offer_id, fut in list(orch.offers.items()):
            orch.resolve_offer(
                offer_id, {"accept": True, "webrtc_call_id": "webrtc-leg"}
            )

    accept_task = asyncio.create_task(_accept_soon())

    answered, leg, pushed, _is_webrtc = await CallControlService._queue_transfer_ring_webrtc(
        tenant_id=7,
        queue_id=5,
        customer_call_id="sip-customer",
        employee_id=77,
        offer_id="offer-1",
        redis=object(),
        caller_number="13800000000",
        called_number="4008000000",
    )
    await accept_task

    assert answered is True
    assert leg == "webrtc-leg"
    assert pushed is True
    assert _is_webrtc is True
    assert orch.incoming
    payload = orch.incoming[0][2]
    assert payload["from"] == "13800000000"
    assert payload["to"] == "4008000000"
    assert payload["offer_id"] == "offer-1"
    assert payload["call_id"] == "sip-customer"
    assert payload["queue_type"] == "employee_group"
    assert payload["queue_id"] == 5


@pytest.mark.asyncio
async def test_webrtc_ring_skips_offline_agent_immediately(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    orch = _fake_orchestrator(monkeypatch)

    async def _is_connected(*_a, **_k):
        return False

    monkeypatch.setattr(
        "app.services.agent_status_service.AgentStatusService.is_connected",
        _is_connected,
    )

    answered, leg, pushed, _is_webrtc = await CallControlService._queue_transfer_ring_webrtc(
        tenant_id=7,
        queue_id=5,
        customer_call_id="sip-customer",
        employee_id=13,
        offer_id="offer-ghost",
        redis=object(),
    )

    assert (answered, leg, pushed) == (False, None, False)
    assert _is_webrtc is True
    assert orch.incoming == []
    assert orch.offers == {}
    assert orch.cancelled_offers == []


@pytest.mark.asyncio
async def test_unexpected_loop_error_releases_and_times_out(monkeypatch):
    tracker = SessionTracker()
    _install_tracked_session(monkeypatch, tracker)
    _bypass_tone(monkeypatch)
    _fake_orchestrator(monkeypatch)

    async def _budget(*_a, **_k):
        return 2.0

    async def _alive(*_a, **_k):
        return True

    monkeypatch.setattr(CallControlService, "_queue_transfer_wait_budget", _budget)
    monkeypatch.setattr(CallControlService, "_queue_transfer_call_alive", _alive)
    _stub_customer_numbers(monkeypatch)

    async def _pick(**_kw):
        return {"employee_id": 33, "name": "X"}

    monkeypatch.setattr(CallControlService, "_queue_transfer_pick_agent", _pick)

    async def _ring(*_a, **_kw):
        raise RuntimeError("boom mid-ring")

    monkeypatch.setattr(CallControlService, "_queue_transfer_ring_agent", _ring)

    releases: list = []

    async def _release(**kw):
        releases.append(kw)

    monkeypatch.setattr(CallControlService, "_queue_transfer_release_agent", _release)

    import app.services.call_center.call_control.queue_transfer as qt_mod

    monkeypatch.setattr(qt_mod, "_RETRY_INTERVAL_S", 1.0)
    # Each monotonic() call advances so error-recovery sleeps consume budget.
    mono_now = {"t": 0.0}

    def _mono():
        mono_now["t"] += 1.0
        return mono_now["t"]

    monkeypatch.setattr(qt_mod.time, "monotonic", _mono)

    async def _sleep(_s):
        return None

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    tel = MockTelephonyClient()
    await tel.connect()
    await CallControlService._run_queue_transfer_wait(
        tel, tenant_id=7, queue_id=5, customer_call_id="sip-customer"
    )

    assert releases
    assert releases[0]["employee_id"] == 33
    assert releases[0]["reason"] == "queue_transfer_error"
    assert (
        "call.hangup",
        {"call_id": "sip-customer", "reason": "queue_transfer_timeout"},
    ) in tel.recorded
