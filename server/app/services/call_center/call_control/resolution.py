"""Resolution of the agent's current call legs and media reconnect flows."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable

from sqlalchemy import desc, or_, select

from app.constants.call_center import (
    INCALL_LEGS_KEY_PREFIX,
    ConsultState,
)
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.libs.telephony.base import BaseTelephonyClient, TelephonyRPCError
from app.models.call_record import CallRecord
from app.services.call_center import consult_session

logger = logging.getLogger(__name__)


class ResolutionMixin:
    # ───────────────────────── resolution ─────────────────────────

    @staticmethod
    async def _customer_leg_alive_in_kernel(
        telephony: BaseTelephonyClient,
        customer_call_id: str,
    ) -> bool | None:
        """Delegate to telephony ``call_alive`` (three-state; ``None`` = fail open)."""

        try:
            return await telephony.call_alive(customer_call_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "customer leg alive check failed call_id=%s",
                customer_call_id,
                exc_info=True,
            )
            return None

    @staticmethod
    async def _customer_context_for_call(call: _ccs.CurrentCall) -> dict:
        """User/number snapshot from the initiator's active CDR for consult targets.

        The consulted agent's browser has only an internal synthetic call_id, so
        without this payload their user-info panel stays empty.
        """
        from app.repositories.call_record_repository import CallRecordRepository
        from app.repositories.user_repository import UserRepository

        ctx: dict = {"source_call_id": call.customer_call_id}
        async with _ccs.AsyncSessionLocal() as db:
            row = await CallRecordRepository.get_by_id(
                db, call.record_id, call.tenant_id
            )
            if row is None:
                row = await CallRecordRepository.get_by_call_id(
                    db, call.customer_call_id, call.tenant_id
                )
            if row is None:
                return ctx
            if row.direction == "inbound":
                ctx["customer_from"] = row.customer_number or ""
                ctx["customer_to"] = row.service_number or ""
            else:
                ctx["customer_from"] = row.service_number or ""
                ctx["customer_to"] = row.customer_number or ""
            user_id = getattr(row, "user_id", None)
            if user_id is not None:
                ctx["user_id"] = user_id
                user = await UserRepository.get_by_id(db, user_id)
                if user is not None and getattr(user, "public_id", None):
                    ctx["user_public_id"] = user.public_id
        return ctx

    @staticmethod
    async def _resolve_current_call(tenant_id: int, employee_id: int) -> _ccs.CurrentCall:
        """Find the agent's active customer leg + media leg.

        Raises NotFoundError when the agent has no active call. The short DB
        session is closed before the caller issues any kernel RPC.

        Prefers the live ``agent_media_call_id`` recorded at bridge time over
        ``AgentWebRTCSession`` — SIP-phone and per-call WebRTC legs diverge from
        the long-lived softphone presence session, and using the stale id makes
        consult/transfer ``call.bridge`` fail with "呼叫目标坐席失败".
        """

        async with _ccs.AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(CallRecord)
                    .where(
                        CallRecord.tenant_id == tenant_id,
                        or_(
                            CallRecord.last_serving_agent_id == employee_id,
                            CallRecord.initiator_agent_id == employee_id,
                        ),
                        CallRecord.lifecycle_status == "active",
                    )
                    .order_by(desc(CallRecord.started_at))
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("当前没有进行中的通话")
            record_call_id = row.call_id
            customer_call_id = row.root_call_id or row.call_id
            record_id = row.id
            session = await _ccs.AgentWebRTCSessionService.get_active(
                db, tenant_id, employee_id
            )
            session_leg = session["webrtc_call_id"] if session else None

        legs = await _ccs._legs(tenant_id, employee_id)

        # A new queue offer may already own the agent resource while an old
        # outbound CDR was left active by an early carrier rejection. Never
        # reconnect media to a different call than the resource currently
        # reserves/rings/serves.
        from app.services.call_center.orchestrator import _get_redis_client

        redis = _get_redis_client()
        if redis is not None:
            try:
                snapshot = await _ccs.CcAgentResourceService.get_snapshot(
                    redis, tenant_id, employee_id
                )
            except Exception:  # noqa: BLE001 — DB resolution remains available
                logger.warning(
                    "current call resource unreadable agent=%s/%s",
                    tenant_id,
                    employee_id,
                    exc_info=True,
                )
                snapshot = None
            resource_call_id = snapshot.get("current_call_id") if snapshot else None
            if resource_call_id and resource_call_id != record_call_id:
                raise NotFoundError("当前通话状态已变化，请重新接听")

        webrtc_call_id = legs.agent_media_call_id or session_leg

        return _ccs.CurrentCall(
            record_id=record_id,
            tenant_id=tenant_id,
            customer_call_id=customer_call_id,
            webrtc_call_id=webrtc_call_id,
        )

    @staticmethod
    async def bind_agent_media_leg(
        tenant_id: int,
        employee_id: int,
        agent_media_call_id: str,
        *,
        preserve_consult: bool = False,
        preserve_room: bool = False,
    ) -> None:
        """Record the live agent media leg after customer↔agent bridge.

        When the media leg changes for a new customer bridge, drop leftover
        consult/conference pointers from a prior call. Pass
        ``preserve_consult=True`` for mid-consult host media reconnect and
        ``preserve_room=True`` when replacing a leg inside an active room.
        """

        legs = await _ccs._legs(tenant_id, employee_id)
        if (
            not preserve_consult
            and not preserve_room
            and legs.agent_media_call_id != agent_media_call_id
            and (
                legs.consult_call_id
                or legs.conference_participant_call_id
                or legs.room_id
            )
        ):
            logger.info(
                "bind agent media: clearing stale multiparty state agent=%s/%s "
                "old_media=%s new_media=%s stale_consult=%s",
                tenant_id, employee_id, legs.agent_media_call_id,
                agent_media_call_id, legs.consult_call_id,
            )
            if consult_session.is_consult_active(legs):
                consult_session.apply(
                    legs,
                    to_state=ConsultState.NONE,
                    reason="bind_media_clear_stale",
                    tenant_id=tenant_id,
                    host_employee_id=employee_id,
                    consult_call_id=legs.consult_call_id,
                )
            legs.conference_participant_call_id = None
            legs.conference_target_employee_id = None
            legs.room_id = None
            legs.room_legs = []
        legs.agent_media_call_id = agent_media_call_id
        legs.customer_held = False
        await _ccs._save_legs(tenant_id, employee_id, legs)

    @staticmethod
    async def media_reconnect(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        sdp: str,
    ) -> dict:
        """Rebuild the agent's WebRTC leg after a browser refresh / media_eof.

        - Consult *target* (no CDR of their own): rebuild and re-bridge to the
          host's media leg.
        - Consult *host*: keep the customer on hold and re-bridge to the target.
        - Otherwise: bridge the new leg back to the customer.
        """

        if not sdp or not sdp.strip():
            raise ValidationError("sdp required")

        # Consult targets have Redis in_call but no CallRecord — try that first
        # so B's refresh does not 404 on "当前没有进行中的通话".
        host = await _ccs.CallControlService._find_consult_host_for_target(
            tenant_id, employee_id
        )
        if host is not None:
            return await _ccs.CallControlService._media_reconnect_consult_target(
                telephony,
                tenant_id=tenant_id,
                employee_id=employee_id,
                sdp=sdp,
                host=host,
            )

        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        customer_call_id = call.customer_call_id
        # Agent already left for after-call work; the customer is on a survey.
        # Re-bridging here would steal the IVR audio path mid-prompt.
        async with _ccs.AsyncSessionLocal() as db:
            from app.repositories.call_satisfaction_execution_repository import (
                CallSatisfactionExecutionRepository,
            )

            survey = await CallSatisfactionExecutionRepository.get_by_call_record_id(
                db, call.record_id
            )
            if survey is not None and survey.status in {"preparing", "in_progress"}:
                raise ConflictError("客户正在满意度调查中，无法恢复坐席媒体")
        legs = await _ccs._legs(tenant_id, employee_id)
        consult_call_id = legs.consult_call_id
        consult_target_employee_id = legs.consult_target_employee_id

        customer_alive = await _ccs.CallControlService._customer_leg_alive_in_kernel(
            telephony, customer_call_id
        )
        if customer_alive is False:
            logger.info(
                "media reconnect: customer leg gone in kernel agent=%s customer=%s",
                employee_id, customer_call_id,
            )
            from app.services.call_center.orchestrator import get_orchestrator

            await get_orchestrator().finalize_agent_call(
                tenant_id=tenant_id,
                employee_id=employee_id,
                call_id=customer_call_id,
                reason="media_timeout",
                mark_cdr_completed=True,
            )
            await _ccs._clear_legs(tenant_id, employee_id)
            raise NotFoundError("客户通话已结束，无法恢复坐席媒体")

        result = await telephony.webrtc_offer(sdp, call_id=customer_call_id)
        new_leg = result.get("call_id") or ""
        answer_sdp = result.get("sdp") or ""
        if not new_leg or not answer_sdp:
            raise ValidationError("webrtc.offer returned incomplete payload")

        try:
            await telephony.call_answer(new_leg)
        except Exception:  # noqa: BLE001
            # Kernels that auto-answer reject a duplicate answer — safe to ignore.
            pass

        # Replace the browser leg inside an existing room (supervisor
        # whisper/barge or a regular conference). A plain call.bridge would try
        # to transition the already-roomed customer from bridged -> bridged.
        stale = call.webrtc_call_id
        room_active = bool(legs.room_id)
        if room_active:
            replaced = False
            if stale and stale != new_leg:
                try:
                    await telephony.room_replace_leg(legs.room_id, stale, new_leg)
                    replaced = True
                except Exception:  # noqa: BLE001
                    # The old browser leg commonly reaches media_eof before the
                    # reconnect request, so the room may already have detached
                    # it. Adding the new leg is the correct recovery in that case.
                    logger.info(
                        "media reconnect: old room leg already detached; adding "
                        "new leg room=%s old=%s new=%s",
                        legs.room_id, stale, new_leg,
                    )
            if not replaced:
                try:
                    await telephony.room_add_leg(legs.room_id, new_leg)
                except TelephonyRPCError as exc:
                    if exc.code != -32002:
                        raise
                    # The kernel drops a room once fewer than two legs remain
                    # (a conference collapsed to 1:1 and the old browser leg
                    # then left), leaving the customer unroomed. Bridge the new
                    # leg to the customer directly instead.
                    logger.info(
                        "media reconnect: room gone; bridging customer directly "
                        "room=%s customer=%s new=%s",
                        legs.room_id, customer_call_id, new_leg,
                    )
                    room_active = False
            if room_active:
                legs.room_legs = [
                    new_leg if leg == stale else leg
                    for leg in legs.room_legs
                    if leg != new_leg
                ]
                if new_leg not in legs.room_legs:
                    legs.room_legs.append(new_leg)

        if stale and stale != new_leg:
            try:
                await telephony.call_hangup(stale, reason=_ccs._CONSULT_TARGET_REPLACED_REASON)
            except Exception:  # noqa: BLE001
                pass

        if room_active:
            pass
        elif consult_call_id:
            # Keep the customer held with the consult tone; only rebuild A↔B.
            try:
                await telephony.call_bridge(
                    new_leg,
                    consult_call_id,
                    keepalive_on_peer_hangup=True,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "media reconnect: consult re-bridge failed agent=%s "
                    "consult=%s — falling back to customer",
                    employee_id, consult_call_id,
                )
                await _ccs.CallControlService._drop_active_consult_for_reconnect(
                    telephony,
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    customer_call_id=customer_call_id,
                    agent_media_call_id=None,
                )
                await _ccs.CallControlService._stop_tone(telephony, customer_call_id)
                await telephony.call_bridge(
                    customer_call_id,
                    new_leg,
                    user_call_id=customer_call_id,
                    keepalive_on_peer_hangup=True,
                )
                consult_call_id = None
                consult_target_employee_id = None
        else:
            await _ccs.CallControlService._stop_tone(telephony, customer_call_id)
            await telephony.call_bridge(
                customer_call_id,
                new_leg,
                user_call_id=customer_call_id,
                keepalive_on_peer_hangup=True,
            )

        await _ccs.CallControlService.bind_agent_media_leg(
            tenant_id,
            employee_id,
            new_leg,
            preserve_consult=bool(consult_call_id),
            preserve_room=room_active,
        )

        async with _ccs.AsyncSessionLocal() as db:
            await _ccs.AgentWebRTCSessionService.upsert_with_real_call_id(
                db, tenant_id, employee_id, new_leg,
            )

        logger.info(
            "media reconnect: agent=%s customer=%s new_leg=%s consult=%s",
            employee_id, customer_call_id, new_leg, consult_call_id,
        )
        return {
            "call_id": new_leg,
            "sdp": answer_sdp,
            "consult_active": bool(consult_call_id),
            "consult_target_employee_id": consult_target_employee_id,
        }

    @staticmethod
    async def _find_consult_host_for_target(
        tenant_id: int, target_employee_id: int
    ) -> dict | None:
        """Return host agent + legs when ``target`` is their active consult peer."""

        return await _ccs.CallControlService._find_host_for_colleague(
            tenant_id, target_employee_id, _consult_leg_of
        )

    @staticmethod
    async def _find_colleague_leg(
        tenant_id: int, employee_id: int
    ) -> tuple[dict, str] | None:
        """Host + this agent's own leg when they joined a colleague's call as a
        consult target or conference participant (they own no call record)."""

        host = await _ccs.CallControlService._find_host_for_colleague(
            tenant_id, employee_id, _colleague_leg_of
        )
        if host is None:
            return None
        return host, _colleague_leg_of(host["legs"], employee_id)

    @staticmethod
    async def _find_host_for_colleague(
        tenant_id: int,
        target_employee_id: int,
        leg_of: Callable[[_ccs.InCallLegs, int], str | None],
    ) -> dict | None:
        """First host agent whose in-call legs give ``target`` a leg via ``leg_of``."""

        def matches(legs: _ccs.InCallLegs) -> bool:
            return bool(leg_of(legs, target_employee_id))

        for (tid, eid), legs in list(_ccs._in_call_state.items()):
            if tid == tenant_id and matches(legs):
                return {"tenant_id": tid, "employee_id": eid, "legs": legs}

        from app.services.call_center.orchestrator import _get_redis_client

        r = _get_redis_client()
        if r is None:
            return None
        try:
            keys = [
                k
                async for k in r.scan_iter(
                    match=f"{INCALL_LEGS_KEY_PREFIX}:{tenant_id}:*"
                )
            ]
        except Exception:  # noqa: BLE001
            logger.warning("find consult host: redis scan failed", exc_info=True)
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
            legs = _ccs.InCallLegs.from_dict(data)
            if not matches(legs):
                continue
            parts = str(key).split(":")
            if len(parts) < 5:
                continue
            try:
                host_id = int(parts[-1])
            except (TypeError, ValueError):
                continue
            _ccs._in_call_state[(tenant_id, host_id)] = legs
            return {"tenant_id": tenant_id, "employee_id": host_id, "legs": legs}
        return None

    @staticmethod
    async def _media_reconnect_consult_target(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        sdp: str,
        host: dict,
    ) -> dict:
        """Rebuild B's WebRTC leg and re-bridge to A's media (consult target refresh)."""

        host_employee_id = host["employee_id"]
        host_legs: _ccs.InCallLegs = host["legs"]
        old_consult_leg = host_legs.consult_call_id
        host_media = host_legs.agent_media_call_id
        if not host_media:
            raise ValidationError("主座席媒体腿不可用，无法恢复咨询")

        try:
            host_call = await _ccs.CallControlService._resolve_current_call(
                tenant_id, host_employee_id
            )
            affinity = host_call.customer_call_id
        except Exception:  # noqa: BLE001
            affinity = host_media

        result = await telephony.webrtc_offer(sdp, call_id=affinity)
        new_leg = result.get("call_id") or ""
        answer_sdp = result.get("sdp") or ""
        if not new_leg or not answer_sdp:
            raise ValidationError("webrtc.offer returned incomplete payload")

        try:
            await telephony.call_answer(new_leg)
        except Exception:  # noqa: BLE001
            pass

        if old_consult_leg and old_consult_leg != new_leg:
            try:
                await telephony.call_hangup(
                    old_consult_leg, reason=_ccs._CONSULT_TARGET_REPLACED_REASON,
                )
            except Exception:  # noqa: BLE001
                pass

        await telephony.call_bridge(
            host_media, new_leg, keepalive_on_peer_hangup=True,
        )

        # Refresh host legs from cache/Redis in case of concurrent updates.
        await consult_session.transition(
            tenant_id=tenant_id,
            host_employee_id=host_employee_id,
            to_state=ConsultState.ACTIVE,
            reason="consult_target_media_reconnect",
            consult_call_id=new_leg,
            target_employee_id=employee_id,
        )
        _ccs.CallControlService._cancel_consult_target_grace(old_consult_leg)

        from app.services.call_center.orchestrator import _get_redis_client

        r = _get_redis_client()
        if r is not None:
            try:
                await _ccs.CcAgentResourceService.mark_in_call(
                    r,
                    tenant_id,
                    employee_id,
                    call_id=new_leg,
                    direction="inbound",
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "consult target reconnect: mark_in_call failed target=%s",
                    employee_id, exc_info=True,
                )

        async with _ccs.AsyncSessionLocal() as db:
            await _ccs.AgentWebRTCSessionService.upsert_with_real_call_id(
                db, tenant_id, employee_id, new_leg,
            )
            await _ccs.AgentWebRTCSessionService.set_busy(
                db, tenant_id, employee_id, busy=True,
            )

        logger.info(
            "media reconnect (consult target): target=%s host=%s new_leg=%s "
            "old_leg=%s",
            employee_id, host_employee_id, new_leg, old_consult_leg,
        )
        return {
            "call_id": new_leg,
            "sdp": answer_sdp,
            "consult_active": True,
            "consult_target_employee_id": employee_id,
        }

    @staticmethod
    def _cancel_consult_target_grace(dead_leg_id: str | None) -> None:
        if not dead_leg_id:
            return
        suffix = f":{dead_leg_id}"
        for key, task in list(_ccs._consult_target_grace_tasks.items()):
            if key.endswith(suffix):
                task.cancel()
                _ccs._consult_target_grace_tasks.pop(key, None)

    @staticmethod
    async def _drop_active_consult_for_reconnect(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        customer_call_id: str,
        agent_media_call_id: str | None,
    ) -> None:
        """End an in-progress consult before media reconnect restores the customer.

        Best-effort: never abort media reconnect if consult teardown fails.
        """

        legs = await _ccs._legs(tenant_id, employee_id)
        consult_call_id = legs.consult_call_id
        if not consult_call_id:
            return
        target_employee_id = legs.consult_target_employee_id

        # Clear Redis consult pointers before hanging up so a concurrent
        # call.hangup on the consult leg does not also run
        # on_consult_target_departed against the half-rebuilt initiator media.
        await consult_session.clear(
            tenant_id=tenant_id,
            host_employee_id=employee_id,
            reason="initiator_media_reconnect",
            consult_call_id=consult_call_id,
        )

        if agent_media_call_id:
            try:
                await telephony.call_unbridge(agent_media_call_id, consult_call_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "media reconnect: consult unbridge failed agent=%s",
                    employee_id, exc_info=True,
                )
        try:
            await telephony.call_hangup(
                consult_call_id, reason="initiator_media_reconnect",
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "media reconnect: consult hangup failed agent=%s consult=%s",
                employee_id, consult_call_id, exc_info=True,
            )

        if target_employee_id is not None:
            await _ccs.CallControlService._release_internal_target(
                tenant_id, target_employee_id, reason="initiator_media_reconnect",
            )
            await _ccs.CallControlService._notify_browser_call_ended(
                tenant_id,
                target_employee_id,
                consult_call_id,
                reason="consult_ended",
            )

        try:
            await _ccs.CallControlService._stop_tone(telephony, customer_call_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "media reconnect: stop consult tone failed customer=%s",
                customer_call_id, exc_info=True,
            )
        logger.info(
            "media reconnect: dropped consult agent=%s consult_leg=%s target=%s",
            employee_id, consult_call_id, target_employee_id,
        )

    @staticmethod
    async def _notify_media_reconnect_required(
        *,
        tenant_id: int,
        employee_id: int,
        customer_call_id: str,
        reason: str,
    ) -> None:
        from app.constants.call_center import CcSocketEvent

        await _ccs.CallControlService._notify_control_result(
            tenant_id=tenant_id,
            initiator_employee_id=employee_id,
            method=CcSocketEvent.MEDIA_RECONNECT_REQUIRED.value,
            payload={
                "customer_call_id": customer_call_id,
                "reason": reason,
            },
        )

    @staticmethod
    async def _agent_uses_sip_phone(tenant_id: int, employee_id: int) -> bool:
        """True when the agent's current device is a SIP desk phone."""

        from app.services.call_center.device_strategy import resolve_agent_strategy

        strategy = await resolve_agent_strategy(tenant_id, employee_id)
        return strategy.is_sip_phone

def _consult_leg_of(legs, employee_id: int) -> str | None:
    if legs.consult_target_employee_id == employee_id:
        return legs.consult_call_id
    return None


def _conference_leg_of(legs, employee_id: int) -> str | None:
    if legs.conference_target_employee_id == employee_id:
        return legs.conference_participant_call_id
    return None


def _colleague_leg_of(legs, employee_id: int) -> str | None:
    return _consult_leg_of(legs, employee_id) or _conference_leg_of(legs, employee_id)


# Imported after the mixin class so this module can be imported directly
# without a circular-import error (call_control_service imports the mixins).
from app.services.call_center import call_control_service as _ccs  # noqa: E402
