from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from app.core.exceptions import ConflictError
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_visible_ready_maps_to_idle(fake_redis):
    snapshot = await CcAgentResourceService.set_visible_status(
        fake_redis, tenant_id=7, employee_id=42, status="ready"
    )

    assert snapshot["visible_status"] == "ready"
    assert snapshot["resource_state"] == "idle"


@pytest.mark.asyncio
async def test_inbound_reserve_ringing_and_in_call(fake_redis):
    await CcAgentResourceService.set_visible_status(
        fake_redis, tenant_id=7, employee_id=42, status="ready"
    )

    reserved = await CcAgentResourceService.reserve_inbound(
        fake_redis,
        7,
        42,
        call_id="call-1",
        offer_id="offer-1",
        queue_id=9,
        ttl_seconds=30,
    )
    assert reserved is not None
    assert reserved["resource_state"] == "reserved"

    conflict = await CcAgentResourceService.reserve_inbound(
        fake_redis,
        7,
        42,
        call_id="call-2",
        offer_id="offer-2",
        queue_id=9,
        ttl_seconds=30,
    )
    assert conflict is None

    ringing = await CcAgentResourceService.mark_ringing(
        fake_redis,
        7,
        42,
        offer_id="offer-1",
        call_id="call-1",
        ttl_seconds=30,
    )
    assert ringing["resource_state"] == "ringing"

    valid = await CcAgentResourceService.validate_offer(
        fake_redis, 7, 42, offer_id="offer-1"
    )
    assert valid is not None
    assert valid["current_call_id"] == "call-1"

    in_call = await CcAgentResourceService.mark_in_call(
        fake_redis,
        7,
        42,
        call_id="call-1",
        direction="inbound",
        offer_id="offer-1",
    )
    assert in_call["visible_status"] == "busy"
    assert in_call["resource_state"] == "in_call"


@pytest.mark.asyncio
async def test_manual_status_change_rejected_during_real_call(fake_redis, monkeypatch):
    """A real in_call (backed by an active call record) must block manual
    status changes — the agent stays busy until the call ends."""

    await CcAgentResourceService.set_visible_status(fake_redis, 7, 42, "ready")
    await CcAgentResourceService.reserve_inbound(
        fake_redis, 7, 42, call_id="call-1", offer_id="o1", queue_id=9, ttl_seconds=300,
    )
    await CcAgentResourceService.mark_in_call(
        fake_redis, 7, 42, call_id="call-1", direction="inbound", offer_id="o1",
    )

    async def _get_latest_active(*_a, **_k):
        return SimpleNamespace(call_id="call-1", direction="inbound", state="in_progress")

    async def _no_active_session(*_a, **_k):
        return None

    monkeypatch.setattr(
        "app.services.cc_agent_status_service.CallRecordRepository.get_latest_active_for_agent",
        _get_latest_active,
    )
    monkeypatch.setattr(
        "app.services.cc_agent_status_service.AgentWebRTCSessionRepository.get_active",
        _no_active_session,
    )

    with pytest.raises(ConflictError):
        await CcAgentStatusService.set_status(
            db=None, tenant_id=7, employee_id=42, status="ready", reason=None, r=fake_redis,
        )

    snap = await CcAgentResourceService.get_snapshot(fake_redis, 7, 42)
    assert snap["resource_state"] == "in_call"


