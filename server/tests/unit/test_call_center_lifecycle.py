"""
Cross-store lifecycle consistency tests (regression net for the state-hardening
work — see develop/call-center-state-audit.md).

These lock in the invariants that repeatedly broke: after every terminal
transition the agent's Redis call resource must end in a NON-active state, and a
ghost in_call (no backing call record / session) must self-heal. They use
fakeredis + mocked repos so they run in CI without a live DB/Redis, and act as
the safety net before the _in_call_state → Redis migration.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from app.services.cc_agent_resource_service import (
    ACTIVE_RESOURCE_STATES,
    CcAgentResourceService,
)
from app.services.cc_agent_status_service import CcAgentStatusService


@pytest.fixture
def r():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


async def _go_in_call(r, tenant=7, emp=42, call_id="call-1", offer_id="off-1"):
    await CcAgentResourceService.set_visible_status(r, tenant, emp, "ready")
    await CcAgentResourceService.reserve_inbound(
        r, tenant, emp, call_id=call_id, offer_id=offer_id, queue_id=9, ttl_seconds=300,
    )
    await CcAgentResourceService.mark_in_call(
        r, tenant, emp, call_id=call_id, direction="inbound", offer_id=offer_id,
    )


@pytest.mark.asyncio
async def test_invariant_release_leaves_non_active(r):
    """After release the resource must not be in any active state."""
    await _go_in_call(r)
    await CcAgentResourceService.release(r, 7, 42, reason="hangup", allow_in_call=True)
    snap = await CcAgentResourceService.get_snapshot(r, 7, 42)
    assert snap is None or snap["resource_state"] not in ACTIVE_RESOURCE_STATES


@pytest.mark.asyncio
async def test_invariant_force_release_leaves_non_active(r):
    """force_release (reset / internal target cleanup) always frees the agent."""
    await _go_in_call(r)
    await CcAgentResourceService.force_release(r, 7, 42, reason="reset")
    snap = await CcAgentResourceService.get_snapshot(r, 7, 42)
    assert snap is None or snap["resource_state"] not in ACTIVE_RESOURCE_STATES


@pytest.mark.asyncio
async def test_invariant_after_call_work_then_ready(r):
    """acw → ready is a clean, reservable idle state again (no leftover lease)."""
    await _go_in_call(r)
    await CcAgentResourceService.mark_after_call_work(r, 7, 42, call_id="call-1")
    ready = await CcAgentResourceService.set_visible_status(r, 7, 42, "ready")
    assert ready["resource_state"] == "idle"
    # ...and can be reserved for a new inbound call.
    reserved = await CcAgentResourceService.reserve_inbound(
        r, 7, 42, call_id="call-2", offer_id="off-2", queue_id=9, ttl_seconds=30,
    )
    assert reserved is not None


@pytest.mark.asyncio
async def test_invariant_ghost_in_call_self_heals(r, monkeypatch):
    """A leaked in_call with no backing call record/session self-heals via the
    status read (reconcile_agent), returning the agent to a usable state."""
    import app.services.cc_agent_status_service as css_mod

    await _go_in_call(r)
    monkeypatch.setattr(
        css_mod.CallRecordRepository, "get_latest_active_for_agent",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        css_mod.AgentWebRTCSessionRepository, "get_active", AsyncMock(return_value=None),
    )

    await CcAgentStatusService.reconcile_agent(db=None, r=r, tenant_id=7, employee_id=42)
    snap = await CcAgentResourceService.get_snapshot(r, 7, 42)
    assert snap is None or snap["resource_state"] not in ACTIVE_RESOURCE_STATES
    # And a status change now succeeds (agent no longer locked out).

    async def _sync_pg(_db, tid, eid, status, reason=None):
        return {"employee_id": eid, "status": status, "reason": reason,
                "status_changed_at": None, "updated_at": None}

    monkeypatch.setattr(CcAgentStatusService, "sync_pg_status", staticmethod(_sync_pg))
    result = await CcAgentStatusService.set_status(
        db=None, tenant_id=7, employee_id=42, status="ready", reason=None, r=r,
    )
    assert result["status"] == "ready"


@pytest.mark.asyncio
async def test_invariant_real_in_call_survives_reconcile(r, monkeypatch):
    """A genuine in_call (backed by an active call record) must NOT be released
    by reconcile — the safety boundary that stops it killing live calls."""
    import app.services.cc_agent_status_service as css_mod

    await _go_in_call(r)
    monkeypatch.setattr(
        css_mod.CallRecordRepository, "get_latest_active_for_agent",
        AsyncMock(return_value=SimpleNamespace(call_id="call-1")),
    )
    monkeypatch.setattr(
        css_mod.AgentWebRTCSessionRepository, "get_active", AsyncMock(return_value=None),
    )
    snap = await CcAgentStatusService.reconcile_agent(db=None, r=r, tenant_id=7, employee_id=42)
    assert snap["resource_state"] == "in_call"
