"""
Self-healing for stranded call-center agents.

An agent bound `in_call` used to be stuck on "busy" forever if the call-end
event was lost (kernel crash / WS disconnect): `in_call` had no TTL and the
status switch rejected any transition. These tests cover the three recovery
paths:

  1. in_call carries a bounded lease; an expired lease frees the agent.
  2. reconcile_in_call releases agents whose call is gone from the kernel and
     renews the lease for calls still live.
  3. force_release is an unconditional escape hatch.
"""
import fakeredis.aioredis
import pytest

from app.services.cc_agent_resource_service import CcAgentResourceService as Svc


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


async def _put_in_call(r, *, tenant_id=7, employee_id=42, call_id="c1"):
    await Svc.set_visible_status(r, tenant_id, employee_id, "ready")
    await Svc.reserve_inbound(
        r, tenant_id, employee_id, call_id=call_id, offer_id="o1", queue_id=9, ttl_seconds=30
    )
    return await Svc.mark_in_call(
        r, tenant_id, employee_id, call_id=call_id, direction="inbound", offer_id="o1"
    )


async def _expire_lease(r, *, tenant_id=7, employee_id=42):
    # Backdate the lease so the resource is considered stale.
    await r.hset(Svc.key(tenant_id, employee_id), "reserved_until", "1")


@pytest.mark.asyncio
async def test_in_call_gets_a_lease(fake_redis):
    snap = await _put_in_call(fake_redis)
    assert snap["resource_state"] == "in_call"
    assert snap["reserved_until_epoch"] is not None  # bounded, not forever


@pytest.mark.asyncio
async def test_expired_in_call_lets_agent_switch_status(fake_redis):
    await _put_in_call(fake_redis)
    await _expire_lease(fake_redis)

    # Previously raised ConflictError("Current call resource is occupied").
    snap = await Svc.set_visible_status(fake_redis, 7, 42, "ready")
    assert snap["visible_status"] == "ready"
    assert snap["resource_state"] == "idle"


@pytest.mark.asyncio
async def test_get_snapshot_releases_expired_in_call(fake_redis):
    await _put_in_call(fake_redis)
    await _expire_lease(fake_redis)

    snap = await Svc.get_snapshot(fake_redis, 7, 42)
    assert snap["resource_state"] != "in_call"
    assert snap["last_release_reason"] == "in_call_lease_expired"


@pytest.mark.asyncio
async def test_reconcile_releases_stranded_and_keeps_live(fake_redis):
    await _put_in_call(fake_redis, employee_id=42, call_id="gone")
    await _put_in_call(fake_redis, employee_id=43, call_id="live")

    released = await Svc.reconcile_in_call(fake_redis, active_call_ids={"live"})
    assert released == [(7, 42, "gone")]  # (tenant, employee, call) for CDR cleanup

    stranded = await Svc.get_snapshot(fake_redis, 7, 42)
    assert stranded["resource_state"] != "in_call"
    assert stranded["last_release_reason"] == "reconnect_reconcile"

    live = await Svc.get_snapshot(fake_redis, 7, 43)
    assert live["resource_state"] == "in_call"  # untouched


@pytest.mark.asyncio
async def test_reconcile_renews_live_lease(fake_redis):
    await _put_in_call(fake_redis, call_id="live")
    # Nearly-expired lease for a call that IS still active.
    await fake_redis.hset(Svc.key(7, 42), "reserved_until", str(Svc._now_epoch() + 1))

    await Svc.reconcile_in_call(fake_redis, active_call_ids={"live"})

    snap = await Svc.get_snapshot(fake_redis, 7, 42)
    assert snap["resource_state"] == "in_call"
    assert snap["reserved_until_epoch"] > Svc._now_epoch() + 60  # lease extended


@pytest.mark.asyncio
async def test_recover_from_sources_leases_rebuilt_in_call(fake_redis):
    # Rebuilding in_call from a (possibly stale) call record must carry a lease
    # so the agent self-heals instead of being resurrected into permanent busy.
    snap = await Svc.recover_from_sources(
        fake_redis, 7, 42,
        visible_status="busy",
        active_call_id="c1",
        active_call_state="in_progress",
        active_call_direction="inbound",
    )
    assert snap["resource_state"] == "in_call"
    assert snap["reserved_until_epoch"] is not None


@pytest.mark.asyncio
async def test_force_release_frees_stuck_in_call(fake_redis):
    await _put_in_call(fake_redis)

    released = await Svc.force_release(fake_redis, 7, 42, reason="manual_reset")
    assert released["resource_state"] != "in_call"
    assert released["last_release_reason"] == "manual_reset"

    # And the agent can now go ready.
    snap = await Svc.set_visible_status(fake_redis, 7, 42, "ready")
    assert snap["visible_status"] == "ready"
