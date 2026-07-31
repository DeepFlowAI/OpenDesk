"""Cross-node outbound state: originator / webrtc pair / ended live in Redis."""
from __future__ import annotations

import pytest
import fakeredis.aioredis

from app.libs.telephony.base import CallEvent
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center import orchestrator as orch_module
from app.services.call_center.orchestrator import CallCenterOrchestrator


@pytest.mark.asyncio
async def test_outbound_originator_round_trips_via_redis(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "app.services.call_center.orchestrator._get_redis_client",
        lambda: fake,
    )
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._outbound_originators = {}
    orch._outbound_ended = {}
    orch._outbound_webrtc_pairs = {}
    orch._call_traces = {}

    await orch.register_outbound_call(
        call_id="out-1",
        tenant_id=9,
        employee_id=42,
        outbound_did="+86021",
    )
    # Simulate another node: empty local cache, hydrate from Redis.
    orch._outbound_originators.clear()
    info = await orch._peek_outbound_originator("out-1")
    assert info == (9, 42, "+86021")


@pytest.mark.asyncio
async def test_outbound_webrtc_pair_pop_from_redis(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "app.services.call_center.orchestrator._get_redis_client",
        lambda: fake,
    )
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._outbound_originators = {}
    orch._outbound_ended = {}
    orch._outbound_webrtc_pairs = {}

    await orch.pair_outbound_webrtc(
        outbound_call_id="out-1", webrtc_call_id="rtc-9"
    )
    orch._outbound_webrtc_pairs.clear()
    got = await orch._pop_outbound_webrtc("out-1")
    assert got == "rtc-9"
    assert await orch._pop_outbound_webrtc("out-1") is None


@pytest.mark.asyncio
async def test_outbound_ended_visible_across_nodes(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "app.services.call_center.orchestrator._get_redis_client",
        lambda: fake,
    )
    orch = CallCenterOrchestrator.__new__(CallCenterOrchestrator)
    orch._outbound_originators = {}
    orch._outbound_ended = {}
    orch._outbound_webrtc_pairs = {}

    await orch._mark_outbound_ended("out-1", "busy", 486)
    orch._outbound_ended.clear()
    ended = await orch.outbound_ended_reason("out-1")
    assert ended == ("busy", 486)


@pytest.mark.asyncio
async def test_hangup_before_originator_marks_ended_for_dial_webrtc(monkeypatch):
    """Carrier 404 in <50ms must still make /dial-webrtc return 410."""

    class _NoRow:
        def scalar_one_or_none(self):
            return None

    class _DbNoRow:
        async def execute(self, _q):
            return _NoRow()

    class _SessionNoRow:
        async def __aenter__(self):
            return _DbNoRow()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _SessionNoRow())
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: None)

    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    orch._outbound_originators = {}
    orch._outbound_ended = {}
    orch._outbound_webrtc_pairs = {}

    async def _noop(_call_id):
        return None

    monkeypatch.setattr(orch, "_delayed_trace_cleanup", _noop)
    monkeypatch.setattr(orch, "_delayed_outbound_cleanup", _noop)

    await orch._on_hangup(
        CallEvent(
            method="call.hangup",
            data={
                "call_id": "out-race",
                "reason": "rejected",
                "sip_status": 404,
            },
        )
    )

    assert await orch.outbound_ended_reason("out-race") == ("rejected", 404)