@pytest.mark.asyncio
async def test_manual_status_change_allowed_after_ghost_reconcile(fake_redis, monkeypatch):
    """A leaked in_call (no active call record or WebRTC session) is healed by
    reconcile_agent, so the manual status change succeeds on retry."""

    await CcAgentResourceService.set_visible_status(fake_redis, 7, 42, "ready")
    await CcAgentResourceService.reserve_inbound(
        fake_redis, 7, 42, call_id="ghost", offer_id="o1", queue_id=9, ttl_seconds=300,
    )
    await CcAgentResourceService.mark_in_call(
        fake_redis, 7, 42, call_id="ghost", direction="inbound", offer_id="o1",
    )
    # The resource is occupied with a non-expired lease, so a plain visible
    # status change is rejected.
    with pytest.raises(ConflictError):
        await CcAgentResourceService.set_visible_status(fake_redis, 7, 42, "ready")

    async def _no_active_call(*_a, **_k):
        return None

    async def _no_active_session(*_a, **_k):
        return None

    async def _no_consult_host(*_a, **_k):
        return None

    monkeypatch.setattr(
        "app.services.cc_agent_status_service.CallRecordRepository.get_latest_active_for_agent",
        _no_active_call,
    )
    monkeypatch.setattr(
        "app.services.cc_agent_status_service.AgentWebRTCSessionRepository.get_active",
        _no_active_session,
    )
    monkeypatch.setattr(
        "app.services.call_center.call_control_service.CallControlService._find_consult_host_for_target",
        _no_consult_host,
    )

    async def _sync_pg(_db, tenant_id, employee_id, status, reason=None):
        return {
            "employee_id": employee_id, "status": status, "reason": reason,
            "status_changed_at": None, "updated_at": None,
        }

    monkeypatch.setattr(CcAgentStatusService, "sync_pg_status", staticmethod(_sync_pg))

    result = await CcAgentStatusService.set_status(
        db=None, tenant_id=7, employee_id=42, status="ready", reason=None, r=fake_redis,
    )
    assert result["status"] == "ready"
    snap = await CcAgentResourceService.get_snapshot(fake_redis, 7, 42)
    assert snap["visible_status"] == "ready"
    assert snap["resource_state"] != "in_call"


@pytest.mark.asyncio
async def test_mark_in_call_is_idempotent_for_same_call(fake_redis):
    """The in_call flip happens twice for an internal-ring leg (the browser
    accept endpoint AND the initiator, same call_id). The first clears offer_id,
    so a repeat must not fail with a spurious 'Offer expired'."""

    await CcAgentResourceService.set_visible_status(fake_redis, 7, 42, "ready")
    await CcAgentResourceService.reserve_inbound(
        fake_redis, 7, 42, call_id="leg-1", offer_id="offer-1", queue_id=9, ttl_seconds=30,
    )
    # First flip: with the offer_id (clears it on transition to in_call).
    first = await CcAgentResourceService.mark_in_call(
        fake_redis, 7, 42, call_id="leg-1", direction="inbound", offer_id="offer-1",
    )
    assert first["resource_state"] == "in_call"
    assert first.get("in_call_since") is not None

    # Repeat with the (now-cleared) offer_id must not raise "Offer expired".
    again = await CcAgentResourceService.mark_in_call(
        fake_redis, 7, 42, call_id="leg-1", direction="inbound", offer_id="offer-1",
    )
    assert again["resource_state"] == "in_call"
    assert again["current_call_id"] == "leg-1"
    assert again.get("in_call_since") == first.get("in_call_since")

    # And the initiator's re-assert (no offer_id, same call) is also a no-op.
    reassert = await CcAgentResourceService.mark_in_call(
        fake_redis, 7, 42, call_id="leg-1", direction="inbound",
    )
    assert reassert["resource_state"] == "in_call"


@pytest.mark.asyncio
async def test_mark_in_call_idempotent_across_different_call_ids(fake_redis):
    """The two internal-ring paths key in_call on DIFFERENT call_ids (accept
    endpoint = reservation id, initiator = WebRTC leg id). Once in_call, a repeat
    with the other call_id must still be a no-op, not a 'Offer expired' 409."""

    await CcAgentResourceService.set_visible_status(fake_redis, 7, 42, "ready")
    await CcAgentResourceService.reserve_inbound(
        fake_redis, 7, 42, call_id="reservation-leg", offer_id="offer-1", queue_id=9, ttl_seconds=30,
    )
    # Initiator flips first, keyed on the WebRTC leg (clears offer_id).
    first = await CcAgentResourceService.mark_in_call(
        fake_redis, 7, 42, call_id="webrtc-leg", direction="inbound",
    )
    assert first["resource_state"] == "in_call"
    # Accept endpoint then marks with the reservation call_id AND the offer_id —
    # must not raise despite the offer_id now being cleared and call_id differing.
    second = await CcAgentResourceService.mark_in_call(
        fake_redis, 7, 42, call_id="reservation-leg", direction="inbound", offer_id="offer-1",
    )
    assert second["resource_state"] == "in_call"


