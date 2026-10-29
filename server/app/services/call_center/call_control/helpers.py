"""Shared helpers: target originate/wait, failure restore paths and consult cleanup."""
from __future__ import annotations

import asyncio
import json
import logging

from app.constants.call_center import (
    INCALL_LEGS_KEY_PREFIX,
    ConsultState,
)
from app.core.exceptions import ValidationError
from app.libs.telephony.base import (
    BaseTelephonyClient,
    TelephonyRPCError,
)
from app.services.call_center import consult_session

logger = logging.getLogger(__name__)


class HelpersMixin:
    # ───────────────────────── helpers ─────────────────────────

    @staticmethod
    async def _room_remove(
        telephony: BaseTelephonyClient, legs: _ccs.InCallLegs, call_id: str
    ) -> None:
        try:
            await telephony.room_remove_leg(legs.room_id, call_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "room_remove_leg failed room=%s leg=%s",
                legs.room_id, call_id, exc_info=True,
            )
        if call_id in legs.room_legs:
            legs.room_legs.remove(call_id)

    @staticmethod
    async def _originate_target(
        telephony: BaseTelephonyClient, originate_kwargs: dict
    ) -> str:
        """Originate a transfer/consult/conference target leg.

        Maps typed kernel rejections to ValidationError (→ 400) so the original
        call is never lost on a bad target. Returns the new leg's call_id.
        """

        try:
            result = await telephony.call_originate(**originate_kwargs)
        except TelephonyRPCError as exc:
            logger.warning("target originate rejected code=%s", exc.code)
            raise ValidationError(str(exc)) from exc
        target_call_id = result.get("call_id")
        if not target_call_id:
            raise ValidationError("语音内核未返回目标呼叫标识")
        return target_call_id

    @staticmethod
    def _spawn_target_wait(
        telephony: BaseTelephonyClient,
        *,
        target_call_id: str,
        on_answer,
        on_fail,
    ) -> None:
        """Wait off the request path for `target_call_id` to answer.

        Reuses the orchestrator's leg-wait (fed by call.answered / call.hangup).
        Calls `on_answer()` on pickup, or `on_fail(reason)` on decline / no-answer
        / timeout. Every persistence step inside the callbacks opens its own
        short session — this coroutine holds none.
        """

        from app.services.call_center.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        waiter = orchestrator.register_leg_wait(target_call_id)

        async def _runner() -> None:
            try:
                decision = await asyncio.wait_for(
                    waiter, timeout=_ccs._TARGET_ANSWER_TIMEOUT_SEC
                )
            except asyncio.TimeoutError:
                orchestrator.cancel_leg_wait(target_call_id)
                await on_fail("no_answer")
                return
            except Exception:  # noqa: BLE001
                logger.exception("target wait failed leg=%s", target_call_id)
                await on_fail("wait_error")
                return
            if decision.get("answered"):
                await on_answer()
            else:
                await on_fail(decision.get("reason") or "declined")

        asyncio.create_task(_runner(), name=f"call-target-wait:{target_call_id}")

    @staticmethod
    async def _restore_after_target_failure(
        telephony: BaseTelephonyClient,
        call: _ccs.CurrentCall,
        target_call_id: str,
        reason: str,
    ) -> None:
        """Blind-transfer target never answered — keep the customer with the agent."""

        await _ccs.CallControlService._stop_tone(telephony, call.customer_call_id)
        # The target leg is usually already gone on decline/timeout; best-effort.
        # Empty for an internal (browser-ring) transfer that failed before any
        # leg existed — the internal path already released the target.
        if target_call_id:
            try:
                await telephony.call_hangup(target_call_id, reason="transfer_aborted")
            except Exception:  # noqa: BLE001
                pass
        logger.info(
            "transfer aborted customer=%s target=%s reason=%s (customer kept)",
            call.customer_call_id, target_call_id, reason,
        )

    @staticmethod
    async def _restore_after_consult_failure(
        telephony: BaseTelephonyClient,
        tenant_id: int,
        employee_id: int,
        call: _ccs.CurrentCall,
        target_call_id: str,
        reason: str,
    ) -> None:
        """Consult target never answered — resume the held customer.

        `target_call_id` may be empty for an internal (browser-ring) consult that
        failed before any leg existed — the internal path already released the
        target's reservation, so there is nothing to hang up.
        """

        if target_call_id:
            try:
                await telephony.call_hangup(target_call_id, reason="consult_aborted")
            except Exception:  # noqa: BLE001
                pass
        await _ccs.CallControlService._stop_tone(telephony, call.customer_call_id)
        try:
            if call.webrtc_call_id:
                await telephony.call_bridge(
                    call.customer_call_id,
                    call.webrtc_call_id,
                    user_call_id=call.customer_call_id,
                    keepalive_on_peer_hangup=True,
                )
        except Exception:  # noqa: BLE001
            logger.warning("consult abort re-bridge failed", exc_info=True)
        await consult_session.clear(
            tenant_id=tenant_id,
            host_employee_id=employee_id,
            reason=f"consult_aborted:{reason}",
            consult_call_id=target_call_id or None,
        )
        logger.info(
            "consult aborted customer=%s consult_leg=%s reason=%s (customer resumed)",
            call.customer_call_id, target_call_id, reason,
        )

    @staticmethod
    async def _locate_consult_host_by_leg(
        *,
        consult_call_id: str | None = None,
        agent_media_call_id: str | None = None,
    ) -> tuple[int, int, _ccs.InCallLegs] | None:
        """Find (tenant_id, host_employee_id, legs) by consult or host media leg."""

        for (tid, eid), legs in list(_ccs._in_call_state.items()):
            if consult_call_id and legs.consult_call_id == consult_call_id:
                return tid, eid, legs
            if agent_media_call_id and legs.agent_media_call_id == agent_media_call_id:
                if legs.consult_call_id:
                    return tid, eid, legs

        from app.services.call_center.orchestrator import _get_redis_client

        r = _get_redis_client()
        if r is None:
            return None
        try:
            keys = [k async for k in r.scan_iter(match=f"{INCALL_LEGS_KEY_PREFIX}:*")]
        except Exception:  # noqa: BLE001
            logger.warning("consult host locate: redis scan failed", exc_info=True)
            return None
        for key in keys:
            try:
                raw = await r.get(key)
            except Exception:  # noqa: BLE001
                continue
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                continue
            matched = bool(
                consult_call_id and data.get("consult_call_id") == consult_call_id
            ) or bool(
                agent_media_call_id
                and data.get("agent_media_call_id") == agent_media_call_id
                and data.get("consult_call_id")
            )
            if not matched:
                continue
            parts = str(key).split(":")
            if len(parts) < 5:
                continue
            try:
                tenant_id = int(parts[-2])
                employee_id = int(parts[-1])
            except (TypeError, ValueError):
                continue
            legs = _ccs.InCallLegs.from_dict(data)
            _ccs._in_call_state[(tenant_id, employee_id)] = legs
            return tenant_id, employee_id, legs
        return None

    @staticmethod
    async def on_consult_target_departed(
        call_id: str, reason: str | None = None
    ) -> bool:
        """Handle hangup of a consult target leg (B).

        Intentional hangup ends the consult immediately. Media loss (refresh /
        media_eof) gives B a short grace window to media-reconnect before the
        host is resumed with the customer.
        """

        if reason == _ccs._CONSULT_TARGET_REPLACED_REASON:
            return False

        located = await _ccs.CallControlService._locate_consult_host_by_leg(
            consult_call_id=call_id
        )
        if located is None:
            return False
        tenant_id, employee_id, legs = located
        target_emp = legs.consult_target_employee_id

        intentional = (reason or "") in _ccs._CONSULT_TARGET_INTENTIONAL_HANGUP
        if not intentional and target_emp is not None:
            # Page refresh: keep consult state, ask B to rebuild media.
            await _ccs.CallControlService._notify_media_reconnect_required(
                tenant_id=tenant_id,
                employee_id=target_emp,
                customer_call_id=call_id,
                reason="consult_target_media_lost",
            )
            grace_key = f"{tenant_id}:{employee_id}:{call_id}"
            _ccs.CallControlService._cancel_consult_target_grace(call_id)

            async def _grace_end() -> None:
                try:
                    await asyncio.sleep(_ccs._CONSULT_TARGET_RECONNECT_GRACE_SEC)
                except asyncio.CancelledError:
                    return
                current = await _ccs._legs(tenant_id, employee_id)
                if current.consult_call_id != call_id:
                    return
                await _ccs.CallControlService._finalize_consult_target_departed(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    dead_consult_leg=call_id,
                    reason=reason or "consult_target_media_timeout",
                )

            _ccs._consult_target_grace_tasks[grace_key] = asyncio.create_task(
                _grace_end(), name=f"consult-target-grace:{grace_key}"
            )
            logger.info(
                "consult target media lost: host=%s/%s leg=%s grace=%.0fs "
                "(waiting for target reconnect)",
                tenant_id, employee_id, call_id, _ccs._CONSULT_TARGET_RECONNECT_GRACE_SEC,
            )
            return True

        return await _ccs.CallControlService._finalize_consult_target_departed(
            tenant_id=tenant_id,
            employee_id=employee_id,
            dead_consult_leg=call_id,
            reason=reason or "consult_target_hangup",
        )

    @staticmethod
    async def _finalize_consult_target_departed(
        *,
        tenant_id: int,
        employee_id: int,
        dead_consult_leg: str,
        reason: str,
    ) -> bool:
        """End consult after B left (or grace expired) and resume host↔customer."""

        from app.libs.telephony import get_telephony_client

        _ccs.CallControlService._cancel_consult_target_grace(dead_consult_leg)
        telephony = get_telephony_client()
        try:
            call = await _ccs.CallControlService._resolve_current_call(
                tenant_id, employee_id
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "consult target departed but no current call agent=%s/%s",
                tenant_id, employee_id, exc_info=True,
            )
            legs = await _ccs._legs(tenant_id, employee_id)
            target_emp = legs.consult_target_employee_id
            await consult_session.clear(
                tenant_id=tenant_id,
                host_employee_id=employee_id,
                reason=reason,
                consult_call_id=dead_consult_leg,
            )
            if target_emp is not None:
                await _ccs.CallControlService._release_internal_target(
                    tenant_id, target_emp, reason=reason,
                )
                await _ccs.CallControlService._notify_browser_call_ended(
                    tenant_id, target_emp, dead_consult_leg, reason="consult_ended",
                )
            return True

        legs = await _ccs._legs(tenant_id, employee_id)
        if legs.consult_call_id and legs.consult_call_id != dead_consult_leg:
            # Target already reconnected onto a new leg.
            return False
        target_emp = legs.consult_target_employee_id
        await consult_session.clear(
            tenant_id=tenant_id,
            host_employee_id=employee_id,
            reason=reason,
            consult_call_id=dead_consult_leg,
        )
        if target_emp is not None:
            await _ccs.CallControlService._release_internal_target(
                tenant_id, target_emp, reason=reason,
            )
            await _ccs.CallControlService._notify_browser_call_ended(
                tenant_id, target_emp, dead_consult_leg, reason="consult_ended",
            )

        resumed = False
        host_media = call.webrtc_call_id
        if host_media:
            # Drop A↔B before customer↔A. With keepalive consult bridges, B's
            # hangup races FlowKit's peer-gone cleanup; bridging while A is still
            # paired fails with "call already bridged" and leaves the customer
            # on hold (silence on the mobile).
            try:
                await telephony.call_unbridge(host_media, dead_consult_leg)
            except Exception:  # noqa: BLE001
                pass
            await _ccs.CallControlService._stop_tone(telephony, call.customer_call_id)
            for attempt in range(2):
                try:
                    await telephony.call_bridge(
                        call.customer_call_id,
                        host_media,
                        user_call_id=call.customer_call_id,
                        keepalive_on_peer_hangup=True,
                    )
                    resumed = True
                    break
                except Exception:  # noqa: BLE001
                    if attempt == 0:
                        await asyncio.sleep(0.35)
                        continue
                    logger.warning(
                        "consult target hangup: re-bridge customer failed "
                        "agent=%s customer=%s",
                        employee_id, call.customer_call_id, exc_info=True,
                    )
            if not resumed:
                try:
                    await _ccs.CallControlService._play_scene_tone(
                        telephony,
                        tenant_id=tenant_id,
                        customer_call_id=call.customer_call_id,
                        scene="consult",
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "consult target hangup: hold tone restore failed",
                        exc_info=True,
                    )
                # SIP desk-phone media lives on the handset — never ask the
                # browser to media-reconnect (that steals the customer bridge).
                if not await _ccs.CallControlService._agent_uses_sip_phone(
                    tenant_id, employee_id
                ):
                    await _ccs.CallControlService._notify_media_reconnect_required(
                        tenant_id=tenant_id,
                        employee_id=employee_id,
                        customer_call_id=call.customer_call_id,
                        reason="consult_rebridge_failed",
                    )
        elif not await _ccs.CallControlService._agent_uses_sip_phone(
            tenant_id, employee_id
        ):
            await _ccs.CallControlService._notify_media_reconnect_required(
                tenant_id=tenant_id,
                employee_id=employee_id,
                customer_call_id=call.customer_call_id,
                reason="agent_media_missing",
            )

        await _ccs.CallControlService._notify_control_result(
            tenant_id=tenant_id,
            initiator_employee_id=employee_id,
            method="cc.consult_result",
            payload={
                "ok": True,
                "kind": "consult",
                "ended": True,
                "resumed": resumed,
                "reason": (
                    "对方已结束咨询，已恢复与客户通话"
                    if resumed
                    else "对方已结束咨询，正在恢复与客户通话"
                ),
            },
        )
        logger.info(
            "consult target departed: agent=%s consult_leg=%s resumed=%s reason=%s",
            employee_id, dead_consult_leg, resumed, reason,
        )
        return True

    @staticmethod
    async def on_consult_host_media_departed(
        call_id: str, reason: str | None = None
    ) -> bool:
        """Host (A) media leg hung up while a consult was active — drop B + clean up.

        SIP handset hangup during consult never hits B's browser unless we push
        ``cc.call_hangup`` and release B's resource here.
        """

        if reason == _ccs._CONSULT_TARGET_REPLACED_REASON:
            return False
        located = await _ccs.CallControlService._locate_consult_host_by_leg(
            agent_media_call_id=call_id
        )
        if located is None:
            return False
        tenant_id, employee_id, legs = located
        if legs.agent_media_call_id != call_id or not legs.consult_call_id:
            return False
        await _ccs.CallControlService.cleanup_consult_for_host(
            tenant_id,
            employee_id,
            reason=reason or "host_media_hangup",
            hangup_customer=True,
        )
        logger.info(
            "consult host media departed: host=%s/%s media=%s reason=%s",
            tenant_id, employee_id, call_id, reason,
        )
        return True

    @staticmethod
    async def cleanup_consult_for_host(
        tenant_id: int,
        employee_id: int,
        *,
        reason: str,
        hangup_customer: bool = False,
    ) -> bool:
        """Tear down an active consult for the host and notify the target (B)."""

        from app.libs.telephony import get_telephony_client

        legs = await _ccs._legs(tenant_id, employee_id)
        consult_call_id = legs.consult_call_id
        if not consult_session.is_consult_active(legs):
            return False
        target_emp = legs.consult_target_employee_id
        consult_offer_id = legs.consult_offer_id
        was_ringing = consult_session.derive_state(legs) is ConsultState.RINGING
        host_media = legs.agent_media_call_id
        _ccs.CallControlService._cancel_consult_target_grace(consult_call_id)
        await consult_session.clear(
            tenant_id=tenant_id,
            host_employee_id=employee_id,
            reason=reason,
            consult_call_id=consult_call_id,
        )

        # A still-ringing browser consult has a pending offer wait — cancel it
        # so a late accept can't bridge onto the torn-down call.
        if was_ringing and consult_offer_id:
            await _ccs.CallControlService._cancel_pending_consult_offer(
                consult_offer_id, reason,
            )

        telephony = get_telephony_client()
        if host_media and consult_call_id:
            try:
                await telephony.call_unbridge(host_media, consult_call_id)
            except Exception:  # noqa: BLE001
                pass
        if consult_call_id:
            try:
                await telephony.call_hangup(consult_call_id, reason=reason)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "cleanup consult: hangup target failed host=%s consult=%s",
                    employee_id, consult_call_id, exc_info=True,
                )
        if target_emp is not None:
            await _ccs.CallControlService._release_internal_target(
                tenant_id, target_emp, reason=reason,
            )
            # During RINGING there is no media leg yet — the target browser is
            # ringing on the synthetic internal offer call_id.
            notify_call_id = consult_call_id or (
                f"internal:{consult_offer_id}" if consult_offer_id else None
            )
            if notify_call_id:
                await _ccs.CallControlService._notify_browser_call_ended(
                    tenant_id, target_emp, notify_call_id, reason="consult_ended",
                )

        if hangup_customer:
            try:
                call = await _ccs.CallControlService._resolve_current_call(
                    tenant_id, employee_id
                )
            except Exception:  # noqa: BLE001
                call = None
            if call is not None:
                try:
                    await _ccs.CallControlService._stop_tone(
                        telephony, call.customer_call_id
                    )
                except Exception:  # noqa: BLE001
                    pass
                try:
                    await telephony.call_hangup(
                        call.customer_call_id, reason=reason or "host_hangup",
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "cleanup consult: customer hangup failed host=%s",
                        employee_id, exc_info=True,
                    )
        await _ccs._clear_legs(tenant_id, employee_id)
        return True

    @staticmethod
    async def _release_internal_target(
        tenant_id: int, target_employee_id: int, *, reason: str
    ) -> None:
        """Free a colleague we occupied via the internal browser-ring path.

        The consult / transfer machinery reserved and marked that colleague
        ``in_call`` on their own call-center resource to ring their browser. When
        the consult ends (or handover completes with their leg gone) we must
        unconditionally free it — the occupation is keyed on the internal leg, so
        a normal ``release`` would refuse an ``in_call`` state and the colleague
        would stay stuck busy. Runs on Redis only; holds no DB session.
        """

        from app.services.call_center.orchestrator import _get_redis_client

        from app.services.cc_agent_status_service import CcAgentStatusService

        r = _get_redis_client()
        if r is None:
            logger.warning(
                "internal target release skipped (no redis) target=%s/%s",
                tenant_id, target_employee_id,
            )
            return
        try:
            released = await _ccs.CcAgentResourceService.force_release(
                r, tenant_id, target_employee_id, reason=reason,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "internal target release failed target=%s/%s reason=%s",
                tenant_id, target_employee_id, reason, exc_info=True,
            )
            return
        # Mirror Redis restore into PG — accept_offer set busy without a CDR
        # hangup path to flip it back.
        restore = (released or {}).get("visible_status") or "ready"
        if restore == "busy":
            restore = "ready"
        try:
            async with _ccs.AsyncSessionLocal() as db:
                await CcAgentStatusService.sync_pg_status(
                    db, tenant_id, target_employee_id, restore, None,
                )
                await _ccs.AgentWebRTCSessionService.set_busy(
                    db, tenant_id, target_employee_id, busy=False,
                )
        except Exception:  # noqa: BLE001
            logger.warning(
                "internal target PG status restore failed target=%s/%s",
                tenant_id, target_employee_id, exc_info=True,
            )

    @staticmethod
    async def _rekey_internal_target_to_customer(
        tenant_id: int, target_employee_id: int, customer_call_id: str
    ) -> None:
        """Re-key a handed-over colleague's resource onto the customer call.

        After a blind transfer to an internal browser-ring colleague, that
        colleague becomes the customer's owning agent. Their resource was keyed
        on the internal consult leg; re-point it at the customer call so the
        customer's own ``call.hangup`` finalizes them cleanly instead of raising
        ``Call resource belongs to another call``. Redis only; no DB session.
        """

        from app.services.call_center.orchestrator import _get_redis_client

        r = _get_redis_client()
        if r is None:
            logger.warning(
                "internal target re-key skipped (no redis) target=%s/%s",
                tenant_id, target_employee_id,
            )
            return
        try:
            await _ccs.CcAgentResourceService.rekey_current_call(
                r,
                tenant_id,
                target_employee_id,
                call_id=customer_call_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "internal target re-key failed target=%s/%s call=%s",
                tenant_id, target_employee_id, customer_call_id, exc_info=True,
            )

    @staticmethod
    async def _mark_sip_transfer_target_in_call(
        tenant_id: int, target_employee_id: int, customer_call_id: str
    ) -> None:
        """Mark a SIP desk-phone transfer target in-call on the customer call.

        Blind transfer to an extension never reserves the colleague via the
        browser-ring path, so Redis would otherwise leave them idle and the
        queue could offer another call. Best-effort: Redis failures must not
        undo a completed handover, and a reservation for a different call must
        not be overwritten.
        """

        import uuid

        from app.services.call_center.orchestrator import _get_redis_client

        r = _get_redis_client()
        if r is None:
            logger.warning(
                "sip transfer mark_in_call skipped (no redis) target=%s/%s",
                tenant_id, target_employee_id,
            )
            return
        try:
            snap = await _ccs.CcAgentResourceService.get_snapshot(
                r, tenant_id, target_employee_id
            )
            state = (snap or {}).get("resource_state") or "idle"
            current_call = (snap or {}).get("current_call_id") or ""

            if state in {"reserved", "ringing", "in_call"}:
                if current_call and current_call != customer_call_id:
                    logger.warning(
                        "sip transfer mark_in_call skipped: target=%s/%s "
                        "already on call=%s (wanted %s)",
                        tenant_id, target_employee_id, current_call,
                        customer_call_id,
                    )
                    return
                offer_id = (snap or {}).get("offer_id") or None
                await _ccs.CcAgentResourceService.mark_in_call(
                    r,
                    tenant_id,
                    target_employee_id,
                    call_id=customer_call_id,
                    direction="inbound",
                    offer_id=offer_id,
                )
                return

            offer_id = uuid.uuid4().hex
            reserved = await _ccs.CcAgentResourceService.reserve_inbound(
                r,
                tenant_id,
                target_employee_id,
                call_id=customer_call_id,
                offer_id=offer_id,
                queue_id=None,
            )
            if reserved is None:
                logger.warning(
                    "sip transfer mark_in_call skipped: could not reserve "
                    "target=%s/%s call=%s",
                    tenant_id, target_employee_id, customer_call_id,
                )
                return
            await _ccs.CcAgentResourceService.mark_in_call(
                r,
                tenant_id,
                target_employee_id,
                call_id=customer_call_id,
                direction="inbound",
                offer_id=offer_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "sip transfer mark_in_call failed target=%s/%s call=%s",
                tenant_id, target_employee_id, customer_call_id, exc_info=True,
            )

    @staticmethod
    async def _finalize_initiator_after_transfer(
        *,
        tenant_id: int,
        employee_id: int,
        call: _ccs.CurrentCall,
        new_agent_id: int | None,
        clear_bridged_agent: bool = False,
    ) -> None:
        """After a successful handover: reassign CDR, free initiator UI/resource.

        The SIP/extension transfer path previously only bridged the customer and
        hung up the agent media leg — without telling the browser or moving the
        initiator to after-call-work — so A stayed "通话中" while B already had
        the customer. Shared by both the SIP and internal-WebRTC transfer paths.

        ``clear_bridged_agent`` is for external blind transfer only: there is no
        receiving agent, so ``sys._bridged_agent_id`` must be cleared. Queue
        transfer also passes ``new_agent_id=None`` but must leave the variable
        alone until a queue agent answers and rebinds.
        """

        if new_agent_id is not None:
            await _ccs.CallControlService._reassign_call_record_to_agent(
                tenant_id, call.customer_call_id, new_agent_id,
            )
            # Live ASR is routed via workflow sys._bridged_agent_id; without a
            # rebind, captions keep going to the initiator (now in wrap-up).
            try:
                from app.services.call_center.orchestrator import get_orchestrator

                wf = get_orchestrator().active_workflow(call.customer_call_id)
                if wf is not None:
                    wf.rebind_bridged_agent(new_agent_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "transfer: rebind bridged agent failed call=%s new_agent=%s",
                    call.customer_call_id, new_agent_id, exc_info=True,
                )
        elif clear_bridged_agent:
            # No agent owns the call after an external handover. Drop the stale
            # pointer so transcript routing / hangup settlement stop targeting
            # the initiator. ``rebind_bridged_agent`` only accepts an employee id.
            try:
                from app.services.call_center.orchestrator import get_orchestrator

                wf = get_orchestrator().active_workflow(call.customer_call_id)
                if wf is not None:
                    wf.ctx.variables.pop("sys._bridged_agent_id", None)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "transfer: clear bridged agent failed call=%s",
                    call.customer_call_id, exc_info=True,
                )
        await _ccs.CallControlService._notify_control_result(
            tenant_id=tenant_id,
            initiator_employee_id=employee_id,
            method="cc.transfer_result",
            payload={"ok": True, "kind": "transfer"},
        )
        await _ccs.CallControlService._notify_browser_call_ended(
            tenant_id,
            employee_id,
            call.customer_call_id,
            reason="transferred",
        )
        from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
        from app.services.call_center.orchestrator import _get_redis_client

        r = _get_redis_client()
        try:
            async with _ccs.AsyncSessionLocal() as db:
                from app.services.call_wrapup_service import (
                    apply_post_call_agent_status,
                    resolve_effective_wrapup_seconds,
                )

                wrapup_seconds = await resolve_effective_wrapup_seconds(
                    db, tenant_id, call.customer_call_id
                )
                try:
                    await apply_post_call_agent_status(
                        db,
                        r,
                        tenant_id,
                        employee_id,
                        call_id=call.customer_call_id,
                        reason="transferred",
                        wrapup_seconds=wrapup_seconds,
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "transfer: post-call status failed agent=%s/%s",
                        tenant_id, employee_id, exc_info=True,
                    )
                    if r is not None:
                        try:
                            await _ccs.CcAgentResourceService.force_release(
                                r, tenant_id, employee_id, reason="transferred",
                            )
                        except Exception:  # noqa: BLE001
                            logger.warning(
                                "transfer: force_release failed agent=%s/%s",
                                tenant_id, employee_id, exc_info=True,
                            )
                await AgentWebRTCSessionService.set_busy(
                    db, tenant_id, employee_id, busy=False
                )
        except Exception:  # noqa: BLE001
            logger.warning(
                "transfer: sync post-call status failed agent=%s/%s",
                tenant_id, employee_id, exc_info=True,
            )
        # Initiator has left the call; drop stale room/consult legs so they
        # cannot bleed into a later call. Per-employee key — does not touch
        # the transfer target's legs.
        try:
            await _ccs._clear_legs(tenant_id, employee_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "transfer: clear legs failed agent=%s/%s",
                tenant_id, employee_id, exc_info=True,
            )

    @staticmethod
    async def _reassign_call_record_to_agent(
        tenant_id: int, customer_call_id: str, new_agent_id: int
    ) -> None:
        """Re-point the customer's call record to the transfer target.

        After a successful transfer the colleague owns the call, but the CDR
        still names the initiator. Left unchanged, the initiator's hangup would
        resolve to (and kill) the customer call, and the customer's own hangup
        would notify the initiator instead of the colleague (who then stays
        stuck "通话中"). Best-effort; a short session is opened and closed here.
        """

        from sqlalchemy import select
        from app.models.call_record import CallRecord

        try:
            async with _ccs.AsyncSessionLocal() as db:
                row = (
                    await db.execute(
                        select(CallRecord).where(
                            CallRecord.tenant_id == tenant_id,
                            CallRecord.call_id == customer_call_id,
                        )
                    )
                ).scalar_one_or_none()
                if row is None:
                    row = (
                        await db.execute(
                            select(CallRecord).where(
                                CallRecord.tenant_id == tenant_id,
                                CallRecord.root_call_id == customer_call_id,
                            )
                        )
                    ).scalar_one_or_none()
                if row is not None and row.last_serving_agent_id != new_agent_id:
                    row.last_serving_agent_id = new_agent_id
                    await db.commit()
                    logger.info(
                        "transfer: call %s reassigned to agent %s",
                        customer_call_id, new_agent_id,
                    )
        except Exception:  # noqa: BLE001
            logger.warning(
                "transfer: call-record reassign failed call=%s agent=%s",
                customer_call_id, new_agent_id, exc_info=True,
            )
        try:
            from app.services.call_center.orchestrator import get_orchestrator

            await get_orchestrator().reassign_outbound_originator(
                customer_call_id, new_agent_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "transfer: outbound originator reassign failed call=%s agent=%s",
                customer_call_id, new_agent_id, exc_info=True,
            )

    @staticmethod
    def _validate_target(
        target_type: str, target_id: int | None, number: str | None
    ) -> None:
        """Validate that the target payload matches its type."""

        if target_type in ("employee", "queue"):
            if target_id is None:
                raise ValidationError(f"{target_type} target requires target_id")
        elif target_type == "external":
            if not number:
                raise ValidationError("external target requires number")
        else:
            raise ValidationError(f"Unsupported target_type: {target_type}")

# Imported after the mixin class so this module can be imported directly
# without a circular-import error (call_control_service imports the mixins).
from app.services.call_center import call_control_service as _ccs  # noqa: E402
