"""Socket.IO pushes to agent browsers: incoming / answered / ended / outbound
lifecycle notifications and the in-call UI republish after a browser
reconnect."""
from __future__ import annotations

import logging

from app.constants.call_center import CcSocketEvent

logger = logging.getLogger(__name__)


class AgentPushMixin:

    # ────────────────── Outbound push to agent browsers ──────────────────

    async def notify_agent_incoming(
        self,
        *,
        tenant_id: int,
        employee_id: int,
        payload: dict,
    ) -> bool:
        return await _orch.emit_to_agent(
            tenant_id=tenant_id,
            employee_id=employee_id,
            method=CcSocketEvent.CALL_INCOMING.value,
            payload=payload,
        )

    async def republish_agent_call_ui(
        self, *, tenant_id: int, employee_id: int
    ) -> None:
        """Re-push ringing / in-call UI state after an agent browser reconnects.

        Incoming offers are fire-and-forget Socket events. A page refresh loses
        the in-memory ``incoming`` state even though Redis still marks the agent
        as ringing and the caller is waiting. On Socket.IO connect we rebuild the
        payload from the resource snapshot + CDR and emit again.
        """

        from app.db.redis import redis_client
        from app.db.session import AsyncSessionLocal
        from app.repositories.call_record_repository import CallRecordRepository
        from app.services.agent_call_device_service import AgentCallDeviceService
        from app.services.call_workspace_context_service import (
            CallWorkspaceContextService,
        )

        from app.services.cc_agent_status_service import CcAgentStatusService

        r = redis_client.client
        if r is None:
            return

        # Heal ghost Redis in_call (no active CDR / WebRTC session) before we
        # re-push UI — otherwise a deploy reconnect resurrects hung-up calls.
        try:
            async with AsyncSessionLocal() as db:
                snapshot = await CcAgentStatusService.reconcile_agent(
                    db, r, tenant_id, employee_id
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "republish call UI: reconcile failed agent=%s/%s",
                tenant_id, employee_id,
            )
            try:
                snapshot = await _orch.CcAgentResourceService.get_snapshot(
                    r, tenant_id, employee_id
                )
            except Exception:  # noqa: BLE001
                return

        snap = snapshot or {}
        state = snap.get("resource_state")
        call_id = snap.get("current_call_id")
        offer_id = snap.get("offer_id") or ""
        queue_id = snap.get("queue_id")
        direction = snap.get("direction") or "inbound"
        from_number = ""
        to_number = ""
        device_type = None
        answered_at = None
        call_type = None
        source_call_id = None
        workspace_call_record = None
        workspace_context: dict[str, str | int] = {}
        try:
            async with AsyncSessionLocal() as db:
                # Redis resource can drift (e.g. SIP desk-phone consult after a
                # refresh) while the CDR is still in_progress. Recover so the
                # browser gets 通话中 UI back instead of stuck 忙碌.
                # Only answered calls (in_progress) — never resurrect a stuck
                # ringing/queued CDR after the real call already ended.
                if not call_id or state not in {"ringing", "in_call"}:
                    active = await CallRecordRepository.get_latest_active_for_agent(
                        db, tenant_id, employee_id
                    )
                    if active is None or active.first_agent_connected_at is None:
                        logger.info(
                            "republish call UI: skip agent=%s/%s "
                            "state=%s call_id=%s (no live in_progress CDR)",
                            tenant_id, employee_id, state, call_id,
                        )
                        return
                    # After inviting a survey the CDR stays active for the
                    # customer leg, but the agent has already left. Recovering
                    # them to in_call would media-reconnect and steal the
                    # survey's audio path.
                    from app.repositories.call_satisfaction_execution_repository import (
                        CallSatisfactionExecutionRepository,
                    )

                    survey = await CallSatisfactionExecutionRepository.get_by_call_record_id(
                        db, active.id
                    )
                    if survey is not None and survey.status in {
                        "preparing",
                        "in_progress",
                    }:
                        logger.info(
                            "republish call UI: skip agent=%s/%s call_id=%s "
                            "(customer in satisfaction survey execution=%s)",
                            tenant_id,
                            employee_id,
                            active.root_call_id or active.call_id,
                            survey.id,
                        )
                        return
                    call_id = active.root_call_id or active.call_id
                    workspace_call_record = active
                    state = "in_call"
                    offer_id = ""
                    if active.direction == "inbound":
                        from_number = active.customer_number or ""
                        to_number = active.service_number or ""
                    else:
                        from_number = active.service_number or ""
                        to_number = active.customer_number or ""
                    direction = active.direction or "inbound"
                    answered_at = (
                        active.first_agent_connected_at
                        or active.customer_connected_at
                        or getattr(active, "started_at", None)
                    )
                    try:
                        await _orch.CcAgentResourceService.recover_from_sources(
                            r,
                            tenant_id,
                            employee_id,
                            visible_status="busy",
                            active_call_id=call_id,
                            active_call_direction=direction,
                            active_call_state="in_progress",
                        )
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "republish call UI: recover in_call failed "
                            "agent=%s/%s call_id=%s",
                            tenant_id, employee_id, call_id, exc_info=True,
                        )
                else:
                    record = await CallRecordRepository.get_by_call_id(
                        db, call_id, tenant_id
                    )
                    if record is None or record.lifecycle_status != "active":
                        # Consult targets are keyed on their WebRTC leg and have
                        # no CDR — keep the UI if a host still lists them.
                        from app.services.call_center.call_control_service import (
                            CallControlService,
                        )

                        host = await CallControlService._find_consult_host_for_target(
                            tenant_id, employee_id
                        )
                        if host is None or state != "in_call":
                            logger.info(
                                "republish call UI: drop ghost redis call "
                                "agent=%s/%s call_id=%s cdr_state=%s",
                                tenant_id, employee_id, call_id,
                                getattr(record, "lifecycle_status", None),
                            )
                            try:
                                await _orch.CcAgentResourceService.force_release(
                                    r, tenant_id, employee_id,
                                    reason="republish_ghost_cdr",
                                )
                            except Exception:  # noqa: BLE001
                                logger.warning(
                                    "republish call UI: force_release failed "
                                    "agent=%s/%s",
                                    tenant_id, employee_id, exc_info=True,
                                )
                            return
                        call_type = "internal_consult"
                        answered_at = snap.get("in_call_since")
                        try:
                            host_call = await CallControlService._resolve_current_call(
                                tenant_id, host["employee_id"]
                            )
                            source_call_id = host_call.customer_call_id
                            host_rec = await CallRecordRepository.get_by_call_id(
                                db, source_call_id, tenant_id
                            )
                            if host_rec is not None:
                                if host_rec.direction == "inbound":
                                    from_number = host_rec.customer_number or ""
                                    to_number = host_rec.service_number or ""
                                else:
                                    from_number = host_rec.service_number or ""
                                    to_number = host_rec.customer_number or ""
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        workspace_call_record = record
                        if record.direction == "inbound":
                            from_number = record.customer_number or ""
                            to_number = record.service_number or ""
                        else:
                            from_number = record.service_number or ""
                            to_number = record.customer_number or ""
                        answered_at = (
                            record.first_agent_connected_at
                            or record.customer_connected_at
                            or getattr(record, "started_at", None)
                        )
                        # SIP desk-phone can answer on the handset while Redis stays
                        # "ringing" (missed mark_in_call). Promote so refresh restores
                        # 通话中 instead of a fake 来电 UI.
                        if (
                            state == "ringing"
                            and record.first_agent_connected_at is not None
                        ):
                            prev_offer = offer_id
                            state = "in_call"
                            offer_id = ""
                            try:
                                await _orch.CcAgentResourceService.mark_in_call(
                                    r,
                                    tenant_id,
                                    employee_id,
                                    call_id=call_id,
                                    direction=direction,
                                    offer_id=prev_offer or None,
                                )
                            except Exception:  # noqa: BLE001
                                logger.warning(
                                    "republish call UI: promote ringing→in_call failed "
                                    "agent=%s/%s call_id=%s",
                                    tenant_id, employee_id, call_id, exc_info=True,
                                )
                if not device_type:
                    device = await AgentCallDeviceService.get_current_device(
                        db, tenant_id, employee_id
                    )
                    device_type = (device or {}).get("device_type")
                workspace_context = (
                    await CallWorkspaceContextService.get_auto_outbound_context(
                        db,
                        tenant_id=tenant_id,
                        call_record=workspace_call_record,
                    )
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "republish call UI: CDR lookup failed call_id=%s", call_id
            )
            return

        if not call_id or state not in {"ringing", "in_call"}:
            logger.info(
                "republish call UI: skip agent=%s/%s state=%s call_id=%s",
                tenant_id, employee_id, state, call_id,
            )
            return

        # WebRTC ringing requires the in-memory offer future; if this API node
        # restarted mid-ring, accept cannot work — skip the UI re-push.
        # SIP-phone rings don't register a browser offer future; still push.
        if state == "ringing" and device_type != "sip_phone":
            if not offer_id or offer_id not in self._pending_offers:
                logger.info(
                    "republish call UI: skip ringing without pending offer "
                    "agent=%s/%s offer_id=%s",
                    tenant_id, employee_id, offer_id or "(empty)",
                )
                return

        if answered_at is None:
            answered_at = snap.get("in_call_since")

        # CDR can stay in_progress after the customer leg left the kernel
        # without a SIP BYE (e.g. RTP idle timeout). Do not resurrect 通话中.
        if state == "in_call":
            customer_leg_id = source_call_id or call_id
            try:
                from app.services.call_center.call_control_service import (
                    CallControlService,
                )

                alive = await CallControlService._customer_leg_alive_in_kernel(
                    self.telephony, customer_leg_id
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "republish call UI: kernel alive check failed "
                    "agent=%s/%s call_id=%s",
                    tenant_id, employee_id, customer_leg_id, exc_info=True,
                )
                alive = None
            if alive is False:
                logger.info(
                    "republish call UI: skip agent=%s/%s call_id=%s "
                    "(customer leg not in kernel)",
                    tenant_id, employee_id, customer_leg_id,
                )
                try:
                    await self.finalize_agent_call(
                        tenant_id=tenant_id,
                        employee_id=employee_id,
                        call_id=customer_leg_id,
                        reason="media_timeout",
                        mark_cdr_completed=True,
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "republish call UI: finalize after dead customer failed "
                        "agent=%s/%s call_id=%s",
                        tenant_id, employee_id, customer_leg_id, exc_info=True,
                    )
                    try:
                        await _orch.CcAgentResourceService.force_release(
                            r, tenant_id, employee_id,
                            reason="republish_dead_customer_leg",
                        )
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "republish call UI: force_release failed "
                            "agent=%s/%s",
                            tenant_id, employee_id, exc_info=True,
                        )
                return

        payload = {
            "offer_id": offer_id,
            "call_id": call_id,
            "from": from_number,
            "to": to_number,
            "queue_id": queue_id,
            "direction": direction,
        }
        payload.update(workspace_context)
        if device_type:
            payload["device_type"] = device_type
        if call_type:
            payload["call_type"] = call_type
        if source_call_id:
            payload["source_call_id"] = source_call_id
        if answered_at is not None:
            payload["answered_at"] = (
                answered_at.isoformat()
                if hasattr(answered_at, "isoformat")
                else str(answered_at)
            )

        if state == "ringing":
            await self.notify_agent_incoming(
                tenant_id=tenant_id,
                employee_id=employee_id,
                payload=payload,
            )
            logger.info(
                "republish call UI: ringing agent=%s/%s call_id=%s offer_id=%s",
                tenant_id, employee_id, call_id, offer_id,
            )
            return

        # in_call: push restore metadata (not a fresh ring) so the browser does
        # not flash the incoming UI, then answered so phase stays/returns to
        # 通话中 (media may still need a fresh WebRTC leg).
        await self.notify_agent_incoming(
            tenant_id=tenant_id,
            employee_id=employee_id,
            payload={**payload, "restore": True},
        )
        await self.notify_agent_call_answered(
            tenant_id=tenant_id,
            employee_id=employee_id,
            call_id=call_id,
        )
        logger.info(
            "republish call UI: in_call agent=%s/%s call_id=%s",
            tenant_id, employee_id, call_id,
        )

    async def notify_agent_call_ended(
        self,
        *,
        tenant_id: int,
        employee_id: int,
        call_id: str,
        reason: str | None,
    ) -> None:
        await _orch.emit_to_agent(
            tenant_id=tenant_id,
            employee_id=employee_id,
            method=CcSocketEvent.CALL_HANGUP.value,
            payload={"call_id": call_id, "reason": reason},
        )

    async def notify_agent_call_answered(
        self, *, tenant_id: int, employee_id: int, call_id: str
    ) -> None:
        """Tell an agent's browser the call was answered on their physical phone.

        For SIP-phone agents the off-hook happens on the handset, not in the
        browser, so the workspace must be moved to 通话中 by this push instead of
        by a browser "接听" click.
        """
        await _orch.emit_to_agent(
            tenant_id=tenant_id,
            employee_id=employee_id,
            method=CcSocketEvent.CALL_ANSWERED.value,
            payload={"call_id": call_id},
        )

    async def notify_conference_participant_left(
        self, *, tenant_id: int, employee_id: int
    ) -> None:
        """Tell a conference host their participant left → collapse the 3-way."""
        await _orch.emit_to_agent(
            tenant_id=tenant_id,
            employee_id=employee_id,
            method=CcSocketEvent.CONFERENCE_PARTICIPANT_LEFT.value,
            payload={},
        )

    async def notify_agent_outbound_event(
        self,
        *,
        tenant_id: int,
        employee_id: int,
        method: str,
        payload: dict,
    ) -> None:
        """Push an outbound-lifecycle event to the agent's browser.

        Used for cc.outbound_ringing / cc.outbound_answered / cc.outbound_hangup.
        Same room/namespace convention as the inbound notifications.
        """
        await _orch.emit_to_agent(
            tenant_id=tenant_id,
            employee_id=employee_id,
            method=method,
            payload=payload,
        )

    async def notify_agent_control_result(
        self,
        *,
        tenant_id: int,
        employee_id: int,
        method: str,
        payload: dict,
    ) -> None:
        """Push a consult / transfer result to the initiating agent's browser.

        Used for cc.consult_result / cc.transfer_result so the initiator's UI
        leaves the "咨询中/转接中" state once the background ring resolves
        (target answered, declined, timed out, or errored). Same room/namespace
        convention as the inbound notifications.
        """
        await _orch.emit_to_agent(
            tenant_id=tenant_id,
            employee_id=employee_id,
            method=method,
            payload=payload,
        )


# Imported after the mixin class so this module can be imported directly
# without a circular-import error (orchestrator imports the mixins).
from app.services.call_center import orchestrator as _orch  # noqa: E402