@pytest.mark.asyncio
async def test_rekey_current_call_updates_occupied_resource(fake_redis):
    """Blind transfer to a browser-ring colleague: they answered on the
    internal consult leg (``internal:<offer>``) and own the customer call now.
    Re-keying must update current_call_id even though the resource is already
    in_call (where mark_in_call is a deliberate no-op), or the customer's own
    hangup finalize would trip 'Call resource belongs to another call'.

    The occupied hash is forged directly (the local fakeredis env breaks the
    watch/multi path used by reserve_inbound+mark_in_call)."""

    svc = CcAgentResourceService
    key = svc.key(7, 42)
    await fake_redis.hset(
        key,
        mapping=svc._base_mapping(
            visible_status="busy",
            resource_state="in_call",
            current_call_id="internal:offer-1",
            offer_id=None,
            queue_id=None,
            direction="inbound",
            reserved_until=svc._now_epoch() + 3600,
            in_call_since=svc._now_iso(),
        ),
    )
    before = svc._snapshot_from_raw(42, await fake_redis.hgetall(key))

    rekeyed = await svc.rekey_current_call(fake_redis, 7, 42, call_id="customer-call")
    assert rekeyed is not None
    assert rekeyed["resource_state"] == "in_call"
    assert rekeyed["current_call_id"] == "customer-call"
    assert rekeyed.get("in_call_since") == before.get("in_call_since")

    # The customer's hangup finalize now passes the ownership guard.
    released = await svc.mark_after_call_work(
        fake_redis, 7, 42, call_id="customer-call", reason="call_hangup",
    )
    assert released["resource_state"] == "after_call_work"


@pytest.mark.asyncio
async def test_rekey_current_call_noop_when_same_or_unoccupied(fake_redis):
    svc = CcAgentResourceService

    # Nothing occupied → no-op, no resource created.
    result = await svc.rekey_current_call(fake_redis, 7, 42, call_id="customer-call")
    assert result is None or result.get("current_call_id") != "customer-call"

    await fake_redis.hset(
        svc.key(7, 42),
        mapping=svc._base_mapping(
            visible_status="busy",
            resource_state="in_call",
            current_call_id="call-1",
            direction="inbound",
            reserved_until=svc._now_epoch() + 3600,
        ),
    )
    same = await svc.rekey_current_call(fake_redis, 7, 42, call_id="call-1")
    assert same is not None
    assert same["current_call_id"] == "call-1"


@pytest.mark.asyncio
async def test_manual_status_change_rejected_while_ringing(fake_redis):
    await CcAgentResourceService.set_visible_status(
        fake_redis, tenant_id=7, employee_id=42, status="ready"
    )
    await CcAgentResourceService.reserve_inbound(
        fake_redis,
        7,
        42,
        call_id="call-1",
        offer_id="offer-1",
        queue_id=9,
        ttl_seconds=30,
    )

    with pytest.raises(ConflictError):
        await CcAgentResourceService.set_visible_status(
            fake_redis, tenant_id=7, employee_id=42, status="offline"
        )


@pytest.mark.asyncio
async def test_release_ringing_returns_ready_idle(fake_redis):
    await CcAgentResourceService.set_visible_status(
        fake_redis, tenant_id=7, employee_id=42, status="ready"
    )
    await CcAgentResourceService.reserve_inbound(
        fake_redis,
        7,
        42,
        call_id="call-1",
        offer_id="offer-1",
        queue_id=9,
        ttl_seconds=30,
    )

    released = await CcAgentResourceService.release(
        fake_redis,
        7,
        42,
        reason="rejected",
        expected_offer_id="offer-1",
    )

    assert released["visible_status"] == "ready"
    assert released["resource_state"] == "idle"
    assert released["last_release_reason"] == "rejected"


@pytest.mark.asyncio
async def test_reserve_outbound_rejects_offline(fake_redis):
    await CcAgentResourceService.set_visible_status(
        fake_redis, tenant_id=7, employee_id=42, status="offline"
    )

    with pytest.raises(ConflictError, match="离线"):
        await CcAgentResourceService.reserve_outbound(
            fake_redis,
            7,
            42,
            reservation_id="outbound-token",
            ttl_seconds=30,
        )


@pytest.mark.asyncio
async def test_reserve_inbound_skips_offline(fake_redis):
    await CcAgentResourceService.set_visible_status(
        fake_redis, tenant_id=7, employee_id=42, status="offline"
    )

    reserved = await CcAgentResourceService.reserve_inbound(
        fake_redis,
        7,
        42,
        call_id="call-1",
        offer_id="offer-1",
        queue_id=9,
        ttl_seconds=30,
    )

    assert reserved is None


