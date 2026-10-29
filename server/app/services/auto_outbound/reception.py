"""
Post-answer reception strategies for auto-outbound (Wave B2).

Dispatches by task.execution_mode:
  - ivr: start published VoiceFlowWorkflow on the customer leg
  - bot: bridge to VoiceSpeed via synthetic graph / VoiceSpeedExecutor path
  - agent: queue pick + offer (or abandon when no ready agent)

Media I/O never holds a request-scoped DB session (CLAUDE.md §8).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from app.configs.settings import settings
from app.db.session import AsyncSessionLocal
from app.enums import QueueType
from app.repositories.auto_outbound_repository import AutoOutboundRepository
from app.services.auto_outbound import frequency as freq
from app.services.auto_outbound.call_variables import build_call_variables
from app.services.auto_outbound.engine import DialSessionContext
from app.services.auto_outbound.tenant_time import resolve_tenant_timezone
from app.services.call_center.nodes import CALL_VARIABLES_KEY, CALL_VARIABLES_STATUS_KEY
from app.services.auto_outbound.pacing import (
    record_abandon_for_pacing,
    record_answered_for_pacing,
)

logger = logging.getLogger(__name__)

QUEUE_TYPE_GROUP = QueueType.EMPLOYEE_GROUP.value

# Throttle "no idle agent" INFO logs per (tenant, queue). Signature changes
# always log immediately; identical signatures re-log at most every 5 minutes.
_NO_IDLE_LOG_INTERVAL_S = 300.0
_no_idle_log_state: dict[tuple[int, int], tuple[str, float]] = {}


def _should_log_no_idle_agent(
    tenant_id: int, queue_id: int, blocked_signature: str
) -> bool:
    now = time.monotonic()
    key = (tenant_id, queue_id)
    prev = _no_idle_log_state.get(key)
    if (
        prev is None
        or prev[0] != blocked_signature
        or (now - prev[1]) >= _NO_IDLE_LOG_INTERVAL_S
    ):
        _no_idle_log_state[key] = (blocked_signature, now)
        return True
    return False


@dataclass(frozen=True)
class TaskReceptionSnap:
    id: int
    tenant_id: int
    execution_mode: str
    voice_flow_id: int | None
    transfer_queue_id: int | None
    voicespeed_agent_id: str | None
    voicespeed_agent_name: str | None
    intent_result_field_key: str | None
    queue_id: int | None
    abandon_prompt: str | None
    fields: list
    wrapup_seconds: int


class ReceptionStrategy(Protocol):
    async def handle(self, call_id: str, ctx: DialSessionContext, task: TaskReceptionSnap) -> None: ...


def _is_simulation() -> bool:
    return bool(settings.AUTO_OUTBOUND_SIMULATION_ENABLED)


def _is_mock_telephony() -> bool:
    return str(getattr(settings, "TELEPHONY_PROVIDER", "") or "").lower() == "mock"


def _degrade_media() -> bool:
    """Simulation or mock telephony: skip real workflow / VS bridge."""
    return _is_simulation() or _is_mock_telephony()


def _public_variables(variables: dict[str, Any]) -> dict[str, Any]:
    """Collect DTMF / assign outputs; drop sys.* and internal __* bags."""
    out: dict[str, Any] = {}
    for key, value in variables.items():
        if key.startswith("sys.") or key.startswith("__"):
            continue
        if callable(value):
            continue
        out[key] = value
    return out


def _extract_intent(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    for key in ("intent", "intent_label", "intention", "label", "tag"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    tags = payload.get("tags") or payload.get("intent_tags")
    if isinstance(tags, list) and tags:
        return str(tags[0]).strip() or None
    if isinstance(tags, str) and tags.strip():
        return tags.strip()
    return None


def _field_is_single_select(fields: list, key: str) -> bool:
    for field in fields or []:
        if isinstance(field, dict):
            fkey = str(field.get("key") or "")
            ftype = str(field.get("field_type") or field.get("type") or "")
        else:
            fkey = str(getattr(field, "key", "") or "")
            ftype = str(getattr(field, "field_type", None) or getattr(field, "type", "") or "")
        if fkey == key and ftype in {"single_select", "single_choice", "select"}:
            return True
    # If the key exists on the task but type is unknown, still allow write when
    # the product configured intent_result_field_key against that field.
    for field in fields or []:
        fkey = str(field.get("key") if isinstance(field, dict) else getattr(field, "key", "") or "")
        if fkey == key:
            return True
    return False


async def _load_task_snap(task_id: int) -> TaskReceptionSnap | None:
    async with AsyncSessionLocal() as db:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if task is None:
            return None
        return TaskReceptionSnap(
            id=task.id,
            tenant_id=task.tenant_id,
            execution_mode=task.execution_mode,
            voice_flow_id=task.voice_flow_id,
            transfer_queue_id=task.transfer_queue_id,
            voicespeed_agent_id=task.voicespeed_agent_id,
            voicespeed_agent_name=task.voicespeed_agent_name,
            intent_result_field_key=task.intent_result_field_key,
            queue_id=task.queue_id,
            abandon_prompt=task.abandon_prompt,
            fields=list(task.fields or []),
            wrapup_seconds=int(task.wrapup_seconds or 60),
        )


async def _update_record(record_id: int, data: dict) -> None:
    async with AsyncSessionLocal() as db:
        record = await AutoOutboundRepository.get_record(db, record_id)
        if record is None:
            return
        await AutoOutboundRepository.update_record(db, record, data)


async def _merge_target_field_values(target_id: int, patch: dict[str, Any]) -> None:
    if not patch:
        return
    async with AsyncSessionLocal() as db:
        target = await AutoOutboundRepository.get_target(db, target_id)
        if target is None:
            return
        values = dict(target.field_values or {})
        values.update(patch)
        await AutoOutboundRepository.update_target(db, target, {"field_values": values})


async def _load_call_variables(
    ctx: DialSessionContext, task: TaskReceptionSnap
) -> list[dict[str, Any]]:
    """Build this call's bot variables from the target's current field values."""
    try:
        async with AsyncSessionLocal() as db:
            target = await AutoOutboundRepository.get_target(db, ctx.target_id)
            if target is None:
                return []
            field_values = dict(target.field_values or {})
            tz = await resolve_tenant_timezone(db, task.tenant_id)
        return build_call_variables(task.fields, field_values, tz)
    except Exception:  # noqa: BLE001
        logger.warning(
            "auto_outbound call variables build failed record_id=%s",
            ctx.record_id,
            exc_info=True,
        )
        return []


def _call_variables_update(workflow: Any, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Record update for the preset snapshot; empty when no preset was attempted."""
    status = workflow.ctx.variables.get(CALL_VARIABLES_STATUS_KEY)
    if not items or status not in {"passed", "failed"}:
        return {}
    return {"call_variables": {"status": status, "items": items}}


