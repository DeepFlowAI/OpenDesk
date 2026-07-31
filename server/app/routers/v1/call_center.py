"""
Call-center workspace + history endpoints.

Note: the orchestrator-facing "pick idle agent from group" call also lives
here under /agent-status/group/{id}/online and is guarded by the call
workspace permission.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, status
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.deps import (
    get_current_user,
    get_current_principal,
    get_db,
    get_redis,
    require_permission,
    require_permission_short_session,
)
from app.db.session import AsyncSessionLocal
from app.schemas.permission import EffectivePrincipal
from app.libs.telephony import get_telephony_client
from app.schemas.call_control import (
    CallControlResult,
    ConferenceAddRequest,
    ConsultRequest,
    DtmfRequest,
    MuteRequest,
    TransferRequest,
)
from app.schemas.call_center import (
    AcceptOfferRequest,
    AcceptOfferResponse,
    AgentStatusResponse,
    AgentStatusUpdate,
    CallRecordDetail,
    CallRecordUserLinkRequest,
    CallTranscriptResponse,
    CallUserAssociationResponse,
    CallRecordListResponse,
    CancelOutboundRequest,
    ConsultableAgent,
    DialOutboundRequest,
    DialOutboundResponse,
    DialWebRTCOfferRequest,
    DialWebRTCOfferResponse,
    MediaReconnectRequest,
    MediaReconnectResponse,
    OnlineAgentList,
    RejectOfferRequest,
    TransferQueue,
    WebRTCIceRequest,
    WebRTCOfferRequest,
    WebRTCOfferResponse,
    WebRTCSessionOpenRequest,
    WebRTCSessionResponse,
)
from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
from app.services.call_center.outbound_dial_service import OutboundDialService
from app.services.call_center.outbound_webrtc_service import OutboundWebRTCService
from app.repositories.call_record_repository import CallRecordRepository
from app.services.call_record_service import CallRecordService
from app.services.call_transcript_service import CallTranscriptService
from app.services.call_user_association_service import CallUserAssociationService
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService
from app.services.tenant_phone_number_service import TenantPhoneNumberService
from app.schemas.tenant_phone_number import (
    TenantPhoneNumberListResponse,
    TenantPhoneNumberResponse,
    TenantPhoneNumberTagsUpdate,
)

router = APIRouter(prefix="/call-center", tags=["CallCenter"])


# ─────────── Agent status ───────────


@router.get(
    "/agent-status/me",
    response_model=AgentStatusResponse,
    dependencies=[Depends(require_permission("call.workspace.use"))],
)
async def get_my_agent_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    return await CcAgentStatusService.get_for_employee(
        db, current_user["tenant_id"], current_user["user_id"], r
    )


@router.put(
    "/agent-status/me",
    response_model=AgentStatusResponse,
    dependencies=[Depends(require_permission("call.workspace.use"))],
)
async def set_my_agent_status(
    body: AgentStatusUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    # Going "ready" requires an available current call device — enforced
    # server-side so it can't be bypassed by the client.
    if body.status == "ready":
        from app.services.agent_call_device_service import AgentCallDeviceService

        await AgentCallDeviceService.ensure_ready_allowed(
            db, current_user["tenant_id"], current_user["user_id"], r
        )
    return await CcAgentStatusService.set_status(
        db,
        current_user["tenant_id"],
        current_user["user_id"],
        body.status,
        body.reason,
        r,
    )


@router.post(
    "/agent-status/me/reset",
    response_model=AgentStatusResponse,
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def reset_my_agent_call_resource(
    current_user: dict = Depends(get_current_user),
    r: aioredis.Redis = Depends(get_redis),
):
    """Escape hatch for a stranded agent: one-click force-clean every place a
    stuck call can hide — WebRTC session + lingering kernel leg, all active call
    records, in-memory conference/consult legs, and the Redis call resource — so
    the agent can switch status again without any DB surgery.

    Uses short DB sessions around reads/writes; no session across telephony RPC.
    """
    return await CcAgentStatusService.reset_call_resource_managed(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
        r=r,
    )


@router.get(
    "/agent-status/group/{group_id}/online",
    response_model=OnlineAgentList,
    dependencies=[Depends(require_permission("call.workspace.use"))],
)
async def list_online_agents_for_group(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CcAgentStatusService.list_online_for_group(
        db, current_user["tenant_id"], group_id
    )


@router.get(
    "/agents/consultable",
    response_model=list[ConsultableAgent],
    dependencies=[Depends(require_permission("call.workspace.use"))],
)
async def list_consultable_agents(
    keyword: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Workspace agents (excluding the caller) that can be a consult /
    transfer / conference target, each with their live call-center status.
    Used by the in-call target picker."""
    return await CcAgentStatusService.list_consultable_agents(
        db,
        current_user["tenant_id"],
        current_user["user_id"],
        keyword,
        r,
    )


