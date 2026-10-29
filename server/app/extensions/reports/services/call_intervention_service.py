"""Supervisor call-intervention service.

Implements listen / whisper / barge / takeover / force-hangup on another agent's
live call. Every action runs the same gate chain before touching media:

  page permission (call.monitor.view)  — enforced at the router
  → operation permission (listen/whisper/barge/takeover/force_hangup)
  → data scope (call_record) — the target call must be within the supervisor's
    visible scope, and never the supervisor's own call
  → phase capability matrix (文档 3.8)
  → concurrency: the call must be free (no other supervisor) and the supervisor
    must be idle (not already monitoring another call)

Media orchestration — the media kernel exposes a multi-party mixing room
(``room.create`` / ``room.set_mix_gain`` / ``room.replace_leg`` / ``room.close``)
alongside the one-way ``call.listen`` monitor injection. Modes map to media as
follows:

  * listen  — lightweight one-way monitor via ``call.listen`` (no room, no
    supervisor media leg). Kept as the cheapest path.
  * whisper / barge — the supervisor needs to be audible, so the supervisor's
    own WebRTC media leg is joined with the customer + agent legs into a mixing
    room; the mode is then just a mix-gain matrix (who hears the supervisor).
    Switching between listen ⇄ whisper ⇄ barge inside a live room is a pure
    gain change — no leg rebuild.
  * takeover — ``room.replace_leg`` swaps the agent leg out for the supervisor
    leg; the customer never drops.
  * force_hangup — closes the whole chain (``room.close`` when a room exists,
    else every enumerated leg is hung up).

When the kernel has rooms disabled it raises ``TelephonyMethodNotFoundError``;
the speaking modes degrade to a clear "not supported" (501) WITHOUT tearing
down the agent/customer call, and one-way listen still works.
"""
from __future__ import annotations

import logging

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    NotImplementedApiError,
    ValidationError,
)
from app.db.session import AsyncSessionLocal
from app.libs.realtime import get_realtime_transport
from app.libs.telephony.base import BaseTelephonyClient, TelephonyMethodNotFoundError
from app.models.call_record import CallRecord
from app.models.employee import Employee
from app.schemas.permission import EffectivePrincipal
from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
from app.services.call_record_service import CallRecordService
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService
from app.services.data_scope_service import (
    DataScopeService,
    RESOURCE_CALL_RECORD,
    SCOPE_SELF,
)

from ..lib import intervention_state
from ..lib.active_calls import LIVE_STATE
from ..lib.intervention_state import MonitorHolder

logger = logging.getLogger(__name__)

# Message shown when the media kernel has room mixing disabled and a speaking
# mode (whisper / barge / takeover) cannot be assembled. The agent/customer call
# is never disturbed in this path.
_ROOMS_UNAVAILABLE = "The call service does not currently support this operation"

# Operation permission keys per mode (page permission is checked in the router).
_MODE_PERMISSION = {
    "listen": "call.monitor.listen",
    "whisper": "call.monitor.whisper",
    "barge": "call.monitor.barge",
    "takeover": "call.monitor.takeover",
    "force_hangup": "call.monitor.force_hangup",
}

# Phase capability matrix (文档 3.8). ``True`` = allowed for that phase.
# ``consulting`` and ``three_way`` are derived from the agent's persisted call
# legs (see ``_derive_phase``). ``customer_hold`` and ``transferring`` have no
# durable marker to read, so a call in either lands on ``single``; hold is the
# most permissive row anyway, and a blind transfer is a sub-second window.
_PHASE_MATRIX: dict[str, dict[str, bool]] = {
    "single": {"listen": True, "whisper": True, "barge": True, "takeover": True, "force_hangup": True},
    "customer_hold": {"listen": True, "whisper": True, "barge": False, "takeover": False, "force_hangup": True},
    "consulting": {"listen": True, "whisper": True, "barge": False, "takeover": False, "force_hangup": True},
    "three_way": {"listen": True, "whisper": True, "barge": False, "takeover": False, "force_hangup": True},
    "transferring": {"listen": False, "whisper": False, "barge": False, "takeover": False, "force_hangup": False},
}


class _ResolvedTarget:
    """A monitorable target call plus the phase used for the capability check."""

    def __init__(
        self,
        *,
        record_id: int,
        call_id: str,
        customer_call_id: str,
        agent_id: int,
        phase: str,
        agent_call_id: str | None = None,
    ):
        self.record_id = record_id
        self.call_id = call_id
        self.customer_call_id = customer_call_id
        # The agent's own WebRTC media leg (from their AgentWebRTCSession); the
        # leg that mixes into the room and is swapped out on takeover. ``None``
        # when the agent has no active WebRTC leg (e.g. a SIP-phone agent).
        self.agent_call_id = agent_call_id
        self.agent_id = agent_id
        self.phase = phase