async def _resolve_call_id(ctx: DialSessionContext) -> str | None:
    if getattr(ctx, "call_id", None):
        return str(ctx.call_id)
    return None


async def _get_telephony():
    from app.libs.telephony.factory import get_telephony_client

    return get_telephony_client()


async def _safe_hangup(call_id: str, reason: str) -> None:
    try:
        telephony = await _get_telephony()
        await telephony.call_hangup(call_id, reason=reason)
    except Exception:  # noqa: BLE001
        logger.info("auto_outbound hangup skipped call_id=%s reason=%s", call_id, reason)


async def _safe_say(call_id: str, text: str) -> bool:
    """
    Play a short prompt on the customer leg.

    Returns False when the provider cannot play (mock records the call; real
    media failures are treated as unavailable). There is no dedicated
    abandon-hold audio asset — we use call_say TTS text.
    """
    try:
        telephony = await _get_telephony()
        await telephony.call_say(call_id, text)
        return True
    except Exception:  # noqa: BLE001
        logger.info("auto_outbound call_say failed call_id=%s", call_id, exc_info=True)
        return False


class IvrReception:
    async def handle(self, call_id: str, ctx: DialSessionContext, task: TaskReceptionSnap) -> None:
        await _update_record(ctx.record_id, {"reception_type": "ivr"})

        if _degrade_media() or not task.voice_flow_id:
            await _update_record(
                ctx.record_id,
                {
                    "reception_result": {
                        "exit": "simulated" if _degrade_media() else "no_flow",
                        "collected": {},
                        "degraded": _degrade_media(),
                    }
                },
            )
            if _degrade_media():
                return
            await _safe_hangup(call_id, "auto_outbound_ivr_no_flow")
            return

        graph, version_id = await self._load_published_graph(task)
        if graph is None:
            await _update_record(
                ctx.record_id,
                {"reception_result": {"exit": "no_flow_version", "collected": {}}},
            )
            await _safe_hangup(call_id, "auto_outbound_ivr_no_version")
            return

        asyncio.create_task(
            self._run_workflow(call_id, ctx, task, graph, version_id),
            name=f"auto-outbound-ivr-{call_id}",
        )

    async def _load_published_graph(
        self, task: TaskReceptionSnap
    ) -> tuple[dict | None, int | None]:
        from app.models.voice_flow import VoiceFlow

        async with AsyncSessionLocal() as db:
            flow = await db.get(VoiceFlow, task.voice_flow_id)
            if flow is None or flow.tenant_id != task.tenant_id:
                return None, None
            version = flow.current_version
            if version is None or not version.graph_json:
                return None, None
            return dict(version.graph_json), version.id

    async def _run_workflow(
        self,
        call_id: str,
        ctx: DialSessionContext,
        task: TaskReceptionSnap,
        graph: dict,
        version_id: int | None,
    ) -> None:
        from app.services.call_center.orchestrator import get_orchestrator
        from app.services.call_center.workflow import VoiceFlowWorkflow

        try:
            orch = get_orchestrator()
        except Exception:  # noqa: BLE001
            orch = None

        telephony = await _get_telephony()
        # Outbound leg is already answered — do not call call_answer again.
        # Tradeoff vs inbound `_on_incoming`: we skip DID routing / answer /
        # RTP warmup and attach the published graph directly to the live call.
        workflow = VoiceFlowWorkflow(
            call_id=call_id,
            tenant_id=task.tenant_id,
            graph=graph,
            telephony=telephony,
            orchestrator=orch,
            initial_variables={
                "sys.caller_number": "",
                "sys.called_number": ctx.phone_number,
                "sys._auto_outbound_source": "auto_outbound",
                "sys._auto_outbound_task_id": task.id,
                "sys._auto_outbound_record_id": ctx.record_id,
                "sys._direction": "outbound",
            },
        )
        if orch is not None:
            orch._workflows[call_id] = workflow  # noqa: SLF001 — register for event routing

        try:
            await workflow.start()
            await asyncio.wait_for(workflow.done.wait(), timeout=3600)
        except Exception:  # noqa: BLE001
            logger.exception("auto_outbound IVR workflow failed call_id=%s", call_id)
            await _update_record(
                ctx.record_id,
                {
                    "reception_result": {
                        "exit": "workflow_error",
                        "collected": {},
                        "voice_flow_version_id": version_id,
                    }
                },
            )
            return
        finally:
            # A bridged call outlives the workflow: the customer leg's hangup
            # event settles the agent via the orchestrator, which needs this
            # registry entry to find the bridged agent. Unbridged calls are
            # hung up by the workflow itself, so the entry can go now.
            if orch is not None and workflow.bridged_agent_info() is None:
                orch._workflows.pop(call_id, None)  # noqa: SLF001

        collected = _public_variables(dict(workflow.ctx.variables))
        result = {
            "exit": workflow.ended_reason or "end",
            "collected": collected,
            "voice_flow_version_id": version_id,
            "transferred": workflow.bridged_agent_info() is not None,
        }
        bridged = workflow.bridged_agent_info()
        updates: dict[str, Any] = {"reception_result": result}
        if bridged is not None:
            updates["agent_id"] = bridged["employee_id"]
        await _update_record(ctx.record_id, updates)


