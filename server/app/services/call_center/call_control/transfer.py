"""Blind (direct) transfer of the customer to a new target."""
from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from app.libs.telephony.base import BaseTelephonyClient

logger = logging.getLogger(__name__)


class TransferMixin:
    # ───────────────────────── transfer (blind) ─────────────────────────

    @staticmethod
    async def transfer(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        target_type: str,
        target_id: int | None,
        number: str | None,
    ) -> dict:
        """Blind (direct) transfer of the customer to a new target.

        Flow: originate the target leg (employee extension / external number),
        play the transfer prompt to the customer, then hand the target-answer
        wait to the orchestrator. When the target answers, the customer is
        bridged to it and the agent's own leg is dropped — off the request path.
        On no-answer / decline the customer is restored to the agent so the call
        is never lost. The request returns as soon as the target rings.
        """

        _ccs.CallControlService._validate_target(target_type, target_id, number)

        # Queue blind-transfer has its own wait/ring orchestration; consult and
        # add-participant still reject queue targets via _resolve_target_originate.
        if target_type == "queue":
            return await _ccs.CallControlService.transfer_to_queue(
                telephony,
                tenant_id=tenant_id,
                employee_id=employee_id,
                queue_id=target_id,
            )

        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        operation_id = f"transfer:{uuid4().hex}"
        await _ccs.CallControlService._record_transfer_event(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            operation_id=operation_id,
            event_type="transfer_started",
            employee_id=employee_id,
            target_type=target_type,
            target_id=target_id,
            target_name=number,
        )

        # Route an employee target with no SIP extension but an available Web
        # phone to the internal browser-ring transfer path.
        if target_type == "employee" and await _ccs.CallControlService._employee_target_is_webrtc(
            tenant_id, target_id
        ):
            # Fail fast (before touching the customer) if the colleague is
            # offline or already busy, so the customer's call is never disturbed.
            await _ccs.CallControlService._precheck_webrtc_target_available(
                tenant_id, target_id, action="转接"
            )
            return await _ccs.CallControlService._transfer_webrtc_employee(
                telephony,
                tenant_id=tenant_id,
                employee_id=employee_id,
                target_employee_id=target_id,
                call=call,
                operation_id=operation_id,
            )

        originate_kwargs, desc_str = await _ccs.CallControlService._resolve_target_originate(
            tenant_id, target_type, target_id, number
        )
        target_call_id = await _ccs.CallControlService._originate_target(
            telephony, originate_kwargs
        )
        await _ccs.CallControlService._record_transfer_event(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            operation_id=operation_id,
            event_type="transfer_target_ringing",
            employee_id=employee_id,
            target_type=target_type,
            target_id=target_id,
            target_name=desc_str,
            target_call_id=target_call_id,
        )

        # Waiting tone for the customer while the target rings (single play).
        await _ccs.CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="transfer",
        )

        async def _on_transfer_answered() -> None:
            await _ccs.CallControlService._record_transfer_event(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                operation_id=operation_id,
                event_type="transfer_target_answered",
                employee_id=employee_id,
                target_type=target_type,
                target_id=target_id,
                target_name=desc_str,
                target_call_id=target_call_id,
                result="succeeded",
            )
            handed_over = await _ccs.CallControlService._complete_blind_transfer(
                telephony, call, target_call_id
            )
            if not handed_over:
                await _ccs.CallControlService._record_transfer_event(
                    tenant_id=tenant_id,
                    call_id=call.customer_call_id,
                    operation_id=operation_id,
                    event_type="transfer_failed",
                    employee_id=employee_id,
                    target_type=target_type,
                    target_id=target_id,
                    target_name=desc_str,
                    target_call_id=target_call_id,
                    result="failed",
                    reason_code="bridge_failed",
                )
                await _ccs.CallControlService._notify_transfer_failed(
                    tenant_id, employee_id, "转接失败，客户通话仍在继续",
                )
                return
            new_agent_id = target_id if target_type == "employee" else None
            await _ccs.CallControlService._finalize_initiator_after_transfer(
                tenant_id=tenant_id,
                employee_id=employee_id,
                call=call,
                new_agent_id=new_agent_id,
                # External target has no owning agent — clear stale transcript
                # routing. Queue transfer also uses new_agent_id=None but must
                # keep the variable until a queue agent answers and rebinds.
                clear_bridged_agent=(target_type == "external"),
            )
            await _ccs.CallControlService._record_transfer_event(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                operation_id=operation_id,
                event_type="transfer_completed",
                employee_id=employee_id,
                target_type=target_type,
                target_id=target_id,
                target_name=desc_str,
                target_call_id=target_call_id,
                result="succeeded",
            )
            from app.services.call_record_service import CallRecordService

            await CallRecordService.mark_reception_transferred_managed(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                from_agent_id=employee_id,
                to_agent_id=new_agent_id,
                operation_id=operation_id,
                target_leg_id=target_call_id,
            )
            # SIP desk-phone answer never rings the target browser, so occupy
            # their Redis resource and push the in-call workspace now that the
            # CDR points at them.
            if new_agent_id is not None:
                await _ccs.CallControlService._mark_sip_transfer_target_in_call(
                    tenant_id, new_agent_id, call.customer_call_id,
                )
                try:
                    from app.services.call_center.orchestrator import get_orchestrator

                    await get_orchestrator().republish_agent_call_ui(
                        tenant_id=tenant_id, employee_id=new_agent_id,
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "transfer: republish target call UI failed "
                        "agent=%s/%s call=%s",
                        tenant_id, new_agent_id, call.customer_call_id,
                        exc_info=True,
                    )

        async def _on_transfer_failed(reason: str) -> None:
            await _ccs.CallControlService._restore_after_target_failure(
                telephony, call, target_call_id, reason
            )
            await _ccs.CallControlService._notify_transfer_failed(
                tenant_id, employee_id, reason,
            )
            await _ccs.CallControlService._record_transfer_event(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                operation_id=operation_id,
                event_type="transfer_failed",
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
            on_answer=_on_transfer_answered,
            on_fail=_on_transfer_failed,
        )

        logger.info(
            "transfer: agent=%s customer=%s -> %s target_leg=%s (ringing)",
            employee_id, call.customer_call_id, desc_str, target_call_id,
        )
        return {"ok": True, "call_id": call.customer_call_id, "note": "ringing_target"}

    @staticmethod
    async def _complete_blind_transfer(
        telephony: BaseTelephonyClient,
        call: _ccs.CurrentCall,
        target_call_id: str,
        *,
        target_is_webrtc: bool = False,
    ) -> bool:
        """Target answered → bridge customer to target, drop the agent leg.

        Returns True when the handover completed (customer is now with the
        target); False when it failed and the customer was restored to the agent.
        """

        await _ccs.CallControlService._stop_tone(telephony, call.customer_call_id)
        # Detach the customer from the initiating agent FIRST — the kernel
        # refuses to bridge an already-bridged call (-32003), which was silently
        # aborting the whole handover (customer stayed stuck on the agent, the
        # target's answered leg orphaned). Best-effort: a no-op if already held.
        if call.webrtc_call_id:
            try:
                await telephony.call_unbridge(
                    call.customer_call_id, call.webrtc_call_id
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "transfer: detach customer from agent before handover failed"
                    " customer=%s agent_leg=%s",
                    call.customer_call_id, call.webrtc_call_id, exc_info=True,
                )
        try:
            await telephony.call_bridge(
                call.customer_call_id,
                target_call_id,
                keepalive_on_peer_hangup=target_is_webrtc,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "transfer bridge failed customer=%s target=%s",
                call.customer_call_id, target_call_id,
            )
            # Re-attach the customer to the agent so the call isn't lost.
            if call.webrtc_call_id:
                try:
                    await telephony.call_bridge(
                        call.customer_call_id,
                        call.webrtc_call_id,
                        keepalive_on_peer_hangup=True,
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "transfer: re-attach customer to agent after bridge-fail"
                        " failed customer=%s", call.customer_call_id, exc_info=True,
                    )
            await _ccs.CallControlService._restore_after_target_failure(
                telephony, call, target_call_id, "bridge_failed"
            )
            return False
        # Customer is now with the target; release the agent's own leg.
        if call.webrtc_call_id:
            try:
                await telephony.call_hangup(call.webrtc_call_id, reason="transferred")
            except Exception:  # noqa: BLE001
                logger.warning(
                    "transfer: agent leg hangup failed leg=%s",
                    call.webrtc_call_id, exc_info=True,
                )
        logger.info(
            "transfer complete: customer=%s bridged to target=%s",
            call.customer_call_id, target_call_id,
        )
        return True

    @staticmethod
    async def _transfer_webrtc_employee(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        target_employee_id: int,
        call: _ccs.CurrentCall,
        operation_id: str | None = None,
    ) -> dict:
        """Blind-transfer the customer to a colleague on the Web phone.

        Play the transfer tone, ring the target's browser off the request path,
        and on accept bridge the CUSTOMER to the target's WebRTC leg then drop
        the initiator's own leg. On decline / no-answer the customer is kept with
        the initiator (never lost). Returns ``ringing_target`` immediately.
        """

        operation_id = operation_id or f"transfer:{uuid4().hex}"
        await _ccs.CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="transfer",
        )
        await _ccs.CallControlService._record_transfer_event(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            operation_id=operation_id,
            event_type="transfer_target_ringing",
            employee_id=employee_id,
            target_type="employee",
            target_id=target_employee_id,
        )
        display = await _ccs.CallControlService._resolve_initiator_display(
            tenant_id, employee_id
        )

        async def _ring_and_handover() -> None:
            from app.services.call_center.internal_consult_service import (
                InternalConsultService,
            )
            from app.services.call_center.orchestrator import _get_redis_client

            r = _get_redis_client()
            if r is None:
                await _ccs.CallControlService._restore_after_target_failure(
                    telephony, call, "", "no_redis",
                )
                await _ccs.CallControlService._notify_transfer_failed(
                    tenant_id, employee_id, "no_redis"
                )
                await _ccs.CallControlService._record_transfer_event(
                    tenant_id=tenant_id,
                    call_id=call.customer_call_id,
                    operation_id=operation_id,
                    event_type="transfer_failed",
                    employee_id=employee_id,
                    target_type="employee",
                    target_id=target_employee_id,
                    result="failed",
                    reason_code="target_unavailable",
                    reason_detail="no_redis",
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
                    call_type="internal_transfer",
                    customer_context=customer_context,
                )
            except Exception as exc:  # noqa: BLE001
                await _ccs.CallControlService._restore_after_target_failure(
                    telephony, call, "", str(exc),
                )
                await _ccs.CallControlService._notify_transfer_failed(
                    tenant_id, employee_id, str(exc)
                )
                await _ccs.CallControlService._record_transfer_event(
                    tenant_id=tenant_id,
                    call_id=call.customer_call_id,
                    operation_id=operation_id,
                    event_type="transfer_failed",
                    employee_id=employee_id,
                    target_type="employee",
                    target_id=target_employee_id,
                    result="failed",
                    reason_code="target_unavailable",
                    reason_detail=str(exc),
                )
                return
            target_leg_id = result["target_webrtc_call_id"]
            await _ccs.CallControlService._record_transfer_event(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                operation_id=operation_id,
                event_type="transfer_target_answered",
                employee_id=employee_id,
                target_type="employee",
                target_id=target_employee_id,
                target_call_id=target_leg_id,
                result="succeeded",
            )
            # The colleague now owns the customer call: re-point their occupied
            # resource from the internal consult leg onto the customer call so it
            # finalizes cleanly on the customer's own hangup.
            await _ccs.CallControlService._rekey_internal_target_to_customer(
                tenant_id, target_employee_id, call.customer_call_id,
            )
            handed_over = await _ccs.CallControlService._complete_blind_transfer(
                telephony, call, target_leg_id, target_is_webrtc=True
            )
            if not handed_over:
                # Bridge failed → customer was restored to the initiator; free
                # the colleague we occupied and report the failure.
                await _ccs.CallControlService._release_internal_target(
                    tenant_id, target_employee_id, reason="transfer_bridge_failed",
                )
                await _ccs.CallControlService._notify_transfer_failed(
                    tenant_id, employee_id, "转接失败，客户通话仍在继续",
                )
                await _ccs.CallControlService._record_transfer_event(
                    tenant_id=tenant_id,
                    call_id=call.customer_call_id,
                    operation_id=operation_id,
                    event_type="transfer_failed",
                    employee_id=employee_id,
                    target_type="employee",
                    target_id=target_employee_id,
                    target_call_id=target_leg_id,
                    result="failed",
                    reason_code="bridge_failed",
                )
                return
            await _ccs.CallControlService._finalize_initiator_after_transfer(
                tenant_id=tenant_id,
                employee_id=employee_id,
                call=call,
                new_agent_id=target_employee_id,
            )
            await _ccs.CallControlService._record_transfer_event(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                operation_id=operation_id,
                event_type="transfer_completed",
                employee_id=employee_id,
                target_type="employee",
                target_id=target_employee_id,
                target_call_id=target_leg_id,
                result="succeeded",
            )
            from app.services.call_record_service import CallRecordService

            await CallRecordService.mark_reception_transferred_managed(
                tenant_id=tenant_id,
                call_id=call.customer_call_id,
                from_agent_id=employee_id,
                to_agent_id=target_employee_id,
                operation_id=operation_id,
                target_leg_id=target_leg_id,
            )
            # Re-push the target's in-call UI keyed on the customer call so the
            # transcript panel and call controls anchor to the customer leg
            # (mirrors the SIP transfer target path above).
            try:
                from app.services.call_center.orchestrator import get_orchestrator

                await get_orchestrator().republish_agent_call_ui(
                    tenant_id=tenant_id, employee_id=target_employee_id,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "transfer (webrtc): republish target call UI failed "
                    "agent=%s/%s call=%s",
                    tenant_id, target_employee_id, call.customer_call_id,
                    exc_info=True,
                )

        asyncio.create_task(
            _ring_and_handover(),
            name=f"internal-transfer:{tenant_id}:{target_employee_id}",
        )
        logger.info(
            "transfer (webrtc): agent=%s customer=%s -> employee:%s (ringing browser)",
            employee_id, call.customer_call_id, target_employee_id,
        )
        # Distinct note: the browser stays in "转接中" until a cc.transfer_result
        # socket event reports the outcome (the ring resolves off the request path).
        return {
            "ok": True,
            "call_id": call.customer_call_id,
            "note": "ringing_webrtc_target",
        }

    @staticmethod
    async def _record_transfer_event(
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
            event_category="transfer",
            actor_type="agent",
            actor_id=str(employee_id),
            source="opendesk",
            operation_id=operation_id,
            call_leg_id=target_call_id,
            participant_role="transfer_target" if target_call_id else None,
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
