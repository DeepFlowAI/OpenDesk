"""
Per-call ownership for multi-node deployments.

FlowKit broadcasts call.incoming to every connected orchestrator, so exactly one
node must claim (and handle) each call; the rest skip. Ownership is a Redis
SET NX lock keyed on the call id.
"""
import fakeredis.aioredis
import pytest

from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center import orchestrator as orch_module
from app.services.call_center.orchestrator import CallCenterOrchestrator


def _node(node_id):
    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    orch._node_id = node_id
    return orch


@pytest.mark.asyncio
async def test_only_one_node_claims_a_call(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: fake)
    n1 = _node("node-1")
    n2 = _node("node-2")

    assert await n1._claim_call("c1") is True   # first node wins
    assert await n2._claim_call("c1") is False  # second node skips

    assert await n1._owns_call("c1") is True
    assert await n2._owns_call("c1") is False


@pytest.mark.asyncio
async def test_release_is_owner_only(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: fake)
    n1 = _node("node-1")
    n2 = _node("node-2")
    await n1._claim_call("c1")

    await n2._release_call("c1")           # non-owner cannot release
    assert await n1._owns_call("c1") is True

    await n1._release_call("c1")           # owner releases
    # Lock gone → a fresh node can now claim it.
    assert await n2._claim_call("c1") is True


@pytest.mark.asyncio
async def test_no_redis_always_owns(monkeypatch):
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: None)
    n = _node("solo")
    assert await n._claim_call("c1") is True
    assert await n._owns_call("c1") is True