class BotReception:
    async def handle(self, call_id: str, ctx: DialSessionContext, task: TaskReceptionSnap) -> None:
        await _update_record(ctx.record_id, {"reception_type": "bot"})

        if _degrade_media() or not task.voicespeed_agent_id:
            intent = "simulated_intent" if _degrade_media() else None
            result = {
                "intent": intent,
                "handoff": False,
                "degraded": _degrade_media(),
            }
            await _update_record(ctx.record_id, {"reception_result": result})
            if intent and task.intent_result_field_key:
                await self._maybe_write_intent(ctx, task, intent)
            return

        asyncio.create_task(
            self._run_bot(call_id, ctx, task),
            name=f"auto-outbound-bot-{call_id}",
        )

    async def _run_bot(
        self, call_id: str, ctx: DialSessionContext, task: TaskReceptionSnap
    ) -> None:
        from app.services.call_center.nodes import build_voicespeed_direct_graph
        from app.services.call_center.orchestrator import get_orchestrator
        from app.services.call_center.workflow import VoiceFlowWorkflow

        transfer_target = None
        if task.transfer_queue_id:
            transfer_target = {
                "queue_type": QUEUE_TYPE_GROUP,
                "queue_id": int(task.transfer_queue_id),
            }
        graph = build_voicespeed_direct_graph(
            agent_id=task.voicespeed_agent_id or "",
            agent_name=task.voicespeed_agent_name,
            transfer_target=transfer_target,
        )

        call_variables = await _load_call_variables(ctx, task)
        initial_variables: dict[str, Any] = {
            "sys.caller_number": "",
            "sys.called_number": ctx.phone_number,
            "sys._auto_outbound_source": "auto_outbound",
            "sys._auto_outbound_task_id": task.id,
            "sys._auto_outbound_record_id": ctx.record_id,
            "sys._direction": "outbound",
        }
        if call_variables:
            initial_variables[CALL_VARIABLES_KEY] = {
                item["name"]: item["value"] for item in call_variables
            }

        try:
            orch = get_orchestrator()
        except Exception:  # noqa: BLE001
            orch = None
        telephony = await _get_telephony()
        workflow = VoiceFlowWorkflow(
            call_id=call_id,
            tenant_id=task.tenant_id,
            graph=graph,
            telephony=telephony,
            orchestrator=orch,
            initial_variables=initial_variables,
        )
        if orch is not None:
            orch._workflows[call_id] = workflow  # noqa: SLF001

        try:
            await workflow.start()
            await asyncio.wait_for(workflow.done.wait(), timeout=3600)
        except Exception:  # noqa: BLE001
            logger.exception("auto_outbound bot workflow failed call_id=%s", call_id)
            await _update_record(
                ctx.record_id,
                {
                    "reception_result": {"intent": None, "handoff": False, "error": "workflow_error"},
                    **_call_variables_update(workflow, call_variables),
                },
            )
            return
        finally:
            # A bridged call outlives the workflow: the customer leg's hangup
            # event settles the agent via the orchestrator, which needs this
            # registry entry to find the bridged agent. Unbridged calls are
            # hung up by the workflow itself, so the entry can go now.
            if orch is not None and workflow.bridged_agent_info() is None:
                orch._workflows.pop(call_id, None)  # noqa: SLF001

        handoff_payload = workflow.ctx.variables.get("sys._handoff_payload") or {}
        intent = _extract_intent(handoff_payload if isinstance(handoff_payload, dict) else {})
        handoff = bool(workflow.ctx.variables.get("sys._handoff_handled"))
        bridged = workflow.bridged_agent_info()
        result = {
            "intent": intent,
            "handoff": handoff,
            "handoff_payload": handoff_payload if isinstance(handoff_payload, dict) else {},
            "exit": workflow.ended_reason or "end",
            "transferred": bridged is not None,
        }
        updates: dict[str, Any] = {
            "reception_result": result,
            **_call_variables_update(workflow, call_variables),
        }
        if bridged is not None:
            updates["agent_id"] = bridged["employee_id"]
        await _update_record(ctx.record_id, updates)
        if intent and task.intent_result_field_key:
            await self._maybe_write_intent(ctx, task, intent)

    async def _maybe_write_intent(
        self, ctx: DialSessionContext, task: TaskReceptionSnap, intent: str
    ) -> None:
        key = task.intent_result_field_key
        if not key or not _field_is_single_select(task.fields, key):
            return
        await _merge_target_field_values(ctx.target_id, {key: intent})