@pytest.mark.asyncio
async def test_outbound_release_restores_previous_visible_status(fake_redis):
    await CcAgentResourceService.set_visible_status(
        fake_redis, tenant_id=7, employee_id=42, status="break"
    )
    await CcAgentResourceService.reserve_outbound(
        fake_redis,
        7,
        42,
        reservation_id="outbound-token",
        ttl_seconds=30,
    )
    await CcAgentResourceService.bind_outbound_call(
        fake_redis,
        7,
        42,
        reservation_id="outbound-token",
        call_id="out-call-1",
        ttl_seconds=30,
    )

    released = await CcAgentResourceService.release(
        fake_redis,
        7,
        42,
        reason="agent_cancel",
        expected_call_id="out-call-1",
    )

    assert released["visible_status"] == "break"
    assert released["resource_state"] == "unavailable"


async def _seed_in_call(fake_redis, tenant=7, emp=42):
    await CcAgentResourceService.set_visible_status(fake_redis, tenant, emp, "ready")
    await CcAgentResourceService.reserve_inbound(
        fake_redis, tenant, emp, call_id="c1", offer_id="o1", queue_id=9, ttl_seconds=300,
    )
    await CcAgentResourceService.mark_in_call(
        fake_redis, tenant, emp, call_id="c1", direction="inbound", offer_id="o1",
    )


@pytest.mark.asyncio
async def test_get_for_employee_reports_busy_while_in_call(fake_redis, monkeypatch):
    """Consult target: PG may stay ready; API must still report busy from Redis."""
    import app.services.cc_agent_status_service as css_mod
    from app.services.call_workspace_context_service import CallWorkspaceContextService

    await _seed_in_call(fake_redis)
    monkeypatch.setattr(
        css_mod.AgentStatusRepository,
        "get_for_employee",
        AsyncMock(
            return_value=SimpleNamespace(
                employee_id=42,
                status="ready",
                reason=None,
                status_changed_at=None,
                updated_at=None,
            )
        ),
    )
    monkeypatch.setattr(
        css_mod.CcAgentStatusService,
        "reconcile_agent",
        AsyncMock(
            return_value={
                "resource_state": "in_call",
                "current_call_id": "c1",
                "visible_status": "busy",
            }
        ),
    )
    monkeypatch.setattr(
        css_mod.CallRecordRepository,
        "get_by_call_id",
        AsyncMock(return_value=SimpleNamespace(id=99, call_source="auto_outbound")),
    )
    monkeypatch.setattr(
        CallWorkspaceContextService,
        "get_auto_outbound_context",
        AsyncMock(
            return_value={
                "source": "auto_outbound",
                "task_id": 12,
                "record_id": 34,
            }
        ),
    )

    status = await CcAgentStatusService.get_for_employee(
        db=None, tenant_id=7, employee_id=42, r=fake_redis,
    )
    assert status["status"] == "busy"
    assert status["resource_state"] == "in_call"
    assert status["source"] == "auto_outbound"
    assert status["task_id"] == 12
    assert status["record_id"] == 34


@pytest.mark.asyncio
async def test_get_for_employee_restores_auto_outbound_context_during_wrap_up(
    fake_redis, monkeypatch
):
    """The wrap-up workspace must keep its task record tab after hangup."""
    import app.services.cc_agent_status_service as css_mod
    from app.services.call_workspace_context_service import CallWorkspaceContextService

    await _seed_in_call(fake_redis)
    await CcAgentResourceService.mark_after_call_work(
        fake_redis,
        7,
        42,
        call_id="c1",
        reason="call_hangup",
    )
    monkeypatch.setattr(
        css_mod.AgentStatusRepository,
        "get_for_employee",
        AsyncMock(
            return_value=SimpleNamespace(
                employee_id=42,
                status="after_call_work",
                reason=None,
                status_changed_at=None,
                updated_at=None,
            )
        ),
    )
    call_record = SimpleNamespace(id=99, call_source="auto_outbound")
    get_call_record = AsyncMock(return_value=call_record)
    monkeypatch.setattr(
        css_mod.CallRecordRepository,
        "get_by_call_id",
        get_call_record,
    )
    get_context = AsyncMock(
        return_value={
            "source": "auto_outbound",
            "task_id": 12,
            "record_id": 34,
        }
    )
    monkeypatch.setattr(
        CallWorkspaceContextService,
        "get_auto_outbound_context",
        get_context,
    )

    status = await CcAgentStatusService.get_for_employee(
        db=None,
        tenant_id=7,
        employee_id=42,
        r=fake_redis,
    )

    assert status["resource_state"] == "after_call_work"
    assert status["wrap_up_call_id"] == "c1"
    assert status["source"] == "auto_outbound"
    assert status["task_id"] == 12
    assert status["record_id"] == 34
    get_call_record.assert_awaited_once_with(None, "c1", 7)
    get_context.assert_awaited_once_with(
        None,
        tenant_id=7,
        call_record=call_record,
    )


