"""
Voice flow node executors — one Strategy class per node type.

Each executor receives an `ExecutionContext` (call state + telephony +
db factory) and a raw graph_json node dict. It returns a `NextStep`:
  - `Goto(node_id)` — jump synchronously
  - `WaitForEvent(method, on_event)` — yield control until FlowKit event
  - `End()` — flow terminates

Adding a new node type:
  1. Create a new subclass of `BaseNodeExecutor` here.
  2. Register it in `NODE_EXECUTORS`.
No other code needs to change (Open-Closed Principle).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.libs.telephony.base import BaseTelephonyClient
from app.services.call_center.queue import get_queue_picker
from app.services.call_center.variables import evaluate_group


# ─────────────────── Context + Step Types ───────────────────


@dataclass
class ExecutionContext:
    call_id: str
    tenant_id: int
    variables: dict[str, Any] = field(default_factory=dict)
    # Pre-mapped {source_node_id: {handle: target_node_id}} for fast edge lookup.
    edges_by_source: dict[str, dict[str, str]] = field(default_factory=dict)
    telephony: BaseTelephonyClient = None  # injected by Workflow
    # Tracks retry counters per node_id+kind (no_input / no_match).
    retry_state: dict[tuple[str, str], int] = field(default_factory=dict)


@dataclass
class Goto:
    node_id: str


@dataclass
class WaitForEvent:
    # `method` is either a single FlowKit event name (e.g. "call.dtmf") or a
    # tuple of accepted ones (e.g. ("call.dtmf", "call.speech_end")). The
    # workflow resolves whichever arrives first; the on_event callback can
    # inspect `ev` to figure out which.
    method: str | tuple[str, ...]
    timeout_ms: int | None = None
    on_event: Callable[[ExecutionContext, dict, dict], Awaitable["NextStep"]] | None = None
    on_timeout: Callable[[ExecutionContext, dict], Awaitable["NextStep"]] | None = None

    def matches(self, m: str) -> bool:
        if isinstance(self.method, tuple):
            return m in self.method
        return self.method == m


@dataclass
class End:
    reason: str = "normal"


NextStep = Goto | WaitForEvent | End


# ─────────────────── Edge helpers ───────────────────


def edge_target(ctx: ExecutionContext, node_id: str, handle: str) -> str | None:
    return ctx.edges_by_source.get(node_id, {}).get(handle)


def goto_or_end(ctx: ExecutionContext, node_id: str, handle: str) -> NextStep:
    target = edge_target(ctx, node_id, handle)
    return Goto(target) if target else End()


# ─────────────────── Base + per-type executors ───────────────────


class BaseNodeExecutor(ABC):

    @abstractmethod
    async def execute(self, ctx: ExecutionContext, node: dict) -> NextStep: ...


class StartExecutor(BaseNodeExecutor):

    async def execute(self, ctx: ExecutionContext, node: dict) -> NextStep:
        return goto_or_end(ctx, node["id"], "next")


class PlayExecutor(BaseNodeExecutor):

    async def execute(self, ctx: ExecutionContext, node: dict) -> NextStep:
        prompt = node["data"]["prompt"]
        text = prompt.get("text", "") if prompt.get("kind") == "tts" else f"[audio #{prompt.get('asset_id')}]"
        await ctx.telephony.call_say(ctx.call_id, text)

        async def _on_play_end(ctx_: ExecutionContext, node_: dict, _data: dict) -> NextStep:
            return goto_or_end(ctx_, node_["id"], "next")

        return WaitForEvent(method="call.play_end", on_event=_on_play_end)


class CollectExecutor(BaseNodeExecutor):
    """
    Collect input from the SIP user leg.

    Spec (1.6.2 §3.3.2) is "DTMF only". In practice many trunks drop
    in-band DTMF or callers instinctively *speak* their answer instead of
    pressing the keypad. To keep IVRs usable end-to-end we accept either:

      - `call.dtmf` (SIP DTMF, the spec'd path)
      - `call.speech_end` (ASR transcript, normalized to a digit string —
        Chinese number words like "一/二/三" are mapped to "1/2/3")

    `call.listen` is issued so the kernel actually runs ASR.

    On `no_input` timeout we replay the prompt and try again (bounded by
    retry.no_input).
    """

    async def execute(self, ctx: ExecutionContext, node: dict) -> NextStep:
        data = node["data"]
        prompt = data["prompt"]
        text = prompt.get("text", "") if prompt.get("kind") == "tts" else f"[audio #{prompt.get('asset_id')}]"
        await ctx.telephony.call_say(ctx.call_id, text)
        # Start ASR so we have a fallback when in-band DTMF is dropped by
        # the trunk. Pass a short timeout so the kernel can recycle the
        # ASR session if the caller stays silent.
        try:
            await ctx.telephony.call_listen(
                ctx.call_id,
                timeout_ms=data["timeout"]["first_input_ms"],
            )
        except Exception:  # noqa: BLE001
            # Some kernels treat repeated listens as no-ops; don't bail
            # on a listen error — DTMF is still in play.
            pass
        return _await_first_input(node, data, attempt=0)


# ── Chinese / English digit-word → digit mapping for ASR fallback ──
_DIGIT_WORD_MAP = {
    # numerals
    "0": "0", "1": "1", "2": "2", "3": "3", "4": "4",
    "5": "5", "6": "6", "7": "7", "8": "8", "9": "9",
    # Chinese cardinal
    "零": "0", "一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
    "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
    # Chinese formal cardinal
    "壹": "1", "贰": "2", "叁": "3", "肆": "4", "伍": "5",
    "陆": "6", "柒": "7", "捌": "8", "玖": "9",
    # English single-word
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}


def _extract_digit(text: str) -> str | None:
    """Pull the first digit (Arabic/Chinese/English word) out of ASR text."""

    if not text:
        return None
    cleaned = text.strip().lower()
    # Whole-word match first (English).
    if cleaned in _DIGIT_WORD_MAP:
        return _DIGIT_WORD_MAP[cleaned]
    # Scan char-by-char for the first matching numeral or CJK digit.
    for ch in cleaned:
        if ch in _DIGIT_WORD_MAP:
            return _DIGIT_WORD_MAP[ch]
    return None


def _await_first_input(node: dict, data: dict, *, attempt: int) -> NextStep:
    # Pump the timeout up so the caller has time to think + speak/press.
    # FlowKit ASR sessions also need refresh; a 5s window is too tight if
    # the user mumbles ("嗯。") first and only later says the real digit.
    first_timeout_ms = max(data["timeout"]["first_input_ms"], 20_000)
    retry_cfg = data.get("retry", {"enabled": False, "no_input": 0})
    max_no_input_retries = retry_cfg["no_input"] if retry_cfg.get("enabled") else 0

    async def _on_input(ctx_: ExecutionContext, node_: dict, ev: dict) -> NextStep:
        import logging
        log = logging.getLogger(__name__)
        method = ev.get("_event_method", "")
        # Normalize whichever event we got to a single digit (or empty string).
        if method == "call.dtmf":
            digit = ev.get("digit", "")
            log.info("collect: DTMF received digit=%r call_id=%s", digit, ctx_.call_id)
        else:  # call.speech_end
            text = ev.get("text", "")
            digit = _extract_digit(text) or ""
            log.info(
                "collect: ASR text=%r → digit=%r call_id=%s",
                text, digit, ctx_.call_id,
            )
            if not digit:
                # ASR returned filler ("嗯", "啊", a whole sentence with no
                # digit). Re-arm the ASR session in the kernel and keep
                # waiting with a fresh long timeout — this is NOT a retry,
                # the user just hasn't given us the answer yet.
                try:
                    await ctx_.telephony.call_listen(
                        ctx_.call_id, timeout_ms=first_timeout_ms,
                    )
                except Exception:  # noqa: BLE001
                    pass
                return WaitForEvent(
                    method=("call.dtmf", "call.speech_end"),
                    on_event=_on_input,
                    timeout_ms=first_timeout_ms,
                    on_timeout=_on_no_input,
                )

        mode = data["input"]["mode"]
        output_var = data["output_variable"]

        if mode == "single":
            ctx_.variables[output_var] = digit
            return goto_or_end(ctx_, node_["id"], "success")

        # multi / any — accumulate into the output_var buffer.
        buf = str(ctx_.variables.get(output_var, ""))
        terminator = data["input"].get("terminator")
        if terminator and digit == terminator:
            ctx_.variables[output_var] = buf
            return goto_or_end(ctx_, node_["id"], "success")
        buf += digit
        ctx_.variables[output_var] = buf
        max_d = data["input"]["max_digits"]
        if mode == "multi" and len(buf) >= max_d:
            return goto_or_end(ctx_, node_["id"], "success")
        return WaitForEvent(
            method=("call.dtmf", "call.speech_end"),
            on_event=_on_input,
            timeout_ms=first_timeout_ms,
            on_timeout=_on_no_input,
        )

    async def _on_no_input(ctx_: ExecutionContext, node_: dict) -> NextStep:
        import logging
        log = logging.getLogger(__name__)
        if attempt < max_no_input_retries:
            log.info(
                "collect: no_input retry %d/%d call_id=%s",
                attempt + 1, max_no_input_retries, ctx_.call_id,
            )
            prompt = data["prompt"]
            text = prompt.get("text", "") if prompt.get("kind") == "tts" else f"[audio #{prompt.get('asset_id')}]"
            await ctx_.telephony.call_say(ctx_.call_id, text)
            try:
                await ctx_.telephony.call_listen(
                    ctx_.call_id, timeout_ms=first_timeout_ms,
                )
            except Exception:  # noqa: BLE001
                pass
            return _await_first_input(node_, data, attempt=attempt + 1)
        # Caller never gave us a valid digit. If the graph wired the
        # `no_input` outlet, follow it; otherwise fall back to a polite
        # hangup so we don't strand the caller in dead silence.
        target = edge_target(ctx_, node_["id"], "no_input")
        if target:
            log.info("collect: timeout → no_input outlet call_id=%s", ctx_.call_id)
            return Goto(target)
        log.info("collect: timeout, no_input outlet unwired — hanging up call_id=%s", ctx_.call_id)
        await ctx_.telephony.call_say(
            ctx_.call_id, "未收到您的输入，本次通话即将结束。",
        )
        await ctx_.telephony.call_hangup(ctx_.call_id, reason="no_input_timeout")
        return End("no_input_no_outlet")

    return WaitForEvent(
        method=("call.dtmf", "call.speech_end"),
        on_event=_on_input,
        timeout_ms=first_timeout_ms,
        on_timeout=_on_no_input,
    )


class ConditionExecutor(BaseNodeExecutor):

    async def execute(self, ctx: ExecutionContext, node: dict) -> NextStep:
        for g in node["data"]["groups"]:
            if evaluate_group(g, ctx.variables):
                return goto_or_end(ctx, node["id"], g["id"])
        return goto_or_end(ctx, node["id"], "default")


class AssignQueueExecutor(BaseNodeExecutor):
    """
    Ring-on-demand transfer to an agent selected from one or more queues.
    """

    _FAILURE_PROMPT_FIELDS = {
        "queue_limit_reached": "queue_limit_prompt_text",
        "no_available_queue": "no_available_queue_prompt_text",
        "queue_timeout": "queue_timeout_prompt_text",
        "agent_no_answer": "agent_no_answer_prompt_text",
    }

    _DEFAULT_FAILURE_PROMPTS = {
        "queue_limit_reached": "当前排队人数较多，请稍后再拨。",
        "no_available_queue": "当前坐席繁忙，请稍后再拨。",
        "queue_timeout": "暂时无法接通坐席，请稍后再拨。",
        "agent_no_answer": "暂无坐席接听，请稍后再拨。",
    }

    async def execute(self, ctx: ExecutionContext, node: dict) -> NextStep:
        import asyncio
        import logging
        import uuid
        from contextlib import suppress

        log = logging.getLogger(__name__)
        data = node.get("data") or {}
        timeout_s = float(data.get("timeout_seconds") or 60)

        from app.db.session import AsyncSessionLocal
        from app.db.redis import redis_client
        from app.services.call_record_service import CallRecordService
        from app.services.cc_agent_resource_service import CcAgentResourceService
        from app.services.call_center.assign_queue import AssignQueueSelector

        picker = get_queue_picker()
        pick: dict | None = None
        offer_id = uuid.uuid4().hex
        try:
            redis = redis_client.client
        except RuntimeError as exc:
            log.error(
                "assign_queue: Redis is required for call-center resource reservation"
            )
            raise RuntimeError(
                "Call-center assign_queue requires Redis for agent resource reservation"
            ) from exc

        async with AsyncSessionLocal() as db:
            selection = await AssignQueueSelector.select(
                db,
                redis,
                ctx.tenant_id,
                data,
                call_id=ctx.call_id,
            )
            selected = selection.candidate
            if selected is None:
                status = selection.failure_status or "no_available_queue"
                self._set_failure_status(ctx, status, selection.limit_reason)
                await self._say(ctx, self._failure_prompt(data, status))
                return goto_or_end(ctx, node["id"], "timeout")

            ctx.variables["sys._assigned_queue_type"] = selected.queue_type
            ctx.variables["sys._assigned_queue_id"] = selected.queue_id
            if selected.queue_type == "employee_group":
                ctx.variables["sys._assigned_group_id"] = selected.queue_id

            pick = await picker.pick_ready_agent_for_queue(
                db,
                ctx.tenant_id,
                selected.queue_type,
                selected.queue_id,
                redis,
                call_id=ctx.call_id,
                offer_id=offer_id,
                ttl_seconds=timeout_s,
            )
            if pick:
                await CallRecordService.bind_queue(
                    db,
                    ctx.tenant_id,
                    ctx.call_id,
                    selected.queue_type,
                    selected.queue_id,
                )

        if pick is None:
            log.info(
                "assign_queue: no ready agent queue=%s/%s call_id=%s",
                ctx.variables.get("sys._assigned_queue_type"),
                ctx.variables.get("sys._assigned_queue_id"),
                ctx.call_id,
            )
            self._set_failure_status(ctx, "agent_no_answer")
            await self._say(ctx, self._failure_prompt(data, "agent_no_answer"))
            return goto_or_end(ctx, node["id"], "timeout")

        orchestrator = ctx.variables.get("__orchestrator__")
        if orchestrator is None:
            log.warning("assign_queue: orchestrator missing from ctx")
            if redis is not None:
                await CcAgentResourceService.release(
                    redis,
                    ctx.tenant_id,
                    pick["employee_id"],
                    reason="orchestrator_missing",
                    expected_offer_id=offer_id,
                )
            self._set_failure_status(ctx, "agent_no_answer")
            await self._say(ctx, self._failure_prompt(data, "agent_no_answer"))
            return goto_or_end(ctx, node["id"], "timeout")

        future = orchestrator.register_offer(offer_id)
        queue_type = ctx.variables.get("sys._assigned_queue_type")
        queue_id = ctx.variables.get("sys._assigned_queue_id")

        try:
            pushed = await orchestrator.notify_agent_incoming(
                tenant_id=ctx.tenant_id,
                employee_id=pick["employee_id"],
                payload={
                    "offer_id": offer_id,
                    "call_id": ctx.call_id,
                    "from": ctx.variables.get("sys.caller_number", ""),
                    "to": ctx.variables.get("sys.called_number", ""),
                    "queue_type": queue_type,
                    "queue_id": queue_id,
                },
            )
        except Exception:  # noqa: BLE001
            log.exception("assign_queue: notify push failed")
            pushed = False
        if not pushed:
            orchestrator.cancel_offer(offer_id)
            if redis is not None:
                await CcAgentResourceService.release(
                    redis,
                    ctx.tenant_id,
                    pick["employee_id"],
                    reason="offer_push_failed",
                    expected_offer_id=offer_id,
                )
            self._set_failure_status(ctx, "agent_no_answer")
            await self._say(ctx, self._failure_prompt(data, "agent_no_answer"))
            return goto_or_end(ctx, node["id"], "timeout")

        if redis is not None:
            try:
                await CcAgentResourceService.mark_ringing(
                    redis,
                    ctx.tenant_id,
                    pick["employee_id"],
                    offer_id=offer_id,
                    call_id=ctx.call_id,
                    ttl_seconds=timeout_s,
                )
            except Exception:  # noqa: BLE001
                log.exception("assign_queue: mark ringing failed")
                orchestrator.cancel_offer(offer_id)
                await CcAgentResourceService.release(
                    redis,
                    ctx.tenant_id,
                    pick["employee_id"],
                    reason="offer_push_failed",
                    expected_offer_id=offer_id,
                )
                self._set_failure_status(ctx, "agent_no_answer")
                await self._say(ctx, self._failure_prompt(data, "agent_no_answer"))
                return goto_or_end(ctx, node["id"], "timeout")

        prompt_task: asyncio.Task | None = None
        if data.get("prompt_play_mode") == "loop":
            prompt_task = asyncio.create_task(
                self._play_waiting_prompt(ctx, data),
                name=f"assign-queue-prompt:{ctx.call_id}",
            )
        else:
            await self._say(ctx, data.get("queue_prompt_text") or "正在为您转接，请稍候。")

        log.info(
            "assign_queue: offered to agent=%s offer_id=%s timeout=%ss call_id=%s",
            pick["employee_id"], offer_id, timeout_s, ctx.call_id,
        )
        try:
            decision = await asyncio.wait_for(future, timeout=timeout_s)
        except asyncio.TimeoutError:
            decision = None
            orchestrator.cancel_offer(offer_id)
            if redis is not None:
                await CcAgentResourceService.release(
                    redis,
                    ctx.tenant_id,
                    pick["employee_id"],
                    reason="offer_timeout",
                    expected_offer_id=offer_id,
                )
        finally:
            if prompt_task is not None:
                prompt_task.cancel()
                with suppress(asyncio.CancelledError):
                    await prompt_task

        if not decision or not decision.get("accept"):
            log.info(
                "assign_queue: offer not accepted (decision=%s) call_id=%s",
                decision, ctx.call_id,
            )
            if redis is not None:
                await CcAgentResourceService.release(
                    redis,
                    ctx.tenant_id,
                    pick["employee_id"],
                    reason=(decision or {}).get("reason") or "offer_timeout",
                    expected_offer_id=offer_id,
                )
            self._set_failure_status(ctx, "agent_no_answer")
            await self._say(ctx, self._failure_prompt(data, "agent_no_answer"))
            return goto_or_end(ctx, node["id"], "timeout")

        webrtc_call_id = decision["webrtc_call_id"]

        # CDR + status updates AFTER the agent commits.
        async with AsyncSessionLocal() as db:
            from app.services.agent_webrtc_session_service import (
                AgentWebRTCSessionService,
            )
            from app.services.cc_agent_status_service import CcAgentStatusService

            await CallRecordService.mark_answered(
                db, ctx.tenant_id, ctx.call_id, agent_id=pick["employee_id"],
            )
            await CcAgentStatusService.set_status(
                db, ctx.tenant_id, pick["employee_id"], "busy", None,
            )
            await AgentWebRTCSessionService.set_busy(
                db, ctx.tenant_id, pick["employee_id"], busy=True,
            )

        ctx.variables["sys._bridged_agent_id"] = pick["employee_id"]
        ctx.variables["sys._bridged_webrtc_call_id"] = webrtc_call_id
        ctx.variables.pop("sys.assign_queue_status", None)
        ctx.variables.pop("sys.assign_queue_limit_reason", None)

        log.info(
            "assign_queue: bridging sip=%s ↔ webrtc=%s",
            ctx.call_id, webrtc_call_id,
        )
        await ctx.telephony.call_stop(ctx.call_id)
        await ctx.telephony.call_bridge(ctx.call_id, webrtc_call_id)

        async def _on_bridged(ctx_: ExecutionContext, node_: dict, _ev: dict) -> NextStep:
            return End("bridged")

        return WaitForEvent(method="call.bridged", on_event=_on_bridged)

    @classmethod
    def _set_failure_status(
        cls,
        ctx: ExecutionContext,
        status: str,
        limit_reason: str | None = None,
    ) -> None:
        ctx.variables["sys.assign_queue_status"] = status
        if limit_reason:
            ctx.variables["sys.assign_queue_limit_reason"] = limit_reason
        else:
            ctx.variables.pop("sys.assign_queue_limit_reason", None)

    @classmethod
    def _failure_prompt(cls, data: dict, status: str) -> str:
        field = cls._FAILURE_PROMPT_FIELDS.get(status)
        if field:
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return cls._DEFAULT_FAILURE_PROMPTS.get(status, "当前坐席繁忙，请稍后再拨。")

    @staticmethod
    async def _say(ctx: ExecutionContext, text: str) -> None:
        try:
            await ctx.telephony.call_say(ctx.call_id, text)
        except Exception:  # noqa: BLE001
            pass

    async def _play_waiting_prompt(self, ctx: ExecutionContext, data: dict) -> None:
        import asyncio

        interval = float(data.get("prompt_loop_interval_seconds") or 15)
        prompt = data.get("queue_prompt_text") or "正在为您转接，请稍候。"
        while True:
            await self._say(ctx, prompt)
            await asyncio.sleep(interval)


class HangupExecutor(BaseNodeExecutor):

    async def execute(self, ctx: ExecutionContext, node: dict) -> NextStep:
        pre = node["data"].get("pre_play")

        async def _hang(ctx_: ExecutionContext, _node_: dict, _ev: dict) -> NextStep:
            await ctx_.telephony.call_hangup(ctx_.call_id)
            return End("hangup")

        if pre:
            text = pre.get("text", "") if pre.get("kind") == "tts" else f"[audio #{pre.get('asset_id')}]"
            await ctx.telephony.call_say(ctx.call_id, text)
            return WaitForEvent(method="call.play_end", on_event=_hang)
        await ctx.telephony.call_hangup(ctx.call_id)
        return End("hangup")


# ─────────────────── Registry (factory) ───────────────────


NODE_EXECUTORS: dict[str, BaseNodeExecutor] = {
    "start": StartExecutor(),
    "play": PlayExecutor(),
    "collect": CollectExecutor(),
    "condition": ConditionExecutor(),
    "assign_queue": AssignQueueExecutor(),
    "hangup": HangupExecutor(),
}


def get_executor(node_type: str) -> BaseNodeExecutor:
    try:
        return NODE_EXECUTORS[node_type]
    except KeyError as exc:
        raise ValueError(f"Unknown node type: {node_type}") from exc