class AgentReception:
    """
    Progressive / ratio / predictive agent bridging.

    Reuses QueuePicker reservation + orchestrator notify when available.
    On abandon: hangup immediately, or play a wait prompt then hangup when
    media cannot keep a real hold queue without AssignQueueExecutor's loop.
    """

    def __init__(self, *, redis: Any | None = None, picker=None) -> None:
        self._redis = redis
        self._picker = picker

    def _r(self) -> Any:
        if self._redis is not None:
            return self._redis
        try:
            return freq._default_redis()
        except Exception:  # noqa: BLE001
            return None

    async def handle(self, call_id: str, ctx: DialSessionContext, task: TaskReceptionSnap) -> None:
        await record_answered_for_pacing(task.id, redis=self._r())
        await _update_record(ctx.record_id, {"reception_type": "agent"})

        if not task.queue_id:
            await self._abandon(call_id, ctx, task, reason="no_queue")
            return

        # Degraded / simulation path: no real offer/bridge — pick or abandon.
        if _degrade_media() or self._must_degrade_dispatch():
            await self._handle_degraded(call_id, ctx, task)
            return

        asyncio.create_task(
            self._run_assign_workflow(call_id, ctx, task),
            name=f"auto-outbound-agent-{call_id}",
        )

    def _must_degrade_dispatch(self) -> bool:
        try:
            from app.services.call_center.orchestrator import get_orchestrator

            orch = get_orchestrator()
            return orch is None or not getattr(orch, "_started", True)
        except Exception:  # noqa: BLE001
            return True

    async def _handle_degraded(
        self, call_id: str, ctx: DialSessionContext, task: TaskReceptionSnap
    ) -> None:
        pick = await self._try_pick(call_id, ctx, task, reserve=False)
        if pick is None:
            await self._abandon(call_id, ctx, task, reason="no_ready_agent")
            return
        await _update_record(
            ctx.record_id,
            {
                "agent_id": int(pick["employee_id"]),
                "reception_result": {
                    "assigned": True,
                    "degraded": True,
                    "agent_id": int(pick["employee_id"]),
                },
            },
        )

    async def _run_assign_workflow(
        self, call_id: str, ctx: DialSessionContext, task: TaskReceptionSnap
    ) -> None:
        from app.services.call_center.orchestrator import get_orchestrator
        from app.services.call_center.workflow import VoiceFlowWorkflow

        graph = {
            "version": 1,
            "nodes": [
                {"id": "start", "type": "start", "data": {}, "position": {"x": 0, "y": 0}},
                {
                    "id": "assign_queue",
                    "type": "assign_queue",
                    "position": {"x": 1, "y": 0},
                    "data": {
                        "queue_targets": [
                            {
                                "queue_type": QUEUE_TYPE_GROUP,
                                "queue_id": int(task.queue_id),
                            }
                        ],
                        "timeout_seconds": 60,
                        # For predictive/ratio abandon semantics: short hold then fail.
                        "queue_wait_seconds": 5 if task.abandon_prompt == "hangup" else 60,
                        # Empty string disables the transfer prompt so the callee
                        # hears silence, then the agent — no TTS cue.
                        "queue_prompt_text": "",
                    },
                },
                {
                    "id": "hangup",
                    "type": "hangup",
                    "position": {"x": 2, "y": 0},
                    "data": {"pre_play": None},
                },
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "start",
                    "target": "assign_queue",
                    "source_handle": "next",
                },
                {
                    "id": "e2",
                    "source": "assign_queue",
                    "target": "hangup",
                    "source_handle": "timeout",
                },
            ],
            "variables": [],
        }

        try:
            orch = get_orchestrator()
        except Exception:  # noqa: BLE001
            orch = None
        if orch is None:
            await self._handle_degraded(call_id, ctx, task)
            return

        telephony = await _get_telephony()
        workflow = VoiceFlowWorkflow(
            call_id=call_id,
            tenant_id=task.tenant_id,
            graph=graph,
            telephony=telephony,
            orchestrator=orch,
            initial_variables={
                "sys.caller_number": "",
                "sys.called_number": ctx.phone_number,
                "sys._auto_outbound_source": "auto_outbound",
                "sys._auto_outbound_task_id": task.id,
                "sys._auto_outbound_record_id": ctx.record_id,
                "sys._direction": "outbound",
            },
        )
        orch._workflows[call_id] = workflow  # noqa: SLF001

        try:
            await workflow.start()
            await asyncio.wait_for(workflow.done.wait(), timeout=600)
        except Exception:  # noqa: BLE001
            logger.exception("auto_outbound agent assign failed call_id=%s", call_id)
            await self._abandon(call_id, ctx, task, reason="assign_error")
            return
        finally:
            # Keep the registry entry once bridged: the customer leg's hangup
            # settles the agent via the orchestrator's bridged-agent path,
            # which looks the workflow up here.
            if workflow.bridged_agent_info() is None:
                orch._workflows.pop(call_id, None)  # noqa: SLF001

        bridged = workflow.bridged_agent_info()
        if bridged is not None:
            await _update_record(
                ctx.record_id,
                {
                    "agent_id": bridged["employee_id"],
                    "reception_result": {
                        "assigned": True,
                        "agent_id": bridged["employee_id"],
                        "exit": workflow.ended_reason or "bridged",
                    },
                },
            )
            return

        # No bridge → treat as abandon (呼损).
        await self._abandon(
            call_id,
            ctx,
            task,
            reason=workflow.ended_reason or "no_agent",
            already_hung_up=True,
        )

    async def _try_pick(
        self,
        call_id: str,
        ctx: DialSessionContext,
        task: TaskReceptionSnap,
        *,
        reserve: bool,
    ) -> dict | None:
        from app.services.call_center.queue import QueuePicker, get_queue_picker

        picker = self._picker or get_queue_picker()
        redis = self._r()
        import uuid

        offer_id = uuid.uuid4().hex if reserve else None
        async with AsyncSessionLocal() as db:
            return await picker.pick_ready_agent_for_queue(
                db,
                task.tenant_id,
                QUEUE_TYPE_GROUP,
                int(task.queue_id),
                redis,
                call_id=call_id if reserve else None,
                offer_id=offer_id,
                ttl_seconds=60.0 if reserve else None,
            )

    async def _abandon(
        self,
        call_id: str,
        ctx: DialSessionContext,
        task: TaskReceptionSnap,
        *,
        reason: str,
        already_hung_up: bool = False,
    ) -> None:
        await record_abandon_for_pacing(task.id, redis=self._r())
        prompt = task.abandon_prompt or "hangup"
        if prompt == "play_wait" and not already_hung_up:
            # No dedicated hold-music asset for abandon; TTS wait then hangup.
            # Full "continue queuing" reuse of AssignQueueExecutor hold loop is
            # only available on the non-degraded workflow path above.
            played = await _safe_say(call_id, "正在为您转接，请稍候。")
            if not played:
                logger.info(
                    "auto_outbound abandon play_wait unavailable — hanging up call_id=%s",
                    call_id,
                )

        await _update_record(
            ctx.record_id,
            {
                "reception_type": "none",
                "reception_result": {
                    "abandoned": True,
                    "reason": reason,
                    "abandon_prompt": prompt,
                },
            },
        )
        if not already_hung_up:
            await _safe_hangup(call_id, "auto_outbound_abandoned")