@router.get(
    "/transfer-queues",
    response_model=list[TransferQueue],
    dependencies=[Depends(require_permission("call.workspace.use"))],
)
async def list_transfer_queues(
    keyword: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Employee-group queues available as blind-transfer targets, each with
    a live count of agents who can take a call. Used by the in-call
    target picker."""
    return await CcAgentStatusService.list_transfer_queues(
        db,
        current_user["tenant_id"],
        keyword,
        r,
    )


# ─────────── Call records ───────────


@router.get(
    "/call-records",
    response_model=CallRecordListResponse,
    dependencies=[Depends(require_permission("call.record.view"))],
)
async def list_call_records(
    page: int = 1,
    per_page: int = 20,
    direction: str | None = None,
    agent_id: int | None = None,
    user_id: int | None = None,
    keyword: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    principal: EffectivePrincipal = Depends(require_permission("call.record.view")),
    db: AsyncSession = Depends(get_db),
):
    return await CallRecordService.get_paginated(
        db,
        principal.tenant_id,
        page,
        per_page,
        direction,
        agent_id,
        user_id,
        keyword,
        start_time,
        end_time,
        principal=principal,
    )


@router.get(
    "/call-records/{record_id}",
    response_model=CallRecordDetail,
    dependencies=[Depends(require_permission("call.record.view"))],
)
async def get_call_record(
    record_id: int,
    principal: EffectivePrincipal = Depends(require_permission("call.record.view")),
    db: AsyncSession = Depends(get_db),
):
    return await CallRecordService.get_by_id(db, record_id, principal.tenant_id, principal)


@router.get(
    "/call-records/{record_id}/transcript",
    response_model=CallTranscriptResponse,
    dependencies=[Depends(require_permission("call.record.view"))],
)
async def get_call_record_transcript(
    record_id: int,
    principal: EffectivePrincipal = Depends(require_permission("call.record.view")),
    db: AsyncSession = Depends(get_db),
):
    return await CallTranscriptService.get_for_record(
        db, record_id, principal.tenant_id, principal
    )


@router.post(
    "/call-records/{record_id}/identify-user",
    response_model=CallUserAssociationResponse,
    dependencies=[Depends(require_permission("call.record.view"))],
)
async def identify_call_record_user(
    record_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CallUserAssociationService.identify_for_record_id(
        db,
        current_user["tenant_id"],
        record_id,
        actor_id=current_user.get("user_id"),
    )


@router.put(
    "/call-records/{record_id}/associated-user",
    response_model=CallUserAssociationResponse,
    dependencies=[Depends(require_permission("call.record.view"))],
)
async def link_call_record_user(
    record_id: int,
    body: CallRecordUserLinkRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CallUserAssociationService.link_user(
        db,
        current_user["tenant_id"],
        record_id,
        body.user_id,
    )


# ─────────── Agent WebRTC session ───────────


@router.get(
    "/agents/me/webrtc-session",
    response_model=WebRTCSessionResponse | None,
    dependencies=[Depends(require_permission("call.workspace.use"))],
)
async def get_my_webrtc_session(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await AgentWebRTCSessionService.get_active(
        db, current_user["tenant_id"], current_user["user_id"]
    )


@router.post(
    "/agents/me/webrtc-session",
    response_model=WebRTCSessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("call.workspace.use"))],
)
async def open_my_webrtc_session(
    body: WebRTCSessionOpenRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await AgentWebRTCSessionService.open(
        db,
        current_user["tenant_id"],
        current_user["user_id"],
        body.webrtc_call_id,
    )


@router.delete(
    "/agents/me/webrtc-session",
    dependencies=[Depends(require_permission("call.workspace.use"))],
)
async def close_my_webrtc_session(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await AgentWebRTCSessionService.close(
            db, current_user["tenant_id"], current_user["user_id"]
        )
    except NotFoundError:
        # Idempotent close — no active session is OK
        return {"message": "No active session"}
    return {"message": "Closed"}


# ─────────── WebRTC signaling (Browser ↔ Backend ↔ Telephony kernel) ───────────


@router.post(
    "/agents/me/webrtc/offer",
    response_model=WebRTCOfferResponse,
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def webrtc_offer(
    body: WebRTCOfferRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Forward a browser SDP offer to the telephony kernel. The kernel responds
    with an SDP answer and a fresh call_id that uniquely identifies this
    agent's WebRTC leg — we persist that real call_id into the agent's
    AgentWebRTCSession so subsequent `call.bridge` calls reference the
    correct leg.

    DB session is not held across FlowKit RPCs (CLAUDE.md §8).
    """

    tenant_id = current_user["tenant_id"]
    employee_id = current_user["user_id"]
    telephony = get_telephony_client()
    result = await telephony.webrtc_offer(body.sdp)
    real_call_id = result.get("call_id", "")
    if not real_call_id:
        raise NotFoundError("Telephony kernel did not return a call_id")
    # Transition the leg from `idle` to `active`. FlowKit refuses
    # `call.bridge` while either leg is still in `idle`; without this
    # explicit answer the orchestrator's bridge call later fails with
    # `-32003 call state invalid: invalid state (active ↔ idle)`.
    try:
        await telephony.call_answer(real_call_id)
    except Exception:  # noqa: BLE001
        # A kernel that auto-answers WebRTC legs may reject this as a
        # duplicate; either way the upsert below records the leg.
        pass
    async with AsyncSessionLocal() as db:
        await AgentWebRTCSessionService.upsert_with_real_call_id(
            db, tenant_id, employee_id, real_call_id
        )
    return WebRTCOfferResponse(call_id=real_call_id, sdp=result.get("sdp", ""))


@router.post(
    "/agents/me/webrtc/ice",
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def webrtc_ice(
    body: WebRTCIceRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Forward a browser-side ICE candidate to the kernel.

    Failures are downgraded to 200 with `ok=false` so the browser doesn't
    treat them as fatal — ICE is best-effort signaling, and an unknown
    call_id on the kernel side just means that particular candidate can't
    be delivered (typical when the leg was torn down between the browser
    starting ICE gathering and the candidate arriving).
    """

    import asyncio
    import logging
    from app.libs.telephony.base import TelephonyRPCError

    log = logging.getLogger(__name__)
    _ = current_user  # auth enforced via dep

    telephony = get_telephony_client()
    candidate_init = {"candidate": body.candidate.candidate}
    if body.candidate.sdp_mid is not None:
        candidate_init["sdpMid"] = body.candidate.sdp_mid
    if body.candidate.sdp_m_line_index is not None:
        candidate_init["sdpMLineIndex"] = body.candidate.sdp_m_line_index
    try:
        # Tighter timeout than the default 30s — ICE is fire-and-forget
        # signaling; if the kernel doesn't respond in a few seconds, the
        # candidate is effectively lost and the browser will produce more.
        await asyncio.wait_for(
            telephony.webrtc_ice(body.call_id, candidate_init),
            timeout=5.0,
        )
        return {"ok": True}
    except TelephonyRPCError as e:
        log.info("webrtc.ice rejected by kernel: call_id=%s code=%s", body.call_id, e.code)
        return {"ok": False, "error": "rpc_error", "code": e.code, "message": e.args[0] if e.args else str(e)}
    except asyncio.TimeoutError:
        log.info("webrtc.ice timeout call_id=%s — kernel not responding, dropping", body.call_id)
        return {"ok": False, "error": "timeout"}


# ─────────── Current-call control (hangup / reject) ───────────


@router.post(
    "/agents/me/current-call/hangup",
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def hangup_current_call(
    current_user: dict = Depends(get_current_user),
):
    """
    Hang up whatever call the current agent is on.

    Delegated to the orchestrator, which tears down the agent's OWN WebRTC leg
    as well as the customer SIP leg and resets the agent's status. When the
    customer leg is already gone the orchestrator finalizes locally (no
    `call.hangup` event will arrive to drive cleanup), so the agent can always
    hang up and never gets stuck on 忙碌.
    """

    from app.services.call_center.orchestrator import get_orchestrator

    return await get_orchestrator().hangup_agent_current_call(
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
    )


# ─────────── In-call control (hold / dtmf / transfer / consult / conference) ───────────


@router.post(
    "/agents/me/current-call/hold",
    response_model=CallControlResult,
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def hold_current_call(current_user: dict = Depends(get_current_user)):
    """Put the current agent's customer on hold."""

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.hold(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
    )


@router.post(
    "/agents/me/current-call/unhold",
    response_model=CallControlResult,
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def unhold_current_call(current_user: dict = Depends(get_current_user)):
    """Resume the current agent's held customer."""

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.unhold(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
    )


@router.post(
    "/agents/me/current-call/dtmf",
    response_model=CallControlResult,
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def send_dtmf(
    body: DtmfRequest,
    current_user: dict = Depends(get_current_user),
):
    """Send DTMF digits into the current agent's live call."""

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.dtmf(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
        digits=body.digits,
    )


@router.post(
    "/agents/me/current-call/mute",
    response_model=CallControlResult,
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def set_mute(
    body: MuteRequest,
    current_user: dict = Depends(get_current_user),
):
    """Mute or unmute the agent's own leg of the current call.

    A browser agent also switches off its local track, which is faster and
    keeps working if this call fails; an agent on a SIP handset has no local
    track and depends on this entirely.
    """

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.mute(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
        muted=body.muted,
    )


@router.post(
    "/agents/me/current-call/transfer",
    response_model=CallControlResult,
    dependencies=[Depends(require_permission_short_session("call.operation.transfer"))],
)
async def transfer_current_call(
    body: TransferRequest,
    current_user: dict = Depends(get_current_user),
):
    """Blind-transfer the current call to an employee, queue or external number."""

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.transfer(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
        target_type=body.target_type,
        target_id=body.target_id,
        number=body.number,
    )


@router.post(
    "/agents/me/current-call/consult",
    response_model=CallControlResult,
    dependencies=[Depends(require_permission_short_session("call.operation.consult"))],
)
async def start_consult(
    body: ConsultRequest,
    current_user: dict = Depends(get_current_user),
):
    """Start a consultation: auto-hold the customer and call a third party."""

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.consult_start(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
        target_type=body.target_type,
        target_id=body.target_id,
        number=body.number,
    )


@router.post(
    "/agents/me/current-call/consult/end",
    response_model=CallControlResult,
    dependencies=[Depends(require_permission_short_session("call.operation.consult"))],
)
async def end_consult(current_user: dict = Depends(get_current_user)):
    """End the consultation: drop the third party and resume the customer."""

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.consult_end(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
    )


@router.post(
    "/agents/me/current-call/conference/add",
    response_model=CallControlResult,
    dependencies=[Depends(require_permission_short_session("call.operation.conference"))],
)
async def conference_add(
    body: ConferenceAddRequest,
    current_user: dict = Depends(get_current_user),
):
    """Call a new participant to (later) merge into a 3-way call."""

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.conference_add(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
        target_type=body.target_type,
        target_id=body.target_id,
        number=body.number,
    )


@router.post(
    "/agents/me/current-call/conference/merge",
    response_model=CallControlResult,
    dependencies=[Depends(require_permission_short_session("call.operation.conference"))],
)
async def conference_merge(current_user: dict = Depends(get_current_user)):
    """Merge the held customer, agent and participant into one 3-way call."""

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.conference_merge(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
    )


@router.post(
    "/agents/me/current-call/conference/remove",
    response_model=CallControlResult,
    dependencies=[Depends(require_permission_short_session("call.operation.conference"))],
)
async def conference_remove(current_user: dict = Depends(get_current_user)):
    """Remove the added participant from the conference."""

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.conference_remove(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
    )


@router.post(
    "/agents/me/current-call/conference/leave",
    response_model=CallControlResult,
    dependencies=[Depends(require_permission_short_session("call.operation.conference"))],
)
async def conference_leave(current_user: dict = Depends(get_current_user)):
    """Leave the conference; the customer and participant keep talking."""

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.conference_leave(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
    )


@router.post(
    "/agents/me/current-call/conference/end-all",
    response_model=CallControlResult,
    dependencies=[Depends(require_permission_short_session("call.operation.conference"))],
)
async def conference_end_all(current_user: dict = Depends(get_current_user)):
    """End the call for everyone in the conference."""

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.conference_end_all(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
    )


@router.post(
    "/agents/me/current-call/media-reconnect",
    response_model=MediaReconnectResponse,
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def media_reconnect(
    body: MediaReconnectRequest,
    current_user: dict = Depends(get_current_user),
):
    """Rebuild the agent's WebRTC media leg after refresh / media_eof.

    Preserves an active consultation (re-bridges to the consult target); otherwise
    bridges back to the customer. DB session is not held across FlowKit RPCs.
    """

    from app.services.call_center.call_control_service import CallControlService

    return await CallControlService.media_reconnect(
        get_telephony_client(),
        tenant_id=current_user["tenant_id"],
        employee_id=current_user["user_id"],
        sdp=body.sdp,
    )


@router.post(
    "/agents/me/current-call/accept",
    response_model=AcceptOfferResponse,
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def accept_offer(
    body: AcceptOfferRequest,
    current_user: dict = Depends(get_current_user),
    r: aioredis.Redis = Depends(get_redis),
):
    """
    Accept a ring-on-demand offer pushed by `assign_queue`.

    Steps in order:
      1. Forward the browser SDP to FlowKit via `webrtc.offer` → get back
         the kernel-side call_id (this is the agent's WebRTC leg).
      2. `call.answer` it so the leg transitions from idle → active.
         Without this `call.bridge` will fail with -32003.
      3. Persist the leg in `agent_webrtc_sessions` so hangup cleanup +
         CDR queries can find it.
      4. Resolve the orchestrator's pending offer Future so the workflow
         proceeds with `call.stop` + `call.bridge`.
      5. Return the SDP answer to the browser for `setRemoteDescription`.

    If the offer expired (timeout / already resolved), step 1's call_id is
    abandoned by best-effort cleanup; the response carries `ok=false`.

    DB session is not held across FlowKit RPCs (CLAUDE.md §8).

    FLOWKIT GAP: this endpoint is the Web-phone accept path (browser SDP →
    webrtc.offer → bridge). When the agent's current device is a SIP phone the
    inbound leg must ring the physical phone directly and auto-enter the call on
    off-hook — no browser accept. FlowKit exposes no "ring a registered
    extension endpoint" RPC yet, so that media path is not wired here. Until it
    lands, agents on a SIP phone should keep using the Web phone for inbound;
    the current-device selection is persisted and ready to drive this branch.
    """

    import logging
    from app.libs.telephony.base import TelephonyRPCError
    from app.services.call_center.orchestrator import get_orchestrator

    log = logging.getLogger(__name__)
    tenant_id = current_user["tenant_id"]
    employee_id = current_user["user_id"]
    telephony = get_telephony_client()

    async def fail_current_offer(reason: str) -> None:
        await CcAgentResourceService.release(
            r,
            tenant_id,
            employee_id,
            reason=reason,
            expected_offer_id=body.offer_id,
        )
        await get_orchestrator().deliver_offer_decision(
            body.offer_id, {"accept": False, "reason": reason}
        )

    offer_snapshot = await CcAgentResourceService.validate_offer(
        r, tenant_id, employee_id, offer_id=body.offer_id
    )
    if offer_snapshot is None:
        return AcceptOfferResponse(ok=False, error="offer_expired")

    accept_lock_token = await CcAgentResourceService.acquire_offer_accept_lock(
        r,
        tenant_id,
        body.offer_id,
        ttl_seconds=CcAgentResourceService.accept_lock_ttl_seconds(offer_snapshot),
    )
    if accept_lock_token is None:
        return AcceptOfferResponse(ok=False, error="offer_accept_in_progress")

    try:
        from app.services.call_center.internal_consult_service import (
            InternalConsultService,
        )

        # Internal consult/transfer: pin the new WebRTC leg to the customer's
        # FlowKit kernel so the subsequent bridge is same-node.
        affinity_call_id = await InternalConsultService.pop_offer_affinity(
            r, body.offer_id
        )
        try:
            if affinity_call_id:
                result = await telephony.webrtc_offer(
                    body.sdp, call_id=affinity_call_id
                )
            else:
                result = await telephony.webrtc_offer(body.sdp)
        except TelephonyRPCError as e:
            log.warning("accept_offer: webrtc.offer failed code=%s", e.code)
            await fail_current_offer("webrtc_offer_failed")
            return AcceptOfferResponse(ok=False, error=f"webrtc_offer_failed: {e.code}")
        except Exception:  # noqa: BLE001
            log.exception("accept_offer: webrtc.offer failed unexpectedly")
            await fail_current_offer("webrtc_offer_failed")
            raise
        call_id = result.get("call_id", "")
        if not call_id:
            await fail_current_offer("kernel_no_call_id")
            return AcceptOfferResponse(ok=False, error="kernel_no_call_id")

        try:
            await telephony.call_answer(call_id)
        except Exception:  # noqa: BLE001
            # Kernels that auto-answer reject duplicate answer as state-conflict;
            # safe to ignore — the upsert + bridge logic below still works.
            pass

        async with AsyncSessionLocal() as db:
            await AgentWebRTCSessionService.upsert_with_real_call_id(
                db, tenant_id, employee_id, call_id,
            )
            # Keep PG status in sync for consult targets (no assign_queue CDR
            # path) and inbound accepts alike — otherwise the workspace keeps
            # showing 就绪 while Redis is already in_call.
            from app.services.cc_agent_status_service import CcAgentStatusService

            await CcAgentStatusService.sync_pg_status(
                db, tenant_id, employee_id, "busy", None,
            )
            await AgentWebRTCSessionService.set_busy(
                db, tenant_id, employee_id, busy=True,
            )

        orchestrator = get_orchestrator()
        resolved = await orchestrator.deliver_offer_decision(
            body.offer_id, {"accept": True, "webrtc_call_id": call_id},
        )
        if not resolved:
            # Offer expired or unknown — best-effort: hang up the just-created
            # webrtc leg so we don't leak resources on the kernel.
            log.info("accept_offer: offer_id=%s already resolved/expired", body.offer_id)
            try:
                await telephony.call_hangup(call_id, reason="offer_expired")
            except Exception:  # noqa: BLE001
                pass
            await CcAgentResourceService.release(
                r,
                tenant_id,
                employee_id,
                reason="offer_expired",
                expected_offer_id=body.offer_id,
            )
            return AcceptOfferResponse(ok=False, error="offer_expired")

        await CcAgentResourceService.mark_in_call(
            r,
            tenant_id,
            employee_id,
            call_id=offer_snapshot.get("current_call_id") or call_id,
            direction="inbound",
            offer_id=body.offer_id,
        )

        return AcceptOfferResponse(ok=True, call_id=call_id, sdp=result.get("sdp", ""))
    finally:
        await CcAgentResourceService.release_offer_accept_lock(
            r, tenant_id, body.offer_id, accept_lock_token
        )


@router.post(
    "/agents/me/current-call/reject",
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def reject_offer(
    body: RejectOfferRequest,
    current_user: dict = Depends(get_current_user),
    r: aioredis.Redis = Depends(get_redis),
):
    """Reject a pending offer; the workflow exits via the timeout outlet."""

    from app.services.call_center.orchestrator import get_orchestrator

    tenant_id = current_user["tenant_id"]
    employee_id = current_user["user_id"]
    offer_snapshot = await CcAgentResourceService.validate_offer(
        r, tenant_id, employee_id, offer_id=body.offer_id
    )
    if offer_snapshot is None:
        return {"ok": False, "error": "offer_expired"}

    released = await CcAgentResourceService.release(
        r,
        tenant_id,
        employee_id,
        reason="rejected",
        expected_offer_id=body.offer_id,
    )
    if (
        released.get("last_release_reason") != "rejected"
        or released.get("resource_state") in {"reserved", "ringing", "in_call"}
    ):
        return {"ok": False, "error": "offer_expired"}

    orchestrator = get_orchestrator()
    await orchestrator.deliver_offer_decision(
        body.offer_id, {"accept": False, "reason": "rejected"}
    )
    return {"ok": True}


@router.post(
    "/agents/me/dial",
    response_model=DialOutboundResponse,
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def dial_outbound(
    body: DialOutboundRequest,
    current_user: dict = Depends(get_current_user),
    r: aioredis.Redis = Depends(get_redis),
):
    """Agent-initiated outbound call. Forwards to FlowKit `call.originate`
    after resolving the bound trunk_id and using the DID as caller_id.

    Uses short DB sessions around reads/writes; no session across RPC.
    """

    telephony = get_telephony_client()
    return await OutboundDialService.dial_managed(
        telephony,
        tenant_pk=current_user["tenant_id"],
        employee_id=current_user["user_id"],
        outbound_phone_number_id=body.outbound_phone_number_id,
        destination=body.destination,
        r=r,
    )


@router.post(
    "/agents/me/dial/cancel",
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def cancel_outbound(
    body: CancelOutboundRequest,
    current_user: dict = Depends(get_current_user),
    r: aioredis.Redis = Depends(get_redis),
):
    """Cancel an in-flight outbound call started by this agent.

    Safe to call even when the call has already ended — we only verify
    ownership when the call_id is still tracked; an unknown call_id falls
    through silently so the UI's "always reset on cancel" path doesn't
    surface server errors to the user when their click races with the
    carrier's hangup."""

    from app.services.call_center.orchestrator import get_orchestrator

    orchestrator = get_orchestrator()
    info = await orchestrator._peek_outbound_originator(body.call_id)
    if info is not None:
        owner_tenant, owner_employee, _did = info
        if (owner_tenant, owner_employee) != (
            current_user["tenant_id"], current_user["user_id"],
        ):
            # Belongs to a different agent — don't leak its existence.
            return {"ok": True}
    await orchestrator.cancel_outbound(body.call_id)
    released = await CcAgentResourceService.release(
        r,
        current_user["tenant_id"],
        current_user["user_id"],
        reason="agent_cancel",
        expected_call_id=body.call_id,
    )
    async with AsyncSessionLocal() as db:
        await CcAgentStatusService.sync_pg_status(
            db,
            current_user["tenant_id"],
            current_user["user_id"],
            released["visible_status"],
            None,
        )
    return {"ok": True}


@router.post(
    "/agents/me/dial-webrtc/offer",
    response_model=DialWebRTCOfferResponse,
    dependencies=[Depends(require_permission_short_session("call.workspace.use"))],
)
async def dial_webrtc_offer(
    body: DialWebRTCOfferRequest,
    current_user: dict = Depends(get_current_user),
):
    """Attach the agent's browser WebRTC leg to an in-flight outbound SIP
    call. Backend forwards the offer SDP to FlowKit, records the pairing,
    and returns the answer SDP so the browser can finish the handshake."""

    telephony = get_telephony_client()
    return await OutboundWebRTCService.attach(
        telephony,
        tenant_pk=current_user["tenant_id"],
        employee_id=current_user["user_id"],
        outbound_call_id=body.outbound_call_id,
        sdp=body.sdp,
    )


# ─────────── Tenant phone numbers (admin) ───────────


@router.get(
    "/phone-numbers",
    response_model=TenantPhoneNumberListResponse,
    dependencies=[Depends(require_permission("call.admin.number.manage"))],
)
async def list_tenant_phone_numbers(
    page: int = 1,
    per_page: int = 20,
    q: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TenantPhoneNumberService.list_for_tenant(
        db, current_user["tenant_id"], page, per_page, q
    )


@router.get(
    "/phone-numbers/{phone_number_id}",
    response_model=TenantPhoneNumberResponse,
    dependencies=[Depends(require_permission("call.admin.number.manage"))],
)
async def get_tenant_phone_number(
    phone_number_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TenantPhoneNumberService.get_for_tenant(
        db, current_user["tenant_id"], phone_number_id
    )


@router.put(
    "/phone-numbers/{phone_number_id}/tags",
    response_model=TenantPhoneNumberResponse,
    dependencies=[Depends(require_permission("call.admin.number.manage"))],
)
async def update_tenant_phone_number_tags(
    phone_number_id: str,
    body: TenantPhoneNumberTagsUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TenantPhoneNumberService.update_tags(
        db, current_user["tenant_id"], phone_number_id, body
    )
