"""Prompt tones plus the hold/unhold, DTMF and mute call controls."""
from __future__ import annotations

import logging

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.telephony.base import BaseTelephonyClient

logger = logging.getLogger(__name__)


class BasicControlsMixin:
    # ───────────────────────── prompt tones ─────────────────────────

    @staticmethod
    async def _play_scene_tone(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        customer_call_id: str,
        scene: str,
    ) -> None:
        """Start the configured waiting tone for `scene` on the customer leg.

        Best-effort: any failure (config read, missing/unsupported audio, kernel
        reject) is logged and swallowed so the underlying call operation still
        succeeds — a missing waiting tone must never abort a hold / consult /
        transfer. Looping scenes repeat every 15s; `transfer` plays once.
        """

        try:
            tone = await _ccs.CallControlService._load_scene_tone(tenant_id, scene)
        except Exception:  # noqa: BLE001
            logger.warning("prompt tone config read failed scene=%s", scene, exc_info=True)
            return
        if tone is None:
            return

        text, audio_url, voice = tone
        loop = scene != "transfer"
        try:
            await telephony.call_play(
                customer_call_id,
                text=text,
                audio_url=audio_url,
                loop=loop,
                interval_ms=_ccs._TONE_LOOP_INTERVAL_MS if loop else None,
                voice=voice,
            )
        except Exception:  # noqa: BLE001
            # Silent continue — the customer just hears no waiting tone.
            logger.warning(
                "prompt tone play failed scene=%s call=%s",
                scene, customer_call_id, exc_info=True,
            )

    @staticmethod
    async def _load_scene_tone(
        tenant_id: int, scene: str
    ) -> tuple[str | None, str | None, str | None] | None:
        """Resolve a scene's playable prompt to `(text, audio_url, voice)`.

        Returns None when the scene is disabled, or when it is an audio scene
        whose asset is missing or in an unsupported (non-WAV) container. The
        prompt-tone config read uses its own short session and closes it before
        we touch storage.
        """

        settings = await _ccs.CallPromptToneService.get_settings_managed(tenant_id)
        cfg = next((s for s in settings.scenes if s.scene == scene), None)
        if cfg is None or not cfg.enabled:
            return None

        if cfg.prompt_type == "tts":
            text = (cfg.tts_text or "").strip()
            if not text:
                return None
            return text, None, None

        # audio: resolve a temporary playable URL; WAV only.
        if not cfg.audio_asset_id:
            return None
        async with _ccs.AsyncSessionLocal() as db:
            asset = await _ccs.AudioAssetRepository.get_by_id(
                db, cfg.audio_asset_id, tenant_id
            )
        if asset is None:
            return None
        if asset.mime_type not in _ccs._PLAYABLE_AUDIO_MIME:
            logger.info(
                "prompt tone scene=%s audio asset=%s is %s (not WAV) — skipped",
                scene, asset.id, asset.mime_type,
            )
            return None
        from app.libs.storage import create_storage_client

        storage = create_storage_client()
        url = await storage.get_temporary_url(asset.storage_key, expires_seconds=900)
        return None, url, None

    @staticmethod
    async def _stop_tone(
        telephony: BaseTelephonyClient, customer_call_id: str
    ) -> None:
        """Stop any looping waiting tone on the customer leg. Best-effort."""

        try:
            await telephony.call_stop(customer_call_id, target="play")
        except Exception:  # noqa: BLE001
            logger.warning(
                "prompt tone stop failed call=%s", customer_call_id, exc_info=True
            )

    @staticmethod
    async def _hold_customer_for_conference(
        telephony: BaseTelephonyClient, *, tenant_id: int, call: _ccs.CurrentCall
    ) -> None:
        """Hold the customer with the three-party waiting tone while a
        participant is being invited.

        Mirrors consult hold: unbridge the agent leg (keeps the customer's RTP
        flowing so the tone is audible) and start the configured three-party
        waiting tone on the customer leg.
        """

        if call.webrtc_call_id:
            await telephony.call_unbridge(call.customer_call_id, call.webrtc_call_id)
        await _ccs.CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="three_party",
        )

    @staticmethod
    async def _restore_customer_from_conference(
        telephony: BaseTelephonyClient, *, tenant_id: int, employee_id: int
    ) -> None:
        """Stop the three-party waiting tone and re-bridge the held customer
        back to the agent when the invite is aborted.

        Re-resolves the current call defensively (the invite may have failed
        after the customer already left); best-effort — kernel errors are
        swallowed with a warning so the abort path never breaks.
        """

        try:
            call = await _ccs.CallControlService._resolve_current_call(
                tenant_id, employee_id
            )
        except NotFoundError:
            return
        await _ccs.CallControlService._stop_tone(telephony, call.customer_call_id)
        if call.webrtc_call_id:
            try:
                await telephony.call_bridge(
                    call.customer_call_id,
                    call.webrtc_call_id,
                    keepalive_on_peer_hangup=True,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "conference restore re-bridge failed customer=%s",
                    call.customer_call_id, exc_info=True,
                )

    # ───────────────────────── hold / unhold ─────────────────────────

    @staticmethod
    async def hold(
        telephony: BaseTelephonyClient, *, tenant_id: int, employee_id: int
    ) -> dict:
        """Put the customer on hold + start the hold waiting tone.

        A custom hold tone needs the customer's RTP to keep flowing, so hold is
        an unbridge (stops two-way agent<->customer audio) plus a tone played to
        the customer leg — not a SIP-level ``call.hold``, which pauses RTP and
        would silence the tone. Both legs stay up (StateActive); unhold
        re-bridges them.
        """

        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        if call.webrtc_call_id:
            await telephony.call_unbridge(call.customer_call_id, call.webrtc_call_id)
        await _ccs.CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="hold",
        )
        legs = await _ccs._legs(tenant_id, employee_id)
        legs.customer_held = True
        await _ccs._save_legs(tenant_id, employee_id, legs)
        from app.services.call_trajectory_service import CallTrajectoryService

        await CallTrajectoryService.append_for_call_id_best_effort(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            event_type="hold_started",
            event_category="control",
            actor_type="agent",
            actor_id=str(employee_id),
            source="opendesk",
            call_leg_id=call.customer_call_id,
            participant_role="customer",
        )
        logger.info("hold: agent=%s call=%s", employee_id, call.customer_call_id)
        return {"ok": True, "call_id": call.customer_call_id}

    @staticmethod
    async def unhold(
        telephony: BaseTelephonyClient, *, tenant_id: int, employee_id: int
    ) -> dict:
        """Resume the customer + stop the hold waiting tone."""

        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        await _ccs.CallControlService._stop_tone(telephony, call.customer_call_id)
        if call.webrtc_call_id:
            await telephony.call_bridge(
                call.customer_call_id,
                call.webrtc_call_id,
                keepalive_on_peer_hangup=True,
            )
        legs = await _ccs._legs(tenant_id, employee_id)
        legs.customer_held = False
        await _ccs._save_legs(tenant_id, employee_id, legs)
        from app.services.call_trajectory_service import CallTrajectoryService

        await CallTrajectoryService.append_for_call_id_best_effort(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            event_type="hold_ended",
            event_category="control",
            actor_type="agent",
            actor_id=str(employee_id),
            source="opendesk",
            call_leg_id=call.customer_call_id,
            participant_role="customer",
            result="succeeded",
            reason_code="normal",
        )
        logger.info("unhold: agent=%s call=%s", employee_id, call.customer_call_id)
        return {"ok": True, "call_id": call.customer_call_id}

    # ───────────────────────── DTMF ─────────────────────────

    @staticmethod
    async def dtmf(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        digits: str,
    ) -> dict:
        """Send DTMF into the live call. Backed by `call.dtmf`.

        Digits are sent on the customer leg so the far end / IVR hears them.
        """

        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        await telephony.call_dtmf(call.customer_call_id, digits)
        from app.services.call_trajectory_service import CallTrajectoryService

        await CallTrajectoryService.append_for_call_id_best_effort(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            event_type="dtmf_sent",
            event_category="control",
            actor_type="agent",
            actor_id=str(employee_id),
            source="opendesk",
            call_leg_id=call.customer_call_id,
            result="succeeded",
            details={"digit_count": len(digits)},
        )
        logger.info(
            "dtmf: agent=%s call=%s count=%d",
            employee_id, call.customer_call_id, len(digits),
        )
        return {"ok": True, "call_id": call.customer_call_id}

    # ───────────────────────── mute ─────────────────────────

    @staticmethod
    async def mute(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        muted: bool,
    ) -> dict:
        """Mute the agent's own leg in the kernel.

        A browser agent has already switched off its local track before this
        arrives, which stays the fastest path and the one that survives a
        dropped connection; muting the leg as well keeps the two ends in step.
        An agent on a SIP handset has no local track, so this is the only
        thing that mutes them — the console's button used to report success
        while they stayed audible.
        """

        call = await _ccs.CallControlService._resolve_current_call(tenant_id, employee_id)
        if not call.webrtc_call_id:
            raise ValidationError("当前通话还没有坐席通道，无法静音")
        if muted:
            await telephony.call_mute(call.webrtc_call_id)
        else:
            await telephony.call_unmute(call.webrtc_call_id)
        from app.services.call_trajectory_service import CallTrajectoryService

        await CallTrajectoryService.append_for_call_id_best_effort(
            tenant_id=tenant_id,
            call_id=call.customer_call_id,
            event_type="mute_started" if muted else "mute_ended",
            event_category="control",
            actor_type="agent",
            actor_id=str(employee_id),
            source="opendesk",
            call_leg_id=call.webrtc_call_id,
            participant_role="serving_agent",
            result="succeeded" if not muted else None,
            reason_code="normal" if not muted else None,
        )
        logger.info(
            "mute: agent=%s call=%s agent_leg=%s muted=%s",
            employee_id, call.customer_call_id, call.webrtc_call_id, muted,
        )
        return {"ok": True, "call_id": call.customer_call_id}

# Imported after the mixin class so this module can be imported directly
# without a circular-import error (call_control_service imports the mixins).
from app.services.call_center import call_control_service as _ccs  # noqa: E402
