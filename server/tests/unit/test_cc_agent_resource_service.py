import fakeredis.aioredis
import pytest

from app.core.exceptions import ConflictError
from app.services.cc_agent_resource_service import CcAgentResourceService


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
