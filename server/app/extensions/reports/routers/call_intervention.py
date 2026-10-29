"""Supervisor call-intervention router.

Live-call list (GET) plus the five intervention actions (POST). The page
permission ``call.monitor.view`` gates every endpoint; the per-action
permission (listen / whisper / barge / takeover / force_hangup), data scope,
phase capability and concurrency are enforced inside the service.

Intervention endpoints do telephony RPC (a network round-trip). They
authenticate with the short-session permission dep so no pooled DB connection
is held across the kernel call — the service opens its own short sessions only
around DB reads/writes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import (
    get_current_principal_short_session,
    get_db,
    get_redis,
    require_permission,
    require_permission_short_session,
)
from app.libs.telephony import get_telephony_client
from app.schemas.permission import EffectivePrincipal

from ..schemas import (
    InterventionReasonRequest,
    InterventionResult,
    LiveCallsResponse,
    SupervisorIceRequest,
    SupervisorWebRTCOfferRequest,
    SupervisorWebRTCOfferResponse,
)
from ..services import live_calls_service
from ..services.call_intervention_service import CallInterventionService

router = APIRouter(prefix="/reports/call-monitor/live", tags=["Reports"])


async def _optional_redis():
    """Redis if configured, else None (in-process lock fallback)."""

    try:
        return await get_redis()
    except Exception:  # noqa: BLE001 — Redis not configured in this deployment
        return None


@router.get("/calls", response_model=LiveCallsResponse)
async def list_live_calls(
    db: AsyncSession = Depends(get_db),
    redis=Depends(_optional_redis),
    principal: EffectivePrincipal = Depends(require_permission("call.monitor.view")),
) -> dict:
    """Data-scope-filtered list of in-progress calls the supervisor may monitor."""

    return await live_calls_service.get_live_calls(db, redis, principal)


@router.post("/calls/{call_id}/listen", response_model=InterventionResult)
async def listen_call(
    call_id: str,
    redis=Depends(_optional_redis),
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.monitor.view")
    ),
) -> dict:
    """Enter listen-only mode on the target call."""

    return await CallInterventionService.listen(
        get_telephony_client(), redis, principal, call_id
    )


@router.post(
    "/calls/{call_id}/webrtc/offer", response_model=SupervisorWebRTCOfferResponse
)
async def supervisor_webrtc_offer(
    call_id: str,
    body: SupervisorWebRTCOfferRequest,
    redis=Depends(_optional_redis),
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.monitor.view")
    ),
) -> dict:
    """Negotiate the supervisor's own WebRTC media leg for a monitored call.

    Needed before whisper / barge / takeover so the supervisor is audible. The
    kernel round-trip holds no pooled DB connection (short-session dep).
    """

    return await CallInterventionService.register_supervisor_leg(
        get_telephony_client(), redis, principal, call_id, body.sdp
    )


@router.post("/calls/{call_id}/webrtc/ice")
async def supervisor_webrtc_ice(
    call_id: str,
    body: SupervisorIceRequest,
    redis=Depends(_optional_redis),
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.monitor.view")
    ),
) -> dict:
    """Trickle a browser ICE candidate to the supervisor's WebRTC leg.

    ``call_id`` is the target call; the supervisor's own media-leg id is resolved
    from the monitor holder. Short-session dep — the kernel round-trip holds no
    pooled DB connection.
    """

    candidate: dict = {"candidate": body.candidate}
    if body.sdp_mid is not None:
        candidate["sdpMid"] = body.sdp_mid
    if body.sdp_m_line_index is not None:
        candidate["sdpMLineIndex"] = body.sdp_m_line_index
    return await CallInterventionService.add_supervisor_ice(
        get_telephony_client(), redis, principal, call_id, candidate
    )


@router.post("/calls/{call_id}/whisper", response_model=InterventionResult)
async def whisper_call(
    call_id: str,
    redis=Depends(_optional_redis),
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.monitor.view")
    ),
) -> dict:
    """Whisper to the agent on the target call."""

    return await CallInterventionService.whisper(
        get_telephony_client(), redis, principal, call_id
    )


@router.post("/calls/{call_id}/barge", response_model=InterventionResult)
async def barge_call(
    call_id: str,
    redis=Depends(_optional_redis),
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.monitor.view")
    ),
) -> dict:
    """Barge into the target call as a third party."""

    return await CallInterventionService.barge(
        get_telephony_client(), redis, principal, call_id
    )


@router.post("/calls/{call_id}/takeover", response_model=InterventionResult)
async def takeover_call(
    call_id: str,
    body: InterventionReasonRequest,
    redis=Depends(_optional_redis),
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.monitor.view")
    ),
) -> dict:
    """Take over the target call from the agent (requires reason)."""

    CallInterventionService.validate_reason(body.reason, body.note)
    return await CallInterventionService.takeover(
        get_telephony_client(), redis, principal, call_id, body.reason, body.note
    )


@router.post("/calls/{call_id}/takeover/hangup", response_model=InterventionResult)
async def end_takeover_call(
    call_id: str,
    redis=Depends(_optional_redis),
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.monitor.view")
    ),
) -> dict:
    """End a call the supervisor has taken over (hang up the customer)."""

    return await CallInterventionService.end_takeover(
        get_telephony_client(), redis, principal, call_id
    )


@router.post("/calls/{call_id}/force-hangup", response_model=InterventionResult)
async def force_hangup_call(
    call_id: str,
    body: InterventionReasonRequest,
    redis=Depends(_optional_redis),
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.monitor.view")
    ),
) -> dict:
    """Force-end the whole call chain of the target call (requires reason)."""

    CallInterventionService.validate_reason(body.reason, body.note)
    return await CallInterventionService.force_hangup(
        get_telephony_client(), redis, principal, call_id, body.reason, body.note
    )


@router.post("/calls/{call_id}/stop", response_model=InterventionResult)
async def stop_monitoring(
    call_id: str,
    redis=Depends(_optional_redis),
    principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.monitor.view")
    ),
) -> dict:
    """Exit monitoring on the target call (does not affect the agent/customer)."""

    return await CallInterventionService.stop(
        get_telephony_client(), redis, principal, call_id
    )
