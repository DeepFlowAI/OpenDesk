"""
Internal (agent-to-agent) WebRTC consult / transfer.

When a consult or transfer target is a colleague whose current call device is
the Web phone (not a SIP extension), there is no extension to dial. Instead we
reuse the *inbound ring-on-demand* machinery: reserve the target agent's
call-center resource, ring their browser (`cc.call_incoming`), and let them
accept through the exact same `/current-call/accept` endpoint used for real
inbound calls. Accept returns the target's freshly-built WebRTC leg id, which
the caller then bridges into the consult / transfer.

Lifecycle & resource safety:
  - The target agent is reserved (`reserve_inbound`) so the queue engine won't
    also hand them a real inbound call while they're ringing for the consult.
  - Any failure path — push failed, timeout, decline, no answer — releases the
    reservation and cancels the offer so the agent is never left stuck.
  - No DB session is held while waiting for the target to answer: the wait runs
    on the orchestrator's offer Future (resolved off the request path when the
    target's browser accepts).
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import redis.asyncio as aioredis

from app.core.exceptions import ConflictError, ValidationError
from app.db.session import AsyncSessionLocal
from app.libs.telephony.base import BaseTelephonyClient
from app.services.agent_call_device_service import DEVICE_WEBRTC, AgentCallDeviceService
from app.services.cc_agent_resource_service import CcAgentResourceService

logger = logging.getLogger(__name__)

# How long the target agent's browser is allowed to ring before we give up,
# release the reservation, and report the consult/transfer failed.
_RING_TIMEOUT_SEC = 45.0


class InternalConsultService:
    """Ring a Web-phone colleague and hand back their answered WebRTC leg."""

    @staticmethod
    async def initiate_webrtc_consult(
        telephony: BaseTelephonyClient,
        r: aioredis.Redis,
        *,
        tenant_id: int,
        initiator_employee_id: int,
        target_employee_id: int,
        initiator_display: str | None = None,
        internal_call_id: str | None = None,
        call_type: str = "internal_consult",
        timeout_seconds: float = _RING_TIMEOUT_SEC,
    ) -> dict:
        """Ring `target_employee_id`'s browser and wait for them to accept.

        Returns ``{"ok": True, "target_webrtc_call_id": <leg>, "offer_id": ...}``
        once the target accepts (their `/current-call/accept` resolved the offer
        with the WebRTC leg id). Raises on every failure after releasing the
        reserved resource and cancelling the offer, so nothing leaks.
        """

        from app.services.call_center.orchestrator import get_orchestrator

        # 1. Target must currently be on the Web phone and it must be available.
        device = await InternalConsultService._resolve_target_device(
            tenant_id, target_employee_id
        )
        if device.get("device_type") != DEVICE_WEBRTC or not device.get("available"):
            raise ValidationError(
                "目标坐席当前不是可用的 Web 电话，无法发起浏览器呼叫"
            )

        offer_id = uuid.uuid4().hex
        # A synthetic call_id anchors the reservation to this internal offer so
        # it doesn't collide with any real customer call the target might get.
        resource_call_id = internal_call_id or f"internal:{offer_id}"

        # 2. Reserve the target so the queue engine excludes them (ringing state
        #    is auto-excluded). Failure means they're already busy / not ready.
        reserved = await CcAgentResourceService.reserve_inbound(
            r,
            tenant_id,
            target_employee_id,
            call_id=resource_call_id,
            offer_id=offer_id,
            queue_id=None,
            ttl_seconds=timeout_seconds,
        )
        if reserved is None:
            raise ConflictError("目标坐席正在通话或不可用")

        orchestrator = get_orchestrator()
        future = orchestrator.register_offer(offer_id)

        try:
            await CcAgentResourceService.mark_ringing(
                r,
                tenant_id,
                target_employee_id,
                offer_id=offer_id,
                call_id=resource_call_id,
                ttl_seconds=timeout_seconds,
            )
            pushed = await orchestrator.notify_agent_incoming(
                tenant_id=tenant_id,
                employee_id=target_employee_id,
                payload={
                    "offer_id": offer_id,
                    "call_id": resource_call_id,
                    "call_type": call_type,
                    "from": initiator_display or "",
                    "from_employee_id": initiator_employee_id,
                },
            )
            if not pushed:
                raise ConflictError("目标坐席不在线，无法振铃")

            decision = await asyncio.wait_for(future, timeout=timeout_seconds)
        except asyncio.TimeoutError:
            await InternalConsultService._release(
                orchestrator, r, tenant_id, target_employee_id, offer_id,
                reason="internal_offer_timeout",
            )
            raise ValidationError("目标坐席未接听")
        except (ConflictError, ValidationError):
            await InternalConsultService._release(
                orchestrator, r, tenant_id, target_employee_id, offer_id,
                reason="internal_offer_failed",
            )
            raise
        except Exception:  # noqa: BLE001
            await InternalConsultService._release(
                orchestrator, r, tenant_id, target_employee_id, offer_id,
                reason="internal_offer_error",
            )
            raise

        if not decision or not decision.get("accept"):
            await InternalConsultService._release(
                orchestrator, r, tenant_id, target_employee_id, offer_id,
                reason=(decision or {}).get("reason") or "declined",
            )
            raise ValidationError("目标坐席拒接")

        target_webrtc_call_id = decision.get("webrtc_call_id")
        if not target_webrtc_call_id:
            await InternalConsultService._release(
                orchestrator, r, tenant_id, target_employee_id, offer_id,
                reason="no_webrtc_leg",
            )
            raise ValidationError("目标坐席媒体腿建立失败")

        # 3. Target accepted. Their accept path already ran mark_in_call, but the
        #    resource was keyed on the ACCEPT's call_id; re-assert in_call keyed
        #    on our reservation so the target stays busy for the consult.
        await CcAgentResourceService.mark_in_call(
            r,
            tenant_id,
            target_employee_id,
            call_id=target_webrtc_call_id,
            direction="inbound",
        )

        logger.info(
            "internal consult accepted: initiator=%s target=%s target_leg=%s offer=%s",
            initiator_employee_id, target_employee_id, target_webrtc_call_id, offer_id,
        )
        return {
            "ok": True,
            "target_webrtc_call_id": target_webrtc_call_id,
            "target_employee_id": target_employee_id,
            "offer_id": offer_id,
        }

    @staticmethod
    async def _resolve_target_device(tenant_id: int, employee_id: int) -> dict:
        """Read the target agent's current call device on a short session."""

        async with AsyncSessionLocal() as db:
            return await AgentCallDeviceService.get_current_device(
                db, tenant_id, employee_id
            )

    @staticmethod
    async def _release(
        orchestrator,
        r: aioredis.Redis,
        tenant_id: int,
        employee_id: int,
        offer_id: str,
        *,
        reason: str,
    ) -> None:
        """Free the target's reservation and cancel the offer. Best-effort."""

        orchestrator.cancel_offer(offer_id)
        try:
            await CcAgentResourceService.release(
                r,
                tenant_id,
                employee_id,
                reason=reason,
                expected_offer_id=offer_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "internal consult release failed target=%s/%s reason=%s",
                tenant_id, employee_id, reason, exc_info=True,
            )
