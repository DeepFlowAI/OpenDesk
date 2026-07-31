"""Agent-initiated outbound call tracking: originator / ended / WebRTC-pair
state shared via Redis, leg and play-completion waiters, and the SIP-phone
two-stage outbound dial flow."""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio

    from app.libs.telephony import CallEvent
    from app.services.call_center.orchestrator import SipOutboundDialParams

logger = logging.getLogger(__name__)


class OutboundMixin:

    # ────────────────── Outbound (agent-initiated) tracking ──────────────────

    # SIP failure reasons that can arrive before register_outbound_call runs.
    # Inbound hangups use different reasons (remote_bye / media_eof / …).
    _OUTBOUND_EARLY_FAIL_REASONS = frozenset({
        "rejected",
        "busy",
        "no_answer",
        "originate_failed",
        "local_cancel",
        "alloc_failed",
        "invite_failed",
        "ringing_failed",
        "answer_failed",
        "bind_failed",
        "at_capacity",
    })

    @classmethod
    def _is_outbound_early_fail(cls, reason: object) -> bool:
        return isinstance(reason, str) and reason in cls._OUTBOUND_EARLY_FAIL_REASONS

    async def register_outbound_call(
        self,
        *,
        call_id: str,
        tenant_id: int,
        employee_id: int,
        outbound_did: str,
    ) -> None:
        """Remember which agent dialed which call_id so subsequent
        call.ringing / call.answered / call.hangup events can be routed
        back to that agent's browser. Cleared by _on_hangup.

        Written to Redis so a different node can resolve cancel / dial-webrtc
        / answered bridge when the dial hit another replica.
        """

        self._outbound_originators[call_id] = (tenant_id, employee_id, outbound_did)
        redis = _orch._get_redis_client()
        if redis is not None:
            try:
                await redis.set(
                    self._outbound_originator_key(call_id),
                    json.dumps(
                        {
                            "tenant_id": tenant_id,
                            "employee_id": employee_id,
                            "outbound_did": outbound_did,
                        }
                    ),
                    ex=self._OUTBOUND_STATE_TTL_SEC,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "outbound originator redis set failed call_id=%s",
                    call_id,
                    exc_info=True,
                )
        # Capture the dialing request's trace so outbound kernel events
        # (which arrive on fresh tasks) can re-bind the same trace_id.
        trace_id = _orch.get_trace_id()
        if trace_id and trace_id != "-":
            self._register_call_trace(call_id, trace_id, call_id)

    async def outbound_ended_reason(
        self, call_id: str
    ) -> tuple[str | None, int | None] | None:
        """If the outbound SIP leg has already ended, return its (reason,
        sip_status). Else None. Used by /dial-webrtc/offer to surface a
        clean 410 Gone when the race fires."""
        local = self._outbound_ended.get(call_id)
        if local is not None:
            return local
        redis = _orch._get_redis_client()
        if redis is None:
            return None
        try:
            raw = await redis.get(self._outbound_ended_key(call_id))
        except Exception:  # noqa: BLE001
            logger.warning(
                "outbound ended redis get failed call_id=%s", call_id, exc_info=True
            )
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            ended = (data.get("reason"), data.get("sip_status"))
            self._outbound_ended[call_id] = ended
            return ended
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    async def _mark_outbound_ended(
        self,
        call_id: str,
        reason: str | None,
        sip_status: int | None,
    ) -> None:
        self._outbound_ended[call_id] = (reason, sip_status)
        redis = _orch._get_redis_client()
        if redis is None:
            return
        try:
            await redis.set(
                self._outbound_ended_key(call_id),
                json.dumps({"reason": reason, "sip_status": sip_status}),
                ex=self._OUTBOUND_CLEANUP_DELAY_SEC,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "outbound ended redis set failed call_id=%s", call_id, exc_info=True
            )

    async def _delayed_outbound_cleanup(self, call_id: str) -> None:
        import asyncio as _aio
        await _aio.sleep(self._OUTBOUND_CLEANUP_DELAY_SEC)
        self._outbound_originators.pop(call_id, None)
        self._outbound_ended.pop(call_id, None)
        redis = _orch._get_redis_client()
        if redis is None:
            return
        try:
            await redis.delete(
                self._outbound_originator_key(call_id),
                self._outbound_ended_key(call_id),
                self._outbound_webrtc_key(call_id),
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "outbound redis cleanup failed call_id=%s", call_id, exc_info=True
            )

    async def _delayed_trace_cleanup(self, call_id: str) -> None:
        import asyncio as _aio
        entry = self._call_traces.get(call_id)
        await _aio.sleep(self._TRACE_CLEANUP_DELAY_SEC)
        self._call_traces.pop(call_id, None)
        # Also drop the root/media key that maps to the same trace, if any.
        if entry is not None:
            _trace_id, trace_call_id = entry
            if trace_call_id and trace_call_id != call_id:
                self._call_traces.pop(trace_call_id, None)

    async def cancel_outbound(self, call_id: str) -> None:
        """Best-effort hangup of an in-flight outbound SIP leg.

        Used by the agent's UI cancel button. The call may already be ended
        (carrier rejected before the user reacted, lease expired, etc.);
        we swallow downstream errors because the UX is "either way, the
        call is now over" — the cleanup (originator pop + WebRTC tear) is
        driven by the call.hangup event which will eventually arrive even
        if our explicit hangup races with the carrier rejection."""

        try:
            await self.telephony.call_hangup(call_id, reason="agent_cancel")
        except Exception:  # noqa: BLE001
            logger.warning("cancel_outbound: call_hangup raised", exc_info=True)

    async def pair_outbound_webrtc(
        self, *, outbound_call_id: str, webrtc_call_id: str
    ) -> None:
        """Bind the outbound SIP leg to the agent's media leg. The pairing is
        consumed in _on_outbound_answered to fire call.bridge.

        `webrtc_call_id` is the agent's leg to bridge the customer to — a
        browser WebRTC leg for Web-phone agents, or the physical SIP-extension
        leg for SIP-phone agents. The bridge logic is identical either way."""

        self._outbound_webrtc_pairs[outbound_call_id] = webrtc_call_id
        redis = _orch._get_redis_client()
        if redis is None:
            return
        try:
            await redis.set(
                self._outbound_webrtc_key(outbound_call_id),
                webrtc_call_id,
                ex=self._OUTBOUND_STATE_TTL_SEC,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "outbound webrtc pair redis set failed call_id=%s",
                outbound_call_id,
                exc_info=True,
            )

    def register_leg_wait(self, call_id: str) -> "_asyncio.Future[dict]":
        """Await a leg's first answered/hangup. Returns a Future resolved with
        {"answered": True} on call.answered or {"answered": False, "reason":...}
        on call.hangup. Used by the SIP-phone two-stage originate to know when
        the agent's physical phone goes off-hook before dialing the customer."""

        import asyncio
        fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._leg_waiters[call_id] = fut
        return fut

    def register_play_wait(self, call_id: str) -> "_asyncio.Future[dict]":
        """Await the next ``call.play_end`` on this call. Used so the assign path
        can let an in-flight prompt finish before bridging. Register it right
        after starting the prompt; if the prompt has already ended, the returned
        future simply resolves at that point instead of blocking."""

        import asyncio
        fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._play_waiters[call_id] = fut
        return fut

    def _resolve_play_wait(self, call_id: str, data: dict) -> None:
        fut = self._play_waiters.pop(call_id, None)
        if fut is not None and not fut.done():
            fut.set_result(data)

    def cancel_play_wait(self, call_id: str) -> None:
        self._play_waiters.pop(call_id, None)

    def set_pending_sip_originate(self, call_id: str, agent_leg_call_id: str) -> None:
        """Record that a SIP-phone handset is being rung for this caller, so a
        caller hangup can cancel the ring."""
        self._pending_sip_originate[call_id] = agent_leg_call_id

    def pop_pending_sip_originate(self, call_id: str) -> str | None:
        return self._pending_sip_originate.pop(call_id, None)

    def set_pending_queue_transfer(self, call_id: str, task: "asyncio.Task") -> None:
        """Record the background wait/ring task for a queue blind-transfer."""
        self._pending_queue_transfer[call_id] = task

    def pop_pending_queue_transfer(self, call_id: str) -> "asyncio.Task | None":
        """Remove and return the queue-transfer task for this customer call."""
        return self._pending_queue_transfer.pop(call_id, None)

    def start_sip_outbound_dial(
        self,
        *,
        extension_leg_call_id: str,
        params: "SipOutboundDialParams",
        timeout_sec: float,
    ) -> None:
        """Own the SIP-phone extension-answer wait entirely off the request path.

        The `/dial` request originates the agent's physical extension leg
        synchronously and returns immediately (status ``ringing_extension``); it
        never awaits the phone going off-hook. This method spawns a background
        task that waits on the extension leg's first answered/hangup event (via
        `register_leg_wait`) and:

          * on **answer** → originates the customer leg on a fresh short DB
            session, pairs it to the extension leg, and registers it as an
            outbound originator so the shared `_on_outbound_answered` path
            bridges the two the instant the customer picks up;
          * on **hangup / decline / timeout** → tears down the extension leg,
            releases the agent's reserved resource, and notifies the agent's
            browser — the customer is never dialed.

        No DB session is held across the wait; every persistence step opens its
        own short session. This is the event-driven replacement for the old
        in-request `asyncio.wait_for(...)` that held a pooled connection for up
        to the full ring timeout.
        """

        import asyncio

        waiter = self.register_leg_wait(extension_leg_call_id)
        asyncio.create_task(
            self._run_sip_outbound_dial(
                extension_leg_call_id=extension_leg_call_id,
                waiter=waiter,
                params=params,
                timeout_sec=timeout_sec,
            ),
            name=f"sip-outbound-dial:{extension_leg_call_id}",
        )

    async def _run_sip_outbound_dial(
        self,
        *,
        extension_leg_call_id: str,
        waiter: "_asyncio.Future[dict]",
        params: "SipOutboundDialParams",
        timeout_sec: float,
    ) -> None:
        import asyncio

        self.bind_call_trace(extension_leg_call_id)
        try:
            decision = await asyncio.wait_for(waiter, timeout=timeout_sec)
        except asyncio.TimeoutError:
            self.cancel_leg_wait(extension_leg_call_id)
            await self._abort_sip_outbound_dial(
                extension_leg_call_id, params, reason="no_answer",
            )
            return
        except Exception:  # noqa: BLE001
            logger.exception(
                "sip outbound dial wait failed ext_leg=%s", extension_leg_call_id,
            )
            await self._abort_sip_outbound_dial(
                extension_leg_call_id, params, reason="wait_error",
            )
            return

        if not decision.get("answered"):
            # Declined / hung up before answering — the extension leg is already
            # gone, so only release the reserved agent and notify the browser.
            await self._abort_sip_outbound_dial(
                extension_leg_call_id,
                params,
                reason=decision.get("reason") or "extension_declined",
                teardown_leg=False,
            )
            return

        await self._originate_sip_outbound_customer(extension_leg_call_id, params)

    async def _originate_sip_outbound_customer(
        self, extension_leg_call_id: str, params: "SipOutboundDialParams",
    ) -> None:
        """Extension answered → dial the customer and pair the legs.

        Runs off the request path on a fresh short session. On originate failure
        the extension leg is torn down, the agent resource released, and the
        browser told the outbound failed.
        """

        from app.libs.telephony.base import TelephonyRPCError

        try:
            result = await self.telephony.call_originate(
                uri=params.dialed,
                caller_id=params.caller_id,
                trunk_id=params.trunk_id,
            )
        except Exception as exc:  # noqa: BLE001
            reason = "originate_rejected"
            if isinstance(exc, TelephonyRPCError):
                logger.warning(
                    "sip outbound customer originate rejected code=%s trunk_id=%s",
                    exc.code, params.trunk_id,
                )
            else:
                logger.exception(
                    "sip outbound customer originate failed ext_leg=%s",
                    extension_leg_call_id,
                )
            await self._abort_sip_outbound_dial(
                extension_leg_call_id, params, reason=reason,
            )
            return

        call_id = result.get("call_id")
        if not call_id:
            logger.warning(
                "sip outbound customer originate returned no call_id ext_leg=%s",
                extension_leg_call_id,
            )
            await self._abort_sip_outbound_dial(
                extension_leg_call_id, params, reason="no_call_id",
            )
            return

        redis = _orch._get_redis_client()
        if redis is not None:
            try:
                await _orch.CcAgentResourceService.bind_outbound_call(
                    redis,
                    params.tenant_pk,
                    params.employee_id,
                    reservation_id=params.reservation_id,
                    call_id=call_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "sip outbound bind_outbound_call failed call_id=%s", call_id,
                )

        # Register the customer leg so its ringing/answered/hangup events route
        # back to the agent, and pair it to the already-answered extension leg so
        # _on_outbound_answered bridges them when the customer picks up.
        await self.register_outbound_call(
            call_id=call_id,
            tenant_id=params.tenant_pk,
            employee_id=params.employee_id,
            outbound_did=params.caller_id,
        )
        await self.pair_outbound_webrtc(
            outbound_call_id=call_id, webrtc_call_id=extension_leg_call_id,
        )

        try:
            async with _orch.AsyncSessionLocal() as db:
                await _orch.CcAgentStatusService.sync_pg_status(
                    db, params.tenant_pk, params.employee_id, "busy", None,
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "sip outbound status busy sync failed call_id=%s", call_id,
            )

        try:
            async with _orch.AsyncSessionLocal() as db:
                await _orch.CallRecordService.create_for_outbound(
                    db, params.tenant_pk,
                    call_id=call_id,
                    conversation_id=result.get("conversation_id"),
                    root_call_id=result.get("root_call_id") or call_id,
                    from_number=params.caller_id,
                    to_number=params.destination,
                    agent_id=params.employee_id,
                    device_type=params.device_type,
                    device_identifier=params.device_identifier,
                )
                await db.commit()
        except Exception:  # noqa: BLE001
            logger.exception(
                "sip outbound CDR create_for_outbound failed call_id=%s", call_id,
            )

        await self.notify_agent_outbound_event(
            tenant_id=params.tenant_pk, employee_id=params.employee_id,
            method="cc.outbound_customer_dialing",
            payload={"call_id": call_id, "extension_call_id": extension_leg_call_id},
        )
        logger.info(
            "sip outbound: extension %s answered → customer leg %s (dialed=%s)",
            extension_leg_call_id, call_id, params.dialed,
        )

    async def _abort_sip_outbound_dial(
        self,
        extension_leg_call_id: str,
        params: "SipOutboundDialParams",
        *,
        reason: str,
        teardown_leg: bool = True,
    ) -> None:
        """Failure path for a SIP-phone outbound dial before the customer leg
        exists: tear down the extension leg (unless already gone), release the
        agent's reserved resource, and notify the browser. Holds no DB session
        across the RPC/Redis/Socket.IO calls."""

        if teardown_leg:
            try:
                await self.telephony.call_hangup(
                    extension_leg_call_id, reason="outbound_aborted",
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "sip outbound abort: extension leg teardown failed ext_leg=%s",
                    extension_leg_call_id, exc_info=True,
                )

        redis = _orch._get_redis_client()
        if redis is not None:
            try:
                released = await _orch.CcAgentResourceService.release(
                    redis,
                    params.tenant_pk,
                    params.employee_id,
                    reason=reason,
                    expected_call_id=params.reservation_id,
                )
                async with _orch.AsyncSessionLocal() as db:
                    await _orch.CcAgentStatusService.sync_pg_status(
                        db,
                        params.tenant_pk,
                        params.employee_id,
                        released["visible_status"],
                        None,
                    )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "sip outbound abort: resource release failed agent=%s/%s",
                    params.tenant_pk, params.employee_id,
                )

        await self.notify_agent_outbound_event(
            tenant_id=params.tenant_pk, employee_id=params.employee_id,
            method="cc.outbound_hangup",
            payload={
                "call_id": extension_leg_call_id,
                "reason": reason,
                "stage": "extension",
            },
        )
        logger.info(
            "sip outbound aborted ext_leg=%s reason=%s (customer not dialed)",
            extension_leg_call_id, reason,
        )

    def cancel_leg_wait(self, call_id: str) -> None:
        self._leg_waiters.pop(call_id, None)

    def _resolve_leg_wait(self, call_id: str, result: dict) -> None:
        fut = self._leg_waiters.pop(call_id, None)
        if fut is not None and not fut.done():
            fut.set_result(result)

    async def _pop_outbound_webrtc(self, outbound_call_id: str) -> str | None:
        local = self._outbound_webrtc_pairs.pop(outbound_call_id, None)
        redis = _orch._get_redis_client()
        if redis is None:
            return local
        try:
            raw = await redis.getdel(self._outbound_webrtc_key(outbound_call_id))
        except Exception:  # noqa: BLE001
            # Older Redis without GETDEL — fall back to GET+DELETE.
            try:
                key = self._outbound_webrtc_key(outbound_call_id)
                raw = await redis.get(key)
                if raw is not None:
                    await redis.delete(key)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "outbound webrtc pair redis pop failed call_id=%s",
                    outbound_call_id,
                    exc_info=True,
                )
                return local
        if raw is None:
            return local
        value = raw if isinstance(raw, str) else raw.decode()
        if local is None:
            return value
        return local

    async def _pop_outbound_originator(
        self, call_id: str
    ) -> tuple[int, int, str] | None:
        info = await self._peek_outbound_originator(call_id)
        self._outbound_originators.pop(call_id, None)
        redis = _orch._get_redis_client()
        if redis is not None:
            try:
                await redis.delete(self._outbound_originator_key(call_id))
            except Exception:  # noqa: BLE001
                logger.warning(
                    "outbound originator redis delete failed call_id=%s",
                    call_id,
                    exc_info=True,
                )
        return info

    async def _peek_outbound_originator(
        self, call_id: str
    ) -> tuple[int, int, str] | None:
        local = self._outbound_originators.get(call_id)
        if local is not None:
            return local
        redis = _orch._get_redis_client()
        if redis is None:
            return None
        try:
            raw = await redis.get(self._outbound_originator_key(call_id))
        except Exception:  # noqa: BLE001
            logger.warning(
                "outbound originator redis get failed call_id=%s",
                call_id,
                exc_info=True,
            )
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            info = (
                int(data["tenant_id"]),
                int(data["employee_id"]),
                str(data["outbound_did"]),
            )
            self._outbound_originators[call_id] = info
            return info
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    async def _on_outbound_ringing(self, event: CallEvent) -> None:
        """call.ringing (180) or call.early_media (183) for an outbound call."""

        call_id = event.data.get("call_id") or ""
        info = await self._peek_outbound_originator(call_id)
        if info is None:
            return  # not an agent-initiated outbound, ignore
        self.bind_call_trace(call_id)
        tenant_id, employee_id, _did = info
        await self.notify_agent_outbound_event(
            tenant_id=tenant_id, employee_id=employee_id,
            method="cc.outbound_ringing",
            payload={"call_id": call_id, "event": event.method},
        )

    async def _on_outbound_answered(self, event: CallEvent) -> None:
        call_id = event.data.get("call_id") or ""
        # SIP-phone two-stage: the agent's extension leg answered. Wake the
        # dialer waiting on it so it proceeds to originate the customer.
        self._resolve_leg_wait(call_id, {"answered": True})
        info = await self._peek_outbound_originator(call_id)
        if info is None:
            return
        self.bind_call_trace(call_id)
        tenant_id, employee_id, _did = info

        redis = _orch._get_redis_client()
        if redis is not None:
            try:
                await _orch.CcAgentResourceService.mark_in_call(
                    redis,
                    tenant_id,
                    employee_id,
                    call_id=call_id,
                    direction="outbound",
                )
            except Exception:  # noqa: BLE001
                logger.exception("outbound resource mark_in_call failed call_id=%s", call_id)

        # CDR transition: ringing → in_progress with answered_at + agent_id.
        # Best-effort; failures here MUST NOT block the bridge that follows.
        try:
            async with _orch.AsyncSessionLocal() as db:
                await _orch.CallRecordService.mark_answered(
                    db, tenant_id, call_id, agent_id=employee_id,
                )
                await db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("CDR mark_answered (outbound) failed call_id=%s", call_id)

        # Bridge to the agent's pre-built WebRTC leg so audio flows instantly.
        # No pairing means the agent never POSTed /dial-webrtc/offer — call
        # still goes through SIP but agent has no media path. We surface the
        # answered event regardless so the UI advances.
        webrtc_call_id = await self._pop_outbound_webrtc(call_id)
        if webrtc_call_id:
            # Read the tenant's live-transcription toggle on a short session that
            # closes before the bridge RPC (no DB session held across I/O).
            from app.services.system_settings_service import SystemSettingsService

            transcribe = await SystemSettingsService.is_bridge_asr_enabled_managed(tenant_id)
            # An agent who dialled on their handset has been hearing ringback on
            # this leg. It loops until told otherwise, so it would play over the
            # conversation. No-op for the other dial paths, which play nothing.
            try:
                await self.telephony.call_stop(webrtc_call_id, target="play")
            except Exception:  # noqa: BLE001
                logger.warning(
                    "outbound: stopping ringback failed leg=%s", webrtc_call_id,
                    exc_info=True,
                )
            try:
                await self.telephony.call_bridge(call_id, webrtc_call_id, transcribe=transcribe)
                logger.info(
                    "outbound auto-bridge: sip=%s webrtc=%s", call_id, webrtc_call_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "outbound auto-bridge failed sip=%s webrtc=%s",
                    call_id, webrtc_call_id,
                )
        else:
            logger.warning(
                "outbound answered without WebRTC pairing (no audio path): %s",
                call_id,
            )
        await self.notify_agent_outbound_event(
            tenant_id=tenant_id, employee_id=employee_id,
            method="cc.outbound_answered",
            payload={"call_id": call_id},
        )


# Imported after the mixin class so this module can be imported directly
# without a circular-import error (orchestrator imports the mixins).
from app.services.call_center import orchestrator as _orch  # noqa: E402
