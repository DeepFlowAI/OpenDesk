"""Simulator drain must finalize in-flight calls with on_ended(cancelled)."""
from __future__ import annotations

import asyncio

import pytest

from app.services.auto_outbound.simulator import CallSimulator, SimulationProfile


@pytest.mark.asyncio
async def test_drain_emits_ended_for_ringing_call():
    ended: list[tuple] = []

    async def on_answered(_call_id: str) -> None:
        return None

    async def on_ended(call_id: str, reason: str | None, sip: int | None) -> None:
        ended.append((call_id, reason, sip))

    sim = CallSimulator(
        profile=SimulationProfile(
            answer_rate=1.0,
            min_ring_seconds=30.0,
            max_ring_seconds=30.0,
            min_talk_seconds=1.0,
            max_talk_seconds=1.0,
        )
    )
    sim.spawn("sim-drain-1", on_answered=on_answered, on_ended=on_ended)
    await asyncio.sleep(0.05)
    await sim.drain(timeout=2.0)
    assert ended == [("sim-drain-1", "cancelled", None)]
