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
async def test_manual_status_change_force_releases_stuck_resource(fake_redis, monkeypatch):
    """A leaked in_call (4h lease) must not lock an agent out of switching
    status — a manual status change force-releases the stuck resource."""

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

    # Repeat with the (now-cleared) offer_id must not raise "Offer expired".
    again = await CcAgentResourceService.mark_in_call(
        fake_redis, 7, 42, call_id="leg-1", direction="inbound", offer_id="offer-1",
    )
    assert again["resource_state"] == "in_call"
    assert again["current_call_id"] == "leg-1"

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
async def test_reconcile_agent_releases_ghost_in_call(fake_redis, monkeypatch):
    """in_call with no active call record AND no WebRTC session = ghost → freed."""
    import app.services.cc_agent_status_service as css_mod

    await _seed_in_call(fake_redis)
    monkeypatch.setattr(
        css_mod.CallRecordRepository, "get_latest_active_for_agent",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        css_mod.AgentWebRTCSessionRepository, "get_active", AsyncMock(return_value=None),
    )

    await CcAgentStatusService.reconcile_agent(db=None, r=fake_redis, tenant_id=7, employee_id=42)
    snap = await CcAgentResourceService.get_snapshot(fake_redis, 7, 42)
    assert snap is None or snap.get("resource_state") != "in_call"


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
