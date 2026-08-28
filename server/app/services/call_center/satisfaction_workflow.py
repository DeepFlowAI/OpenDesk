"""Per-call runtime for a version-locked DTMF satisfaction survey."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from app.libs.telephony.base import BaseTelephonyClient, TelephonyRPCError
from app.services.audio_asset_service import AudioAssetService
from app.services.call_satisfaction_execution_service import (
    CallSatisfactionExecutionService,
    PreparedSatisfactionExecution,
)


logger = logging.getLogger(__name__)

EventCallback = Callable[[dict], Awaitable[None]]
TimeoutCallback = Callable[[], Awaitable[None]]

CALL_NOT_FOUND_RPC_CODE = -32002


def _call_is_gone(exc: BaseException | None) -> bool:
    """Whether the telephony kernel no longer knows this call."""
    return isinstance(exc, TelephonyRPCError) and exc.code == CALL_NOT_FOUND_RPC_CODE


class SatisfactionWorkflow:
    """Execute the satisfaction-only graph without ASR or queue capabilities."""

    def __init__(
        self,
        *,
        prepared: PreparedSatisfactionExecution,
        telephony: BaseTelephonyClient,
    ) -> None:
        self.execution_id = prepared.execution_id
        self.call_id = prepared.call_id
        self.tenant_id = prepared.tenant_id
        self.graph = prepared.graph
        self.telephony = telephony
        self.done = asyncio.Event()
        self.ended_reason: str | None = None

        self._nodes = {node["id"]: node for node in self.graph["nodes"]}
        self._edges: dict[str, dict[str, str]] = {}
        for edge in self.graph.get("edges", []):
            self._edges.setdefault(edge["source"], {})[
                edge.get("source_handle", "next")
            ] = edge["target"]
        self._current_node_id = next(
            (node["id"] for node in self.graph["nodes"] if node["type"] == "start"),
            None,
        )
        self._waiting: tuple[str, EventCallback] | None = None
        self._timeout_task: asyncio.Task | None = None
        self._expected_play_id: str | None = None
        self._retry_state: dict[tuple[str, str], int] = {}
        self._answers: dict[str, str] = {}
        self._required_questions: set[str] = set()
        self._finish_lock = asyncio.Lock()
        self._starting = False
        self._startup_failed = False

    async def start(self) -> None:
        await CallSatisfactionExecutionService.mark_started_managed(self.execution_id)
        self._starting = True
        try:
            await self._run()
        finally:
            self._starting = False
        if self._startup_failed:
            raise RuntimeError("Satisfaction workflow failed to start")

    async def handle_event(self, method: str, data: dict) -> None:
        if self.done.is_set() or self._waiting is None:
            return
        wanted, callback = self._waiting
        if method != wanted:
            return
        if method == "call.play_end" and self._expected_play_id:
            event_play_id = data.get("play_id")
            if event_play_id and event_play_id != self._expected_play_id:
                return
        self._waiting = None
        self._expected_play_id = None
        self._cancel_timeout()
        try:
            await callback(data)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Satisfaction event handler failed execution_id=%s",
                self.execution_id,
            )
            await self._handle_node_error(exc)

    async def on_call_hangup(self, data: dict) -> None:
        status = "partial" if self._answers else "unanswered"
        # Kernel SIP reasons ("remote_bye") and business language
        # ("customer_hangup") mean the same thing here: the customer left.
        reason = str(data.get("reason") or "customer_hangup")
        if reason in {"remote_bye", "bye", "caller_hangup", "media_timeout"}:
            reason = "customer_hangup"
        await self._finish(
            status=status,
            reason=reason,
            hangup=False,
        )

    def bridged_agent_info(self) -> None:
        return None

    def pending_offer_info(self) -> None:
        return None

    def _cancel_timeout(self) -> None:
        if self._timeout_task is not None and not self._timeout_task.done():
            self._timeout_task.cancel()
        self._timeout_task = None

    def _wait(
        self,
        method: str,
        callback: EventCallback,
        *,
        timeout_seconds: float | None = None,
        on_timeout: TimeoutCallback | None = None,
    ) -> None:
        self._waiting = (method, callback)
        self._cancel_timeout()
        if timeout_seconds is not None and on_timeout is not None:
            self._timeout_task = asyncio.create_task(
                self._fire_timeout(timeout_seconds, on_timeout),
                name=f"satisfaction-timeout:{self.execution_id}",
            )

    async def _fire_timeout(
        self, delay_seconds: float, callback: TimeoutCallback
    ) -> None:
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return
        if self.done.is_set() or self._waiting is None:
            return
        self._waiting = None
        self._expected_play_id = None
        self._timeout_task = None
        try:
            await callback()
        except Exception as exc:  # noqa: BLE001
            if _call_is_gone(exc):
                logger.info(
                    "Satisfaction survey ended: call gone execution_id=%s",
                    self.execution_id,
                )
            else:
                logger.exception(
                    "Satisfaction timeout handler failed execution_id=%s",
                    self.execution_id,
                )
            await self._handle_node_error(exc)

    async def _run(self) -> None:
        while (
            self._current_node_id is not None
            and self._waiting is None
            and not self.done.is_set()
        ):
            node = self._nodes.get(self._current_node_id)
            if node is None:
                await self._handle_node_error()
                return
            try:
                yielded = await self._execute_node(node)
            except Exception as exc:  # noqa: BLE001
                if _call_is_gone(exc):
                    logger.info(
                        "Satisfaction survey ended: call gone execution_id=%s node_id=%s",
                        self.execution_id,
                        node.get("id"),
                    )
                else:
                    logger.exception(
                        "Satisfaction node failed execution_id=%s node_id=%s",
                        self.execution_id,
                        node.get("id"),
                    )
                await self._handle_node_error(exc)
                return
            if yielded:
                return

    async def _execute_node(self, node: dict) -> bool:
        node_type = node["type"]
        if node_type == "start":
            return await self._advance(node, "next")
        if node_type == "play":
            return await self._execute_play(node)
        if node_type == "question":
            return await self._execute_question(node)
        if node_type == "condition":
            return await self._execute_condition(node)
        if node_type == "end":
            return await self._execute_end(node)
        await self._finish_from_answers("unsupported_node")
        return True

    async def _advance(self, node: dict, handle: str) -> bool:
        target = self._edges.get(node["id"], {}).get(handle)
        if target is None:
            await self._finish_from_answers(f"missing_outlet:{handle}")
            return True
        self._current_node_id = target
        return False

    async def _play_prompt(
        self, prompt: dict | None, *, barge_in: bool = False
    ) -> bool:
        if not prompt:
            return False
        kind = prompt.get("kind")
        if kind in {"auto_tts", "tts"}:
            text = str(prompt.get("text") or "").strip()
            if not text:
                return False
            self._expected_play_id = await self.telephony.call_say(
                self.call_id,
                text,
                barge_in=barge_in,
            )
            return True
        if kind == "audio":
            asset = await AudioAssetService.get_managed(
                int(prompt["asset_id"]), self.tenant_id
            )
            result = await self.telephony.call_play(
                self.call_id,
                audio_url=asset["preview_url"],
            )
            self._expected_play_id = result.get("play_id")
            return True
        return False

    async def _execute_play(self, node: dict) -> bool:
        started = await self._play_prompt(node["data"].get("prompt"))
        if not started:
            return await self._advance(node, "next")

        async def on_play_end(_data: dict) -> None:
            await self._advance(node, "next")
            await self._run()

        self._wait("call.play_end", on_play_end)
        return True

    async def _execute_question(self, node: dict) -> bool:
        if node["data"].get("required", True):
            self._required_questions.add(node["id"])
        await self._prompt_and_wait_for_answer(node, node["data"].get("prompt"))
        return True

    async def _prompt_and_wait_for_answer(
        self, node: dict, prompt: dict | None
    ) -> None:
        barge_in = not node["data"].get("barge_in_disabled", False)
        started = await self._play_prompt(prompt, barge_in=barge_in)
        if started and not barge_in:

            async def after_prompt(_data: dict) -> None:
                self._arm_question_input(node)

            self._wait("call.play_end", after_prompt)
            return
        self._arm_question_input(node)

    def _arm_question_input(self, node: dict) -> None:
        async def on_dtmf(data: dict) -> None:
            await self._handle_question_dtmf(node, str(data.get("digit") or ""))

        async def on_timeout() -> None:
            await self._handle_question_retry(node, "no_input")

        self._wait(
            "call.dtmf",
            on_dtmf,
            timeout_seconds=float(node["data"].get("timeout_seconds", 8)),
            on_timeout=on_timeout,
        )

    async def _handle_question_dtmf(self, node: dict, digit: str) -> None:
        option = next(
            (
                item
                for item in node["data"].get("options", [])
                if item.get("dtmf") == digit
            ),
            None,
        )
        if option is None:
            await self._handle_question_retry(node, "no_match")
            return

        if not node["data"].get("barge_in_disabled", False):
            with suppress(Exception):
                await self.telephony.call_stop(self.call_id, target="play")
        answer = await CallSatisfactionExecutionService.record_answer_managed(
            execution_id=self.execution_id,
            question_node_id=node["id"],
            digit=digit,
        )
        if answer is None:
            await self._handle_node_error()
            return
        self._answers[node["id"]] = answer["option_id"]
        await self._advance(node, "answered")
        await self._run()

    async def _handle_question_retry(self, node: dict, kind: str) -> None:
        with suppress(Exception):
            await self.telephony.call_stop(self.call_id, target="play")
        retry = node["data"].get("retry") or {}
        maximum = int(retry.get(kind, 0)) if retry.get("enabled", False) else 0
        key = (node["id"], kind)
        used = self._retry_state.get(key, 0)
        if used >= maximum:
            await self._advance(node, kind)
            await self._run()
            return
        self._retry_state[key] = used + 1
        prompt = retry.get(f"{kind}_prompt")
        await self._prompt_and_wait_for_answer(node, prompt)

    async def _execute_condition(self, node: dict) -> bool:
        selected = "default"
        for group in node["data"].get("groups", []):
            matches = [self._condition_matches(item) for item in group["conditions"]]
            if (all(matches) if group.get("logic", "AND") == "AND" else any(matches)):
                selected = group["id"]
                break
        return await self._advance(node, selected)

    def _condition_matches(self, condition: dict) -> bool:
        actual = self._answers.get(condition["question_node_id"])
        operator = condition["operator"]
        if operator == "is_answered":
            return actual is not None
        if operator == "eq":
            return actual == condition.get("option_id")
        if operator == "neq":
            return actual != condition.get("option_id")
        return False

    async def _execute_end(self, node: dict) -> bool:
        completion_type = node["data"].get("completion_type", "completed")

        async def finish() -> None:
            required_complete = self._required_questions.issubset(self._answers)
            if completion_type == "completed" and required_complete:
                status = "completed"
            else:
                status = "partial" if self._answers else "unanswered"
            await self._finish(status=status, reason=completion_type, hangup=True)

        started = await self._play_prompt(node["data"].get("pre_play"))
        if not started:
            await finish()
            return True

        async def on_play_end(_data: dict) -> None:
            await finish()

        self._wait("call.play_end", on_play_end)
        return True

    async def _handle_node_error(self, exc: BaseException | None = None) -> None:
        self._waiting = None
        self._cancel_timeout()
        if self._starting and not self._answers:
            self._startup_failed = True
            await self._finish(
                status="failed",
                reason="startup_failed",
                hangup=False,
            )
            return
        if _call_is_gone(exc):
            # The customer hung up in the middle of the survey. That is an
            # ordinary way for a survey to end, not a failure of this workflow,
            # and there is no leg left to hang up.
            await self._finish(
                status="partial" if self._answers else "unanswered",
                reason="customer_hangup",
                hangup=False,
            )
            return
        node = self._nodes.get(self._current_node_id or "")
        if node and node.get("type") == "question":
            target = self._edges.get(node["id"], {}).get("error")
            if target:
                self._current_node_id = target
                await self._run()
                return
        await self._finish_from_answers("workflow_error")

    async def _finish_from_answers(self, reason: str) -> None:
        await self._finish(
            status="partial" if self._answers else "unanswered",
            reason=reason,
            hangup=True,
        )

    async def _finish(self, *, status: str, reason: str, hangup: bool) -> None:
        async with self._finish_lock:
            if self.done.is_set():
                return
            self._waiting = None
            self._expected_play_id = None
            self._cancel_timeout()
            final_status = await CallSatisfactionExecutionService.finalize_managed(
                execution_id=self.execution_id,
                status=status,
                reason=reason,
            )
            self.ended_reason = final_status
            self.done.set()
        if hangup:
            with suppress(Exception):
                await self.telephony.call_hangup(
                    self.call_id,
                    reason=f"satisfaction_{final_status}",
                )
