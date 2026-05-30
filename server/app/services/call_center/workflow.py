"""
Per-call voice flow workflow — drives the strategy-pattern node executors.

A workflow owns one call. The orchestrator creates one per `call.incoming`
and routes subsequent events to it via `handle_event(method, data)`.

State:
  - `current_node_id`: which node the workflow is executing
  - `waiting_for`: if not None, the (method, on_event) pair to resume
  - `variables`: runtime variables (sys.* + collected DTMF)

Lifecycle:
  start() → run() loops node-by-node until either:
    - we hit an End() → mark done
    - we hit a WaitForEvent() → store and return; orchestrator will call
      handle_event() when the matching kernel event arrives.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from app.libs.telephony.base import BaseTelephonyClient
from app.services.call_center.nodes import (
    End,
    ExecutionContext,
    Goto,
    NextStep,
    WaitForEvent,
    get_executor,
)


if TYPE_CHECKING:
    from app.services.call_center.orchestrator import CallCenterOrchestrator


logger = logging.getLogger(__name__)


class VoiceFlowWorkflow:

    def __init__(
        self,
        *,
        call_id: str,
        tenant_id: int,
        graph: dict,
        telephony: BaseTelephonyClient,
        orchestrator: "CallCenterOrchestrator | None" = None,
        initial_variables: dict[str, Any] | None = None,
    ) -> None:
        self.call_id = call_id
        self.tenant_id = tenant_id
        self.graph = graph
        self.telephony = telephony
        self.orchestrator = orchestrator
        self.done = asyncio.Event()
        self.ended_reason: str | None = None

        self._nodes_by_id: dict[str, dict] = {n["id"]: n for n in graph["nodes"]}
        self._edges_by_source: dict[str, dict[str, str]] = {}
        for e in graph.get("edges", []):
            self._edges_by_source.setdefault(e["source"], {})[e.get("source_handle", "next")] = e["target"]

        self.ctx = ExecutionContext(
            call_id=call_id,
            tenant_id=tenant_id,
            variables=dict(initial_variables or {}),
            edges_by_source=self._edges_by_source,
            telephony=telephony,
        )
        # Stash the orchestrator + flow header in the variables bag so node
        # executors (notably `assign_queue`) can fire side effects (Socket.IO
        # push, status transitions, CDR bind) without importing the orchestrator
        # module (keeps the executor file dependency-free for tests).
        self.ctx.variables["__orchestrator__"] = orchestrator
        self.ctx.variables["__tenant_id__"] = tenant_id

        self._current_node_id: str | None = self._find_start_node_id()
        self._waiting: tuple[str, Callable[..., Awaitable[NextStep]]] | None = None
        self._timeout_task: asyncio.Task | None = None

    def _find_start_node_id(self) -> str | None:
        for n in self.graph["nodes"]:
            if n["type"] == "start":
                return n["id"]
        return None

    # ─────────────────── Lifecycle ───────────────────

    async def start(self) -> None:
        await self._run_until_yield()

    async def handle_event(self, method: str, data: dict) -> None:
        """Resume the workflow when the FlowKit event we're waiting on arrives.

        Wraps `data` with `_event_method` so the executor's callback can
        tell which event triggered the resume (useful for collect, which
        accepts either `call.dtmf` or `call.speech_end`).
        """

        if self._waiting is None:
            logger.info(
                "workflow: dropping %s call_id=%s (not waiting)",
                method, self.call_id,
            )
            return
        wanted, callback = self._waiting
        wanted_methods = wanted if isinstance(wanted, tuple) else (wanted,)
        if method not in wanted_methods:
            logger.info(
                "workflow: dropping %s call_id=%s (waiting %s)",
                method, self.call_id, wanted_methods,
            )
            return
        logger.info(
            "workflow: handling %s call_id=%s data=%s",
            method, self.call_id,
            {k: v for k, v in data.items() if k in ("digit", "text", "reason")},
        )
        node = self._nodes_by_id.get(self._current_node_id or "")
        if node is None:
            return
        self._waiting = None
        self._cancel_timeout()
        # Inject the actual method into the event payload so multi-method
        # callbacks can branch on it without changing the public signature.
        enriched = dict(data)
        enriched["_event_method"] = method
        try:
            step = await callback(self.ctx, node, enriched)
        except Exception:  # noqa: BLE001
            logger.exception("Workflow callback crashed call_id=%s", self.call_id)
            await self._end("error")
            return
        stopped = await self._apply_step(step)
        if not stopped:
            await self._run_until_yield()

    def _cancel_timeout(self) -> None:
        if self._timeout_task is not None and not self._timeout_task.done():
            self._timeout_task.cancel()
        self._timeout_task = None

    async def _fire_timeout(
        self,
        delay_seconds: float,
        node_id: str,
        on_timeout: Callable[[ExecutionContext, dict], Awaitable[NextStep]],
    ) -> None:
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return
        # Only fire if we're still waiting on the same node (the wait could
        # have been resolved between the sleep finishing and us acquiring
        # control here).
        if self._waiting is None or self._current_node_id != node_id:
            return
        node = self._nodes_by_id.get(node_id)
        if node is None:
            return
        self._waiting = None
        try:
            step = await on_timeout(self.ctx, node)
        except Exception:  # noqa: BLE001
            logger.exception("Workflow timeout callback crashed call_id=%s", self.call_id)
            await self._end("error")
            return
        stopped = await self._apply_step(step)
        if not stopped:
            await self._run_until_yield()

    # ─────────────────── Internals ───────────────────

    async def _run_until_yield(self) -> None:
        while self._current_node_id is not None and not self.done.is_set():
            node = self._nodes_by_id.get(self._current_node_id)
            if node is None:
                logger.warning("Workflow: missing node %s", self._current_node_id)
                await self._end("missing_node")
                return
            executor = get_executor(node["type"])
            try:
                step = await executor.execute(self.ctx, node)
            except Exception:  # noqa: BLE001
                logger.exception("Workflow node %s crashed", node["id"])
                await self._end("error")
                return
            stop = await self._apply_step(step)
            if stop:
                return

    async def _apply_step(self, step: NextStep) -> bool:
        if isinstance(step, Goto):
            self._current_node_id = step.node_id
            return False
        if isinstance(step, WaitForEvent):
            # Store the method as-is (str or tuple) so handle_event can match.
            self._waiting = (step.method, step.on_event) if step.on_event else None
            # Arm a timeout if the executor requested one.
            self._cancel_timeout()
            if step.timeout_ms and step.on_timeout and self._current_node_id:
                self._timeout_task = asyncio.create_task(
                    self._fire_timeout(
                        step.timeout_ms / 1000.0,
                        self._current_node_id,
                        step.on_timeout,
                    ),
                    name=f"wf-timeout:{self.call_id}",
                )
            return True
        if isinstance(step, End):
            await self._end(step.reason)
            return True
        await self._end("unknown_step")
        return True

    async def _end(self, reason: str) -> None:
        self._cancel_timeout()
        self.ended_reason = reason
        self.done.set()

    # ─────────────────── Hangup signal ───────────────────

    async def on_call_hangup(self, data: dict) -> None:
        await self._end(data.get("reason") or "hangup")

    # ─────────────────── Bridged-agent accessor ───────────────────

    def bridged_agent_info(self) -> dict | None:
        """
        Returns `{tenant_id, employee_id}` for the agent the call was bridged
        to (set by AssignQueueExecutor). None if we never reached an
        assign_queue node or the pick failed.
        """

        emp_id = self.ctx.variables.get("sys._bridged_agent_id")
        if emp_id is None:
            return None
        return {"tenant_id": self.tenant_id, "employee_id": int(emp_id)}
