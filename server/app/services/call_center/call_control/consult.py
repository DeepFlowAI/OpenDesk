"""Consultation with a third party while the customer is held."""
from __future__ import annotations

import asyncio
import logging
import uuid

from app.constants.call_center import ConsultState
from app.core.exceptions import NotFoundError, ValidationError
from app.libs.telephony.base import BaseTelephonyClient
from app.services.call_center import consult_session

logger = logging.getLogger(__name__)


class ConsultMixin:
    # ───────────────────────── consult ─────────────────────────

    @staticmethod
    async def consult_start(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        target_type: str,
        target_id: int | None,
        number: str | None,
    ) -> dict:
        """Start a consultation: hold + consult-tone the customer, call a third
        party, and bridge the agent to it when it answers.

        The customer stays held (hearing the consult waiting tone) throughout.
        The agent↔target bridge is established off the request path once the
        target answers; the request returns as soon as the target rings.
        """

        _ccs.CallControlService._validate_target(target_type, target_id, number)
        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        if call.webrtc_call_id is None:
            raise ValidationError("坐席媒体腿不可用，无法发起咨询")

        # Route an employee target with no SIP extension but an available Web
        # phone to the internal browser-ring consult path.
        if target_type == "employee" and await _ccs.CallControlService._employee_target_is_webrtc(
            tenant_id, target_id
        ):
            # Fail fast (before holding the customer) if the colleague is offline
            # or already busy, so the customer's call is never disturbed.
            await _ccs.CallControlService._precheck_webrtc_target_available(
                tenant_id, target_id, action="咨询"
            )
            return await _ccs.CallControlService._consult_webrtc_employee(
                telephony,
                tenant_id=tenant_id,
                employee_id=employee_id,
                target_employee_id=target_id,
                call=call,
            )

        originate_kwargs, desc_str = await _ccs.CallControlService._resolve_target_originate(
            tenant_id, target_type, target_id, number
        )

        # Unbridge the agent leg (keeps customer RTP flowing for the tone) and
        # start the consult waiting tone before dialing the third party.
        await telephony.call_unbridge(call.customer_call_id, call.webrtc_call_id)
        await _ccs.CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="consult",
        )

        target_call_id = await _ccs.CallControlService._originate_target(
            telephony, originate_kwargs
        )
        operation_id = f"consult:{target_call_id}"
        await _ccs.CallControlService._record_consult_event(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            operation_id=operation_id,
            event_type="consult_started",
            employee_id=employee_id,
            target_type=target_type,
            target_id=target_id,
            target_name=desc_str,
            target_call_id=target_call_id,
        )
        await _ccs.CallControlService._record_consult_event(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            operation_id=operation_id,
            event_type="consult_target_ringing",
            employee_id=employee_id,
            target_type=target_type,
            target_id=target_id,
            target_name=desc_str,
            target_call_id=target_call_id,
        )
        await consult_session.transition(
            tenant_id=tenant_id,
            host_employee_id=employee_id,
            to_state=ConsultState.RINGING,
            reason="consult_start_sip",
            consult_call_id=target_call_id,
        )

        webrtc_call_id = call.webrtc_call_id

        async def _bridge_agent_to_consult() -> None:
            # consult_end may have cleared RINGING while the target was still
            # answering — refuse to bridge onto a cancelled consult.
            legs_now = await _ccs._legs(tenant_id, employee_id)
            if (
                consult_session.derive_state(legs_now) is not ConsultState.RINGING
                or legs_now.consult_call_id != target_call_id
            ):
                logger.info(
                    "consult sip answer ignored (cancelled) agent=%s target=%s",
                    employee_id, target_call_id,
                )
                try:
                    await telephony.call_hangup(
                        target_call_id, reason="consult_cancelled",
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "consult cancelled hangup failed target=%s",
                        target_call_id, exc_info=True,
                    )
                return
            try:
                await telephony.call_bridge(webrtc_call_id, target_call_id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "consult bridge failed agent=%s target=%s",
                    webrtc_call_id, target_call_id,
                )
                # Drop the answered target, resume the held customer, and tell
                # the initiator — otherwise the customer stays on the consult
                # tone with no recovery path.
                await _ccs.CallControlService._restore_after_consult_failure(
                    telephony, tenant_id, employee_id, call,
                    target_call_id, "bridge_failed",
                )
                await _ccs.CallControlService._notify_consult_failed(
                    tenant_id, employee_id, "bridge_failed"
                )
                return
            await consult_session.transition(
                tenant_id=tenant_id,
                host_employee_id=employee_id,
                to_state=ConsultState.ACTIVE,
                reason="consult_sip_answered",
                consult_call_id=target_call_id,
            )
            await _ccs.CallControlService._record_consult_event(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                operation_id=operation_id,
                event_type="consult_connected",
                employee_id=employee_id,
                target_type=target_type,
                target_id=target_id,
                target_name=desc_str,
                target_call_id=target_call_id,
                result="succeeded",
            )

        async def _on_consult_failed(reason: str) -> None:
            await _ccs.CallControlService._restore_after_consult_failure(
                telephony, tenant_id, employee_id, call, target_call_id, reason
            )
            await _ccs.CallControlService._record_consult_event(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                operation_id=operation_id,
                event_type="consult_failed",
                employee_id=employee_id,
                target_type=target_type,
                target_id=target_id,
                target_name=desc_str,
                target_call_id=target_call_id,
                result="failed",
                reason_code="target_no_answer" if reason in {"timeout", "no_answer"} else "target_unavailable",
                reason_detail=reason,
            )

        _ccs.CallControlService._spawn_target_wait(
            telephony,
            target_call_id=target_call_id,
            on_answer=_bridge_agent_to_consult,
            on_fail=_on_consult_failed,
        )

        logger.info(
            "consult start: agent=%s customer=%s held -> %s consult_leg=%s (ringing)",
            employee_id, call.customer_call_id, desc_str, target_call_id,
        )
        return {"ok": True, "call_id": call.customer_call_id, "note": "ringing_target"}

    @staticmethod
    async def _consult_webrtc_employee(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        target_employee_id: int,
        call: _ccs.CurrentCall,
    ) -> dict:
        """Consult a colleague on the Web phone: ring their browser, then bridge.

        Mirrors the SIP consult: unbridge + consult-tone the customer, then ring
        the target's browser off the request path. On accept, the target's own
        WebRTC leg (returned by their accept) is stored as the consult leg and
        bridged to the initiator; on decline / no-answer the customer is resumed.
        The request returns ``ringing_target`` as soon as the target rings.
        """

        await telephony.call_unbridge(call.customer_call_id, call.webrtc_call_id)
        await _ccs.CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="consult",
        )
        # Persist RINGING (+ offer_id) before the browser wait so refresh /
        # reconcile sees the in-flight consult, and consult_end can cancel the
        # pending offer by the same id.
        offer_id = uuid.uuid4().hex
        operation_id = f"consult:{offer_id}"
        await _ccs.CallControlService._record_consult_event(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            operation_id=operation_id,
            event_type="consult_started",
            employee_id=employee_id,
            target_type="employee",
            target_id=target_employee_id,
        )
        await _ccs.CallControlService._record_consult_event(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            operation_id=operation_id,
            event_type="consult_target_ringing",
            employee_id=employee_id,
            target_type="employee",
            target_id=target_employee_id,
        )
        await consult_session.transition(
            tenant_id=tenant_id,
            host_employee_id=employee_id,
            to_state=ConsultState.RINGING,
            reason="consult_start_webrtc",
            target_employee_id=target_employee_id,
            offer_id=offer_id,
        )
        display = await _ccs.CallControlService._resolve_initiator_display(
            tenant_id, employee_id
        )
        webrtc_call_id = call.webrtc_call_id

        target_name = await _ccs.CallControlService._resolve_initiator_display(
            tenant_id, target_employee_id
        )

        async def _ring_and_bridge() -> None:
            from app.services.call_center.internal_consult_service import (
                InternalConsultService,
            )
            from app.services.call_center.orchestrator import _get_redis_client

            r = _get_redis_client()
            if r is None:
                await consult_session.clear(
                    tenant_id=tenant_id,
                    host_employee_id=employee_id,
                    reason="consult_webrtc_no_redis",
                )
                await _ccs.CallControlService._restore_after_consult_failure(
                    telephony, tenant_id, employee_id, call, "", "no_redis",
                )
                await _ccs.CallControlService._notify_consult_failed(
                    tenant_id, employee_id, "no_redis"
                )
                return
            try:
                customer_context = await _ccs.CallControlService._customer_context_for_call(call)
                result = await InternalConsultService.initiate_webrtc_consult(
                    telephony,
                    r,
                    tenant_id=tenant_id,
                    initiator_employee_id=employee_id,
                    target_employee_id=target_employee_id,
                    initiator_display=display,
                    call_type="internal_consult",
                    customer_context=customer_context,
                    offer_id=offer_id,
                )
            except Exception as exc:  # noqa: BLE001
                # consult_end may already have cleared + restored; only restore
                # when this consult is still the active RINGING session.
                legs_after = await _ccs._legs(tenant_id, employee_id)
                still_ours = (
                    consult_session.derive_state(legs_after) is ConsultState.RINGING
                    and legs_after.consult_offer_id == offer_id
                )
                if still_ours:
                    await consult_session.clear(
                        tenant_id=tenant_id,
                        host_employee_id=employee_id,
                        reason=f"consult_webrtc_failed:{exc}",
                    )
                    await _ccs.CallControlService._restore_after_consult_failure(
                        telephony, tenant_id, employee_id, call, "", str(exc),
                    )
                    await _ccs.CallControlService._notify_consult_failed(
                        tenant_id, employee_id, str(exc)
                    )
                    await _ccs.CallControlService._record_consult_event(
                        tenant_id=tenant_id,
                        call_id=call.customer_call_id,
                        operation_id=operation_id,
                        event_type="consult_failed",
                        employee_id=employee_id,
                        target_type="employee",
                        target_id=target_employee_id,
                        result="failed",
                        reason_code="target_unavailable",
                        reason_detail=str(exc),
                    )
                else:
                    logger.info(
                        "consult webrtc wait ended after cancel agent=%s offer=%s err=%s",
                        employee_id, offer_id, exc,
                    )
                return
            target_leg = result["target_webrtc_call_id"]
            # Race guard: host may have ended consult while the target accepted.
            legs_now = await _ccs._legs(tenant_id, employee_id)
            if (
                consult_session.derive_state(legs_now) is not ConsultState.RINGING
                or legs_now.consult_offer_id != offer_id
                or legs_now.consult_target_employee_id != target_employee_id
            ):
                logger.info(
                    "consult webrtc accept ignored (cancelled) agent=%s "
                    "target=%s offer=%s leg=%s",
                    employee_id, target_employee_id, offer_id, target_leg,
                )
                try:
                    await telephony.call_hangup(
                        target_leg, reason="consult_cancelled",
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "consult cancelled hangup failed target=%s",
                        target_leg, exc_info=True,
                    )
                await _ccs.CallControlService._release_internal_target(
                    tenant_id, target_employee_id, reason="consult_cancelled",
                )
                await _ccs.CallControlService._notify_browser_call_ended(
                    tenant_id, target_employee_id, target_leg,
                    reason="consult_cancelled",
                )
                return
            await consult_session.transition(
                tenant_id=tenant_id,
                host_employee_id=employee_id,
                to_state=ConsultState.ACTIVE,
                reason="consult_webrtc_answered",
                consult_call_id=target_leg,
                target_employee_id=target_employee_id,
                offer_id=offer_id,
            )
            try:
                await telephony.call_bridge(
                    webrtc_call_id,
                    target_leg,
                    keepalive_on_peer_hangup=True,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "internal consult bridge failed agent=%s target=%s",
                    webrtc_call_id, target_leg,
                )
                await _ccs.CallControlService._release_internal_target(
                    tenant_id, target_employee_id, reason="consult_bridge_failed",
                )
                await _ccs.CallControlService._restore_after_consult_failure(
                    telephony, tenant_id, employee_id, call, target_leg, "bridge_failed",
                )
                await _ccs.CallControlService._notify_consult_failed(
                    tenant_id, employee_id, "bridge_failed"
                )
                return
            await _ccs.CallControlService._record_consult_event(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                operation_id=operation_id,
                event_type="consult_connected",
                employee_id=employee_id,
                target_type="employee",
                target_id=target_employee_id,
                target_name=target_name,
                target_call_id=target_leg,
                result="succeeded",
            )
            # Target answered and the initiator is now bridged to them.
            await _ccs.CallControlService._notify_control_result(
                tenant_id=tenant_id,
                initiator_employee_id=employee_id,
                method="cc.consult_result",
                payload={"ok": True, "kind": "consult", "target_name": target_name},
            )

        asyncio.create_task(
            _ring_and_bridge(),
            name=f"internal-consult:{tenant_id}:{target_employee_id}",
        )
        logger.info(
            "consult start (webrtc): agent=%s customer=%s held -> employee:%s (ringing browser)",
            employee_id, call.customer_call_id, target_employee_id,
        )
        # Distinct note: the browser stays in "咨询呼叫中" until a cc.consult_result
        # socket event reports the outcome (the ring resolves off the request path).
        return {
            "ok": True,
            "call_id": call.customer_call_id,
            "note": "ringing_webrtc_target",
        }

    @staticmethod
    async def consult_end(
        telephony: BaseTelephonyClient, *, tenant_id: int, employee_id: int
    ) -> dict:
        """End a consultation: drop the third party, resume the customer.

        Un-bridges the agent from the consult leg, hangs the consult leg up,
        stops the consult waiting tone, and un-holds the customer back to the
        agent.
        """

        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        legs = await _ccs._legs(tenant_id, employee_id)
        if not consult_session.is_consult_active(legs):
            raise NotFoundError("No active consultation")
        consult_call_id = legs.consult_call_id
        target_employee_id = legs.consult_target_employee_id
        consult_offer_id = legs.consult_offer_id
        was_ringing = consult_session.derive_state(legs) is ConsultState.RINGING
        operation_id = f"consult:{consult_offer_id or consult_call_id or call.customer_call_id}"

        if call.webrtc_call_id and consult_call_id:
            try:
                await telephony.call_unbridge(call.webrtc_call_id, consult_call_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "consult unbridge failed agent=%s consult=%s",
                    employee_id, consult_call_id, exc_info=True,
                )
        if consult_call_id:
            try:
                await telephony.call_hangup(consult_call_id, reason="consult_ended")
            except Exception:  # noqa: BLE001
                logger.warning(
                    "consult leg hangup failed agent=%s consult=%s",
                    employee_id, consult_call_id, exc_info=True,
                )

        # Clear host consult state before waking the background waiter so a
        # late accept sees NONE and refuses to bridge (stale-accept guard).
        await consult_session.clear(
            tenant_id=tenant_id,
            host_employee_id=employee_id,
            reason="consult_end",
            consult_call_id=consult_call_id,
        )

        # Cancel a still-ringing browser offer so initiate_webrtc_consult exits
        # promptly instead of racing with customer resume.
        if was_ringing and consult_offer_id:
            await _ccs.CallControlService._cancel_pending_consult_offer(
                consult_offer_id, "consult_ended",
            )

        # Internal browser-ring target: we occupied that colleague's call-center
        # resource to ring them for this consult, so free it now that the consult
        # is over — otherwise they stay stuck busy and can't be dialed again.
        if target_employee_id is not None:
            await _ccs.CallControlService._release_internal_target(
                tenant_id, target_employee_id, reason="internal_consult_ended",
            )
            # Tell the colleague's browser its consult leg is over so it closes
            # the WebRTC peer cleanly. Without this the target stays stuck at
            # "通话中" until the media times out and reports a spurious ICE
            # failure, and a later hangup click resolves to a stale call.
            # During RINGING there is no media leg yet — use the synthetic
            # internal offer call_id the browser was offered.
            notify_call_id = consult_call_id or (
                f"internal:{consult_offer_id}" if consult_offer_id else None
            )
            if notify_call_id:
                await _ccs.CallControlService._notify_browser_call_ended(
                    tenant_id, target_employee_id, notify_call_id,
                    reason="consult_ended",
                )

        await _ccs.CallControlService._stop_tone(telephony, call.customer_call_id)
        if call.webrtc_call_id:
            await telephony.call_bridge(
                call.customer_call_id,
                call.webrtc_call_id,
                user_call_id=call.customer_call_id,
                keepalive_on_peer_hangup=True,
            )
        logger.info(
            "consult end: agent=%s customer=%s resumed (consult_leg=%s dropped)",
            employee_id, call.customer_call_id, consult_call_id,
        )
        await _ccs.CallControlService._record_consult_event(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            operation_id=operation_id,
            event_type="consult_canceled" if was_ringing else "consult_ended",
            employee_id=employee_id,
            target_type="employee" if target_employee_id is not None else "external",
            target_id=target_employee_id,
            target_call_id=consult_call_id,
            result="canceled" if was_ringing else "succeeded",
            reason_code="canceled_by_actor" if was_ringing else "normal",
        )
        return {"ok": True, "call_id": call.customer_call_id}

    @staticmethod
    async def _record_consult_event(
        *,
        tenant_id: int,
        call_id: str,
        operation_id: str,
        event_type: str,
        employee_id: int,
        target_type: str,
        target_id: int | None,
        target_name: str | None = None,
        target_call_id: str | None = None,
        result: str | None = None,
        reason_code: str | None = None,
        reason_detail: str | None = None,
    ) -> None:
        from app.services.call_trajectory_service import CallTrajectoryService

        await CallTrajectoryService.append_for_call_id_best_effort(
            tenant_id=tenant_id,
            call_id=call_id,
            event_id=f"opendesk:{event_type}:{operation_id}",
            event_type=event_type,
            event_category="consult",
            actor_type="agent",
            actor_id=str(employee_id),
            source="opendesk",
            operation_id=operation_id,
            call_leg_id=target_call_id,
            participant_role="consult_target" if target_call_id else None,
            target_type="external_number" if target_type == "external" else target_type,
            target_id=str(target_id) if target_id is not None else None,
            target_name_snapshot=target_name,
            result=result,
            reason_code=reason_code,
            reason_detail=reason_detail,
        )

# Imported after the mixin class so this module can be imported directly
# without a circular-import error (call_control_service imports the mixins).
from app.services.call_center import call_control_service as _ccs  # noqa: E402
