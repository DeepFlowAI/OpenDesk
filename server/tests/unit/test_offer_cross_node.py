"""
Cross-node agent offer resolution.

An agent's accept can hit any node, but the offer's Future lives on the call's
owner node. deliver_offer_decision resolves locally when possible, otherwise
forwards the decision over Redis and the owning node's subscriber resolves it.
"""
import asyncio
from contextlib import suppress

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
async def test_local_offer_resolves_without_redis(monkeypatch):
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: None)
    node = _node("solo")
    fut = node.register_offer("o1")

    assert await node.deliver_offer_decision("o1", {"accept": True}) is True
    assert fut.done() and fut.result() == {"accept": True}


@pytest.mark.asyncio
async def test_missing_offer_no_redis_returns_false(monkeypatch):
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: None)
    node = _node("solo")
    assert await node.deliver_offer_decision("nope", {"accept": True}) is False


@pytest.mark.asyncio
async def test_offer_resolved_on_owner_from_another_node(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis()
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: fake)
    owner = _node("owner")
    edge = _node("edge")

    fut = owner.register_offer("o1")  # Future lives on the owner
    sub = asyncio.create_task(owner._offer_resolve_loop())
    await asyncio.sleep(0.05)  # let the subscriber attach

    # The accept lands on a different node.
    resolved = await edge.deliver_offer_decision(
        "o1", {"accept": True, "webrtc_call_id": "w1"}
    )

    assert resolved is True
    assert fut.done() and fut.result() == {"accept": True, "webrtc_call_id": "w1"}

    sub.cancel()
    with suppress(asyncio.CancelledError):
        await sub
