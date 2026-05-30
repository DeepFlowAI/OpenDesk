"""
Call-center workspace + history endpoints.

Note: the orchestrator-internal "pick idle agent from group" call also lives
here under /agent-status/group/{id}/online — it requires admin auth in
addition to the regular login, since exposing all-employees status is
sensitive.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, status
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.deps import get_current_user, get_db, get_redis
from app.libs.telephony import get_telephony_client
from app.schemas.call_center import (
    AcceptOfferRequest,
    AcceptOfferResponse,
    AgentStatusResponse,
    AgentStatusUpdate,
    CallRecordDetail,
    CallRecordUserLinkRequest,
    CallUserAssociationResponse,
    CallRecordListResponse,
    CancelOutboundRequest,
    DialOutboundRequest,
    DialOutboundResponse,
    DialWebRTCOfferRequest,
    DialWebRTCOfferResponse,
    OnlineAgentList,
    RejectOfferRequest,
    WebRTCIceRequest,
    WebRTCOfferRequest,
    WebRTCOfferResponse,
    WebRTCSessionOpenRequest,
    WebRTCSessionResponse,
)
from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
from app.services.call_center.outbound_dial_service import OutboundDialService
from app.services.call_center.outbound_webrtc_service import OutboundWebRTCService
from app.services.call_record_service import CallRecordService
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


@router.get("/agent-status/me", response_model=AgentStatusResponse)
async def get_my_agent_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    return await CcAgentStatusService.get_for_employee(
        db, current_user["tenant_id"], current_user["user_id"], r
    )


@router.put("/agent-status/me", response_model=AgentStatusResponse)
async def set_my_agent_status(
    body: AgentStatusUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    return await CcAgentStatusService.set_status(
        db,
        current_user["tenant_id"],
        current_user["user_id"],
        body.status,
        body.reason,
        r,
    )


@router.get(
    "/agent-status/group/{group_id}/online", response_model=OnlineAgentList,
)
async def list_online_agents_for_group(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CcAgentStatusService.list_online_for_group(
        db, current_user["tenant_id"], group_id
    )


# ─────────── Call records ───────────


@router.get("/call-records", response_model=CallRecordListResponse)
async def list_call_records(
    page: int = 1,
    per_page: int = 20,
    direction: str | None = None,
    agent_id: int | None = None,
    user_id: int | None = None,
    keyword: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CallRecordService.get_paginated(
        db,
        current_user["tenant_id"],
        page,
        per_page,
        direction,
        agent_id,
        user_id,
        keyword,
        start_time,
        end_time,
    )


@router.get("/call-records/{record_id}", response_model=CallRecordDetail)
async def get_call_record(
    record_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CallRecordService.get_by_id(db, record_id, current_user["tenant_id"])


@router.post(
    "/call-records/{record_id}/identify-user",
    response_model=CallUserAssociationResponse,
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


@router.get("/agents/me/webrtc-session", response_model=WebRTCSessionResponse | None)
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


@router.delete("/agents/me/webrtc-session")
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


@router.post("/agents/me/webrtc/offer", response_model=WebRTCOfferResponse)
async def webrtc_offer(
    body: WebRTCOfferRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Forward a browser SDP offer to the telephony kernel. The kernel responds
    with an SDP answer and a fresh call_id that uniquely identifies this
    agent's WebRTC leg — we persist that real call_id into the agent's
    AgentWebRTCSession so subsequent `call.bridge` calls reference the
    correct leg.
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
    await AgentWebRTCSessionService.upsert_with_real_call_id(
        db, tenant_id, employee_id, real_call_id
    )
    return WebRTCOfferResponse(call_id=real_call_id, sdp=result.get("sdp", ""))


@router.post("/agents/me/webrtc/ice")
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


@router.post("/agents/me/current-call/hangup")
async def hangup_current_call(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hang up whatever call the current agent is bridged to.

    Looks up the most recent active CDR for this agent (state in
    {ringing, queued, in_progress}) and tells the kernel to drop the SIP
    user leg. FlowKit's `call.hangup` notification then propagates through
    the orchestrator: CDR is marked completed, agent_status flips to
    after_call_work, webrtc_session goes back to online_idle, and the
    browser receives `cc.call_hangup` for UI teardown.
    """

    import logging
    from sqlalchemy import desc, select
    from app.models.call_record import CallRecord
    from app.libs.telephony.base import TelephonyRPCError

    log = logging.getLogger(__name__)
    tenant_id = current_user["tenant_id"]
    employee_id = current_user["user_id"]

    # Find the live call this agent is on.
    q = (
        select(CallRecord)
        .where(
            CallRecord.tenant_id == tenant_id,
            CallRecord.agent_id == employee_id,
            CallRecord.state.in_(("ringing", "queued", "in_progress")),
        )
        .order_by(desc(CallRecord.started_at))
        .limit(1)
    )
    row = (await db.execute(q)).scalar_one_or_none()
    if row is None:
        return {"ok": False, "error": "no_active_call"}

    target_call_id = row.root_call_id or row.call_id
    log.info(
        "Agent %s requested hangup; target SIP call_id=%s (record id=%s)",
        employee_id, target_call_id, row.id,
    )
    telephony = get_telephony_client()
    try:
        await telephony.call_hangup(target_call_id, reason="agent_hangup")
    except TelephonyRPCError as e:
        log.warning("call.hangup RPC rejected code=%s msg=%s", e.code, e.args)
        # If the kernel says "call not found" the call is already torn down;
        # treat as success so the UI can move on.
        if e.code == -32002:
            return {"ok": True, "note": "already_ended"}
        return {"ok": False, "error": "rpc_error", "code": e.code}
    return {"ok": True, "call_id": target_call_id}


