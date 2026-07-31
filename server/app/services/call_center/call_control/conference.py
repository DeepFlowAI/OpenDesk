"""Three-party conference assembled on the kernel room mixer."""
from __future__ import annotations

import asyncio
import logging

from app.core.exceptions import (
    NotFoundError,
    NotImplementedApiError,
    ValidationError,
)
from app.libs.telephony.base import (
    BaseTelephonyClient,
    TelephonyMethodNotFoundError,
)

logger = logging.getLogger(__name__)


class ConferenceMixin:
    # ───────────────────────── conference (3-way) ─────────────────────────

    @staticmethod
    async def conference_add(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        target_type: str,
        target_id: int | None,
        number: str | None,
    ) -> dict:
        """Call a new participant and merge them once they answer.

        The participant leg is originated and the request returns as it rings.
        Answer detection runs off the request path (like transfer/consult): on
        answer the three legs are merged into a room automatically and the
        browser is told the conference is live; on no-answer / decline the
        participant leg is cleaned up and the browser is told it failed so the
        UI never sticks at "呼叫参与人中". The customer is held with the
        three-party waiting tone while the participant rings; the tone stops
        once they merge, and the customer is re-bridged to the agent on
        no-answer / decline.
        """

        _ccs.CallControlService._validate_target(target_type, target_id, number)
        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)

        # A colleague on the Web phone (no SIP extension) is reached by ringing
        # their browser, then merged into the room on answer — the SIP-originate
        # path below only handles SIP-extension employees and external numbers.
        if target_type == "employee" and await _ccs.CallControlService._employee_target_is_webrtc(
            tenant_id, target_id
        ):
            await _ccs.CallControlService._precheck_webrtc_target_available(
                tenant_id, target_id, action="添加参与人"
            )
            return await _ccs.CallControlService._conference_webrtc_employee(
                telephony,
                tenant_id=tenant_id,
                employee_id=employee_id,
                target_employee_id=target_id,
                call=call,
            )

        originate_kwargs, desc_str = await _ccs.CallControlService._resolve_target_originate(
            tenant_id, target_type, target_id, number
        )
        target_call_id = await _ccs.CallControlService._originate_target(
            telephony, originate_kwargs
        )
        legs = await _ccs._legs(tenant_id, employee_id)
        legs.conference_participant_call_id = target_call_id
        await _ccs._save_legs(tenant_id, employee_id, legs)

        # Unbridge the customer immediately so they stop hearing the agent;
        # play the three-party waiting tone off the request path so invite
        # latency is not gated on tone settings / object-storage URL work.
        if call.webrtc_call_id:
            await telephony.call_unbridge(call.customer_call_id, call.webrtc_call_id)

        async def _play_invite_tone() -> None:
            try:
                await _ccs.CallControlService._play_scene_tone(
                    telephony,
                    tenant_id=tenant_id,
                    customer_call_id=call.customer_call_id,
                    scene="three_party",
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "conference invite tone failed call=%s",
                    call.customer_call_id, exc_info=True,
                )

        # Keep a handle so answer / fail can cancel before stop/restore: if the
        # participant settles while tone settings / object-storage work is still
        # in flight, a late call_play must not land after the tone was stopped.
        tone_task = asyncio.create_task(
            _play_invite_tone(),
            name=f"conference-tone:{tenant_id}:{employee_id}",
        )

        async def _cancel_invite_tone() -> None:
            tone_task.cancel()
            try:
                await tone_task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 — never poison answer / fail handlers
                logger.warning(
                    "conference invite tone task ended with error call=%s",
                    call.customer_call_id, exc_info=True,
                )

        async def _on_answer() -> None:
            await _cancel_invite_tone()
            try:
                await _ccs.CallControlService._merge_participant_room(
                    telephony,
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    participant_call_id=target_call_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("conference auto-merge failed", exc_info=True)
                await _ccs.CallControlService._abort_conference_participant(
                    telephony, tenant_id, employee_id, target_call_id, str(exc)
                )
                return
            await _ccs.CallControlService._notify_conference_result(
                tenant_id, employee_id, ok=True, reason=None
            )

        async def _on_fail(reason: str) -> None:
            await _cancel_invite_tone()
            await _ccs.CallControlService._abort_conference_participant(
                telephony, tenant_id, employee_id, target_call_id, reason
            )

        _ccs.CallControlService._spawn_target_wait(
            telephony,
            target_call_id=target_call_id,
            on_answer=_on_answer,
            on_fail=_on_fail,
        )

        logger.info(
            "conference add: agent=%s -> %s participant_leg=%s (ringing)",
            employee_id, desc_str, target_call_id,
        )
        return {
            "ok": True,
            "call_id": call.customer_call_id,
            "note": "ringing_participant",
        }

    @staticmethod
    async def _conference_webrtc_employee(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        target_employee_id: int,
        call: _ccs.CurrentCall,
    ) -> dict:
        """Add a Web-phone colleague to the conference: ring their browser, then
        merge their answered WebRTC leg into the room off the request path.

        Unlike a SIP / external participant, the browser is rung via the shared
        internal ring machinery; on answer the three legs (customer, initiator,
        colleague) are merged into a room. On no-answer / decline / merge error
        the colleague's occupied resource is freed and the browser told it
        failed. The two-party call is never disturbed while it rings.
        """

        if call.webrtc_call_id is None:
            raise ValidationError("坐席媒体腿不可用，无法添加参与人")
        display = await _ccs.CallControlService._resolve_initiator_display(
            tenant_id, employee_id
        )

        # Unbridge on the request path so the customer stops hearing the agent
        # immediately; waiting-tone playback runs inside the background task
        # below (tone settings / object-storage must not delay the HTTP reply).
        await telephony.call_unbridge(call.customer_call_id, call.webrtc_call_id)

        async def _ring_and_merge() -> None:
            from app.services.call_center.internal_consult_service import (
                InternalConsultService,
            )
            from app.services.call_center.orchestrator import _get_redis_client

            try:
                await _ccs.CallControlService._play_scene_tone(
                    telephony,
                    tenant_id=tenant_id,
                    customer_call_id=call.customer_call_id,
                    scene="three_party",
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "conference webrtc invite tone failed call=%s",
                    call.customer_call_id, exc_info=True,
                )

            r = _get_redis_client()
            if r is None:
                await _ccs.CallControlService._restore_customer_from_conference(
                    telephony, tenant_id=tenant_id, employee_id=employee_id
                )
                await _ccs.CallControlService._notify_conference_result(
                    tenant_id, employee_id, ok=False, reason="no_redis"
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
                    call_type="internal_conference",
                    customer_context=customer_context,
                )
            except Exception as exc:  # noqa: BLE001
                # The internal path already released the target on failure.
                await _ccs.CallControlService._restore_customer_from_conference(
                    telephony, tenant_id=tenant_id, employee_id=employee_id
                )
                await _ccs.CallControlService._notify_conference_result(
                    tenant_id, employee_id, ok=False, reason=str(exc)
                )
                return
            target_leg = result["target_webrtc_call_id"]
            legs = await _ccs._legs(tenant_id, employee_id)
            legs.conference_participant_call_id = target_leg
            legs.conference_target_employee_id = target_employee_id
            await _ccs._save_legs(tenant_id, employee_id, legs)
            try:
                await _ccs.CallControlService._merge_participant_room(
                    telephony,
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    participant_call_id=target_leg,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "conference webrtc merge failed: %s", exc, exc_info=True,
                )
                legs.conference_participant_call_id = None
                legs.conference_target_employee_id = None
                await _ccs._save_legs(tenant_id, employee_id, legs)
                await _ccs.CallControlService._restore_customer_from_conference(
                    telephony, tenant_id=tenant_id, employee_id=employee_id
                )
                await _ccs.CallControlService._release_internal_target(
                    tenant_id, target_employee_id, reason="conference_merge_failed"
                )
                await _ccs.CallControlService._notify_browser_call_ended(
                    tenant_id, target_employee_id, target_leg, reason="conference_failed"
                )
                fail_reason = getattr(exc, "message", None) or str(exc) or "conference_merge_failed"
                await _ccs.CallControlService._notify_conference_result(
                    tenant_id, employee_id, ok=False, reason=fail_reason,
                )
                return
            await _ccs.CallControlService._notify_conference_result(
                tenant_id, employee_id, ok=True, reason=None
            )

        asyncio.create_task(
            _ring_and_merge(),
            name=f"internal-conference:{tenant_id}:{target_employee_id}",
        )
        logger.info(
            "conference add (webrtc): agent=%s -> employee:%s (ringing browser)",
            employee_id, target_employee_id,
        )
        return {
            "ok": True,
            "call_id": call.customer_call_id,
            "note": "ringing_participant",
        }

    @staticmethod
    async def _merge_participant_room(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        participant_call_id: str,
    ) -> str:
        """Create the 3-way room for a participant that just answered."""

        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        legs = await _ccs._legs(tenant_id, employee_id)
        if call.webrtc_call_id is None:
            raise ValidationError("坐席媒体腿不可用，无法合并三方")
        # Stop the three-party waiting tone before the room re-includes the
        # customer — the room already carries the customer's audio, so we only
        # stop the tone here (no re-bridge).
        await _ccs.CallControlService._stop_tone(telephony, call.customer_call_id)
        leg_ids = [call.customer_call_id, call.webrtc_call_id, participant_call_id]
        try:
            result = await telephony.room_create(leg_call_ids=leg_ids)
        except TelephonyMethodNotFoundError as exc:
            raise NotImplementedApiError("当前通话服务暂不支持三方") from exc
        room_id = result.get("room_id")
        legs.room_id = room_id
        legs.room_legs = list(leg_ids)
        await _ccs._save_legs(tenant_id, employee_id, legs)
        # Index the participant leg → host so we can collapse this agent's
        # conference when the participant later hangs up / drops.
        await _ccs._register_conference_participant(
            tenant_id, employee_id, participant_call_id
        )
        logger.info(
            "conference merged (auto): agent=%s room=%s legs=%s",
            employee_id, room_id, leg_ids,
        )
        return room_id

    @staticmethod
    async def on_conference_participant_departed(participant_leg: str) -> None:
        """A conference participant's leg ended → collapse the host's 3-way back
        to the two-party call and tell their browser (otherwise the host stays
        stuck at "多方通话 3人"). No-op if the leg wasn't a tracked participant.

        Called from the kernel call.hangup handler, so it fires whether the
        colleague hung up, their browser dropped, or an external phone left.
        """

        from app.services.call_center.orchestrator import _get_redis_client

        r = _get_redis_client()
        if r is None or not participant_leg:
            return
        try:
            raw = await r.get(_ccs._conf_host_key(participant_leg))
        except Exception:  # noqa: BLE001
            return
        if not raw:
            return
        try:
            tenant_str, host_str = raw.split(":", 1)
            tenant_id = int(tenant_str)
            host_employee_id = int(host_str)
        except (ValueError, AttributeError):
            return
        try:
            await r.delete(_ccs._conf_host_key(participant_leg))
        except Exception:  # noqa: BLE001
            pass

        # Drop the participant from the host's in-call legs.
        legs = await _ccs._legs(tenant_id, host_employee_id)
        changed = False
        colleague_id: int | None = None
        if legs.conference_participant_call_id == participant_leg:
            colleague_id = legs.conference_target_employee_id
            legs.conference_participant_call_id = None
            legs.conference_target_employee_id = None
            changed = True
        if participant_leg in legs.room_legs:
            legs.room_legs.remove(participant_leg)
            changed = True
        if changed:
            await _ccs._save_legs(tenant_id, host_employee_id, legs)

        # A Web-phone colleague occupied their own resource for the conference;
        # free it so they are not stuck busy after hanging up.
        if colleague_id is not None:
            await _ccs.CallControlService._release_internal_target(
                tenant_id, colleague_id, reason="conference_participant_departed",
            )

        # Tell the host's browser to collapse the conference to the 1:1 call.
        from app.services.call_center.orchestrator import get_orchestrator

        try:
            await get_orchestrator().notify_conference_participant_left(
                tenant_id=tenant_id, employee_id=host_employee_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "conference participant-left notify failed host=%s/%s",
                tenant_id, host_employee_id, exc_info=True,
            )
        logger.info(
            "conference collapsed: host=%s/%s participant_leg=%s departed",
            tenant_id, host_employee_id, participant_leg,
        )

    @staticmethod
    async def _abort_conference_participant(
        telephony: BaseTelephonyClient,
        tenant_id: int,
        employee_id: int,
        participant_call_id: str,
        reason: str,
    ) -> None:
        """Tear down a participant that never joined and tell the browser."""

        legs = await _ccs._legs(tenant_id, employee_id)
        if participant_call_id:
            try:
                await telephony.call_hangup(
                    participant_call_id, reason="participant_aborted"
                )
            except Exception:  # noqa: BLE001
                pass
        if legs.conference_participant_call_id == participant_call_id:
            legs.conference_participant_call_id = None
            await _ccs._save_legs(tenant_id, employee_id, legs)
        logger.info(
            "conference participant aborted: agent=%s leg=%s reason=%s",
            employee_id, participant_call_id, reason,
        )
        # Stop the three-party tone and re-bridge the held customer back to the
        # agent before telling the browser the invite failed.
        await _ccs.CallControlService._restore_customer_from_conference(
            telephony, tenant_id=tenant_id, employee_id=employee_id
        )
        await _ccs.CallControlService._notify_conference_result(
            tenant_id, employee_id, ok=False, reason=reason
        )

    @staticmethod
    async def _notify_conference_result(
        tenant_id: int, employee_id: int, *, ok: bool, reason: str | None
    ) -> None:
        """Push cc.conference_result to the agent's browser."""

        payload: dict = {"ok": ok, "kind": "conference"}
        if not ok:
            mapping = {
                "no_answer": "参与人未接听",
                "declined": "参与人已拒接",
                "wait_error": "呼叫参与人失败",
                "no_redis": "通话服务暂不可用",
            }
            if reason in mapping:
                payload["reason"] = mapping[reason]
            elif reason and any("一" <= ch <= "鿿" for ch in reason):
                # Already a user-facing Chinese message (e.g. from the WebRTC
                # ring path); surface it as-is instead of a generic fallback.
                payload["reason"] = reason
            else:
                payload["reason"] = "参与人未接通"
        await _ccs.CallControlService._notify_control_result(
            tenant_id=tenant_id,
            initiator_employee_id=employee_id,
            method="cc.conference_result",
            payload=payload,
        )

    @staticmethod
    async def conference_merge(
        telephony: BaseTelephonyClient, *, tenant_id: int, employee_id: int
    ) -> dict:
        """Merge the customer, agent and participant into one 3-way room.

        Uses the kernel room mixer: `room.create` with all three legs (the
        kernel auto-unbridges the original pair). When rooms are unavailable we
        degrade to 501 without disturbing the two-party call.
        """

        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        legs = await _ccs._legs(tenant_id, employee_id)
        participant = legs.conference_participant_call_id
        if not participant:
            raise NotFoundError("No participant to merge")
        if call.webrtc_call_id is None:
            raise ValidationError("坐席媒体腿不可用，无法合并三方")

        leg_ids = [call.customer_call_id, call.webrtc_call_id, participant]
        await _ccs.CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="three_party",
        )
        try:
            result = await telephony.room_create(leg_call_ids=leg_ids)
        except TelephonyMethodNotFoundError as exc:
            await _ccs.CallControlService._stop_tone(telephony, call.customer_call_id)
            raise NotImplementedApiError(
                "当前通话服务暂不支持三方"
            ) from exc

        room_id = result.get("room_id")
        legs.room_id = room_id
        legs.room_legs = list(leg_ids)
        await _ccs._save_legs(tenant_id, employee_id, legs)
        # Same reverse index the auto-merge path registers, so a later
        # participant hangup can collapse the host's "多方通话 3人" UI.
        await _ccs._register_conference_participant(
            tenant_id, employee_id, participant
        )
        logger.info(
            "conference merge: agent=%s room=%s legs=%s",
            employee_id, room_id, leg_ids,
        )
        return {"ok": True, "call_id": call.customer_call_id, "note": room_id}

    @staticmethod
    async def conference_remove(
        telephony: BaseTelephonyClient, *, tenant_id: int, employee_id: int
    ) -> dict:
        """Remove the added participant from the conference room."""

        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        legs = await _ccs._legs(tenant_id, employee_id)
        if not legs.room_id or not legs.conference_participant_call_id:
            raise NotFoundError("No active conference")
        participant = legs.conference_participant_call_id
        colleague_id = legs.conference_target_employee_id
        await _ccs.CallControlService._room_remove(telephony, legs, participant)
        try:
            await telephony.call_hangup(participant, reason="participant_removed")
        except Exception:  # noqa: BLE001
            logger.warning("conference participant hangup failed", exc_info=True)
        await _ccs.CallControlService._unregister_conference_participant(participant)
        # A Web-phone colleague must be released (and told the call ended) or
        # they stay occupied and stop receiving queue offers.
        if colleague_id is not None:
            await _ccs.CallControlService._release_internal_target(
                tenant_id, colleague_id, reason="conference_removed",
            )
            await _ccs.CallControlService._notify_browser_call_ended(
                tenant_id, colleague_id, participant, reason="conference_removed",
            )
        legs.conference_participant_call_id = None
        legs.conference_target_employee_id = None
        await _ccs._save_legs(tenant_id, employee_id, legs)
        logger.info(
            "conference remove: agent=%s room=%s participant=%s",
            employee_id, legs.room_id, participant,
        )
        return {"ok": True, "call_id": call.customer_call_id}

    @staticmethod
    async def conference_leave(
        telephony: BaseTelephonyClient, *, tenant_id: int, employee_id: int
    ) -> dict:
        """Agent leaves the conference; customer and participant keep talking.

        Restores an ordinary two-party bridge for the survivors, then — when the
        participant is a Web-phone colleague — hands call ownership to them and
        moves the departing host into after-call-work. External / SIP
        participants keep the bridged call without an agent ownership transfer.
        """

        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        legs = await _ccs._legs(tenant_id, employee_id)
        if not legs.room_id:
            raise NotFoundError("No active conference")
        colleague_id = legs.conference_target_employee_id
        participant_leg = legs.conference_participant_call_id
        host_media = call.webrtc_call_id
        room_id = legs.room_id

        # 1) Stop mixing the host, then stitch customer ↔ remaining participant
        # into a normal bridge (later hold/transfer/consult assume a bridge).
        if host_media:
            await _ccs.CallControlService._room_remove(telephony, legs, host_media)
        if participant_leg:
            await _ccs.CallControlService._room_remove(telephony, legs, participant_leg)
            try:
                from app.services.system_settings_service import SystemSettingsService

                transcribe = await SystemSettingsService.is_bridge_asr_enabled_managed(
                    tenant_id
                )
                await telephony.call_bridge(
                    call.customer_call_id, participant_leg, transcribe=transcribe,
                )
            except Exception:  # noqa: BLE001
                # Survivors stay up; ownership handover below still proceeds so
                # the new owner can recover rather than dropping the customer.
                logger.warning(
                    "conference leave re-bridge failed customer=%s participant=%s",
                    call.customer_call_id, participant_leg, exc_info=True,
                )

        # 2) Hand ownership to a Web-phone colleague (skip for external / SIP).
        if colleague_id is not None and participant_leg:
            await _ccs.CallControlService._reassign_call_record_to_agent(
                tenant_id, call.customer_call_id, colleague_id,
            )
            try:
                from app.services.call_center.orchestrator import get_orchestrator

                wf = get_orchestrator().active_workflow(call.customer_call_id)
                if wf is not None:
                    wf.rebind_bridged_agent(colleague_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "conference leave: rebind bridged agent failed call=%s new_agent=%s",
                    call.customer_call_id, colleague_id, exc_info=True,
                )
            await _ccs.CallControlService.bind_agent_media_leg(
                tenant_id, colleague_id, participant_leg,
            )
            await _ccs.CallControlService._rekey_internal_target_to_customer(
                tenant_id, colleague_id, call.customer_call_id,
            )
            try:
                from app.services.call_center.orchestrator import get_orchestrator

                await get_orchestrator().republish_agent_call_ui(
                    tenant_id=tenant_id, employee_id=colleague_id,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "conference leave: republish colleague UI failed agent=%s/%s",
                    tenant_id, colleague_id, exc_info=True,
                )

        # 3) Drop the participant→host index (host is leaving).
        if participant_leg:
            await _ccs.CallControlService._unregister_conference_participant(
                participant_leg
            )

        # 4) End the host's media leg and move them to after-call-work.
        if host_media:
            try:
                await telephony.call_hangup(host_media, reason="agent_left")
            except Exception:  # noqa: BLE001
                logger.warning("conference agent leg hangup failed", exc_info=True)
        await _ccs.CallControlService._release_host_after_conference_leave(
            tenant_id=tenant_id,
            employee_id=employee_id,
            customer_call_id=call.customer_call_id,
        )

        logger.info(
            "conference leave: agent=%s room=%s colleague=%s",
            employee_id, room_id, colleague_id,
        )
        return {"ok": True, "call_id": call.customer_call_id}

    @staticmethod
    async def _unregister_conference_participant(participant_leg: str) -> None:
        """Drop the participant leg → host reverse index. Best-effort."""

        if not participant_leg:
            return
        from app.services.call_center.orchestrator import _get_redis_client

        r = _get_redis_client()
        if r is None:
            return
        try:
            await r.delete(_ccs._conf_host_key(participant_leg))
        except Exception:  # noqa: BLE001
            logger.warning(
                "conference host unregister failed leg=%s",
                participant_leg, exc_info=True,
            )

    @staticmethod
    async def _release_host_after_conference_leave(
        *,
        tenant_id: int,
        employee_id: int,
        customer_call_id: str,
    ) -> None:
        """Move the departing conference host to after-call-work and clear state.

        Mirrors the initiator wrap-up used after a blind transfer: Redis ACW,
        Postgres status, browser hangup on the *customer* call id (what the UI
        stores), and a full legs clear so reconnect does not resurrect "通话中".
        """

        await _ccs.CallControlService._notify_browser_call_ended(
            tenant_id, employee_id, customer_call_id, reason="left_conference",
        )
        from app.services.call_center.orchestrator import _get_redis_client
        from app.services.cc_agent_status_service import CcAgentStatusService

        r = _get_redis_client()
        if r is not None:
            try:
                await _ccs.CcAgentResourceService.mark_after_call_work(
                    r,
                    tenant_id,
                    employee_id,
                    call_id=customer_call_id,
                    reason="left_conference",
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "conference leave: mark_after_call_work failed agent=%s/%s",
                    tenant_id, employee_id, exc_info=True,
                )
                try:
                    await _ccs.CcAgentResourceService.force_release(
                        r, tenant_id, employee_id, reason="left_conference",
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "conference leave: force_release failed agent=%s/%s",
                        tenant_id, employee_id, exc_info=True,
                    )
        try:
            async with _ccs.AsyncSessionLocal() as db:
                await CcAgentStatusService.sync_pg_status(
                    db, tenant_id, employee_id, "after_call_work", None
                )
        except Exception:  # noqa: BLE001
            logger.warning(
                "conference leave: sync_pg after_call_work failed agent=%s/%s",
                tenant_id, employee_id, exc_info=True,
            )
        await _ccs._clear_legs(tenant_id, employee_id)

    @staticmethod
    async def cleanup_conference_for_host(
        tenant_id: int,
        employee_id: int,
        *,
        reason: str,
    ) -> bool:
        """Release a conference colleague when the host/customer call ends.

        No-op when there is no Web-phone colleague on the conference. Ends the
        colleague's leg and frees their occupied resource so they are not stuck
        ``in_call`` after the customer hangs up (the room may otherwise keep
        their leg mixed with the departed host).
        """

        from app.libs.telephony import get_telephony_client

        legs = await _ccs._legs(tenant_id, employee_id)
        colleague_id = legs.conference_target_employee_id
        participant_leg = legs.conference_participant_call_id
        if colleague_id is None:
            return False

        legs.conference_participant_call_id = None
        legs.conference_target_employee_id = None
        await _ccs._save_legs(tenant_id, employee_id, legs)
        if participant_leg:
            await _ccs.CallControlService._unregister_conference_participant(
                participant_leg
            )

        telephony = get_telephony_client()
        if participant_leg:
            try:
                await telephony.call_hangup(participant_leg, reason=reason)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "cleanup conference: hangup colleague failed host=%s leg=%s",
                    employee_id, participant_leg, exc_info=True,
                )
        await _ccs.CallControlService._release_internal_target(
            tenant_id, colleague_id, reason=reason,
        )
        if participant_leg:
            await _ccs.CallControlService._notify_browser_call_ended(
                tenant_id, colleague_id, participant_leg, reason="conference_ended",
            )
        return True

    @staticmethod
    async def conference_end_all(
        telephony: BaseTelephonyClient, *, tenant_id: int, employee_id: int
    ) -> dict:
        """End the call for everyone: close the room (if any) and drop all legs.

        Robust to a participant that is still ringing (no room created yet): we
        never 404 here, because that would leave the agent unable to hang up.
        Whatever legs exist — customer, agent, participant — are torn down.
        """

        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        legs = await _ccs._legs(tenant_id, employee_id)
        room_id = legs.room_id
        participant_leg = legs.conference_participant_call_id
        webrtc_participant = legs.conference_target_employee_id
        # In case the conference is ended mid-invite (participant still ringing,
        # no room yet), stop any lingering three-party waiting tone.
        await _ccs.CallControlService._stop_tone(telephony, call.customer_call_id)
        if room_id:
            try:
                await telephony.room_close(room_id, reason="ended_by_agent")
            except Exception:  # noqa: BLE001
                logger.warning("room close failed room=%s", room_id, exc_info=True)
        # Hang up every leg the agent controls.
        for leg in [call.customer_call_id, call.webrtc_call_id, participant_leg]:
            if not leg:
                continue
            try:
                await telephony.call_hangup(leg, reason="conference_ended")
            except Exception:  # noqa: BLE001
                logger.warning("conference leg hangup failed leg=%s", leg, exc_info=True)
        await _ccs._clear_legs(tenant_id, employee_id)
        # Close the agent's own browser leg cleanly and move it to wrap-up.
        if call.webrtc_call_id:
            await _ccs.CallControlService._notify_browser_call_ended(
                tenant_id, employee_id, call.webrtc_call_id, reason="conference_ended",
            )
        # A Web-phone colleague participant: free their occupied resource and
        # close their browser leg too, or they stay stuck busy.
        if webrtc_participant is not None:
            await _ccs.CallControlService._release_internal_target(
                tenant_id, webrtc_participant, reason="conference_ended"
            )
            if participant_leg:
                await _ccs.CallControlService._notify_browser_call_ended(
                    tenant_id, webrtc_participant, participant_leg,
                    reason="conference_ended",
                )
        logger.info("conference end-all: agent=%s room=%s", employee_id, room_id)
        return {"ok": True, "call_id": call.customer_call_id}

# Imported after the mixin class so this module can be imported directly
# without a circular-import error (call_control_service imports the mixins).
from app.services.call_center import call_control_service as _ccs  # noqa: E402
