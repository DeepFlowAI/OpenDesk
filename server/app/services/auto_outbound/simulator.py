"""
Simulated telephony path for auto-outbound acceptance testing.

When enabled, the dial engine never calls a real telephony client. Instead
this module invents a call_id, writes the Redis session mapping (via the
engine), and schedules asyncio tasks that fire the same handle_call_answered /
handle_call_ended callbacks the orchestrator would invoke for real calls.
"""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.configs.settings import settings
from app.services.auto_outbound.outcome_mapping import AutoOutboundTerminalState

if TYPE_CHECKING:
    from app.services.auto_outbound.engine import AutoOutboundDialEngine

logger = logging.getLogger(__name__)

AnsweredHandler = Callable[[str], Awaitable[None]]
EndedHandler = Callable[[str, str | None, int | None], Awaitable[None]]


@dataclass(frozen=True)
class SimulationProfile:
    answer_rate: float = 0.6
    min_ring_seconds: float = 2.0
    max_ring_seconds: float = 8.0
    min_talk_seconds: float = 5.0
    max_talk_seconds: float = 20.0
    # Relative weights among unanswered outcomes (normalized at pick time).
    weight_no_answer: float = 0.5
    weight_busy: float = 0.2
    weight_power_off: float = 0.2
    weight_invalid: float = 0.1


def profile_from_settings() -> SimulationProfile:
    return SimulationProfile(
        answer_rate=float(settings.AUTO_OUTBOUND_SIMULATION_ANSWER_RATE),
        min_ring_seconds=float(settings.AUTO_OUTBOUND_SIMULATION_MIN_RING_SECONDS),
        max_ring_seconds=float(settings.AUTO_OUTBOUND_SIMULATION_MAX_RING_SECONDS),
        min_talk_seconds=float(settings.AUTO_OUTBOUND_SIMULATION_MIN_TALK_SECONDS),
        max_talk_seconds=float(settings.AUTO_OUTBOUND_SIMULATION_MAX_TALK_SECONDS),
        weight_no_answer=float(settings.AUTO_OUTBOUND_SIMULATION_WEIGHT_NO_ANSWER),
        weight_busy=float(settings.AUTO_OUTBOUND_SIMULATION_WEIGHT_BUSY),
        weight_power_off=float(settings.AUTO_OUTBOUND_SIMULATION_WEIGHT_POWER_OFF),
        weight_invalid=float(settings.AUTO_OUTBOUND_SIMULATION_WEIGHT_INVALID),
    )


# Synthetic SIP codes used when the simulator picks an unanswered terminal state.
_UNANSWERED_SIP: dict[AutoOutboundTerminalState, int] = {
    AutoOutboundTerminalState.NO_ANSWER: 408,
    AutoOutboundTerminalState.BUSY: 486,
    AutoOutboundTerminalState.POWER_OFF: 480,
    AutoOutboundTerminalState.INVALID_NUMBER: 404,
}


def _pick_unanswered(profile: SimulationProfile) -> AutoOutboundTerminalState:
    choices = [
        (AutoOutboundTerminalState.NO_ANSWER, max(0.0, profile.weight_no_answer)),
        (AutoOutboundTerminalState.BUSY, max(0.0, profile.weight_busy)),
        (AutoOutboundTerminalState.POWER_OFF, max(0.0, profile.weight_power_off)),
        (AutoOutboundTerminalState.INVALID_NUMBER, max(0.0, profile.weight_invalid)),
    ]
    total = sum(weight for _, weight in choices)
    if total <= 0:
        return AutoOutboundTerminalState.NO_ANSWER
    roll = random.random() * total
    cursor = 0.0
    for state, weight in choices:
        cursor += weight
        if roll <= cursor:
            return state
    return choices[-1][0]


def new_simulated_call_id() -> str:
    return f"sim-{uuid.uuid4().hex}"


class CallSimulator:
    """Schedules ring / answer / hangup callbacks for a simulated call."""

    def __init__(
        self,
        *,
        profile: SimulationProfile | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.profile = profile or profile_from_settings()
        self._rng = rng or random.Random()
        self._tasks: set[asyncio.Task] = set()

    def spawn(
        self,
        call_id: str,
        *,
        on_answered: AnsweredHandler,
        on_ended: EndedHandler,
        # When True, skip the probabilistic answer and force answered → talk → end.
        force_answered: bool | None = None,
        force_terminal: AutoOutboundTerminalState | None = None,
    ) -> asyncio.Task:
        task = asyncio.create_task(
            self._run(
                call_id,
                on_answered=on_answered,
                on_ended=on_ended,
                force_answered=force_answered,
                force_terminal=force_terminal,
            ),
            name=f"auto-outbound-sim-{call_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def drain(self, timeout: float = 5.0) -> None:
        """
        Cancel in-flight simulated calls.

        Each cancelled ``_run`` emits ``on_ended(reason='cancelled')`` so the
        engine can release concurrency / clear calling targets (avoids leftovers
        on worker restart).
        """
        pending = [t for t in self._tasks if not t.done()]
        if not pending:
            return
        for t in pending:
            t.cancel()
        await asyncio.wait(pending, timeout=timeout)
        # Ensure cancelled tasks finish their CancelledError → on_ended path.
        await asyncio.gather(*pending, return_exceptions=True)

    async def _emit_cancelled(self, call_id: str, on_ended: EndedHandler) -> None:
        try:
            await on_ended(call_id, "cancelled", None)
        except Exception:  # noqa: BLE001
            logger.exception("simulator cancel hangup failed call_id=%s", call_id)

    async def _run(
        self,
        call_id: str,
        *,
        on_answered: AnsweredHandler,
        on_ended: EndedHandler,
        force_answered: bool | None,
        force_terminal: AutoOutboundTerminalState | None,
    ) -> None:
        profile = self.profile
        ring = self._rng.uniform(profile.min_ring_seconds, profile.max_ring_seconds)
        try:
            await asyncio.sleep(ring)
        except asyncio.CancelledError:
            # drain() / stop(): finalize so targets do not stick in calling.
            await self._emit_cancelled(call_id, on_ended)
            return

        answered = (
            force_answered
            if force_answered is not None
            else (self._rng.random() < profile.answer_rate)
        )
        if force_terminal is not None:
            answered = force_terminal == AutoOutboundTerminalState.ANSWERED

        if answered:
            try:
                await on_answered(call_id)
            except Exception:  # noqa: BLE001
                logger.exception("simulator on_answered failed call_id=%s", call_id)
            talk = self._rng.uniform(profile.min_talk_seconds, profile.max_talk_seconds)
            try:
                await asyncio.sleep(talk)
            except asyncio.CancelledError:
                await self._emit_cancelled(call_id, on_ended)
                return
            try:
                await on_ended(call_id, "normal", 200)
            except Exception:  # noqa: BLE001
                logger.exception("simulator on_ended(answered) failed call_id=%s", call_id)
            return

        terminal = force_terminal or _pick_unanswered(profile)
        if terminal == AutoOutboundTerminalState.ANSWERED:
            terminal = AutoOutboundTerminalState.NO_ANSWER
        sip = _UNANSWERED_SIP.get(terminal, 408)
        try:
            await on_ended(call_id, terminal.value, sip)
        except Exception:  # noqa: BLE001
            logger.exception("simulator on_ended failed call_id=%s", call_id)


def attach_simulator(engine: AutoOutboundDialEngine, simulator: CallSimulator | None = None) -> CallSimulator:
    """Convenience for tests: bind a simulator instance onto the engine."""
    sim = simulator or CallSimulator()
    engine._simulator = sim  # noqa: SLF001 — intentional test/helper wiring
    return sim