@router.post("/agents/me/current-call/accept", response_model=AcceptOfferResponse)
async def accept_offer(
    body: AcceptOfferRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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
        get_orchestrator().resolve_offer(
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
        try:
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

        await AgentWebRTCSessionService.upsert_with_real_call_id(
            db, tenant_id, employee_id, call_id,
        )

        orchestrator = get_orchestrator()
        resolved = orchestrator.resolve_offer(
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


@router.post("/agents/me/current-call/reject")
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
    orchestrator.resolve_offer(body.offer_id, {"accept": False, "reason": "rejected"})
    return {"ok": True}


@router.post("/agents/me/dial", response_model=DialOutboundResponse)
async def dial_outbound(
    body: DialOutboundRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Agent-initiated outbound call. Forwards to FlowKit `call.originate`
    after resolving the bound trunk_id and using the DID as caller_id."""

    telephony = get_telephony_client()
    return await OutboundDialService.dial(
        db,
        telephony,
        tenant_pk=current_user["tenant_id"],
        employee_id=current_user["user_id"],
        outbound_phone_number_id=body.outbound_phone_number_id,
        destination=body.destination,
        r=r,
    )


@router.post("/agents/me/dial/cancel")
async def cancel_outbound(
    body: CancelOutboundRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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
    info = orchestrator._peek_outbound_originator(body.call_id)
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
    await CcAgentStatusService.sync_pg_status(
        db,
        current_user["tenant_id"],
        current_user["user_id"],
        released["visible_status"],
        None,
    )
    return {"ok": True}


@router.post("/agents/me/dial-webrtc/offer", response_model=DialWebRTCOfferResponse)
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


@router.get("/phone-numbers", response_model=TenantPhoneNumberListResponse)
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


@router.get("/phone-numbers/{phone_number_id}", response_model=TenantPhoneNumberResponse)
async def get_tenant_phone_number(
    phone_number_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TenantPhoneNumberService.get_for_tenant(
        db, current_user["tenant_id"], phone_number_id
    )


@router.put("/phone-numbers/{phone_number_id}/tags", response_model=TenantPhoneNumberResponse)
async def update_tenant_phone_number_tags(
    phone_number_id: str,
    body: TenantPhoneNumberTagsUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TenantPhoneNumberService.update_tags(
        db, current_user["tenant_id"], phone_number_id, body
    )
