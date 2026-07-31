"""Orchestrator drain mode for blue/green API rollouts."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest

from app.libs.telephony.base import CallEvent
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center import orchestrator as orch_module
from app.services.call_center.orchestrator import CallCenterOrchestrator


async def _node(node_id: str) -> CallCenterOrchestrator:
    tel = MockTelephonyClient()
    await tel.connect()
    orch = CallCenterOrchestrator(telephony=tel)
    orch._node_id = node_id
    orch._started = True
    return orch


@pytest.mark.asyncio
async def test_draining_skips_incoming_without_claiming(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: fake)
    orch = await _node("node-drain")
    orch._draining = True

    await orch._on_incoming(
        CallEvent(
            method="call.incoming",
            data={"call_id": "c-drain-1", "transport": "sip", "from": "100", "to": "200"},
        )
    )

    assert await fake.exists(orch._call_owner_key("c-drain-1")) == 0
    assert "c-drain-1" not in orch._workflows
    assert orch.telephony.is_ready is True


@pytest.mark.asyncio
async def test_drain_waits_until_workflows_empty():
    orch = await _node("node-drain")
    mock_wf = MagicMock()
    mock_wf.bridged_agent_info.return_value = None
    mock_wf.pending_offer_info.return_value = None
    mock_wf.on_call_hangup = AsyncMock()
    orch._workflows["c1"] = mock_wf

    async def _clear_after_delay() -> None:
        await asyncio.sleep(0.05)
        orch._workflows.pop("c1", None)

    task = asyncio.create_task(_clear_after_delay())
    leftover = await orch.drain(timeout=2.0)
    await task

    assert leftover == 0
    assert orch._draining is True
    assert orch.telephony.is_ready is True
    assert orch.telephony._ready.is_set()


@pytest.mark.asyncio
async def test_drain_timeout_force_finalizes(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: fake)

    orch = await _node("node-drain")
    await orch._claim_call("c-stuck")

    mock_wf = MagicMock()
    mock_wf.tenant_id = 1
    mock_wf.bridged_agent_info.return_value = None
    mock_wf.pending_offer_info.return_value = None
    mock_wf.on_call_hangup = AsyncMock()
    orch._workflows["c-stuck"] = mock_wf

    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    class _FakeCM:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _FakeCM())

    leftover = await orch.drain(timeout=0.0)

    assert leftover == 1
    assert "c-stuck" not in orch._workflows
    mock_wf.on_call_hangup.assert_awaited()
    assert await fake.exists(orch._call_owner_key("c-stuck")) == 0
    assert orch.telephony.is_ready is True


@pytest.mark.asyncio
async def test_drain_keeps_ws_connected():
    orch = await _node("node-drain")
    assert orch.telephony.is_ready is True

    leftover = await orch.drain(timeout=0.1)

    assert leftover == 0
    assert orch.telephony.is_ready is True