class ReceptionDispatcher:
    """Concrete ``engine._reception`` implementation."""

    def __init__(
        self,
        *,
        redis: Any | None = None,
        strategies: dict[str, ReceptionStrategy] | None = None,
        session_factory=AsyncSessionLocal,
    ) -> None:
        self._redis = redis
        self._session_factory = session_factory
        self._strategies: dict[str, ReceptionStrategy] = strategies or {
            "ivr": IvrReception(),
            "bot": BotReception(),
            "agent": AgentReception(redis=redis),
        }

    async def on_answered(self, ctx: DialSessionContext) -> None:
        call_id = await _resolve_call_id(ctx)
        if not call_id:
            # Fallback: find call_id from redis session reverse is not keyed;
            # engine must pass call_id on DialSessionContext.
            logger.warning(
                "auto_outbound reception missing call_id record_id=%s", ctx.record_id
            )
            return

        task = await _load_task_snap(ctx.task_id)
        if task is None:
            logger.warning("auto_outbound reception task missing id=%s", ctx.task_id)
            return

        strategy = self._strategies.get(task.execution_mode)
        if strategy is None:
            logger.warning(
                "auto_outbound unknown execution_mode=%s task=%s",
                task.execution_mode,
                task.id,
            )
            return
        await strategy.handle(call_id, ctx, task)