class CallInterventionService:
    """Supervisor intervention on another agent's live call.

    Telephony is injected so tests can pass a mock. DB access uses short
    sessions opened only around reads/writes and closed before any kernel RPC.
    """

    # ───────────────────────── public entrypoints ─────────────────────────

    @staticmethod
    async def listen(
        telephony: BaseTelephonyClient,
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
    ) -> dict:
        """Enter (or return to) listen-only mode.

        Two paths:
          * fresh listen — no room yet: the lightweight one-way ``call.listen``
            monitor injection on the customer leg (supervisor hears, is silent).
          * switch back from whisper/barge — a room is already up: keep the room
            and just mute the supervisor into both parties (gain 0), so the
            supervisor keeps hearing both but neither hears the supervisor. No
            leg rebuild.
        """

        target = await CallInterventionService._gate(principal, redis, call_id, "listen")
        holder = await intervention_state.get_call_holder(
            redis, principal.tenant_id, call_id
        )
        room_id = holder.room_id if holder is not None else None
        await CallInterventionService._claim(redis, principal, call_id, "listen")
        try:
            if room_id:
                # In-room mute: supervisor inaudible to both parties.
                sup = holder.supervisor_call_id if holder is not None else None
                if sup:
                    if target.agent_call_id:
                        await telephony.room_set_mix_gain(
                            room_id, listener_call_id=target.agent_call_id,
                            speaker_call_id=sup, gain=0.0,
                        )
                    await telephony.room_set_mix_gain(
                        room_id, listener_call_id=target.customer_call_id,
                        speaker_call_id=sup, gain=0.0,
                    )
            else:
                await telephony.call_listen(target.customer_call_id)
        except Exception as exc:  # noqa: BLE001 — release lock, record failure, re-raise
            await CallInterventionService._release(redis, principal, call_id)
            await CallInterventionService._trail(
                principal, call_id, mode="listen", event="failed", detail=str(exc)
            )
            raise
        if holder is not None and holder.mode in {"whisper", "barge"}:
            await CallInterventionService._trail(
                principal, call_id, mode=holder.mode, event="ended"
            )
        await CallInterventionService._trail(principal, call_id, mode="listen", event="started")
        return CallInterventionService._result(call_id, "listen", principal.user_id)

    @staticmethod
    async def register_supervisor_leg(
        telephony: BaseTelephonyClient,
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
        sdp: str,
    ) -> dict:
        """Negotiate the supervisor's own WebRTC media leg for a monitored call.

        The supervisor's browser sends an SDP offer; the kernel answers with an
        SDP and a fresh call_id identifying the supervisor's media leg. That leg
        id is recorded on the monitor holder so a subsequent whisper / barge /
        takeover can mix it into the room. Must be called by the supervisor who
        already holds (or is about to hold) the monitor lock on this call.

        No DB session is held across the kernel round-trip: the short session
        only reads the supervisor name and validates scope, and it closes before
        ``webrtc.offer`` is sent.
        """

        # Gate (permission + scope + phase + concurrency) with short sessions
        # only; the kernel negotiation below holds no DB connection.
        target = await CallInterventionService._gate(principal, redis, call_id, "listen")
        holder = await intervention_state.get_call_holder(
            redis, principal.tenant_id, call_id
        )
        mode = holder.mode if holder is not None else "listen"

        result = await telephony.webrtc_offer(sdp)
        supervisor_call_id = result.get("call_id", "")
        if not supervisor_call_id:
            raise NotFoundError("Telephony kernel did not return a call_id")
        try:
            await telephony.call_answer(supervisor_call_id)
        except Exception:  # noqa: BLE001 — kernel may auto-answer WebRTC legs
            pass

        # A supervisor page refresh creates a new browser media leg while the
        # monitor holder and mixing room survive in Redis. Replace the stale
        # supervisor leg in-place so the refreshed browser resumes the same
        # intervention instead of leaving two supervisor legs in the room.
        stale_supervisor_call_id = holder.supervisor_call_id if holder is not None else None
        if (
            holder is not None
            and holder.room_id
            and stale_supervisor_call_id
            and stale_supervisor_call_id != supervisor_call_id
        ):
            try:
                await telephony.room_replace_leg(
                    holder.room_id, stale_supervisor_call_id, supervisor_call_id
                )
            except Exception:  # noqa: BLE001 — stale leg may already be detached
                await telephony.room_add_leg(holder.room_id, supervisor_call_id)
            try:
                await telephony.call_hangup(
                    stale_supervisor_call_id, reason="supervisor_media_replaced"
                )
            except Exception:  # noqa: BLE001 — room replacement already succeeded
                pass
            await intervention_state.clear_supervisor_leg_index(
                redis, stale_supervisor_call_id
            )
            await CallInterventionService._persist_agent_room(
                principal.tenant_id,
                target,
                holder.room_id,
                supervisor_call_id,
            )

        # Re-claim the lock carrying the negotiated leg id (same supervisor, so
        # this only augments the holder).
        await CallInterventionService._claim(
            redis, principal, call_id, mode, supervisor_call_id=supervisor_call_id,
            room_id=holder.room_id if holder is not None else None,
        )
        # Index the leg → target so kernel-side ICE candidates for this leg can
        # be routed back to this supervisor's browser (trickle ICE).
        await intervention_state.set_supervisor_leg_index(
            redis, principal.tenant_id, call_id, supervisor_call_id
        )
        await CallInterventionService._trail(
            principal, call_id, mode=mode, event="supervisor_leg_ready"
        )
        return {
            "call_id": call_id,
            "supervisor_call_id": supervisor_call_id,
            "sdp": result.get("sdp", ""),
        }

    @staticmethod
    async def add_supervisor_ice(
        telephony: BaseTelephonyClient,
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
        candidate: dict,
    ) -> dict:
        """Trickle one browser ICE candidate to the supervisor's kernel leg.

        ``call_id`` is the target call id; the supervisor's own media-leg id is
        resolved from the monitor holder. Holds no DB session across the kernel
        round-trip.
        """

        holder = await intervention_state.get_call_holder(
            redis, principal.tenant_id, call_id
        )
        if holder is None or not holder.supervisor_call_id:
            raise NotFoundError("No supervisor audio leg for this call")
        await telephony.webrtc_ice(holder.supervisor_call_id, candidate)
        return {"ok": True}

    @staticmethod
    async def whisper(
        telephony: BaseTelephonyClient,
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
    ) -> dict:
        """Whisper to the agent only.

        The supervisor is audible to the agent leg but not the customer. Needs
        the supervisor media leg + a room, so a room is created/joined if not
        already up, then the mix-gain matrix is applied.
        """

        return await CallInterventionService._enter_speaking_mode(
            telephony, redis, principal, call_id, "whisper"
        )

    @staticmethod
    async def barge(
        telephony: BaseTelephonyClient,
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
    ) -> dict:
        """Barge into the call as a third audible party (three-way).

        Both agent and customer hear the supervisor. Same room as whisper; only
        the mix-gain matrix differs.
        """

        return await CallInterventionService._enter_speaking_mode(
            telephony, redis, principal, call_id, "barge"
        )

    @staticmethod
    async def takeover(
        telephony: BaseTelephonyClient,
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
        reason: str,
        note: str | None,
    ) -> dict:
        """Take over the call from the agent, becoming the new responsible party.

        Extra check beyond the mode permission: takeover also requires
        ``call.workspace.use`` (文档 3.9 requires ``listen`` + ``call.workspace.use``;
        the catalog tree only carries the ``listen`` parent, so the second
        dependency is enforced here explicitly).

        Media: the agent leg is swapped out for the supervisor leg inside the
        room (``room.replace_leg``) so the customer never drops. The original
        agent is then moved to wrap-up and the reception-segment / responsible
        party change is recorded. Requires an established supervisor media leg.
        """

        if not principal.has_permission("call.workspace.use"):
            raise ForbiddenError("Permission denied")
        target = await CallInterventionService._gate(principal, redis, call_id, "takeover")
        holder = await intervention_state.get_call_holder(
            redis, principal.tenant_id, call_id
        )
        supervisor_call_id = holder.supervisor_call_id if holder is not None else None
        if not supervisor_call_id:
            raise ConflictError("Establish the supervisor audio leg before taking over")

        await CallInterventionService._claim(
            redis, principal, call_id, "takeover",
            supervisor_call_id=supervisor_call_id,
            room_id=holder.room_id if holder is not None else None,
        )
        await CallInterventionService._trail(
            principal, call_id, mode="takeover", event="initiated", reason=reason, note=note
        )
        try:
            room_id = await CallInterventionService._ensure_room(
                telephony, redis, principal, call_id, target, supervisor_call_id
            )
            # The supervisor leg is already mixed into the room (_ensure_room
            # adds it when the room is created), so we take over by dropping the
            # agent out of the room — not by room.replace_leg, which would fail
            # with "leg already in room" since the new (supervisor) leg is
            # already present. When the agent leg id is unknown we cannot
            # remove it: their browser is still told to hang up below, but the
            # kernel leg then lingers mixed into the room until the ICE/RTP
            # timeout reaps it (~30s of audible three-way) — log loudly so
            # that delay is explainable from logs.
            if target.agent_call_id:
                await telephony.room_remove_leg(room_id, target.agent_call_id)
            else:
                logger.warning(
                    "takeover: agent media leg unknown, room keeps stale agent "
                    "leg until ICE timeout call=%s agent=%s",
                    call_id, target.agent_id,
                )
            # The customer must now hear the supervisor at full volume even when
            # we arrived here from whisper (which pins customer→supervisor to 0).
            await telephony.room_set_mix_gain(
                room_id, listener_call_id=target.customer_call_id,
                speaker_call_id=supervisor_call_id, gain=1.0,
            )
            await CallInterventionService._finalize_takeover_state(
                redis, principal, target
            )
            # Tell the agent's browser to end its call UI cleanly (→ wrap-up)
            # BEFORE tearing down their kernel leg. The agent's cc.call_hangup
            # handler closes its WebRTC peer with the "closing" guard set, so the
            # media teardown is silent instead of surfacing as an "ICE 连接失败"
            # error, and their call bar closes. Same event the orchestrator sends
            # when a customer hangs up.
            await CallInterventionService._notify_agent(
                principal, target.agent_id, "cc.call_hangup",
                {"call_id": call_id, "reason": "supervisor_takeover"},
            )
            # End the agent's own WebRTC leg so their kernel call terminates. This
            # is the agent's leg id, never the customer's, so the customer is not
            # dropped. Best-effort: the media takeover already succeeded, so a
            # stale/duplicate leg must not fail the whole operation.
            if target.agent_call_id:
                try:
                    await telephony.call_hangup(
                        target.agent_call_id, reason="supervisor_takeover"
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "takeover: agent leg hangup failed call=%s", call_id, exc_info=True
                    )

        except TelephonyMethodNotFoundError:
            await CallInterventionService._trail(
                principal, call_id, mode="takeover", event="unsupported"
            )
            raise NotImplementedApiError(_ROOMS_UNAVAILABLE)
        except Exception as exc:  # noqa: BLE001
            await CallInterventionService._trail(
                principal, call_id, mode="takeover", event="failed", detail=str(exc)
            )
            raise

        # Reception-segment intent: end the original agent's segment and open a
        # supervisor segment. The actual segment cut is derived post-call from
        # reception events; recording the intent keeps it auditable.
        await CallInterventionService._trail(
            principal,
            call_id,
            mode="takeover",
            event="reception_segment_intent",
            detail=f"end_agent_segment agent={target.agent_id}; open_supervisor_segment supervisor={principal.user_id}",
        )
        await CallInterventionService._notify_agent(
            principal, target.agent_id, "cc.supervisor_takeover",
            {"call_id": call_id, "supervisor_id": principal.user_id, "supervisor_name": holder.name if holder else ""},
        )
        await CallRecordService.mark_reception_transferred_managed(
            tenant_id=principal.tenant_id,
            call_id=call_id,
            from_agent_id=target.agent_id,
            to_agent_id=principal.user_id,
            operation_id=f"supervisor:{call_id}:{principal.user_id}",
            target_leg_id=supervisor_call_id,
            reason_code="takeover_completed",
        )
        await CallInterventionService._trail(principal, call_id, mode="takeover", event="succeeded")
        return CallInterventionService._result(call_id, "takeover", principal.user_id)

    @staticmethod
    async def force_hangup(
        telephony: BaseTelephonyClient,
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
        reason: str,
        note: str | None,
    ) -> dict:
        """End the whole call chain — every leg — for the target call.

        Unlike the agent's "挂断用户" (which ends only the customer leg), this
        ends the entire chain. When a mixing room is up it is closed in one shot
        (``room.close`` un-mixes and drops every joined leg). Otherwise the
        customer and agent legs are hung up individually. The original agent is
        then moved to wrap-up.
        """

        target = await CallInterventionService._gate(principal, redis, call_id, "force_hangup")
        holder = await intervention_state.get_call_holder(
            redis, principal.tenant_id, call_id
        )
        room_id = holder.room_id if holder is not None else None
        await CallInterventionService._trail(
            principal, call_id, mode="force_hangup", event="initiated", reason=reason, note=note
        )
        try:
            if room_id:
                # One-shot teardown of the whole mixed chain.
                await telephony.room_close(room_id, reason="supervisor_force_hangup")
            else:
                # No room: enumerate and hang up each known leg of the chain.
                for leg in (target.customer_call_id, target.agent_call_id):
                    if leg:
                        await telephony.call_hangup(leg, reason="supervisor_force_hangup")
        except Exception as exc:  # noqa: BLE001
            await CallInterventionService._trail(
                principal, call_id, mode="force_hangup", event="failed", detail=str(exc)
            )
            raise
        # Move the original agent to wrap-up (整理态) — same terminal state the
        # agent reaches after a normal hangup.
        async with AsyncSessionLocal() as db:
            await CcAgentStatusService.sync_pg_status(
                db, principal.tenant_id, target.agent_id, "after_call_work", "supervisor_force_hangup"
            )
        await CallInterventionService._notify_agent(
            principal, target.agent_id, "cc.supervisor_force_hangup",
            {"call_id": call_id, "reason": reason},
        )
        if holder is not None and holder.supervisor_call_id:
            await intervention_state.clear_supervisor_leg_index(
                redis, holder.supervisor_call_id
            )
        await CallInterventionService._release(redis, principal, call_id)
        await CallInterventionService._close_cdr_after_teardown(
            principal, call_id, hangup_reason="supervisor_force_hangup"
        )
        await CallInterventionService._trail(principal, call_id, mode="force_hangup", event="succeeded")
        return CallInterventionService._result(call_id, "force_hangup", principal.user_id)

    @staticmethod
    async def end_takeover(
        telephony: BaseTelephonyClient,
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
    ) -> dict:
        """End a call the supervisor has taken over.

        After a takeover the supervisor is the responsible party, holding the
        room with the customer (the original agent is gone). Ending it closes
        the room — dropping the customer + supervisor legs — and the
        orchestrator's ``call.hangup`` handler then finalizes the CDR. The
        monitor lock is released. Idempotent: a no-op when this supervisor no
        longer holds the call (e.g. the customer already hung up).
        """

        holder = await intervention_state.get_call_holder(
            redis, principal.tenant_id, call_id
        )
        if holder is None or holder.supervisor_id != principal.user_id:
            return CallInterventionService._result(call_id, "takeover", principal.user_id)
        try:
            if holder.room_id:
                await telephony.room_close(holder.room_id, reason="supervisor_takeover_end")
            else:
                # No room (unexpected post-takeover): hang up the known legs.
                target = await CallInterventionService._resolve(
                    principal, call_id, require_scope=False
                )
                for leg in (target.customer_call_id, holder.supervisor_call_id):
                    if leg:
                        await telephony.call_hangup(leg, reason="supervisor_takeover_end")
        except Exception:  # noqa: BLE001 — teardown best-effort; still release the lock
            logger.warning("end takeover: teardown failed call=%s", call_id, exc_info=True)
        if holder.supervisor_call_id:
            await intervention_state.clear_supervisor_leg_index(
                redis, holder.supervisor_call_id
            )
        await CallInterventionService._release(redis, principal, call_id)
        await CallInterventionService._close_cdr_after_teardown(
            principal, call_id, hangup_reason="supervisor_takeover_end"
        )
        await CallInterventionService._trail(principal, call_id, mode="takeover", event="ended")
        return CallInterventionService._result(call_id, "takeover", principal.user_id)

    # ───────────────────────── media orchestration ─────────────────────────

    @staticmethod
    async def _finalize_takeover_state(
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        target: _ResolvedTarget,
    ) -> None:
        """Move call ownership to the supervisor and block agent reconnects."""

        if redis is not None:
            await CcAgentResourceService.mark_after_call_work(
                redis,
                principal.tenant_id,
                target.agent_id,
                call_id=target.call_id,
                reason="supervisor_takeover",
            )

        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(CallRecord).where(
                        CallRecord.id == target.record_id,
                        CallRecord.tenant_id == principal.tenant_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("No active call")
            row.last_serving_agent_id = principal.user_id
            await db.commit()
            try:
                await AgentWebRTCSessionService.close(
                    db, principal.tenant_id, target.agent_id
                )
            except NotFoundError:
                pass
            await CcAgentStatusService.sync_pg_status(
                db,
                principal.tenant_id,
                target.agent_id,
                "after_call_work",
                "supervisor_takeover",
            )

        from app.services.call_center import call_control_service as call_control

        await call_control._clear_legs(principal.tenant_id, target.agent_id)

    @staticmethod
    async def _enter_speaking_mode(
        telephony: BaseTelephonyClient,
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
        mode: str,
    ) -> dict:
        """Shared whisper/barge path: ensure a room, then apply the mix matrix.

        Requires an already-negotiated supervisor media leg (via
        ``register_supervisor_leg``). Degrades to 501 without disturbing the
        agent/customer call when the kernel has rooms disabled.
        """

        target = await CallInterventionService._gate(principal, redis, call_id, mode)
        holder = await intervention_state.get_call_holder(
            redis, principal.tenant_id, call_id
        )
        supervisor_call_id = holder.supervisor_call_id if holder is not None else None
        if not supervisor_call_id:
            raise ConflictError("Establish the supervisor audio leg before speaking")

        await CallInterventionService._claim(
            redis, principal, call_id, mode,
            supervisor_call_id=supervisor_call_id,
            room_id=holder.room_id if holder is not None else None,
        )
        try:
            room_id = await CallInterventionService._ensure_room(
                telephony, redis, principal, call_id, target, supervisor_call_id
            )
            await CallInterventionService._apply_gain_matrix(
                telephony, room_id, target, supervisor_call_id, mode
            )
        except TelephonyMethodNotFoundError:
            # Rooms disabled on the kernel: the agent/customer call is untouched
            # (no room was created), one-way listen still works. Downgrade mode.
            await CallInterventionService._claim(
                redis, principal, call_id, "listen",
                supervisor_call_id=supervisor_call_id,
                room_id=holder.room_id if holder is not None else None,
            )
            await CallInterventionService._trail(
                principal, call_id, mode=mode, event="unsupported"
            )
            raise NotImplementedApiError(_ROOMS_UNAVAILABLE)
        except Exception as exc:  # noqa: BLE001
            await CallInterventionService._trail(
                principal, call_id, mode=mode, event="failed", detail=str(exc)
            )
            raise
        await CallInterventionService._notify_agent(
            principal, target.agent_id,
            "cc.supervisor_whisper" if mode == "whisper" else "cc.supervisor_barge",
            {"call_id": call_id, "supervisor_id": principal.user_id,
             "supervisor_name": holder.name if holder else ""},
        )
        if holder is not None and holder.mode != mode:
            await CallInterventionService._trail(
                principal, call_id, mode=holder.mode, event="ended"
            )
        await CallInterventionService._trail(principal, call_id, mode=mode, event="started")
        await CallInterventionService._trail(principal, call_id, mode=mode, event="succeeded")
        return CallInterventionService._result(call_id, mode, principal.user_id)

    @staticmethod
    async def _ensure_room(
        telephony: BaseTelephonyClient,
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
        target: _ResolvedTarget,
        supervisor_call_id: str,
    ) -> str:
        """Return the room id for this call, creating it (with all legs) if absent.

        The room joins customer + agent + supervisor legs. The kernel
        auto-unbridges the original pairwise agent↔customer bridge as the legs
        move into the mixer, so the live call is not interrupted. The room id is
        persisted on the holder so mode switches reuse the same room.
        """

        holder = await intervention_state.get_call_holder(
            redis, principal.tenant_id, call_id
        )
        if holder is not None and holder.room_id:
            await CallInterventionService._persist_agent_room(
                principal.tenant_id,
                target,
                holder.room_id,
                supervisor_call_id,
            )
            return holder.room_id

        # A previous supervisor can leave while the customer and agent remain
        # in the two-party mixer. The monitor lock is released, but the shared
        # call state intentionally keeps that room so media reconnects work.
        # Reuse it for the next supervisor instead of trying to create a second
        # room with legs that are already roomed.
        from app.services.call_center import call_control_service as call_control

        shared_legs = await call_control._legs(principal.tenant_id, target.agent_id)
        if shared_legs.room_id:
            await telephony.room_add_leg(shared_legs.room_id, supervisor_call_id)
            await CallInterventionService._claim(
                redis,
                principal,
                call_id,
                holder.mode if holder is not None else "listen",
                supervisor_call_id=supervisor_call_id,
                room_id=shared_legs.room_id,
            )
            await CallInterventionService._persist_agent_room(
                principal.tenant_id,
                target,
                shared_legs.room_id,
                supervisor_call_id,
            )
            return shared_legs.room_id

        legs = [leg for leg in (target.customer_call_id, target.agent_call_id, supervisor_call_id) if leg]
        result = await telephony.room_create(leg_call_ids=legs)
        room_id = result.get("room_id", "")
        if not room_id:
            raise NotFoundError("Telephony kernel did not return a room_id")
        await CallInterventionService._claim(
            redis, principal, call_id,
            holder.mode if holder is not None else "listen",
            supervisor_call_id=supervisor_call_id,
            room_id=room_id,
        )
        await CallInterventionService._trail(
            principal, call_id, mode=holder.mode if holder is not None else "listen",
            event="room_created", detail=f"room={room_id}",
        )
        await CallInterventionService._persist_agent_room(
            principal.tenant_id,
            target,
            room_id,
            supervisor_call_id,
        )
        return room_id

    @staticmethod
    async def _persist_agent_room(
        tenant_id: int,
        target: _ResolvedTarget,
        room_id: str,
        supervisor_call_id: str,
    ) -> None:
        """Expose intervention room membership to the shared reconnect path."""

        from app.services.call_center import call_control_service as call_control

        legs = await call_control._legs(tenant_id, target.agent_id)
        legs.agent_media_call_id = target.agent_call_id
        legs.room_id = room_id
        legs.room_legs = [
            leg
            for leg in (
                target.customer_call_id,
                target.agent_call_id,
                supervisor_call_id,
            )
            if leg
        ]
        await call_control._save_legs(tenant_id, target.agent_id, legs)

    @staticmethod
    async def _apply_gain_matrix(
        telephony: BaseTelephonyClient,
        room_id: str,
        target: _ResolvedTarget,
        supervisor_call_id: str,
        mode: str,
    ) -> None:
        """Apply the who-hears-the-supervisor matrix for the given mode.

        The kernel defaults every leg to hear every other at gain 1.0, so the
        supervisor already hears both parties. We only pin how loudly the
        *supervisor* is mixed into the agent and customer legs:

          * whisper — agent hears supervisor (1.0); customer does not (0.0).
          * barge   — both agent and customer hear supervisor (1.0 / 1.0).
        """

        customer_gain = 1.0 if mode == "barge" else 0.0
        if target.agent_call_id:
            await telephony.room_set_mix_gain(
                room_id, listener_call_id=target.agent_call_id,
                speaker_call_id=supervisor_call_id, gain=1.0,
            )
        await telephony.room_set_mix_gain(
            room_id, listener_call_id=target.customer_call_id,
            speaker_call_id=supervisor_call_id, gain=customer_gain,
        )

    @staticmethod
    async def _notify_agent(
        principal: EffectivePrincipal,
        agent_id: int,
        event: str,
        payload: dict,
    ) -> None:
        """Push a supervisor-intervention event to the agent's workspace.

        Best-effort: a realtime-transport failure must never fail the
        intervention response (the media action already succeeded).
        """

        if not agent_id:
            return
        try:
            rt = get_realtime_transport()
            room = f"agent:{principal.tenant_id}:{agent_id}"
            await rt.emit(event, payload, room=room, namespace="/chat")
        except Exception:  # noqa: BLE001 — realtime push is best-effort
            logger.warning("supervisor event push failed event=%s agent=%s", event, agent_id, exc_info=True)

    @staticmethod
    async def handle_kernel_ice(
        redis: aioredis.Redis | None, call_id: str, candidate: dict
    ) -> None:
        """Route a kernel ICE candidate for a supervisor leg to its browser.

        Called from the telephony ``webrtc.ice`` event. ``call_id`` here is the
        kernel leg the candidate is for; only supervisor media legs are handled
        (a no-op otherwise, since agent legs are routed by the orchestrator). The
        candidate is emitted on a distinct ``cc.supervisor.ice`` event so a
        supervisor who is also an agent never cross-applies it to their agent leg.
        Best-effort: never raises into the event loop.
        """

        try:
            target = await intervention_state.get_supervisor_leg_target(redis, call_id)
            if target is None:
                return
            tenant_id, target_call_id = target
            holder = await intervention_state.get_call_holder(
                redis, tenant_id, target_call_id
            )
            if holder is None:
                return
            rt = get_realtime_transport()
            room = f"agent:{tenant_id}:{holder.supervisor_id}"
            await rt.emit(
                "cc.supervisor.ice",
                {"candidate": candidate},
                room=room,
                namespace="/chat",
            )
        except Exception:  # noqa: BLE001 — event-loop handler must never raise
            logger.warning("supervisor kernel ICE route failed leg=%s", call_id, exc_info=True)

    @staticmethod
    async def stop(
        telephony: BaseTelephonyClient,
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
    ) -> dict:
        """Exit monitoring: stop the supervisor's monitor leg and release the lock.

        Does not affect the agent/customer call. Best-effort ``call.stop`` on the
        listen leg; the lock is released and the exit recorded regardless.
        """

        holder = await intervention_state.get_call_holder(redis, principal.tenant_id, call_id)
        if holder is None or holder.supervisor_id != principal.user_id:
            # Nothing to exit for this supervisor — idempotent.
            return CallInterventionService._result(call_id, "listen", principal.user_id)
        # Best-effort teardown of the supervisor's monitoring. The agent/customer
        # call must survive: when a room is up we remove only the supervisor leg
        # (leaving customer + agent mixed) and drop the supervisor's media leg.
        # When there's no room, we stop the one-way listen injection. The call
        # may already be gone (customer hung up); either way we release the lock.
        try:
            if holder.room_id and holder.supervisor_call_id:
                await telephony.room_remove_leg(holder.room_id, holder.supervisor_call_id)
                await telephony.call_hangup(
                    holder.supervisor_call_id, reason="supervisor_monitor_exit"
                )
            else:
                target = await CallInterventionService._resolve(
                    principal, call_id, require_scope=False
                )
                await telephony.call_stop(target.customer_call_id, target="listen")
                if holder.supervisor_call_id:
                    await telephony.call_hangup(
                        holder.supervisor_call_id, reason="supervisor_monitor_exit"
                    )
        except Exception:  # noqa: BLE001 — teardown is best-effort
            logger.warning("stop monitor: leg teardown failed call=%s", call_id, exc_info=True)
        if holder.supervisor_call_id:
            await intervention_state.clear_supervisor_leg_index(
                redis, holder.supervisor_call_id
            )
        await CallInterventionService._release(redis, principal, call_id)
        await CallInterventionService._trail(
            principal, call_id, mode=holder.mode, event="ended"
        )
        return CallInterventionService._result(call_id, "listen", principal.user_id)

    # ───────────────────────── gate chain ─────────────────────────

    @staticmethod
    async def _gate(
        principal: EffectivePrincipal,
        redis: aioredis.Redis | None,
        call_id: str,
        mode: str,
    ) -> _ResolvedTarget:
        """Run permission + scope + phase + concurrency checks; return the target."""

        if not principal.has_permission(_MODE_PERMISSION[mode]):
            raise ForbiddenError("Permission denied")

        target = await CallInterventionService._resolve(principal, call_id, require_scope=True)

        if not _PHASE_MATRIX[target.phase].get(mode, False):
            raise ConflictError("Operation not available for the current call phase")

        # Only one supervisor per call at a time.
        holder = await intervention_state.get_call_holder(redis, principal.tenant_id, call_id)
        if holder is not None and holder.supervisor_id != principal.user_id:
            raise ConflictError("Another supervisor is monitoring this call")

        # Supervisor must be idle: not already monitoring a different call.
        busy_call = await intervention_state.supervisor_busy_on(
            redis, principal.tenant_id, principal.user_id
        )
        if busy_call is not None and busy_call != call_id:
            raise ConflictError("You are already monitoring another call")

        return target

    @staticmethod
    async def _resolve(
        principal: EffectivePrincipal,
        call_id: str,
        *,
        require_scope: bool,
    ) -> _ResolvedTarget:
        """Load the target call and validate visibility.

        Raises NotFoundError when the call is not live, ForbiddenError when it is
        out of the supervisor's data scope or is the supervisor's own call.
        """

        scope = DataScopeService.get_scope(principal, RESOURCE_CALL_RECORD)
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(CallRecord).where(
                        CallRecord.tenant_id == principal.tenant_id,
                        CallRecord.call_id == call_id,
                        CallRecord.lifecycle_status == LIVE_STATE,
                        CallRecord.ended_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("No active call")

            if require_scope:
                await CallInterventionService._check_scope(db, principal, row, scope)

            customer_call_id = row.root_call_id or row.call_id
            record_id = row.id
            target_call_id = row.call_id
            agent_id = row.last_serving_agent_id or 0
            session_agent_call_id = None
            if row.last_serving_agent_id:
                session = await AgentWebRTCSessionService.get_active(
                    db, principal.tenant_id, row.last_serving_agent_id
                )
                if session is not None:
                    session_agent_call_id = session.get("webrtc_call_id")

        # Shared in-call state is updated on every media reconnect and is more
        # authoritative than the DB mapping during a browser refresh.
        agent_call_id = session_agent_call_id
        if agent_id:
            from app.services.call_center.call_control_service import _legs

            try:
                legs = await _legs(principal.tenant_id, agent_id)
                agent_call_id = legs.agent_media_call_id or session_agent_call_id
            except Exception:  # noqa: BLE001 — DB session mapping remains a safe fallback
                logger.warning(
                    "live agent media state unreadable agent=%s/%s",
                    principal.tenant_id,
                    agent_id,
                    exc_info=True,
                )

        # Outside the DB session: the phase lives in Redis, not Postgres.
        phase = await CallInterventionService._derive_phase(principal.tenant_id, agent_id)
        return _ResolvedTarget(
            record_id=record_id,
            call_id=target_call_id,
            customer_call_id=customer_call_id,
            agent_id=agent_id,
            agent_call_id=agent_call_id,
            phase=phase,
        )

    @staticmethod
    async def _derive_phase(tenant_id: int, agent_id: int) -> str:
        """Classify what the agent's call is currently doing.

        A supervisor barging into a call whose agent is mid-consultation, or
        taking over one leg of a three-party call, would land in the wrong
        conversation. Both shapes are readable from the agent's in-call legs,
        which outlive a process restart. A failure here must not block
        monitoring, so it degrades to ``single`` — the same answer as before
        the phase was derived at all.
        """

        if not agent_id:
            return "single"
        # Imported lazily: the call-control module pulls in the whole
        # orchestrator, which imports reporting in turn.
        from app.services.call_center import consult_session
        from app.services.call_center.call_control_service import _legs

        try:
            legs = await _legs(tenant_id, agent_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "call phase unreadable, treating as single: tenant=%s agent=%s",
                tenant_id, agent_id, exc_info=True,
            )
            return "single"
        # A room id alone is not a business three-way call: supervisor
        # whisper/barge also uses a room. Only the durable conference
        # participant marker means the agent is serving two callers.
        if legs.conference_participant_call_id:
            return "three_way"
        if consult_session.is_consult_active(legs):
            return "consulting"
        return "single"

    @staticmethod
    async def _check_scope(
        db: AsyncSession,
        principal: EffectivePrincipal,
        row: CallRecord,
        scope: str,
    ) -> None:
        # A supervisor may never intervene on their own call.
        if row.last_serving_agent_id == principal.user_id:
            raise ForbiddenError("Cannot monitor your own call")
        if scope == SCOPE_SELF:
            # self scope sees only own calls, which are already excluded above.
            raise ForbiddenError("Permission denied")
        predicate = DataScopeService.build_call_record_predicate(
            principal,
            await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids),
        )
        if predicate is None:
            return  # SCOPE_ALL — unrestricted.
        visible = (
            await db.execute(
                select(CallRecord.id).where(CallRecord.id == row.id, predicate)
            )
        ).scalar_one_or_none()
        if visible is None:
            raise ForbiddenError("Permission denied")

    # ───────────────────────── helpers ─────────────────────────

    @staticmethod
    async def _claim(
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
        mode: str,
        *,
        supervisor_call_id: str | None = None,
        room_id: str | None = None,
    ) -> None:
        # Preserve an already-recorded media leg / room when the caller does not
        # re-supply them (e.g. a plain mode switch), so the room survives.
        existing = await intervention_state.get_call_holder(
            redis, principal.tenant_id, call_id
        )
        if existing is not None and existing.supervisor_id == principal.user_id:
            supervisor_call_id = supervisor_call_id or existing.supervisor_call_id
            room_id = room_id or existing.room_id
        name = await CallInterventionService._supervisor_name(principal.user_id)
        acquired = await intervention_state.acquire(
            redis,
            principal.tenant_id,
            call_id,
            MonitorHolder(
                supervisor_id=principal.user_id,
                name=name,
                mode=mode,
                supervisor_call_id=supervisor_call_id,
                room_id=room_id,
            ),
        )
        if not acquired:
            raise ConflictError("Another supervisor is monitoring this call")

    @staticmethod
    async def _release(
        redis: aioredis.Redis | None,
        principal: EffectivePrincipal,
        call_id: str,
    ) -> None:
        await intervention_state.release(redis, principal.tenant_id, call_id, principal.user_id)

    @staticmethod
    async def _close_cdr_after_teardown(
        principal: EffectivePrincipal, call_id: str, *, hangup_reason: str
    ) -> None:
        """Finalize the CDR after a supervisor-initiated teardown.

        ``room.close`` drops legs locally on the kernel and does NOT emit a
        ``call.hangup`` notification, so the orchestrator never gets a chance to
        run its own finalize step. Closing the record here (idempotent: the
        orchestrator's ``_on_hangup`` would just update the same row again if a
        notification does arrive) keeps the CDR from sticking in ``active``.
        """
        try:
            async with AsyncSessionLocal() as db:
                await CallRecordService.mark_completed(
                    db, principal.tenant_id, call_id, hangup_reason=hangup_reason
                )
        except Exception:  # noqa: BLE001 — CDR finalize is best-effort here
            logger.warning("close CDR after teardown failed call=%s", call_id, exc_info=True)

    @staticmethod
    async def _supervisor_name(supervisor_id: int) -> str:
        async with AsyncSessionLocal() as db:
            emp = await db.get(Employee, supervisor_id)
            if emp is None:
                return ""
            return emp.display_name or emp.name or emp.username or ""

    @staticmethod
    async def _trail(
        principal: EffectivePrincipal,
        call_id: str,
        *,
        mode: str,
        event: str,
        reason: str | None = None,
        note: str | None = None,
        detail: str | None = None,
    ) -> None:
        entry = {
            "supervisor_id": principal.user_id,
            "mode": mode,
            "event": event,
        }
        if reason is not None:
            entry["reason"] = reason
        if note:
            entry["note"] = note
        if detail:
            entry["detail"] = detail
        logger.info(
            "supervisor intervention: supervisor=%s call=%s mode=%s event=%s",
            principal.user_id, call_id, mode, event,
        )
        async with AsyncSessionLocal() as db:
            await intervention_state.append_trail_event(db, principal.tenant_id, call_id, entry)

    @staticmethod
    def _result(call_id: str, mode: str, supervisor_id: int) -> dict:
        return {"ok": True, "call_id": call_id, "mode": mode, "supervisor_id": supervisor_id}

    @staticmethod
    def validate_reason(reason: str, note: str | None) -> None:
        """Validate takeover / force-hangup reason payloads.

        When ``reason`` is ``other`` a note is mandatory (mirrors the UI rule).
        """

        if not reason:
            raise ValidationError("reason is required")
        if reason == "other" and not (note and note.strip()):
            raise ValidationError("note is required when reason is 'other'")
