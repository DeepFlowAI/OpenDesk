"""
Outbound WebRTC leg bootstrap.

The agent presses dial → POST /agents/me/dial returns the outbound SIP
call_id immediately (carrier hasn't answered yet). The browser then runs
getUserMedia + createOffer and POSTs the SDP here.

We forward the SDP to FlowKit (`webrtc.offer`), which builds a WebRTC leg
and returns its own call_id + answer SDP. We register the pairing
(outbound_sip_call_id → webrtc_call_id) with the orchestrator so that
when `call.answered` fires for the SIP leg, the orchestrator calls
`call.bridge(sip_call_id, webrtc_call_id)` and audio starts flowing
instantly without an extra UI step.
"""
from __future__ import annotations

import logging

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.libs.telephony import BaseTelephonyClient


class OutboundCallEndedError(BusinessError):
    """410 Gone — outbound SIP leg ended before the WebRTC handshake could
    complete (commonly fires when a carrier rejects in <50ms, faster than
    the agent's browser can run getUserMedia + createOffer)."""

    def __init__(self, reason: str | None, sip_status: int | None):
        detail = {"reason": reason, "sip_status": sip_status}
        super().__init__(
            "Outbound call already ended",
            status_code=410,
            code="OUTBOUND_CALL_ENDED",
            details=detail,
        )


logger = logging.getLogger(__name__)


class OutboundWebRTCService:

    @staticmethod
    async def attach(
        telephony: BaseTelephonyClient,
        *,
        tenant_pk: int,
        employee_id: int,
        outbound_call_id: str,
        sdp: str,
    ) -> dict:
        from app.services.call_center.orchestrator import get_orchestrator

        if not outbound_call_id:
            raise ValidationError("outbound_call_id required")
        if not sdp:
            raise ValidationError("sdp required")

        orchestrator = get_orchestrator()
        info = orchestrator._peek_outbound_originator(outbound_call_id)
        if info is None:
            raise NotFoundError("outbound call not found")
        owner_tenant, owner_employee, _did = info
        if (owner_tenant, owner_employee) != (tenant_pk, employee_id):
            # Don't leak that the call exists — return 404 for non-owners.
            raise NotFoundError("outbound call not found")

        # Race guard: carrier may have already rejected before the browser
        # finished getUserMedia + SDP. Return 410 so the frontend can show
        # the actual SIP reason instead of a generic "通道连接失败".
        ended = orchestrator.outbound_ended_reason(outbound_call_id)
        if ended is not None:
            reason, sip_status = ended
            raise OutboundCallEndedError(reason=reason, sip_status=sip_status)

        result = await telephony.webrtc_offer(sdp)
        webrtc_call_id = result.get("call_id")
        answer_sdp = result.get("sdp")
        if not webrtc_call_id or not answer_sdp:
            raise ValidationError("FlowKit webrtc.offer returned incomplete payload")

        # webrtc.offer leaves the leg in `idle` state. FlowKit's call.bridge
        # requires both legs in `active`, so advance this one now — mirrors
        # what the inbound /current-call/accept path does for inbound calls.
        # Skip silently on state-already-active errors (idempotent kernels).
        try:
            await telephony.call_answer(webrtc_call_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "outbound webrtc call.answer failed (continuing): %s", exc,
            )

        orchestrator.pair_outbound_webrtc(
            outbound_call_id=outbound_call_id,
            webrtc_call_id=webrtc_call_id,
        )
        logger.info(
            "outbound webrtc paired: sip=%s webrtc=%s tenant=%s employee=%s",
            outbound_call_id, webrtc_call_id, tenant_pk, employee_id,
        )
        return {"webrtc_call_id": webrtc_call_id, "sdp": answer_sdp}