async def count_ready_agents_for_queue(
    tenant_id: int,
    queue_id: int,
    *,
    redis: Any | None = None,
) -> int:
    """Count connected agents whose real-time resource is currently idle."""
    idle, _pacing = await _count_queue_agent_capacity(
        tenant_id,
        queue_id,
        redis=redis,
    )
    return idle


async def count_pacing_agents_for_queue(
    tenant_id: int,
    queue_id: int,
    *,
    redis: Any | None = None,
) -> int:
    """Count idle agents plus agents serving this queue's auto-outbound calls."""
    _idle, pacing = await _count_queue_agent_capacity(
        tenant_id,
        queue_id,
        redis=redis,
    )
    return pacing


async def _count_queue_agent_capacity(
    tenant_id: int,
    queue_id: int,
    *,
    redis: Any | None,
) -> tuple[int, int]:
    from sqlalchemy import select

    from app.models.agent_status import AgentStatus
    from app.models.employee import Employee
    from app.models.employee_group import EmployeeGroupMember

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Employee.id, AgentStatus.status)
            .select_from(EmployeeGroupMember)
            .join(AgentStatus, AgentStatus.employee_id == EmployeeGroupMember.employee_id)
            .join(Employee, Employee.id == EmployeeGroupMember.employee_id)
            .where(
                EmployeeGroupMember.group_id == queue_id,
                AgentStatus.tenant_id == tenant_id,
                AgentStatus.status.in_(["ready", "busy"]),
                Employee.tenant_id == tenant_id,
                Employee.is_active.is_(True),
            )
        )
        agents = [(int(row[0]), str(row[1])) for row in result.all()]

    if not agents:
        return 0, 0
    if redis is None:
        ready = sum(1 for _employee_id, status in agents if status == "ready")
        return ready, ready

    from app.services.agent_status_service import AgentStatusService
    from app.services.cc_agent_resource_service import CcAgentResourceService

    idle = 0
    pacing = 0
    # An agent has to clear three independent gates to be dialable: a chosen
    # status of "ready", a live workspace connection, and an idle call
    # resource. When none qualify, record which gate stopped each one —
    # otherwise a task that never dials looks identical whichever gate failed.
    blocked: list[str] = []
    for employee_id, status in agents:
        try:
            if not await AgentStatusService.is_connected(redis, tenant_id, employee_id):
                blocked.append(f"{employee_id}:{status}/disconnected")
                continue
            snapshot = await CcAgentResourceService.get_snapshot(
                redis,
                tenant_id,
                employee_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "auto_outbound agent capacity probe failed tenant=%s queue=%s employee=%s",
                tenant_id,
                queue_id,
                employee_id,
                exc_info=True,
            )
            continue

        if status == "ready" and (
            snapshot is None or snapshot.get("resource_state") == "idle"
        ):
            idle += 1
            pacing += 1
            continue

        blocked.append(
            f"{employee_id}:{status}/"
            f"{(snapshot or {}).get('resource_state') or 'no-snapshot'}"
        )

        if not snapshot or snapshot.get("resource_state") not in {
            "reserved",
            "ringing",
            "in_call",
        }:
            continue
        call_id = snapshot.get("current_call_id")
        if not call_id:
            continue
        try:
            session = await freq.get_session_mapping(str(call_id), redis=redis)
        except Exception:  # noqa: BLE001
            logger.warning(
                "auto_outbound session probe failed tenant=%s queue=%s employee=%s",
                tenant_id,
                queue_id,
                employee_id,
                exc_info=True,
            )
            continue
        if not session:
            continue
        try:
            same_queue = (
                int(session.get("tenant_id")) == tenant_id
                and int(session.get("queue_id")) == queue_id
            )
        except (TypeError, ValueError):
            same_queue = False
        if same_queue:
            pacing += 1

    if idle == 0 and blocked:
        blocked_signature = ",".join(blocked)
        if _should_log_no_idle_agent(tenant_id, queue_id, blocked_signature):
            logger.info(
                "auto_outbound no idle agent tenant=%s queue=%s blocked=%s",
                tenant_id,
                queue_id,
                blocked_signature,
            )

    return idle, pacing


async def count_in_call_agents_for_queue(
    tenant_id: int,
    queue_id: int,
    *,
    redis: Any | None = None,
) -> int:
    from sqlalchemy import select

    from app.models.employee import Employee
    from app.models.employee_group import EmployeeGroupMember
    from app.services.cc_agent_resource_service import CcAgentResourceService

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(EmployeeGroupMember.employee_id)
            .join(Employee, Employee.id == EmployeeGroupMember.employee_id)
            .where(
                EmployeeGroupMember.group_id == queue_id,
                Employee.tenant_id == tenant_id,
                Employee.is_active.is_(True),
            )
        )
        employee_ids = [int(row[0]) for row in result.all()]

    if not employee_ids or redis is None:
        return 0
    count = 0
    for eid in employee_ids:
        try:
            snap = await CcAgentResourceService.get_snapshot(redis, tenant_id, eid)
        except Exception:  # noqa: BLE001
            continue
        if snap and snap.get("resource_state") == "in_call":
            count += 1
    return count