@pytest.mark.asyncio
async def test_reconcile_agent_releases_ghost_in_call(fake_redis, monkeypatch):
    """in_call with no active call record AND no WebRTC session = ghost → freed."""
    import app.services.cc_agent_status_service as css_mod
    from app.services.call_center.call_control_service import CallControlService

    await _seed_in_call(fake_redis)
    monkeypatch.setattr(
        css_mod.CallRecordRepository, "get_latest_active_for_agent",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        css_mod.AgentWebRTCSessionRepository, "get_active", AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        CallControlService,
        "_find_consult_host_for_target",
        AsyncMock(return_value=None),
    )

    await CcAgentStatusService.reconcile_agent(db=None, r=fake_redis, tenant_id=7, employee_id=42)
    snap = await CcAgentResourceService.get_snapshot(fake_redis, 7, 42)
    assert snap is None or snap.get("resource_state") != "in_call"


@pytest.mark.asyncio
async def test_reconcile_agent_keeps_consult_target_without_cdr(fake_redis, monkeypatch):
    """Consult target B has no CDR; host still lists them → keep in_call on refresh."""
    import app.services.cc_agent_status_service as css_mod
    from app.services.call_center.call_control_service import CallControlService

    await _seed_in_call(fake_redis)
    monkeypatch.setattr(
        css_mod.CallRecordRepository, "get_latest_active_for_agent",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        css_mod.AgentWebRTCSessionRepository, "get_active", AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        CallControlService,
        "_find_consult_host_for_target",
        AsyncMock(return_value={"employee_id": 7, "tenant_id": 7}),
    )

    snap = await CcAgentStatusService.reconcile_agent(
        db=None, r=fake_redis, tenant_id=7, employee_id=42
    )
    assert snap["resource_state"] == "in_call"


@pytest.mark.asyncio
async def test_reconcile_agent_keeps_real_in_call(fake_redis, monkeypatch):
    """A real active call record backs the in_call → left untouched."""
    import app.services.cc_agent_status_service as css_mod

    await _seed_in_call(fake_redis)
    monkeypatch.setattr(
        css_mod.CallRecordRepository, "get_latest_active_for_agent",
        AsyncMock(return_value=SimpleNamespace(call_id="c1")),
    )
    monkeypatch.setattr(
        css_mod.AgentWebRTCSessionRepository, "get_active", AsyncMock(return_value=None),
    )

    snap = await CcAgentStatusService.reconcile_agent(db=None, r=fake_redis, tenant_id=7, employee_id=42)
    assert snap["resource_state"] == "in_call"


@pytest.mark.asyncio
async def test_reconcile_agent_skips_non_in_call_without_db(fake_redis, monkeypatch):
    """An idle/ready agent must not trigger any DB reads (hot poll path)."""
    import app.services.cc_agent_status_service as css_mod

    await CcAgentResourceService.set_visible_status(fake_redis, 7, 42, "ready")
    never = AsyncMock(side_effect=AssertionError("no DB read for idle agent"))
    monkeypatch.setattr(
        css_mod.CallRecordRepository, "get_latest_active_for_agent", never,
    )

    snap = await CcAgentStatusService.reconcile_agent(db=None, r=fake_redis, tenant_id=7, employee_id=42)
    assert snap["resource_state"] != "in_call"
    never.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_agent_restores_stale_offline_presence(fake_redis, monkeypatch):
    """Chose ready + connected, but resource drifted offline while idle → restored."""
    import app.services.cc_agent_status_service as css_mod
    import app.services.agent_status_service as ass_mod

    # Idle resource that has drifted to visible_status=offline.
    await CcAgentResourceService.set_visible_status(fake_redis, 7, 42, "offline")
    monkeypatch.setattr(
        ass_mod.AgentStatusService, "is_connected", AsyncMock(return_value=True),
    )

    healed = await CcAgentStatusService.reconcile_agent(
        db=None, r=fake_redis, tenant_id=7, employee_id=42,
        chosen_status="ready",
    )
    assert healed["visible_status"] == "ready"


