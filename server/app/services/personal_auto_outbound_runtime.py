"""Background runtime for agent-owned personal auto-outbound sessions."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.constants.call_center import CallSource
from app.db.session import AsyncSessionLocal
from app.enums import QueueType
from app.libs.telephony import BaseTelephonyClient, CallEvent
from app.models.phone_number import PhoneNumber
from app.repositories.personal_auto_outbound_repository import PersonalAutoOutboundRepository
from app.services.audio_asset_service import AudioAssetService
from app.services.call_center.workflow import VoiceFlowWorkflow
from app.services.call_record_service import CallRecordService
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService
from app.services.outbound_prescreen_service import OutboundPrescreenService

if TYPE_CHECKING:
    from app.services.call_center.orchestrator import CallCenterOrchestrator

logger = logging.getLogger(__name__)

_RINGING_STAGES = ("dialing", "ringing")
_ACTIVE_STAGES = ("dialing", "ringing", "screening", "assigning", "human", "filtered")
_PRESCREEN_SILENCE_SECONDS = 3
# Eligibility-failure reasons from OutboundPrescreenService: the utterance
# never proved to be a real turn (noise burst, too short, different voice),
# so it must neither stop the opening nor trigger a transfer.
_KEEP_LISTENING_REASONS = frozenset(
    {"insufficient_text", "insufficient_voiced_ms", "voice_mismatch"}
)


class PersonalAutoOutboundRuntime:
    """Event-driven R/S/H state machine with short, re-opened DB sessions."""

    def __init__(
        self,
        telephony: BaseTelephonyClient,
        orchestrator: CallCenterOrchestrator,
    ) -> None:
        self.telephony = telephony
        self.orchestrator = orchestrator
        self._registered = False
        self._session_tasks: dict[int, asyncio.Task] = {}
        self._call_tasks: set[asyncio.Task] = set()
        self._call_rows: dict[str, int] = {}
        self._session_by_call: dict[str, int] = {}
        self._silence_tasks: dict[str, asyncio.Task] = {}
        self._opening_waiters: dict[str, asyncio.Future] = {}
        self._opening_ended: set[str] = set()
        self._speech_active: set[str] = set()
        self._speech_completed: set[str] = set()
        self._closing_waiters: dict[str, asyncio.Future] = {}

    def register_events(self) -> None:
        if self._registered:
            return
        self.telephony.on_event("call.ringing", self._on_ringing)
        self.telephony.on_event("call.answered", self._on_answered)
        self.telephony.on_event("call.speech_start", self._on_speech_start)
        self.telephony.on_event("call.speech_end", self._on_speech_end)
        self.telephony.on_event("call.speech_discard", self._on_speech_discard)
        self.telephony.on_event("call.play_end", self._on_play_end)
        self.telephony.on_event("call.hangup", self._on_hangup)
        self._registered = True

    def owns_call(self, call_id: str) -> bool:
        return call_id in self._call_rows

    async def stop(self) -> None:
        for task in [
            *self._session_tasks.values(),
            *self._call_tasks,
            *self._silence_tasks.values(),
        ]:
            task.cancel()
        self._session_tasks.clear()
        self._call_tasks.clear()
        self._silence_tasks.clear()
        self._opening_waiters.clear()
        self._opening_ended.clear()
        self._speech_active.clear()
        self._speech_completed.clear()
        self._closing_waiters.clear()

    def start_session(self, session_id: int) -> None:
        self._schedule_replenish(session_id)

    async def restore_running_sessions(
        self,
        active_call_ids: set[str] | None = None,
        *,
        complete: bool = False,
    ) -> None:
        async with AsyncSessionLocal() as db:
            session_ids = await PersonalAutoOutboundRepository.list_running_session_ids(db)
            calls = await PersonalAutoOutboundRepository.list_active_calls(db)

        now = datetime.now(timezone.utc)
        for call in calls:
            call_id = str(call.telephony_call_id or "")
            if not call_id:
                if call.stage == "dialing":
                    delay = max(0.0, 60.0 - (now - call.started_at).total_seconds())
                    self._spawn(self._recover_stale_dialing(call.id, delay))
                continue
            if complete and active_call_ids is not None and call_id not in active_call_ids:
                self._call_rows[call_id] = call.id
                self._session_by_call[call_id] = call.session_id
                self._spawn(self._finalize_hangup(call_id, "reconnect_reconcile"))
                continue
            self._call_rows[call_id] = call.id
            self._session_by_call[call_id] = call.session_id
            if call.stage == "screening":
                self._opening_ended.add(call_id)
                self._replace_silence_timer(call_id)
            elif call.stage == "assigning":
                self._spawn(self._recover_assigning(call_id))
            elif call.stage == "filtered":
                self._spawn(self._delayed_hangup(call_id, 15, "personal_prescreen_filtered"))

        for session_id in session_ids:
            self._schedule_replenish(session_id)

    async def _recover_stale_dialing(self, call_row_id: int, delay: float) -> None:
        await asyncio.sleep(delay)
        await self._fail_originate(call_row_id, "originate_state_lost")

    async def _recover_assigning(self, call_id: str) -> None:
        # A draining node may still own the original 40-second assignment
        # workflow. Give it time to settle before rebuilding lost local state.
        await asyncio.sleep(45)
        context = await self._lookup(call_id)
        if context is None:
            return
        async with AsyncSessionLocal() as db:
            call = await PersonalAutoOutboundRepository.get_call_for_update(db, context["id"])
            if call is None or call.stage != "assigning" or call.ended_at is not None:
                return
            await PersonalAutoOutboundRepository.update_call(db, call, {"stage": "screening"})
        await self._assign_human(call_id, degraded_reason="runtime_recovered")

    async def _delayed_hangup(self, call_id: str, delay: float, reason: str) -> None:
        await asyncio.sleep(delay)
        await self._safe_hangup(call_id, reason)

    def _replace_silence_timer(self, call_id: str) -> None:
        self._cancel_silence_timer(call_id)
        self._silence_tasks[call_id] = asyncio.create_task(self._silence_timeout(call_id))

    def _cancel_silence_timer(self, call_id: str) -> None:
        task = self._silence_tasks.pop(call_id, None)
        if task and task is not asyncio.current_task():
            task.cancel()

    def _clear_screening_state(self, call_id: str) -> None:
        self._cancel_silence_timer(call_id)
        waiter = self._opening_waiters.pop(call_id, None)
        if waiter is not None and not waiter.done():
            waiter.cancel()
        self._opening_ended.discard(call_id)
        self._speech_active.discard(call_id)
        self._speech_completed.discard(call_id)

    async def pause_session(self, session_id: int) -> None:
        task = self._session_tasks.pop(session_id, None)
        if task:
            task.cancel()
        await self._release_primary(session_id, "personal_session_paused")

    async def resume_session(self, session_id: int) -> None:
        self._schedule_replenish(session_id)

    async def stop_session(self, session_id: int) -> None:
        await self.pause_session(session_id)
        async with AsyncSessionLocal() as db:
            call_ids = await PersonalAutoOutboundRepository.active_call_ids(
                db, session_id, _RINGING_STAGES
            )
        await asyncio.gather(
            *(self._safe_hangup(call_id, "personal_session_stopped") for call_id in call_ids),
            return_exceptions=True,
        )
        await self._finish_session_if_idle(session_id)

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._call_tasks.add(task)
        task.add_done_callback(self._call_tasks.discard)
        return task

    def _schedule_replenish(self, session_id: int) -> None:
        current = self._session_tasks.get(session_id)
        if current and not current.done():
            return
        task = asyncio.create_task(
            self._replenish(session_id), name=f"personal-auto-outbound-{session_id}"
        )
        self._session_tasks[session_id] = task
        task.add_done_callback(lambda done, sid=session_id: self._clear_session_task(sid, done))

    def _clear_session_task(self, session_id: int, task: asyncio.Task) -> None:
        if self._session_tasks.get(session_id) is task:
            self._session_tasks.pop(session_id, None)
        if not task.cancelled() and task.exception() is not None:
            logger.error(
                "personal auto-outbound replenish failed session_id=%s error=%s",
                session_id,
                task.exception(),
            )

    async def _replenish(self, session_id: int) -> None:
        async with AsyncSessionLocal() as db:
            session = await PersonalAutoOutboundRepository.get_session(db, session_id)
            if session is None or session.status != "running":
                return
            tenant_id = session.tenant_id
            primary_agent_id = session.primary_agent_id
            counts = await PersonalAutoOutboundRepository.counts(db, session_id)
            if counts["screening_current"] > 0 or counts["primary_human_current"] > 0:
                return
            r = self._redis()
            agent_status = await CcAgentStatusService.get_for_employee(
                db, session.tenant_id, session.primary_agent_id, r
            )
            slots = max(0, session.effective_concurrency - counts["ringing_current"])
        owns_primary_reservation = (
            agent_status.get("current_call_id") == self._reservation_id(session_id)
        )
        if not owns_primary_reservation and (
            agent_status["status"] != "ready"
            or agent_status.get("resource_state") in {
                "ringing",
                "in_call",
                "after_call_work",
            }
        ):
            await self._auto_pause(session_id, "primary_agent_unavailable")
            return
        if not await self._ensure_primary_reserved(session_id, tenant_id, primary_agent_id):
            await self._auto_pause(session_id, "primary_agent_unavailable")
            return
        async with AsyncSessionLocal() as db:
            session = await PersonalAutoOutboundRepository.get_session_for_update(db, session_id)
            if session is None or session.status != "running":
                return
            counts = await PersonalAutoOutboundRepository.counts(db, session_id)
            if counts["screening_current"] > 0 or counts["primary_human_current"] > 0:
                return
            slots = max(0, session.effective_concurrency - counts["ringing_current"])
            calls = await PersonalAutoOutboundRepository.claim_calls(db, session, slots)

        if not calls:
            await self._finish_session_if_idle(session_id, exhaust_running=True)
            return
        await asyncio.gather(*(self._dial(call.id) for call in calls))

    async def _dial(self, call_row_id: int) -> None:
        async with AsyncSessionLocal() as db:
            call = await PersonalAutoOutboundRepository.get_call(db, call_row_id)
            if call is None:
                return
            session = await PersonalAutoOutboundRepository.get_session(db, call.session_id)
            if session is None or session.status not in {"running", "paused"}:
                return
            number = await db.get(PhoneNumber, session.outbound_phone_number_id)
            dial_target = call.phone_number.removeprefix("sip:").strip()
            number_unavailable = number is None or not number.trunk_id
            if number_unavailable:
                dialed = caller_id = trunk_id = ""
            else:
                prefix = (number.called_number_prefix or "").strip()
                dialed = (
                    prefix + dial_target
                    if prefix and not dial_target.startswith(prefix)
                    else dial_target
                )
                caller_id = number.phone_number
                trunk_id = number.trunk_id
            tenant_id = session.tenant_id
            session_id = session.id

        if number_unavailable:
            await self._fail_originate(call_row_id, "outbound_number_unavailable")
            return

        try:
            result = await self.telephony.call_originate(
                uri=dialed,
                caller_id=caller_id,
                trunk_id=trunk_id,
                request_id=f"pao:{call_row_id}",
            )
            call_id = str(result["call_id"])
        except Exception:  # noqa: BLE001
            logger.exception("personal auto-outbound originate failed call_row_id=%s", call_row_id)
            await self._fail_originate(call_row_id, "originate_failed")
            return

        self._call_rows[call_id] = call_row_id
        self._session_by_call[call_id] = session_id
        await self.orchestrator._claim_call(call_id)  # noqa: SLF001
        cdr_id = None
        try:
            async with AsyncSessionLocal() as db:
                detail = await CallRecordService.create_for_outbound(
                    db,
                    tenant_id,
                    call_id=call_id,
                    conversation_id=result.get("conversation_id"),
                    root_call_id=result.get("root_call_id") or call_id,
                    from_number=caller_id,
                    to_number=call.phone_number,
                    agent_id=None,
                    call_source=CallSource.PERSONAL_AUTO_OUTBOUND.value,
                )
                cdr_id = detail.get("id")
                for attempt in range(4):
                    ended = await self.orchestrator.finalize_outbound_cdr_if_already_ended(
                        db,
                        tenant_id=tenant_id,
                        call_id=call_id,
                    )
                    if ended is not None:
                        break
                    if attempt < 3:
                        await asyncio.sleep(0.1)
        except Exception:  # noqa: BLE001
            logger.exception("personal auto-outbound CDR create failed call_id=%s", call_id)

        async with AsyncSessionLocal() as db:
            row = await PersonalAutoOutboundRepository.get_call_for_update(db, call_row_id)
            if row is not None:
                updates = {
                    "telephony_call_id": row.telephony_call_id or call_id,
                    "call_record_id": row.call_record_id or cdr_id,
                }
                if row.stage == "dialing" and row.ended_at is None:
                    updates["stage"] = "ringing"
                await PersonalAutoOutboundRepository.update_call(
                    db,
                    row,
                    updates,
                )

    async def _fail_originate(self, call_row_id: int, reason: str) -> None:
        async with AsyncSessionLocal() as db:
            call = await PersonalAutoOutboundRepository.get_call_for_update(db, call_row_id)
            if call is None or call.stage != "dialing" or call.ended_at is not None:
                return
            previous = (call.metadata_json or {}).get("previous_target_status", "pending")
            await PersonalAutoOutboundRepository.update_call_and_settle_target(
                db,
                call,
                {"stage": "not_connected", "hangup_reason": reason, "ended_at": datetime.now(timezone.utc)},
                target_status=previous,
                result=reason,
                answered=False,
            )
            session_id = call.session_id
        self._schedule_replenish(session_id)

    async def _lookup(self, call_id: str):
        row_id = self._call_rows.get(call_id)
        async with AsyncSessionLocal() as db:
            row = (
                await PersonalAutoOutboundRepository.get_call(db, row_id)
                if row_id is not None
                else await PersonalAutoOutboundRepository.get_call_by_telephony_id(db, call_id)
            )
            if row is None:
                return None
            self._call_rows[call_id] = row.id
            self._session_by_call[call_id] = row.session_id
            return {
                "id": row.id,
                "session_id": row.session_id,
                "tenant_id": row.tenant_id,
                "task_id": row.task_id,
                "target_id": row.target_id,
                "phone_number": row.phone_number,
                "stage": row.stage,
            }

    async def _on_ringing(self, event: CallEvent) -> None:
        call_id = str(event.data.get("call_id") or "")
        if not call_id or await self._lookup(call_id) is None:
            return

    async def _on_answered(self, event: CallEvent) -> None:
        call_id = str(event.data.get("call_id") or "")
        context = await self._lookup(call_id)
        if context is None:
            return
        self._spawn(self._begin_screening(call_id, context))

    async def _begin_screening(self, call_id: str, context: dict) -> None:
        async with AsyncSessionLocal() as db:
            call = await PersonalAutoOutboundRepository.get_call_for_update(db, context["id"])
            session = await PersonalAutoOutboundRepository.get_session(db, context["session_id"])
            if call is None or session is None or call.stage not in _RINGING_STAGES:
                return
            await PersonalAutoOutboundRepository.update_call(
                db,
                call,
                {"stage": "screening", "answered_at": datetime.now(timezone.utc)},
            )
            opening_asset_id = session.opening_audio_asset_id
            tenant_id = session.tenant_id

        waiter = asyncio.get_running_loop().create_future()
        self._opening_waiters[call_id] = waiter
        try:
            opening = await AudioAssetService.get_managed(opening_asset_id, tenant_id)
            await self.telephony.call_play(call_id, audio_url=opening["preview_url"])
            await self.telephony.call_listen(
                call_id,
                adaptive_barge_in=True,
                performance={
                    "turn_detection_enabled": False,
                    "endpoint_silence_ms": 1000,
                    "barge_sensitivity": "sensitive",
                },
            )
        except Exception:  # noqa: BLE001
            self._clear_screening_state(call_id)
            logger.exception("personal auto-outbound opening/listen failed call_id=%s", call_id)
            await self._auto_pause(context["session_id"], "opening_audio_unavailable")
            await self._assign_human(call_id, degraded_reason="opening_audio_unavailable")
            return
        self._spawn(self._wait_for_opening_end(call_id, waiter))

    async def _wait_for_opening_end(
        self, call_id: str, waiter: asyncio.Future
    ) -> None:
        try:
            await waiter
        except asyncio.CancelledError:
            return
        finally:
            if self._opening_waiters.get(call_id) is waiter:
                self._opening_waiters.pop(call_id, None)
        self._opening_ended.add(call_id)
        if call_id not in self._speech_active and call_id not in self._speech_completed:
            self._replace_silence_timer(call_id)

    async def _on_speech_start(self, event: CallEvent) -> None:
        call_id = str(event.data.get("call_id") or "")
        context = await self._lookup(call_id)
        if context is None or context["stage"] != "screening":
            return
        self._speech_active.add(call_id)
        self._cancel_silence_timer(call_id)

    async def _on_speech_end(self, event: CallEvent) -> None:
        call_id = str(event.data.get("call_id") or "")
        context = await self._lookup(call_id)
        if context is None or context["stage"] not in {"screening", "filtered"}:
            return
        self._speech_active.discard(call_id)
        self._speech_completed.add(call_id)
        self._cancel_silence_timer(call_id)
        if context["stage"] == "filtered":
            return
        self._spawn(self._classify(call_id, event.data))

    async def _on_speech_discard(self, event: CallEvent) -> None:
        call_id = str(event.data.get("call_id") or "")
        context = await self._lookup(call_id)
        if context is None or context["stage"] not in {"screening", "filtered"}:
            return
        self._speech_active.discard(call_id)
        if context["stage"] == "filtered":
            return
        if call_id in self._opening_ended and call_id not in self._speech_completed:
            self._replace_silence_timer(call_id)

    async def _classify(self, call_id: str, data: dict) -> None:
        timer = self._silence_tasks.pop(call_id, None)
        if timer:
            timer.cancel()
        context = await self._lookup(call_id)
        if context is None:
            return
        async with AsyncSessionLocal() as db:
            session = await PersonalAutoOutboundRepository.get_session(db, context["session_id"])
            if session is None:
                return
            snapshot = list(session.intent_snapshot or [])
        decision = await OutboundPrescreenService.classify_snapshot(
            snapshot,
            str(data.get("text") or ""),
            voiced_ms=data.get("voiced_ms"),
            voice_match=data.get("voice_match"),
        )
        if decision.auto_hangup:
            await self._filter_call(call_id, decision)
        elif decision.reason in _KEEP_LISTENING_REASONS:
            # The utterance failed eligibility (noise burst, too short, or a
            # different voice): it never proved to be a real turn, so it must
            # not stop the opening or trigger a transfer. Keep listening and
            # give the caller the remaining silence window to actually respond.
            logger.info(
                "personal auto-outbound ignoring ineligible utterance call_id=%s reason=%s",
                call_id,
                decision.reason,
            )
            self._speech_completed.discard(call_id)
            if call_id in self._opening_ended:
                self._replace_silence_timer(call_id)
        else:
            await self._assign_human(
                call_id,
                degraded_reason=decision.reason,
                last_utterance=str(data.get("text") or "").strip() or None,
            )

    async def _silence_timeout(self, call_id: str) -> None:
        try:
            await asyncio.sleep(_PRESCREEN_SILENCE_SECONDS)
            await self._assign_human(call_id, degraded_reason="prescreen_timeout")
        except asyncio.CancelledError:
            return
        finally:
            current = self._silence_tasks.get(call_id)
            if current is asyncio.current_task():
                self._silence_tasks.pop(call_id, None)

    async def _filter_call(self, call_id: str, decision) -> None:
        context = await self._lookup(call_id)
        if context is None:
            return
        async with AsyncSessionLocal() as db:
            call = await PersonalAutoOutboundRepository.get_call_for_update(db, context["id"])
            session = await PersonalAutoOutboundRepository.get_session(db, context["session_id"])
            if call is None or session is None or call.stage != "screening":
                return
            result = decision.intent_key or "explicit_rejection"
            target_status = (
                "do_not_call"
                if result == "do_not_contact"
                else "redial"
                if result == "not_convenient"
                else "completed"
            )
            await PersonalAutoOutboundRepository.update_call_and_settle_target(
                db,
                call,
                {
                    "stage": "filtered",
                    "prescreen_result": decision.intent_key or "explicit_rejection",
                    "intent_key": decision.intent_key,
                    "similarity": decision.similarity,
                },
                target_status=target_status,
                result=result,
                answered=True,
            )
            closing_asset_id = session.closing_audio_asset_id
            tenant_id = session.tenant_id

        self._clear_screening_state(call_id)

        # The closing message is terminal (the call hangs up right after), so
        # stop listening first: otherwise the caller-side echo of the closing
        # audio can trip adaptive barge-in and pause the playback mid-way.
        # Best-effort: a stop failure must not block the closing play.
        try:
            await self.telephony.call_stop(call_id, target="listen")
        except Exception:  # noqa: BLE001
            logger.warning(
                "personal auto-outbound stop-listen before closing failed call_id=%s",
                call_id,
                exc_info=True,
            )

        failed = False
        try:
            closing = await AudioAssetService.get_managed(closing_asset_id, tenant_id)
            waiter = asyncio.get_running_loop().create_future()
            self._closing_waiters[call_id] = waiter
            await self.telephony.call_play(call_id, audio_url=closing["preview_url"])
            await asyncio.wait_for(waiter, timeout=15)
        except Exception:  # noqa: BLE001
            failed = True
            logger.exception("personal auto-outbound closing play failed call_id=%s", call_id)
        finally:
            self._closing_waiters.pop(call_id, None)
        if not failed:
            # Let the closing's tail ride out the far-end jitter buffer before
            # the BYE: carrier + phone buffering can hold several hundred ms of
            # audio, and an immediate BYE clips the closing's last syllable.
            await asyncio.sleep(0.6)
        await self._safe_hangup(
            call_id, "closing_audio_failed" if failed else "personal_prescreen_filtered"
        )

    async def _on_play_end(self, event: CallEvent) -> None:
        call_id = str(event.data.get("call_id") or "")
        opening_waiter = self._opening_waiters.get(call_id)
        if opening_waiter is not None and not opening_waiter.done():
            opening_waiter.set_result(event.data)
        waiter = self._closing_waiters.get(call_id)
        if waiter is not None and not waiter.done():
            waiter.set_result(event.data)

    async def _assign_human(
        self,
        call_id: str,
        degraded_reason: str | None = None,
        last_utterance: str | None = None,
    ) -> None:
        context = await self._lookup(call_id)
        if context is None:
            return
        async with AsyncSessionLocal() as db:
            call = await PersonalAutoOutboundRepository.get_call_for_update(db, context["id"])
            session = await PersonalAutoOutboundRepository.get_session(db, context["session_id"])
            if call is None or session is None or call.stage != "screening":
                return
            updates = {
                "stage": "assigning",
                "prescreen_result": "uncertain" if degraded_reason else "non_rejection",
                "degraded_reason": degraded_reason,
            }
            if last_utterance:
                updates["last_utterance"] = last_utterance
            await PersonalAutoOutboundRepository.update_call(
                db,
                call,
                updates,
            )
            tenant_id = session.tenant_id
            primary_agent_id = session.primary_agent_id
            fallback_group_id = session.fallback_group_id
            task_id = session.task_id

        self._clear_screening_state(call_id)

        with suppress(Exception):
            await self.telephony.call_stop(call_id, target="all")
        await self._release_primary(context["session_id"], "personal_assign_started")
        async with AsyncSessionLocal() as db:
            current = await PersonalAutoOutboundRepository.get_call_for_update(db, context["id"])
            if current is None or current.stage != "assigning" or current.ended_at is not None:
                return
        targets = [
            {"queue_type": QueueType.EMPLOYEE.value, "queue_id": primary_agent_id}
        ]
        if fallback_group_id is not None:
            targets.append(
                {"queue_type": QueueType.EMPLOYEE_GROUP.value, "queue_id": fallback_group_id}
            )
        graph = {
            "version": 1,
            "nodes": [
                {"id": "start", "type": "start", "data": {}, "position": {"x": 0, "y": 0}},
                {
                    "id": "assign",
                    "type": "assign_queue",
                    "position": {"x": 1, "y": 0},
                    "data": {
                        "queue_targets": targets,
                        "target_strategy": "sequential_overflow",
                        "timeout_seconds": 20,
                        "queue_wait_seconds": 10,
                        # Empty string explicitly disables the transfer prompt so
                        # the callee hears silence, then the agent — no TTS cue.
                        "queue_prompt_text": "",
                    },
                },
                {"id": "hangup", "type": "hangup", "position": {"x": 2, "y": 0}, "data": {"pre_play": None}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "assign", "source_handle": "next"},
                {"id": "e2", "source": "assign", "target": "hangup", "source_handle": "timeout"},
            ],
            "variables": [],
        }
        workflow = VoiceFlowWorkflow(
            call_id=call_id,
            tenant_id=tenant_id,
            graph=graph,
            telephony=self.telephony,
            orchestrator=self.orchestrator,
            initial_variables={
                "sys.caller_number": "",
                "sys.called_number": context["phone_number"],
                "sys._auto_outbound_source": "personal_auto_outbound",
                "sys._auto_outbound_task_id": task_id,
                "sys._auto_outbound_record_id": context["id"],
                "sys._personal_primary_agent_id": primary_agent_id,
                "sys._direction": "outbound",
            },
        )
        self.orchestrator._workflows[call_id] = workflow  # noqa: SLF001
        try:
            await workflow.start()
            await asyncio.wait_for(workflow.done.wait(), timeout=40)
        except Exception:  # noqa: BLE001
            logger.exception("personal auto-outbound assign failed call_id=%s", call_id)
        bridged = workflow.bridged_agent_info()
        if bridged is None:
            async with AsyncSessionLocal() as db:
                call = await PersonalAutoOutboundRepository.get_call_for_update(db, context["id"])
                if call is not None and call.stage == "assigning":
                    await PersonalAutoOutboundRepository.update_call_and_settle_target(
                        db,
                        call,
                        {
                            "stage": "no_agent",
                            "hangup_reason": workflow.ended_reason or "no_agent",
                            "ended_at": datetime.now(timezone.utc),
                        },
                        target_status="redial",
                        result="no_agent",
                        answered=True,
                    )
            await self._safe_hangup(call_id, "personal_no_agent")
            await self._finish_session_if_idle(context["session_id"])
            self._schedule_replenish(context["session_id"])
            return

        employee_id = int(bridged["employee_id"])
        assignment_type = "primary" if employee_id == primary_agent_id else "fallback"
        async with AsyncSessionLocal() as db:
            call = await PersonalAutoOutboundRepository.get_call_for_update(db, context["id"])
            if call is not None and call.stage == "assigning" and call.ended_at is None:
                await PersonalAutoOutboundRepository.update_call(
                    db,
                    call,
                    {
                        "stage": "human",
                        "assigned_agent_id": employee_id,
                        "assignment_type": assignment_type,
                    },
                )
        if assignment_type == "primary":
            await self._cancel_ringing(context["session_id"], except_call_id=call_id)
        else:
            async with AsyncSessionLocal() as db:
                counts = await PersonalAutoOutboundRepository.counts(db, context["session_id"])
            if counts["screening_current"] == 0:
                await self._ensure_primary_reserved(
                    context["session_id"], tenant_id, primary_agent_id
                )

    async def _cancel_ringing(self, session_id: int, except_call_id: str | None = None) -> None:
        async with AsyncSessionLocal() as db:
            call_ids = await PersonalAutoOutboundRepository.active_call_ids(
                db, session_id, _RINGING_STAGES
            )
        await asyncio.gather(
            *(
                self._safe_hangup(item, "primary_agent_connected")
                for item in call_ids
                if item != except_call_id
            ),
            return_exceptions=True,
        )

    async def _on_hangup(self, event: CallEvent) -> None:
        call_id = str(event.data.get("call_id") or "")
        if not call_id:
            return
        await self._finalize_hangup(call_id, str(event.data.get("reason") or ""))

    async def _finalize_hangup(self, call_id: str, reason: str) -> None:
        context = await self._lookup(call_id)
        if context is None:
            return
        self._clear_screening_state(call_id)
        waiter = self._closing_waiters.pop(call_id, None)
        if waiter is not None and not waiter.done():
            waiter.set_result({"call_id": call_id, "reason": reason})
        async with AsyncSessionLocal() as db:
            call = await PersonalAutoOutboundRepository.get_call_for_update(db, context["id"])
            if call is None or call.ended_at is not None:
                return
            previous = (call.metadata_json or {}).get("previous_target_status", "pending")
            if call.stage in _RINGING_STAGES:
                final_stage = (
                    "cancelled"
                    if reason in {"primary_agent_connected", "personal_session_stopped"}
                    else "not_connected"
                )
                result = final_stage
                target_status = previous
                answered = False
            elif call.stage in {"screening", "assigning"}:
                final_stage = "ended"
                result = "answered_hangup"
                target_status = "redial"
                answered = True
            elif call.stage == "human":
                final_stage = "ended"
                result = "human_completed"
                target_status = "redial"
                answered = True
            else:
                final_stage = "ended"
                result = call.prescreen_result or call.hangup_reason or "ended"
                target_status = None
                answered = call.answered_at is not None
            ended_at = datetime.now(timezone.utc)
            await PersonalAutoOutboundRepository.update_call_and_settle_target(
                db,
                call,
                {
                    "stage": final_stage,
                    "telephony_call_id": call.telephony_call_id or call_id,
                    "prescreen_result": call.prescreen_result or result,
                    "hangup_reason": reason or call.hangup_reason,
                    "ended_at": ended_at,
                },
                target_status=target_status,
                result=result,
                answered=answered,
            )
            session_id = call.session_id
        self._call_rows.pop(call_id, None)
        self._session_by_call.pop(call_id, None)
        await self._finish_session_if_idle(session_id)
        self._schedule_replenish(session_id)

    async def _auto_pause(self, session_id: int, reason: str) -> None:
        async with AsyncSessionLocal() as db:
            session = await PersonalAutoOutboundRepository.get_session(db, session_id)
            if session is not None and session.status == "running":
                await PersonalAutoOutboundRepository.update_session(
                    db,
                    session,
                    {
                        "status": "auto_paused",
                        "pause_reason": reason,
                        "paused_at": datetime.now(timezone.utc),
                    },
                )

    async def _finish_session_if_idle(
        self, session_id: int, *, exhaust_running: bool = False
    ) -> None:
        finished = False
        async with AsyncSessionLocal() as db:
            session = await PersonalAutoOutboundRepository.get_session(db, session_id)
            if session is None:
                return
            counts = await PersonalAutoOutboundRepository.counts(db, session_id)
            active = sum(
                counts[key]
                for key in ("ringing_current", "screening_current", "human_current", "filtered_current")
            )
            should_finish = active == 0 and (
                session.status == "stopping" or (exhaust_running and session.status == "running")
            )
            if should_finish:
                await PersonalAutoOutboundRepository.update_session(
                    db,
                    session,
                    {"status": "stopped", "stopped_at": datetime.now(timezone.utc)},
                )
                finished = True
        if finished:
            await self._release_primary(session_id, "personal_session_finished")

    async def _safe_hangup(self, call_id: str, reason: str) -> None:
        try:
            await self.telephony.call_hangup(call_id, reason=reason)
        except Exception:  # noqa: BLE001
            logger.exception(
                "personal auto-outbound hangup command failed call_id=%s reason=%s",
                call_id,
                reason,
            )
            return

        # A successful RPC acknowledgement means the kernel has ended the
        # call. Finalize locally as part of the command transaction instead of
        # depending exclusively on a later broadcast event, which may be
        # delivered to a different application instance. The event path calls
        # the same idempotent method for remote hangups and remains the safety
        # net for all other endings.
        await self._finalize_hangup(call_id, reason)

    @staticmethod
    def _redis():
        try:
            from app.db.redis import redis_client

            return redis_client.client
        except RuntimeError:
            return None

    @staticmethod
    def _reservation_id(session_id: int) -> str:
        return f"personal-session:{session_id}"

    async def _ensure_primary_reserved(
        self, session_id: int, tenant_id: int, employee_id: int
    ) -> bool:
        r = self._redis()
        if r is None:
            return True
        reservation_id = self._reservation_id(session_id)
        try:
            current = await CcAgentResourceService.get_snapshot(r, tenant_id, employee_id)
            if current and current.get("current_call_id") == reservation_id:
                return True
            await CcAgentResourceService.reserve_outbound(
                r,
                tenant_id,
                employee_id,
                reservation_id=reservation_id,
                ttl_seconds=24 * 60 * 60,
            )
            return True
        except Exception:  # noqa: BLE001
            logger.info(
                "personal auto-outbound primary reservation unavailable session_id=%s employee_id=%s",
                session_id,
                employee_id,
            )
            return False

    async def _release_primary(self, session_id: int, reason: str) -> None:
        r = self._redis()
        if r is None:
            return
        async with AsyncSessionLocal() as db:
            session = await PersonalAutoOutboundRepository.get_session(db, session_id)
            if session is None:
                return
            tenant_id = session.tenant_id
            employee_id = session.primary_agent_id
        with suppress(Exception):
            await CcAgentResourceService.release(
                r,
                tenant_id,
                employee_id,
                reason=reason,
                expected_call_id=self._reservation_id(session_id),
            )
