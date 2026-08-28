"""Blind-transfer a live customer call into an employee-group queue.

The initiating agent leaves immediately (enqueue = success). A per-call
background task then polls for a ready agent, rings them (Web phone or SIP
extension), and bridges the customer when they answer. No ``queue_tasks`` row
is written — reservation uses the same Redis resource path as inbound queue
assign.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import suppress

from app.core.exceptions import BusinessError, NotFoundError
from app.libs.telephony.base import BaseTelephonyClient

logger = logging.getLogger(__name__)

_DEFAULT_WAIT_BUDGET_S = 60.0
_RETRY_INTERVAL_S = 5.0
_RING_TIMEOUT_S = 30.0
_QUEUE_TYPE = "employee_group"
_TIMEOUT_PROMPT = "抱歉，暂无客服接听，请稍后再拨。"


class QueueTransferMixin:
    # ───────────────────────── transfer to queue ─────────────────────────

    @staticmethod
    async def transfer_to_queue(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        queue_id: int,
    ) -> dict:
        """Blind-transfer the current customer into an employee-group queue.

        Validates the queue and availability synchronously, unbridges the
        customer from the initiator, plays the transfer tone once, starts the
        background wait/ring loop, then finalizes the initiator into wrap-up.
        Returns as soon as the customer is queued.
        """

        call = await _ccs.CallControlService._resolve_current_call(
            tenant_id, employee_id
        )
        operation_id = f"queue-transfer:{uuid.uuid4().hex}"
        from app.services.call_trajectory_service import CallTrajectoryService

        await CallTrajectoryService.append_for_call_id_best_effort(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            event_id=f"opendesk:transfer-started:{operation_id}",
            event_type="transfer_started",
            event_category="transfer",
            actor_type="agent",
            actor_id=str(employee_id),
            source="opendesk",
            operation_id=operation_id,
            target_type="queue",
            target_id=str(queue_id),
        )
        await _ccs.CallControlService._validate_queue_transfer_target(
            tenant_id, queue_id
        )

        # Unbridge BEFORE starting the background task. If this fails the
        # request fails and the customer stays with the initiator.
        if call.webrtc_call_id:
            await telephony.call_unbridge(
                call.customer_call_id, call.webrtc_call_id
            )

        # Customer is genuinely queued from this point until a new agent bridges.
        from app.services.call_record_service import CallRecordService

        async with _ccs.AsyncSessionLocal() as db:
            await CallRecordService.bind_queue(
                db, tenant_id, call.customer_call_id, _QUEUE_TYPE, queue_id
            )

        await _ccs.CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="transfer",
        )

        from app.services.call_center.orchestrator import get_orchestrator

        orch = get_orchestrator()
        task = asyncio.create_task(
            _ccs.CallControlService._run_queue_transfer_wait(
                telephony,
                tenant_id=tenant_id,
                queue_id=queue_id,
                customer_call_id=call.customer_call_id,
                operation_id=operation_id,
                from_employee_id=employee_id,
            ),
            name=f"queue-transfer:{call.customer_call_id}",
        )
        orch.set_pending_queue_transfer(call.customer_call_id, task)

        # Customer is queued; release the initiator's own media leg. Desk-phone
        # agents have no browser teardown — without this hangup they stay
        # off-hook on an unbridged leg. Best-effort: hangup failure must not
        # undo a completed enqueue. Employee/external transfers hang up in
        # their own complete path, so this stays queue-transfer-only.
        if call.webrtc_call_id:
            try:
                await telephony.call_hangup(
                    call.webrtc_call_id, reason="transferred"
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "queue transfer: initiator leg hangup failed leg=%s",
                    call.webrtc_call_id, exc_info=True,
                )

        await _ccs.CallControlService._finalize_initiator_after_transfer(
            tenant_id=tenant_id,
            employee_id=employee_id,
            call=call,
            new_agent_id=None,
        )

        logger.info(
            "queue transfer: enqueued tenant=%s agent=%s customer=%s queue=%s",
            tenant_id, employee_id, call.customer_call_id, queue_id,
        )
        return {
            "ok": True,
            "call_id": call.customer_call_id,
            "note": "queued_target",
        }

    @staticmethod
    async def _validate_queue_transfer_target(
        tenant_id: int, queue_id: int
    ) -> None:
        """Ensure the employee group exists for this tenant and can take a call.

        Raises NotFoundError (404) when the group is missing / wrong tenant.
        Raises BusinessError (409) when Redis is unavailable or the queue has
        nobody available and nobody worth waiting for.
        """

        from app.repositories.employee_group_repository import EmployeeGroupRepository
        from app.services.call_center.orchestrator import _get_redis_client
        from app.services.call_center.queue import get_queue_picker
        from app.services.queue_resource_provider import (
            CallCenterResourceProvider,
            filter_ringable_call_center_candidates,
        )

        async with _ccs.AsyncSessionLocal() as db:
            group = await EmployeeGroupRepository.get_by_id(db, queue_id)
            if group is None or group.tenant_id != tenant_id:
                raise NotFoundError("队列不存在")

        r = _get_redis_client()
        if r is None:
            raise BusinessError(
                "该队列当前无人可接待",
                status_code=409,
            )

        async with _ccs.AsyncSessionLocal() as db:
            candidates = await CallCenterResourceProvider().list_candidates(
                db, r, tenant_id, _QUEUE_TYPE, queue_id
            )
            waitable = await get_queue_picker().has_agent_on_call_for_queue(
                db, tenant_id, _QUEUE_TYPE, queue_id, r
            )
        ringable = await filter_ringable_call_center_candidates(
            r, tenant_id, candidates
        )

        if not ringable and waitable is not True:
            raise BusinessError(
                "该队列当前无人可接待",
                status_code=409,
            )

    @staticmethod
    async def _run_queue_transfer_wait(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        queue_id: int,
        customer_call_id: str,
        operation_id: str | None = None,
        from_employee_id: int | None = None,
    ) -> None:
        """Background loop: pick → ring → bridge, until budget ends."""

        from app.services.call_center.orchestrator import (
            _get_redis_client,
            get_orchestrator,
        )

        operation_id = operation_id or f"queue-transfer:{uuid.uuid4().hex}"
        reserved_employee_id: int | None = None
        reserved_offer_id: str | None = None
        agent_leg_call_id: str | None = None
        incoming_pushed = False
        # Agents already tried (no-answer, bridge failure, skipped offline).
        # Keep them out of later picks for the rest of this transfer wait.
        failed_employee_ids: set[int] = set()

        try:
            budget = await _ccs.CallControlService._queue_transfer_wait_budget(
                tenant_id, queue_id
            )
            caller_number, called_number = (
                await _ccs.CallControlService._queue_transfer_customer_numbers(
                    tenant_id, customer_call_id
                )
            )
            waited = 0.0
            hold_started = False

            while waited < budget:
                if not await _ccs.CallControlService._queue_transfer_call_alive(
                    tenant_id, customer_call_id
                ):
                    logger.info(
                        "queue transfer: customer gone tenant=%s call=%s queue=%s",
                        tenant_id, customer_call_id, queue_id,
                    )
                    return

                # Updated as soon as an incoming is pushed so cancel / unexpected
                # errors during the ring wait still release with the right flag.
                pushed_out = [False]
                try:
                    r = _get_redis_client()
                    if r is None:
                        logger.warning(
                            "queue transfer: redis unavailable mid-wait "
                            "tenant=%s call=%s queue=%s",
                            tenant_id, customer_call_id, queue_id,
                        )
                        break

                    offer_id = uuid.uuid4().hex
                    pick = await _ccs.CallControlService._queue_transfer_pick_agent(
                        tenant_id=tenant_id,
                        queue_id=queue_id,
                        customer_call_id=customer_call_id,
                        offer_id=offer_id,
                        redis=r,
                        exclude_employee_ids=failed_employee_ids,
                    )
                    if pick is None:
                        logger.info(
                            "queue transfer: no ready agent tenant=%s call=%s "
                            "queue=%s waited=%.0fs",
                            tenant_id, customer_call_id, queue_id, waited,
                        )
                        # Hold tone loops in the media kernel; start it once,
                        # and only when the customer will actually wait.
                        if not hold_started:
                            await _ccs.CallControlService._play_scene_tone(
                                telephony,
                                tenant_id=tenant_id,
                                customer_call_id=customer_call_id,
                                scene="hold",
                            )
                            hold_started = True
                        t0 = time.monotonic()
                        await asyncio.sleep(_RETRY_INTERVAL_S)
                        waited += time.monotonic() - t0
                        continue

                    employee_id = int(pick["employee_id"])
                    reserved_employee_id = employee_id
                    reserved_offer_id = offer_id
                    agent_leg_call_id = None
                    incoming_pushed = False
                    logger.info(
                        "queue transfer: ringing agent=%s/%s call=%s queue=%s "
                        "offer=%s",
                        tenant_id, employee_id, customer_call_id, queue_id,
                        offer_id,
                    )

                    t0 = time.monotonic()
                    try:
                        (
                            answered,
                            agent_leg_call_id,
                            incoming_pushed,
                            agent_leg_is_webrtc,
                        ) = await _ccs.CallControlService._queue_transfer_ring_agent(
                            telephony,
                            tenant_id=tenant_id,
                            queue_id=queue_id,
                            customer_call_id=customer_call_id,
                            employee_id=employee_id,
                            offer_id=offer_id,
                            redis=r,
                            caller_number=caller_number,
                            called_number=called_number,
                            incoming_pushed_out=pushed_out,
                        )
                    except asyncio.CancelledError:
                        incoming_pushed = pushed_out[0]
                        await _ccs.CallControlService._queue_transfer_release_agent(
                            redis=r,
                            tenant_id=tenant_id,
                            employee_id=employee_id,
                            offer_id=offer_id,
                            reason="queue_transfer_cancelled",
                            agent_leg_call_id=agent_leg_call_id,
                            customer_call_id=customer_call_id,
                            incoming_pushed=incoming_pushed,
                        )
                        reserved_employee_id = None
                        reserved_offer_id = None
                        agent_leg_call_id = None
                        incoming_pushed = False
                        raise

                    waited += time.monotonic() - t0

                    if not answered:
                        failed_employee_ids.add(employee_id)
                        await _ccs.CallControlService._queue_transfer_release_agent(
                            redis=r,
                            tenant_id=tenant_id,
                            employee_id=employee_id,
                            offer_id=offer_id,
                            reason="queue_transfer_no_answer",
                            agent_leg_call_id=agent_leg_call_id,
                            customer_call_id=customer_call_id,
                            incoming_pushed=incoming_pushed,
                        )
                        reserved_employee_id = None
                        reserved_offer_id = None
                        agent_leg_call_id = None
                        incoming_pushed = False
                        continue

                    handed_over = (
                        await _ccs.CallControlService._queue_transfer_handover(
                            telephony,
                            tenant_id=tenant_id,
                            queue_id=queue_id,
                            customer_call_id=customer_call_id,
                            employee_id=employee_id,
                            agent_leg_call_id=agent_leg_call_id or "",
                            agent_leg_is_webrtc=agent_leg_is_webrtc,
                            offer_id=offer_id,
                            redis=r,
                        )
                    )
                    if handed_over:
                        from app.services.call_trajectory_service import CallTrajectoryService

                        await CallTrajectoryService.append_for_call_id_best_effort(
                            tenant_id=tenant_id,
                            call_id=customer_call_id,
                            event_id=f"opendesk:transfer-completed:{operation_id}",
                            event_type="transfer_completed",
                            event_category="transfer",
                            actor_type="agent" if from_employee_id is not None else "system",
                            actor_id=str(from_employee_id) if from_employee_id is not None else None,
                            source="opendesk",
                            operation_id=operation_id,
                            call_leg_id=agent_leg_call_id,
                            participant_role="transfer_target",
                            target_type="employee",
                            target_id=str(employee_id),
                            queue_type=_QUEUE_TYPE,
                            queue_id=queue_id,
                            result="succeeded",
                            reason_code="transfer_completed",
                        )
                        if from_employee_id is not None:
                            from app.services.call_record_service import CallRecordService

                            await CallRecordService.mark_reception_transferred_managed(
                                tenant_id=tenant_id,
                                call_id=customer_call_id,
                                from_agent_id=from_employee_id,
                                to_agent_id=employee_id,
                                operation_id=operation_id,
                                target_leg_id=agent_leg_call_id,
                            )
                        reserved_employee_id = None
                        reserved_offer_id = None
                        incoming_pushed = False
                        logger.info(
                            "queue transfer: handed over tenant=%s call=%s "
                            "queue=%s agent=%s",
                            tenant_id, customer_call_id, queue_id, employee_id,
                        )
                        return

                    failed_employee_ids.add(employee_id)
                    await _ccs.CallControlService._queue_transfer_release_agent(
                        redis=r,
                        tenant_id=tenant_id,
                        employee_id=employee_id,
                        offer_id=offer_id,
                        reason="queue_transfer_bridge_failed",
                        agent_leg_call_id=agent_leg_call_id,
                        customer_call_id=customer_call_id,
                        incoming_pushed=incoming_pushed,
                    )
                    reserved_employee_id = None
                    reserved_offer_id = None
                    agent_leg_call_id = None
                    incoming_pushed = False
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "queue transfer: unexpected error in wait loop "
                        "tenant=%s call=%s queue=%s",
                        tenant_id, customer_call_id, queue_id,
                    )
                    incoming_pushed = pushed_out[0]
                    if (
                        reserved_employee_id is not None
                        and reserved_offer_id is not None
                    ):
                        r = _get_redis_client()
                        if r is not None:
                            await _ccs.CallControlService._queue_transfer_release_agent(
                                redis=r,
                                tenant_id=tenant_id,
                                employee_id=reserved_employee_id,
                                offer_id=reserved_offer_id,
                                reason="queue_transfer_error",
                                agent_leg_call_id=agent_leg_call_id,
                                customer_call_id=customer_call_id,
                                incoming_pushed=incoming_pushed,
                            )
                        reserved_employee_id = None
                        reserved_offer_id = None
                        agent_leg_call_id = None
                        incoming_pushed = False
                    if not hold_started:
                        await _ccs.CallControlService._play_scene_tone(
                            telephony,
                            tenant_id=tenant_id,
                            customer_call_id=customer_call_id,
                            scene="hold",
                        )
                        hold_started = True
                    t0 = time.monotonic()
                    await asyncio.sleep(_RETRY_INTERVAL_S)
                    waited += time.monotonic() - t0

            await _ccs.CallControlService._queue_transfer_timeout_hangup(
                telephony,
                tenant_id=tenant_id,
                customer_call_id=customer_call_id,
                queue_id=queue_id,
            )
            from app.services.call_trajectory_service import CallTrajectoryService

            await CallTrajectoryService.append_for_call_id_best_effort(
                tenant_id=tenant_id,
                call_id=customer_call_id,
                event_id=f"opendesk:transfer-failed:{operation_id}",
                event_type="transfer_failed",
                event_category="transfer",
                actor_type="system",
                source="opendesk",
                operation_id=operation_id,
                target_type="queue",
                target_id=str(queue_id),
                queue_type=_QUEUE_TYPE,
                queue_id=queue_id,
                result="timeout",
                reason_code="queue_timeout",
            )
        except asyncio.CancelledError:
            logger.info(
                "queue transfer: cancelled tenant=%s call=%s queue=%s",
                tenant_id, customer_call_id, queue_id,
            )
            raise
        finally:
            if reserved_employee_id is not None and reserved_offer_id is not None:
                r = _get_redis_client()
                if r is not None:
                    await _ccs.CallControlService._queue_transfer_release_agent(
                        redis=r,
                        tenant_id=tenant_id,
                        employee_id=reserved_employee_id,
                        offer_id=reserved_offer_id,
                        reason="queue_transfer_cleanup",
                        agent_leg_call_id=agent_leg_call_id,
                        customer_call_id=customer_call_id,
                        incoming_pushed=incoming_pushed,
                    )
            with suppress(Exception):
                get_orchestrator().pop_pending_queue_transfer(customer_call_id)

    @staticmethod
    async def _queue_transfer_wait_budget(
        tenant_id: int, queue_id: int
    ) -> float:
        """Customer max wait in this queue (seconds).

        Uses the call-center queue policy ``max_wait_seconds`` as the customer's
        maximum queue wait. When unset, defaults to 60 seconds.
        """

        from app.enums import QueueChannel, QueueType
        from app.services.queue_service import QueuePolicyResolver

        async with _ccs.AsyncSessionLocal() as db:
            policy = await QueuePolicyResolver.resolve(
                db,
                tenant_id,
                channel=QueueChannel.CALL_CENTER.value,
                queue_type=QueueType.EMPLOYEE_GROUP.value,
                queue_id=queue_id,
            )
        raw = policy.get("max_wait_seconds")
        if raw is None:
            return _DEFAULT_WAIT_BUDGET_S
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return _DEFAULT_WAIT_BUDGET_S
        return value if value > 0 else _DEFAULT_WAIT_BUDGET_S

    @staticmethod
    async def _queue_transfer_call_alive(
        tenant_id: int, customer_call_id: str
    ) -> bool:
        """Whether the customer call record is still in an active state."""

        from sqlalchemy import select

        from app.models.call_record import CallRecord

        async with _ccs.AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(CallRecord.lifecycle_status).where(
                        CallRecord.tenant_id == tenant_id,
                        CallRecord.call_id == customer_call_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = (
                    await db.execute(
                        select(CallRecord.lifecycle_status).where(
                            CallRecord.tenant_id == tenant_id,
                            CallRecord.root_call_id == customer_call_id,
                        )
                    )
                ).scalar_one_or_none()
        if row is None:
            return False
        return row == "active"

    @staticmethod
    async def _queue_transfer_customer_numbers(
        tenant_id: int, customer_call_id: str
    ) -> tuple[str, str]:
        """Return (from_number, to_number) for the incoming popup, or empty strings."""

        from app.repositories.call_record_repository import CallRecordRepository

        async with _ccs.AsyncSessionLocal() as db:
            row = await CallRecordRepository.get_by_call_id(
                db, customer_call_id, tenant_id
            )
            if row is None:
                return "", ""
            if row.direction == "inbound":
                return (row.customer_number or "", row.service_number or "")
            return (row.service_number or "", row.customer_number or "")

    @staticmethod
    async def _queue_transfer_restore_in_progress(
        tenant_id: int, customer_call_id: str
    ) -> None:
        """The target CDR remains active across queue transfers."""
        del tenant_id, customer_call_id

    @staticmethod
    async def _queue_transfer_pick_agent(
        *,
        tenant_id: int,
        queue_id: int,
        customer_call_id: str,
        offer_id: str,
        redis,
        exclude_employee_ids: set[int] | None = None,
    ) -> dict | None:
        from app.services.call_center.queue import get_queue_picker

        async with _ccs.AsyncSessionLocal() as db:
            return await get_queue_picker().pick_ready_agent_for_queue(
                db,
                tenant_id,
                _QUEUE_TYPE,
                queue_id,
                redis,
                call_id=customer_call_id,
                offer_id=offer_id,
                ttl_seconds=_RING_TIMEOUT_S,
                exclude_employee_ids=exclude_employee_ids,
            )

    @staticmethod
    async def _queue_transfer_ring_agent(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        queue_id: int,
        customer_call_id: str,
        employee_id: int,
        offer_id: str,
        redis,
        caller_number: str = "",
        called_number: str = "",
        incoming_pushed_out: list[bool] | None = None,
    ) -> tuple[bool, str | None, bool, bool]:
        """Ring one reserved agent.

        Returns ``(answered, agent_leg_call_id, incoming_pushed, leg_is_webrtc)``.
        ``incoming_pushed_out`` is updated as soon as an incoming is pushed so
        a cancel during the ring wait still sees the correct flag.
        """

        from app.services.agent_call_device_service import (
            DEVICE_SIP_PHONE,
            AgentCallDeviceService,
        )

        async with _ccs.AsyncSessionLocal() as db:
            current = await AgentCallDeviceService.get_current_device(
                db, tenant_id, employee_id, redis
            )
        if current.get("device_type") == DEVICE_SIP_PHONE:
            return await _ccs.CallControlService._queue_transfer_ring_sip(
                telephony,
                tenant_id=tenant_id,
                queue_id=queue_id,
                customer_call_id=customer_call_id,
                employee_id=employee_id,
                offer_id=offer_id,
                redis=redis,
                caller_number=caller_number,
                called_number=called_number,
                incoming_pushed_out=incoming_pushed_out,
            )
        return await _ccs.CallControlService._queue_transfer_ring_webrtc(
            tenant_id=tenant_id,
            queue_id=queue_id,
            customer_call_id=customer_call_id,
            employee_id=employee_id,
            offer_id=offer_id,
            redis=redis,
            caller_number=caller_number,
            called_number=called_number,
            incoming_pushed_out=incoming_pushed_out,
        )

    @staticmethod
    async def _queue_transfer_ring_sip(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        queue_id: int,
        customer_call_id: str,
        employee_id: int,
        offer_id: str,
        redis,
        caller_number: str = "",
        called_number: str = "",
        incoming_pushed_out: list[bool] | None = None,
    ) -> tuple[bool, str | None, bool, bool]:
        from app.repositories.sip_extension_repository import SipExtensionRepository
        from app.services.agent_call_device_service import DEVICE_SIP_PHONE
        from app.services.call_center.orchestrator import get_orchestrator
        from app.services.cc_agent_resource_service import CcAgentResourceService

        orchestrator = get_orchestrator()
        incoming_pushed = False

        async with _ccs.AsyncSessionLocal() as db:
            ext = await SipExtensionRepository.get_by_employee(
                db, tenant_id, employee_id
            )
            if (
                ext is not None
                and ext.current_occupant_employee_id != employee_id
            ):
                ext = None
            sip_user_id = (
                ext.sip_user_id
                if ext is not None
                and ext.is_active
                and ext.registration_status == "registered"
                else None
            )

        if not sip_user_id:
            logger.warning(
                "queue transfer: SIP extension unavailable agent=%s/%s call=%s",
                tenant_id, employee_id, customer_call_id,
            )
            return False, None, False, False

        try:
            await CcAgentResourceService.mark_ringing(
                redis,
                tenant_id,
                employee_id,
                offer_id=offer_id,
                call_id=customer_call_id,
                ttl_seconds=_RING_TIMEOUT_S,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "queue transfer: SIP mark_ringing failed agent=%s/%s call=%s",
                tenant_id, employee_id, customer_call_id,
            )
            return False, None, False, False

        try:
            result = await telephony.call_originate(extension=sip_user_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "queue transfer: SIP originate failed agent=%s/%s call=%s",
                tenant_id, employee_id, customer_call_id,
                exc_info=True,
            )
            return False, None, False, False

        agent_leg = (result or {}).get("call_id")
        if not agent_leg:
            return False, None, False, False

        waiter = orchestrator.register_leg_wait(agent_leg)
        orchestrator.set_pending_sip_originate(customer_call_id, agent_leg)
        try:
            await orchestrator.notify_agent_incoming(
                tenant_id=tenant_id,
                employee_id=employee_id,
                payload={
                    "offer_id": offer_id,
                    "call_id": customer_call_id,
                    "from": caller_number,
                    "to": called_number,
                    "queue_type": _QUEUE_TYPE,
                    "queue_id": queue_id,
                    "device_type": DEVICE_SIP_PHONE,
                },
            )
            incoming_pushed = True
            if incoming_pushed_out is not None:
                incoming_pushed_out[0] = True
        except Exception:  # noqa: BLE001
            logger.exception(
                "queue transfer: SIP incoming notify failed agent=%s/%s call=%s",
                tenant_id, employee_id, customer_call_id,
            )

        try:
            decision = await asyncio.wait_for(waiter, timeout=_RING_TIMEOUT_S)
        except asyncio.TimeoutError:
            decision = {"answered": False}
            orchestrator.cancel_leg_wait(agent_leg)
            with suppress(Exception):
                await telephony.call_hangup(agent_leg, reason="no_answer")
        except asyncio.CancelledError:
            orchestrator.cancel_leg_wait(agent_leg)
            with suppress(Exception):
                await telephony.call_hangup(agent_leg, reason="queue_transfer_cancelled")
            raise
        finally:
            orchestrator.pop_pending_sip_originate(customer_call_id)

        if not decision.get("answered"):
            logger.info(
                "queue transfer: SIP no answer agent=%s/%s call=%s",
                tenant_id, employee_id, customer_call_id,
            )
            return False, agent_leg, incoming_pushed, False

        try:
            await orchestrator.notify_agent_call_answered(
                tenant_id=tenant_id,
                employee_id=employee_id,
                call_id=customer_call_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "queue transfer: SIP answered notify failed agent=%s/%s call=%s",
                tenant_id, employee_id, customer_call_id,
            )
        return True, agent_leg, incoming_pushed, False

    @staticmethod
    async def _queue_transfer_ring_webrtc(
        *,
        tenant_id: int,
        queue_id: int,
        customer_call_id: str,
        employee_id: int,
        offer_id: str,
        redis,
        caller_number: str = "",
        called_number: str = "",
        incoming_pushed_out: list[bool] | None = None,
    ) -> tuple[bool, str | None, bool, bool]:
        from app.services.agent_status_service import AgentStatusService
        from app.services.call_center.orchestrator import get_orchestrator
        from app.services.cc_agent_resource_service import CcAgentResourceService

        if not await AgentStatusService.is_connected(redis, tenant_id, employee_id):
            logger.warning(
                "queue transfer: WebRTC agent offline, skip ring "
                "agent=%s/%s call=%s",
                tenant_id, employee_id, customer_call_id,
            )
            return False, None, False, True

        orchestrator = get_orchestrator()
        future = orchestrator.register_offer(offer_id)

        try:
            pushed = await orchestrator.notify_agent_incoming(
                tenant_id=tenant_id,
                employee_id=employee_id,
                payload={
                    "offer_id": offer_id,
                    "call_id": customer_call_id,
                    "from": caller_number,
                    "to": called_number,
                    "queue_type": _QUEUE_TYPE,
                    "queue_id": queue_id,
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "queue transfer: WebRTC notify failed agent=%s/%s call=%s",
                tenant_id, employee_id, customer_call_id,
            )
            pushed = False

        if not pushed:
            orchestrator.cancel_offer(offer_id)
            return False, None, False, True

        if incoming_pushed_out is not None:
            incoming_pushed_out[0] = True

        try:
            await CcAgentResourceService.mark_ringing(
                redis,
                tenant_id,
                employee_id,
                offer_id=offer_id,
                call_id=customer_call_id,
                ttl_seconds=_RING_TIMEOUT_S,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "queue transfer: WebRTC mark_ringing failed agent=%s/%s call=%s",
                tenant_id, employee_id, customer_call_id,
            )
            orchestrator.cancel_offer(offer_id)
            return False, None, True, True

        try:
            decision = await asyncio.wait_for(future, timeout=_RING_TIMEOUT_S)
        except asyncio.TimeoutError:
            decision = None
            orchestrator.cancel_offer(offer_id)
        except asyncio.CancelledError:
            orchestrator.cancel_offer(offer_id)
            raise

        if not decision or not decision.get("accept"):
            logger.info(
                "queue transfer: WebRTC no accept agent=%s/%s call=%s decision=%s",
                tenant_id, employee_id, customer_call_id, decision,
            )
            return False, None, True, True

        webrtc_call_id = decision.get("webrtc_call_id")
        if not webrtc_call_id:
            return False, None, True, True
        return True, str(webrtc_call_id), True, True

    @staticmethod
    async def _queue_transfer_handover(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        queue_id: int,
        customer_call_id: str,
        employee_id: int,
        agent_leg_call_id: str,
        offer_id: str,
        redis,
        agent_leg_is_webrtc: bool = False,
    ) -> bool:
        """Bridge customer to the answering agent and persist ownership.

        Returns False when the bridge fails so the wait loop can try another
        agent without dropping the customer.
        """

        from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
        from app.services.call_center.orchestrator import get_orchestrator
        from app.services.cc_agent_resource_service import CcAgentResourceService
        from app.services.cc_agent_status_service import CcAgentStatusService
        from app.services.system_settings_service import SystemSettingsService

        await _ccs.CallControlService._stop_tone(telephony, customer_call_id)

        transcribe = await SystemSettingsService.is_bridge_asr_enabled_managed(
            tenant_id
        )
        try:
            await telephony.call_bridge(
                customer_call_id,
                agent_leg_call_id,
                transcribe=transcribe,
                keepalive_on_peer_hangup=agent_leg_is_webrtc,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "queue transfer: bridge failed call=%s agent=%s/%s leg=%s",
                customer_call_id, tenant_id, employee_id, agent_leg_call_id,
            )
            return False

        async with _ccs.AsyncSessionLocal() as db:
            await CcAgentStatusService.set_status(
                db, tenant_id, employee_id, "busy", None
            )
            await AgentWebRTCSessionService.set_busy(
                db, tenant_id, employee_id, busy=True
            )

        await _ccs.CallControlService._queue_transfer_restore_in_progress(
            tenant_id, customer_call_id
        )

        await _ccs.CallControlService._reassign_call_record_to_agent(
            tenant_id, customer_call_id, employee_id
        )

        try:
            await CcAgentResourceService.mark_in_call(
                redis,
                tenant_id,
                employee_id,
                call_id=customer_call_id,
                direction="inbound",
                offer_id=offer_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "queue transfer: mark_in_call failed agent=%s/%s call=%s",
                tenant_id, employee_id, customer_call_id, exc_info=True,
            )

        try:
            await _ccs.CallControlService.bind_agent_media_leg(
                tenant_id, employee_id, agent_leg_call_id
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "queue transfer: bind media leg failed agent=%s/%s leg=%s",
                tenant_id, employee_id, agent_leg_call_id, exc_info=True,
            )

        orch = get_orchestrator()
        try:
            wf = orch.active_workflow(customer_call_id)
            if wf is not None:
                wf.rebind_bridged_agent(employee_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "queue transfer: rebind bridged agent failed call=%s agent=%s",
                customer_call_id, employee_id, exc_info=True,
            )

        try:
            await orch.republish_agent_call_ui(
                tenant_id=tenant_id, employee_id=employee_id
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "queue transfer: republish call UI failed agent=%s/%s call=%s",
                tenant_id, employee_id, customer_call_id, exc_info=True,
            )
        return True

    @staticmethod
    async def _queue_transfer_release_agent(
        *,
        redis,
        tenant_id: int,
        employee_id: int,
        offer_id: str,
        reason: str,
        agent_leg_call_id: str | None = None,
        customer_call_id: str = "",
        incoming_pushed: bool = False,
    ) -> None:
        from app.services.call_center.orchestrator import get_orchestrator
        from app.services.cc_agent_resource_service import CcAgentResourceService

        orch = get_orchestrator()
        orch.cancel_offer(offer_id)
        if agent_leg_call_id:
            orch.cancel_leg_wait(agent_leg_call_id)
            # Best-effort: stop a still-ringing SIP handset.
            telephony = getattr(orch, "telephony", None)
            if telephony is not None:
                with suppress(Exception):
                    await telephony.call_hangup(agent_leg_call_id, reason=reason)
        try:
            await CcAgentResourceService.release(
                redis,
                tenant_id,
                employee_id,
                reason=reason,
                expected_offer_id=offer_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "queue transfer: release failed agent=%s/%s reason=%s",
                tenant_id, employee_id, reason, exc_info=True,
            )
        # Only clear an incoming the browser actually showed — an idle agent
        # must not be nudged into wrap-up.
        if not incoming_pushed:
            return
        try:
            await orch.notify_agent_call_ended(
                tenant_id=tenant_id,
                employee_id=employee_id,
                call_id=customer_call_id,
                reason=reason,
            )
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    async def _queue_transfer_timeout_hangup(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        customer_call_id: str,
        queue_id: int,
    ) -> None:
        logger.info(
            "queue transfer: wait budget exhausted tenant=%s call=%s queue=%s",
            tenant_id, customer_call_id, queue_id,
        )
        await _ccs.CallControlService._stop_tone(telephony, customer_call_id)
        with suppress(Exception):
            await telephony.call_play(
                customer_call_id,
                text=_TIMEOUT_PROMPT,
                loop=False,
            )
            await asyncio.sleep(2.0)
        with suppress(Exception):
            await telephony.call_hangup(
                customer_call_id, reason="queue_transfer_timeout"
            )


# Imported after the mixin class so this module can be imported directly
# without a circular-import error (call_control_service imports the mixins).
from app.services.call_center import call_control_service as _ccs  # noqa: E402