@pytest.mark.asyncio
async def test_reconcile_agent_keeps_offline_when_disconnected(fake_redis, monkeypatch):
    """Chose ready but socket is gone → do NOT restore (don't ring a dead browser)."""
    import app.services.agent_status_service as ass_mod

    await CcAgentResourceService.set_visible_status(fake_redis, 7, 42, "offline")
    monkeypatch.setattr(
        ass_mod.AgentStatusService, "is_connected", AsyncMock(return_value=False),
    )

    snap = await CcAgentStatusService.reconcile_agent(
        db=None, r=fake_redis, tenant_id=7, employee_id=42, chosen_status="ready",
    )
    assert snap["visible_status"] == "offline"


@pytest.mark.asyncio
async def test_reconcile_agent_does_not_restore_when_chose_offline(fake_redis, monkeypatch):
    """Agent genuinely chose offline → leave offline even if connected."""
    import app.services.agent_status_service as ass_mod

    await CcAgentResourceService.set_visible_status(fake_redis, 7, 42, "offline")
    never = AsyncMock(side_effect=AssertionError("should not probe socket when chose offline"))
    monkeypatch.setattr(ass_mod.AgentStatusService, "is_connected", never)

    snap = await CcAgentStatusService.reconcile_agent(
        db=None, r=fake_redis, tenant_id=7, employee_id=42, chosen_status="offline",
    )
    assert snap["visible_status"] == "offline"
    never.assert_not_awaited()


@pytest.mark.asyncio
async def test_resource_transition_logs_from_to_call_id(fake_redis, caplog):
    """Every successful state change emits a structured resource_transition line."""
    import logging

    await CcAgentResourceService.set_visible_status(
        fake_redis, tenant_id=7, employee_id=42, status="ready"
    )

    with caplog.at_level(logging.INFO, logger="app.services.cc_agent_resource_service"):
        await CcAgentResourceService.reserve_inbound(
            fake_redis,
            7,
            42,
            call_id="call-log-1",
            offer_id="offer-log-1",
            queue_id=9,
            ttl_seconds=30,
        )
        await CcAgentResourceService.mark_ringing(
            fake_redis,
            7,
            42,
            offer_id="offer-log-1",
            call_id="call-log-1",
            ttl_seconds=30,
        )
        await CcAgentResourceService.mark_in_call(
            fake_redis,
            7,
            42,
            call_id="call-log-1",
            direction="inbound",
            offer_id="offer-log-1",
        )
        await CcAgentResourceService.mark_after_call_work(
            fake_redis, 7, 42, call_id="call-log-1", reason="call_hangup"
        )

    messages = [r.getMessage() for r in caplog.records if "resource_transition" in r.getMessage()]
    assert any("from=idle to=reserved" in m and "call_id=call-log-1" in m for m in messages)
    assert any("from=reserved to=ringing" in m for m in messages)
    assert any("from=ringing to=in_call" in m for m in messages)
    assert any("to=after_call_work" in m and "reason=mark_after_call_work:call_hangup" in m for m in messages)


def test_call_center_constants_active_sets_align():
    from app.constants.call_center import (
        ACTIVE_CALL_LIFECYCLE_STATUSES,
        ACTIVE_RESOURCE_STATES,
        AgentResourceState,
        CallLifecycleStatus,
    )

    assert ACTIVE_RESOURCE_STATES == {
        AgentResourceState.RESERVED.value,
        AgentResourceState.RINGING.value,
        AgentResourceState.IN_CALL.value,
    }
    assert ACTIVE_CALL_LIFECYCLE_STATUSES == {CallLifecycleStatus.ACTIVE.value}
