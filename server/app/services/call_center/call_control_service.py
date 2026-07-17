"""
In-call control service.

Operates on the *current agent's own* active call. Every method resolves the
agent's active customer leg (the customer-facing SIP call_id) and the agent's
own WebRTC leg from server-side state, then drives the media kernel through the
telephony client. Nothing here trusts a client-supplied call_id.

Capability note — the media kernel exposes low-level call primitives
(hold/unhold/dtmf/bridge/unbridge/originate/hangup/stop/play) plus, when
`room.*` is enabled, a conference mixer. High-level transfer / consult are
assembled here from those primitives; three-party uses the room mixer and
degrades to a clear 501 when the kernel has rooms disabled.

Timing rule — a request must never hold a pooled DB connection across a kernel
RPC or across the wait for a freshly-originated target to answer. Leg
resolution uses a short session that closes before any RPC; the target-answer
wait runs off the request path via the orchestrator's leg-wait mechanism, so
the HTTP request returns as soon as the target leg starts ringing.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import desc, select

from app.core.exceptions import (
    NotFoundError,
    NotImplementedApiError,
    ValidationError,
)
from app.db.session import AsyncSessionLocal
from app.libs.telephony.base import (
    BaseTelephonyClient,
    TelephonyMethodNotFoundError,
    TelephonyRPCError,
)
from app.models.call_record import CallRecord
from app.repositories.audio_asset_repository import AudioAssetRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.sip_extension_repository import SipExtensionRepository
from app.repositories.tenant_phone_number_repository import (
    TenantPhoneNumberRepository,
)
from app.services.agent_call_device_service import AgentCallDeviceService
from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
from app.services.call_prompt_tone_service import CallPromptToneService
from app.services.cc_agent_resource_service import CcAgentResourceService

logger = logging.getLogger(__name__)

# States a CallRecord is in while the agent is actively handling the call.
_ACTIVE_STATES = ("ringing", "queued", "in_progress")

# How long (seconds) we wait off the request path for a freshly-originated
# transfer / consult / conference target leg to answer before giving up and
# restoring the original call.
_TARGET_ANSWER_TIMEOUT_SEC = 45.0

# Looping waiting-tone cadence for hold / consult / three-party scenes.
_TONE_LOOP_INTERVAL_MS = 15000

# Containers the voice kernel decodes for audio-file prompts (WAV and MP3).
# An asset in any other container is skipped (TTS fallback is not attempted for
# file scenes — that would change the tenant's configured prompt).
_PLAYABLE_AUDIO_MIME = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/vnd.wave",
    "audio/mpeg",
    "audio/mp3",
}


@dataclass(frozen=True)
class CurrentCall:
    """Resolved legs for the agent's active call."""

    record_id: int
    tenant_id: int
    customer_call_id: str
    webrtc_call_id: str | None


@dataclass
class InCallLegs:
    """State for an agent's assembled multi-party call.

    Lives for the duration of a single consult / conference and is keyed by
    (tenant_id, employee_id). The agent can only be on one such call at a time.
    Persisted to Redis (see ``_save_legs``) so it survives a process restart and
    is shared across blue/green containers; cleared when the operation ends.
    """

    consult_call_id: str | None = None
    conference_participant_call_id: str | None = None
    room_id: str | None = None
    room_legs: list[str] = field(default_factory=list)
    # Set only when the consult / transfer target is a colleague reached via the
    # internal browser-ring path. We reserved & occupied that colleague's own
    # call-center resource to ring their browser, so we must release (consult) or
    # re-key it to the customer call (transfer) when the operation ends —
    # otherwise the colleague stays stuck busy and can't be dialed again.
    consult_target_employee_id: int | None = None
    consult_offer_id: str | None = None
    # Set when a conference participant is a colleague reached via the internal
    # browser-ring path (not a SIP extension / external number). Their own
    # call-center resource is occupied for the conference, so it must be freed
    # when the conference ends.
    conference_target_employee_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "consult_call_id": self.consult_call_id,
            "conference_participant_call_id": self.conference_participant_call_id,
            "room_id": self.room_id,
            "room_legs": list(self.room_legs),
            "consult_target_employee_id": self.consult_target_employee_id,
            "consult_offer_id": self.consult_offer_id,
            "conference_target_employee_id": self.conference_target_employee_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InCallLegs":
        return cls(
            consult_call_id=d.get("consult_call_id"),
            conference_participant_call_id=d.get("conference_participant_call_id"),
            room_id=d.get("room_id"),
            room_legs=list(d.get("room_legs") or []),
            consult_target_employee_id=d.get("consult_target_employee_id"),
            consult_offer_id=d.get("consult_offer_id"),
            conference_target_employee_id=d.get("conference_target_employee_id"),
        )


# In-process cache keyed by (tenant_id, employee_id). Backed by Redis so the
# state is durable across process restarts and shared across blue/green
# containers; this cache is just a fast local mirror in front of Redis.
_in_call_state: dict[tuple[int, int], InCallLegs] = {}

# Redis key prefix + TTL for durable in-call leg state. The TTL is longer than
# any real call so the key never expires mid-call; it's refreshed on every save.
_INCALL_REDIS_PREFIX = "cc:agent:incall"
_INCALL_TTL_SEC = 6 * 60 * 60


def _incall_redis_key(tenant_id: int, employee_id: int) -> str:
    return f"{_INCALL_REDIS_PREFIX}:{tenant_id}:{employee_id}"


async def _legs(tenant_id: int, employee_id: int) -> InCallLegs:
    """Return the agent's in-call legs, hydrating from Redis on a cache miss.

    The in-process cache is checked first (so state set earlier in the same
    process — or seeded in tests — is found without Redis). On a miss, Redis is
    consulted; if it has the state it is hydrated and cached, otherwise a fresh
    empty InCallLegs is created and cached. With no Redis available this
    degrades to pure in-memory behavior.
    """

    key = (tenant_id, employee_id)
    cached = _in_call_state.get(key)
    if cached is not None:
        return cached

    from app.services.call_center.orchestrator import _get_redis_client

    r = _get_redis_client()
    if r is not None:
        try:
            raw = await r.get(_incall_redis_key(tenant_id, employee_id))
        except Exception:  # noqa: BLE001
            logger.warning(
                "in-call legs load failed agent=%s/%s",
                tenant_id, employee_id, exc_info=True,
            )
            raw = None
        if raw:
            legs = InCallLegs.from_dict(json.loads(raw))
            _in_call_state[key] = legs
            return legs

    legs = InCallLegs()
    _in_call_state[key] = legs
    return legs


async def _save_legs(tenant_id: int, employee_id: int, legs: InCallLegs) -> None:
    """Persist the agent's in-call legs to Redis (best-effort) + local cache."""

    _in_call_state[(tenant_id, employee_id)] = legs

    from app.services.call_center.orchestrator import _get_redis_client

    r = _get_redis_client()
    if r is None:
        return
    try:
        await r.set(
            _incall_redis_key(tenant_id, employee_id),
            json.dumps(legs.to_dict()),
            ex=_INCALL_TTL_SEC,
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "in-call legs save failed agent=%s/%s",
            tenant_id, employee_id, exc_info=True,
        )


async def _clear_legs(tenant_id: int, employee_id: int) -> None:
    """Drop the agent's in-call legs from Redis (best-effort) + local cache."""

    _in_call_state.pop((tenant_id, employee_id), None)

    from app.services.call_center.orchestrator import _get_redis_client

    r = _get_redis_client()
    if r is None:
        return
    try:
        await r.delete(_incall_redis_key(tenant_id, employee_id))
    except Exception:  # noqa: BLE001
        logger.warning(
            "in-call legs clear failed agent=%s/%s",
            tenant_id, employee_id, exc_info=True,
        )


# Reverse index: a conference PARTICIPANT leg's call_id -> "{tenant}:{host}", so
# when that leg's kernel call.hangup arrives we can tell the host (initiator) to
# collapse the 3-way back to the two-party call. Keyed by call_id (globally
# unique) so the hangup handler needs no tenant lookup.
_CONF_HOST_PREFIX = "cc:conf:host"


def _conf_host_key(participant_leg: str) -> str:
    return f"{_CONF_HOST_PREFIX}:{participant_leg}"


async def _register_conference_participant(
    tenant_id: int, host_employee_id: int, participant_leg: str
) -> None:
    """Record that ``participant_leg`` is a conference participant of ``host``."""

    from app.services.call_center.orchestrator import _get_redis_client

    r = _get_redis_client()
    if r is None or not participant_leg:
        return
    try:
        await r.set(
            _conf_host_key(participant_leg),
            f"{tenant_id}:{host_employee_id}",
            ex=_INCALL_TTL_SEC,
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "conference host register failed leg=%s", participant_leg, exc_info=True,
        )


class CallControlService:
    """In-call control for the current agent's own call.

    All methods take an explicit telephony client so the router can inject the
    shared singleton and tests can inject a mock. DB access uses short sessions
    opened only around the lookup, then closed before any kernel RPC.
    """

    # ───────────────────────── resolution ─────────────────────────

    @staticmethod
    async def _resolve_current_call(tenant_id: int, employee_id: int) -> CurrentCall:
        """Find the agent's active customer leg + WebRTC leg.

        Raises NotFoundError when the agent has no active call. The short DB
        session is closed before the caller issues any kernel RPC.
        """

        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(CallRecord)
                    .where(
                        CallRecord.tenant_id == tenant_id,
                        CallRecord.agent_id == employee_id,
                        CallRecord.state.in_(_ACTIVE_STATES),
                    )
                    .order_by(desc(CallRecord.started_at))
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("No active call")
            customer_call_id = row.root_call_id or row.call_id
            record_id = row.id
            session = await AgentWebRTCSessionService.get_active(
                db, tenant_id, employee_id
            )
            webrtc_call_id = session["webrtc_call_id"] if session else None

        return CurrentCall(
            record_id=record_id,
            tenant_id=tenant_id,
            customer_call_id=customer_call_id,
            webrtc_call_id=webrtc_call_id,
        )

    # ───────────────────────── target resolution ─────────────────────────

    @staticmethod
    async def _resolve_target_originate(
        tenant_id: int,
        target_type: str,
        target_id: int | None,
        number: str | None,
    ) -> tuple[dict, str]:
        """Turn a transfer/consult/conference target into `call_originate` kwargs.

        Returns `(kwargs, description)`. Uses a self-contained short session that
        closes before returning, so the caller holds no DB session across the
        originate RPC.

        - employee → dial the bound SIP extension directly (no trunk).
        - external → dial the number through the tenant's default outbound DID's
          trunk, using that DID as caller_id.

        Queue targets aren't assembled here (they need agent selection +
        ring-on-demand orchestration); callers surface a 501 for them.
        """

        if target_type == "employee":
            async with AsyncSessionLocal() as db:
                ext = await SipExtensionRepository.get_by_employee(
                    db, tenant_id, target_id
                )
            if ext is None:
                raise ValidationError(
                    "目标坐席未绑定 SIP 分机，且当前无可用 Web 电话"
                )
            if not ext.is_active:
                raise ValidationError("目标坐席的 SIP 分机已停用")
            if ext.registration_status != "registered":
                raise ValidationError("目标坐席的 SIP 分机未注册")
            return {"extension": ext.sip_user_id}, f"employee:{target_id}"

        if target_type == "external":
            async with AsyncSessionLocal() as db:
                tenant = await TenantPhoneNumberRepository.get_tenant(db, tenant_id)
                if tenant is None:
                    raise NotFoundError("Tenant not found")
                dids = await TenantPhoneNumberRepository.list_assigned(
                    db, tenant.tenant_id, limit=50
                )
            outbound = next(
                (
                    d
                    for d in dids
                    if isinstance(d.call_types, list)
                    and "outbound" in d.call_types
                    and d.trunk_id
                ),
                None,
            )
            if outbound is None:
                raise ValidationError("租户未配置可用于外呼的号码/中继")
            prefix = (outbound.called_number_prefix or "").strip()
            dialed = (
                prefix + number
                if prefix and not number.startswith(prefix)
                else number
            )
            return (
                {
                    "uri": dialed,
                    "caller_id": outbound.phone_number,
                    "trunk_id": outbound.trunk_id,
                },
                f"external:{number}",
            )

        raise NotImplementedApiError(
            "Queue targets are not supported for this operation yet"
        )

    @staticmethod
    async def _employee_target_is_webrtc(
        tenant_id: int, target_id: int | None
    ) -> bool:
        """Whether an employee target should be reached via a browser ring.

        True when the colleague is NOT reachable on a SIP extension but their
        current call device is an available Web phone — the internal WebRTC
        consult/transfer path. A short session is opened and closed here.
        """

        if target_id is None:
            return False
        async with AsyncSessionLocal() as db:
            ext = await SipExtensionRepository.get_by_employee(db, tenant_id, target_id)
            sip_ready = bool(
                ext
                and ext.is_active
                and ext.registration_status == "registered"
            )
            if sip_ready:
                return False
            device = await AgentCallDeviceService.get_current_device(
                db, tenant_id, target_id
            )
        from app.services.agent_call_device_service import DEVICE_WEBRTC

        return device.get("device_type") == DEVICE_WEBRTC and bool(
            device.get("available")
        )

    @staticmethod
    async def _reconcile_target_presence(
        r, tenant_id: int, target_employee_id: int
    ) -> dict | None:
        """Heal a stale Redis resource presence from the durable DB status.

        The real-time call-center resource view (Redis) can drift to "offline"
        after a release or key expiry even though the agent last chose "ready"
        and their browser is still connected. When that happens the agent looks
        ready in their own workspace (which reads the DB) but is wrongly
        rejected as offline for consult/transfer (which read Redis). This
        restores the Redis visible_status from the DB when — and only when —
        the agent chose "ready" AND their socket is actually live, so a browser
        that has gone away is never rung. Never touches an agent mid-call.

        Returns the healed snapshot, or None if nothing was healed.
        """

        from app.repositories.agent_status_repository import AgentStatusRepository
        from app.services.agent_status_service import AgentStatusService

        if not await AgentStatusService.is_connected(r, tenant_id, target_employee_id):
            return None
        async with AsyncSessionLocal() as db:
            row = await AgentStatusRepository.get_for_employee(
                db, tenant_id, target_employee_id
            )
        if getattr(row, "status", None) != "ready":
            return None
        from app.core.exceptions import ConflictError

        try:
            return await CcAgentResourceService.set_visible_status(
                r, tenant_id, target_employee_id, "ready"
            )
        except ConflictError:
            # Became busy between the read and the heal — leave state as-is.
            return None

    @staticmethod
    async def _precheck_webrtc_target_available(
        tenant_id: int, target_employee_id: int, *, action: str
    ) -> None:
        """Synchronously verify a Web-phone colleague can be rung right now.

        Runs *before* the customer is unbridged so a target that is offline or
        already busy fails the request outright (400) with a clear message and
        the customer's call is never disturbed.

        `action` is "咨询" or "转接" and is woven into the error text.

        - No snapshot / visible_status "offline" → offline: can't be rung.
        - resource_state reserved / ringing / in_call → already occupied.
        - otherwise (idle) → OK.

        Before deciding, a stale Redis "offline" is reconciled against the
        durable DB status so a genuinely-ready, connected colleague isn't
        wrongly rejected (see ``_reconcile_target_presence``).
        """

        from app.services.call_center.orchestrator import _get_redis_client
        from app.services.cc_agent_resource_service import ACTIVE_RESOURCE_STATES

        r = _get_redis_client()
        if r is None:
            # No Redis means the ring-on-demand path can't run at all; fail fast
            # rather than unbridging the customer for a call that can't proceed.
            raise ValidationError(f"目标坐席不在线，无法{action}")

        snapshot = await CcAgentResourceService.get_snapshot(
            r, tenant_id, target_employee_id
        )
        # Only reconcile when the snapshot looks unavailable and the agent isn't
        # mid-call; a healthy or busy snapshot is already authoritative.
        if snapshot is None or (
            snapshot.get("visible_status") == "offline"
            and snapshot.get("resource_state") not in ACTIVE_RESOURCE_STATES
        ):
            healed = await CallControlService._reconcile_target_presence(
                r, tenant_id, target_employee_id
            )
            if healed is not None:
                snapshot = healed

        if snapshot is None or snapshot.get("visible_status") == "offline":
            raise ValidationError(f"目标坐席不在线，无法{action}")
        if snapshot.get("resource_state") in ACTIVE_RESOURCE_STATES:
            raise ValidationError(f"目标坐席正在通话，无法{action}")

    @staticmethod
    async def _notify_browser_call_ended(
        tenant_id: int, employee_id: int, call_id: str, *, reason: str
    ) -> None:
        """Push cc.call_hangup to an agent's browser so its WebRTC peer closes.

        Used whenever we tear a browser-held leg down server-side — a consult
        target we rang, or the agent's own leg when they leave / end a
        conference. The kernel just stops the media, so without this signal the
        browser stalls on the dead call and reports a spurious ICE failure; the
        cc.call_hangup handler closes the peer cleanly and moves to wrap-up.
        """

        from app.services.call_center.orchestrator import get_orchestrator

        try:
            await get_orchestrator().notify_agent_call_ended(
                tenant_id=tenant_id,
                employee_id=employee_id,
                call_id=call_id,
                reason=reason,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "call-ended push failed agent=%s/%s",
                tenant_id, employee_id, exc_info=True,
            )

    @staticmethod
    async def _notify_control_result(
        *, tenant_id: int, initiator_employee_id: int, method: str, payload: dict
    ) -> None:
        """Push a consult/transfer result to the initiating agent's browser."""

        from app.services.call_center.orchestrator import get_orchestrator

        try:
            await get_orchestrator().notify_agent_control_result(
                tenant_id=tenant_id,
                employee_id=initiator_employee_id,
                method=method,
                payload=payload,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "control result push failed method=%s initiator=%s/%s",
                method, tenant_id, initiator_employee_id, exc_info=True,
            )

    @staticmethod
    async def _notify_consult_failed(
        tenant_id: int, initiator_employee_id: int, reason: str
    ) -> None:
        """Tell the initiator their WebRTC consult ring failed."""

        await CallControlService._notify_control_result(
            tenant_id=tenant_id,
            initiator_employee_id=initiator_employee_id,
            method="cc.consult_result",
            payload={
                "ok": False,
                "kind": "consult",
                "reason": CallControlService._friendly_fail_reason(reason),
            },
        )

    @staticmethod
    async def _notify_transfer_failed(
        tenant_id: int, initiator_employee_id: int, reason: str
    ) -> None:
        """Tell the initiator their WebRTC transfer ring failed."""

        await CallControlService._notify_control_result(
            tenant_id=tenant_id,
            initiator_employee_id=initiator_employee_id,
            method="cc.transfer_result",
            payload={
                "ok": False,
                "kind": "transfer",
                "reason": CallControlService._friendly_fail_reason(reason),
            },
        )

    @staticmethod
    def _friendly_fail_reason(reason: str) -> str:
        """Map an internal failure code to an agent-facing message."""

        mapping = {
            "目标坐席未接听": "目标坐席未接听",
            "目标坐席拒接": "目标坐席拒接",
            "目标坐席不在线，无法振铃": "目标坐席不在线",
            "目标坐席正在通话或不可用": "目标坐席正在通话",
            "no_redis": "通话服务暂不可用",
            "no_answer": "目标坐席未接听",
            "declined": "目标坐席拒接",
        }
        if reason in mapping:
            return mapping[reason]
        # ValidationError / ConflictError messages are already user-facing; pass
        # them through. Fall back to a generic message for opaque error strings.
        if any(ch >= "一" and ch <= "鿿" for ch in reason):
            return reason
        return "呼叫目标坐席失败"

    @staticmethod
    async def _resolve_initiator_display(tenant_id: int, employee_id: int) -> str:
        """Human-readable name of the agent starting the internal call."""

        async with AsyncSessionLocal() as db:
            emp = await EmployeeRepository.get_by_id(db, employee_id)
        if emp is None:
            return ""
        return emp.display_name or emp.nickname or emp.name or emp.username or ""

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
            tone = await CallControlService._load_scene_tone(tenant_id, scene)
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
                interval_ms=_TONE_LOOP_INTERVAL_MS if loop else None,
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

        settings = await CallPromptToneService.get_settings_managed(tenant_id)
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
        async with AsyncSessionLocal() as db:
            asset = await AudioAssetRepository.get_by_id(
                db, cfg.audio_asset_id, tenant_id
            )
        if asset is None:
            return None
        if asset.mime_type not in _PLAYABLE_AUDIO_MIME:
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
        telephony: BaseTelephonyClient, *, tenant_id: int, call: CurrentCall
    ) -> None:
        """Hold the customer with the three-party waiting tone while a
        participant is being invited.

        Mirrors consult hold: unbridge the agent leg (keeps the customer's RTP
        flowing so the tone is audible) and start the configured three-party
        waiting tone on the customer leg.
        """

        if call.webrtc_call_id:
            await telephony.call_unbridge(call.customer_call_id, call.webrtc_call_id)
        await CallControlService._play_scene_tone(
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
            call = await CallControlService._resolve_current_call(
                tenant_id, employee_id
            )
        except NotFoundError:
            return
        await CallControlService._stop_tone(telephony, call.customer_call_id)
        if call.webrtc_call_id:
            try:
                await telephony.call_bridge(
                    call.customer_call_id, call.webrtc_call_id
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

        call = await CallControlService._resolve_current_call(tenant_id, employee_id)
        if call.webrtc_call_id:
            await telephony.call_unbridge(call.customer_call_id, call.webrtc_call_id)
        await CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="hold",
        )
        logger.info("hold: agent=%s call=%s", employee_id, call.customer_call_id)
        return {"ok": True, "call_id": call.customer_call_id}

    @staticmethod
    async def unhold(
        telephony: BaseTelephonyClient, *, tenant_id: int, employee_id: int
    ) -> dict:
        """Resume the customer + stop the hold waiting tone."""

        call = await CallControlService._resolve_current_call(tenant_id, employee_id)
        await CallControlService._stop_tone(telephony, call.customer_call_id)
        if call.webrtc_call_id:
            await telephony.call_bridge(call.customer_call_id, call.webrtc_call_id)
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

        call = await CallControlService._resolve_current_call(tenant_id, employee_id)
        await telephony.call_dtmf(call.customer_call_id, digits)
        logger.info(
            "dtmf: agent=%s call=%s count=%d",
            employee_id, call.customer_call_id, len(digits),
        )
        return {"ok": True, "call_id": call.customer_call_id}

    # ───────────────────────── mute (trail only) ─────────────────────────

    @staticmethod
    async def mute(
        *, tenant_id: int, employee_id: int, muted: bool
    ) -> dict:
        """Record the agent's local mute state.

        Muting the microphone happens in the browser WebRTC layer
        (track.enabled=false); there is no kernel RPC. We only confirm the
        agent has an active call so the state-change event is meaningful for
        the call's operation trail.
        """

        call = await CallControlService._resolve_current_call(tenant_id, employee_id)
        logger.info(
            "mute: agent=%s call=%s muted=%s",
            employee_id, call.customer_call_id, muted,
        )
        return {"ok": True, "call_id": call.customer_call_id}

    # ───────────────────────── transfer (blind) ─────────────────────────

    @staticmethod
    async def transfer(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        target_type: str,
        target_id: int | None,
        number: str | None,
    ) -> dict:
        """Blind (direct) transfer of the customer to a new target.

        Flow: originate the target leg (employee extension / external number),
        play the transfer prompt to the customer, then hand the target-answer
        wait to the orchestrator. When the target answers, the customer is
        bridged to it and the agent's own leg is dropped — off the request path.
        On no-answer / decline the customer is restored to the agent so the call
        is never lost. The request returns as soon as the target rings.
        """

        CallControlService._validate_target(target_type, target_id, number)
        call = await CallControlService._resolve_current_call(tenant_id, employee_id)

        # Route an employee target with no SIP extension but an available Web
        # phone to the internal browser-ring transfer path.
        if target_type == "employee" and await CallControlService._employee_target_is_webrtc(
            tenant_id, target_id
        ):
            # Fail fast (before touching the customer) if the colleague is
            # offline or already busy, so the customer's call is never disturbed.
            await CallControlService._precheck_webrtc_target_available(
                tenant_id, target_id, action="转接"
            )
            return await CallControlService._transfer_webrtc_employee(
                telephony,
                tenant_id=tenant_id,
                employee_id=employee_id,
                target_employee_id=target_id,
                call=call,
            )

        originate_kwargs, desc_str = await CallControlService._resolve_target_originate(
            tenant_id, target_type, target_id, number
        )
        target_call_id = await CallControlService._originate_target(
            telephony, originate_kwargs
        )

        # Waiting tone for the customer while the target rings (single play).
        await CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="transfer",
        )

        CallControlService._spawn_target_wait(
            telephony,
            target_call_id=target_call_id,
            on_answer=lambda: CallControlService._complete_blind_transfer(
                telephony, call, target_call_id
            ),
            on_fail=lambda reason: CallControlService._restore_after_target_failure(
                telephony, call, target_call_id, reason
            ),
        )

        logger.info(
            "transfer: agent=%s customer=%s -> %s target_leg=%s (ringing)",
            employee_id, call.customer_call_id, desc_str, target_call_id,
        )
        return {"ok": True, "call_id": call.customer_call_id, "note": "ringing_target"}

    @staticmethod
    async def _complete_blind_transfer(
        telephony: BaseTelephonyClient, call: CurrentCall, target_call_id: str
    ) -> bool:
        """Target answered → bridge customer to target, drop the agent leg.

        Returns True when the handover completed (customer is now with the
        target); False when it failed and the customer was restored to the agent.
        """

        await CallControlService._stop_tone(telephony, call.customer_call_id)
        # Detach the customer from the initiating agent FIRST — the kernel
        # refuses to bridge an already-bridged call (-32003), which was silently
        # aborting the whole handover (customer stayed stuck on the agent, the
        # target's answered leg orphaned). Best-effort: a no-op if already held.
        if call.webrtc_call_id:
            try:
                await telephony.call_unbridge(
                    call.customer_call_id, call.webrtc_call_id
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "transfer: detach customer from agent before handover failed"
                    " customer=%s agent_leg=%s",
                    call.customer_call_id, call.webrtc_call_id, exc_info=True,
                )
        try:
            await telephony.call_bridge(call.customer_call_id, target_call_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "transfer bridge failed customer=%s target=%s",
                call.customer_call_id, target_call_id,
            )
            # Re-attach the customer to the agent so the call isn't lost.
            if call.webrtc_call_id:
                try:
                    await telephony.call_bridge(
                        call.customer_call_id, call.webrtc_call_id
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "transfer: re-attach customer to agent after bridge-fail"
                        " failed customer=%s", call.customer_call_id, exc_info=True,
                    )
            await CallControlService._restore_after_target_failure(
                telephony, call, target_call_id, "bridge_failed"
            )
            return False
        # Customer is now with the target; release the agent's own leg.
        if call.webrtc_call_id:
            try:
                await telephony.call_hangup(call.webrtc_call_id, reason="transferred")
            except Exception:  # noqa: BLE001
                logger.warning(
                    "transfer: agent leg hangup failed leg=%s",
                    call.webrtc_call_id, exc_info=True,
                )
        logger.info(
            "transfer complete: customer=%s bridged to target=%s",
            call.customer_call_id, target_call_id,
        )
        return True

    @staticmethod
    async def _transfer_webrtc_employee(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        target_employee_id: int,
        call: CurrentCall,
    ) -> dict:
        """Blind-transfer the customer to a colleague on the Web phone.

        Play the transfer tone, ring the target's browser off the request path,
        and on accept bridge the CUSTOMER to the target's WebRTC leg then drop
        the initiator's own leg. On decline / no-answer the customer is kept with
        the initiator (never lost). Returns ``ringing_target`` immediately.
        """

        await CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="transfer",
        )
        display = await CallControlService._resolve_initiator_display(
            tenant_id, employee_id
        )

        async def _ring_and_handover() -> None:
            from app.services.call_center.internal_consult_service import (
                InternalConsultService,
            )
            from app.services.call_center.orchestrator import _get_redis_client

            r = _get_redis_client()
            if r is None:
                await CallControlService._restore_after_target_failure(
                    telephony, call, "", "no_redis",
                )
                await CallControlService._notify_transfer_failed(
                    tenant_id, employee_id, "no_redis"
                )
                return
            try:
                result = await InternalConsultService.initiate_webrtc_consult(
                    telephony,
                    r,
                    tenant_id=tenant_id,
                    initiator_employee_id=employee_id,
                    target_employee_id=target_employee_id,
                    initiator_display=display,
                    call_type="internal_transfer",
                )
            except Exception as exc:  # noqa: BLE001
                await CallControlService._restore_after_target_failure(
                    telephony, call, "", str(exc),
                )
                await CallControlService._notify_transfer_failed(
                    tenant_id, employee_id, str(exc)
                )
                return
            # The colleague now owns the customer call: re-point their occupied
            # resource from the internal consult leg onto the customer call so it
            # finalizes cleanly on the customer's own hangup.
            await CallControlService._rekey_internal_target_to_customer(
                tenant_id, target_employee_id, call.customer_call_id,
            )
            handed_over = await CallControlService._complete_blind_transfer(
                telephony, call, result["target_webrtc_call_id"]
            )
            if not handed_over:
                # Bridge failed → customer was restored to the initiator; free
                # the colleague we occupied and report the failure.
                await CallControlService._release_internal_target(
                    tenant_id, target_employee_id, reason="transfer_bridge_failed",
                )
                await CallControlService._notify_transfer_failed(
                    tenant_id, employee_id, "转接失败，客户通话仍在继续",
                )
                return
            # Hand the call record over to the colleague too. Without this the
            # record still belongs to the initiator, so the initiator's hangup
            # would target (and kill) the customer call, and the customer's
            # hangup would notify the initiator — leaving the colleague stuck.
            await CallControlService._reassign_call_record_to_agent(
                tenant_id, call.customer_call_id, target_employee_id,
            )
            # Customer handed over, initiator's own leg dropped — tell the UI.
            await CallControlService._notify_control_result(
                tenant_id=tenant_id,
                initiator_employee_id=employee_id,
                method="cc.transfer_result",
                payload={"ok": True, "kind": "transfer"},
            )

        asyncio.create_task(
            _ring_and_handover(),
            name=f"internal-transfer:{tenant_id}:{target_employee_id}",
        )
        logger.info(
            "transfer (webrtc): agent=%s customer=%s -> employee:%s (ringing browser)",
            employee_id, call.customer_call_id, target_employee_id,
        )
        # Distinct note: the browser stays in "转接中" until a cc.transfer_result
        # socket event reports the outcome (the ring resolves off the request path).
        return {
            "ok": True,
            "call_id": call.customer_call_id,
            "note": "ringing_webrtc_target",
        }

    # ───────────────────────── consult ─────────────────────────

    @staticmethod
    async def consult_start(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        target_type: str,
        target_id: int | None,
        number: str | None,
    ) -> dict:
        """Start a consultation: hold + consult-tone the customer, call a third
        party, and bridge the agent to it when it answers.

        The customer stays held (hearing the consult waiting tone) throughout.
        The agent↔target bridge is established off the request path once the
        target answers; the request returns as soon as the target rings.
        """

        CallControlService._validate_target(target_type, target_id, number)
        call = await CallControlService._resolve_current_call(tenant_id, employee_id)
        if call.webrtc_call_id is None:
            raise ValidationError("坐席媒体腿不可用，无法发起咨询")

        # Route an employee target with no SIP extension but an available Web
        # phone to the internal browser-ring consult path.
        if target_type == "employee" and await CallControlService._employee_target_is_webrtc(
            tenant_id, target_id
        ):
            # Fail fast (before holding the customer) if the colleague is offline
            # or already busy, so the customer's call is never disturbed.
            await CallControlService._precheck_webrtc_target_available(
                tenant_id, target_id, action="咨询"
            )
            return await CallControlService._consult_webrtc_employee(
                telephony,
                tenant_id=tenant_id,
                employee_id=employee_id,
                target_employee_id=target_id,
                call=call,
            )

        originate_kwargs, desc_str = await CallControlService._resolve_target_originate(
            tenant_id, target_type, target_id, number
        )

        # Unbridge the agent leg (keeps customer RTP flowing for the tone) and
        # start the consult waiting tone before dialing the third party.
        await telephony.call_unbridge(call.customer_call_id, call.webrtc_call_id)
        await CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="consult",
        )

        target_call_id = await CallControlService._originate_target(
            telephony, originate_kwargs
        )
        legs = await _legs(tenant_id, employee_id)
        legs.consult_call_id = target_call_id
        await _save_legs(tenant_id, employee_id, legs)

        webrtc_call_id = call.webrtc_call_id

        async def _bridge_agent_to_consult() -> None:
            try:
                await telephony.call_bridge(webrtc_call_id, target_call_id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "consult bridge failed agent=%s target=%s",
                    webrtc_call_id, target_call_id,
                )

        CallControlService._spawn_target_wait(
            telephony,
            target_call_id=target_call_id,
            on_answer=_bridge_agent_to_consult,
            on_fail=lambda reason: CallControlService._restore_after_consult_failure(
                telephony, tenant_id, employee_id, call, target_call_id, reason
            ),
        )

        logger.info(
            "consult start: agent=%s customer=%s held -> %s consult_leg=%s (ringing)",
            employee_id, call.customer_call_id, desc_str, target_call_id,
        )
        return {"ok": True, "call_id": call.customer_call_id, "note": "ringing_target"}

    @staticmethod
    async def _consult_webrtc_employee(
        telephony: BaseTelephonyClient,
        *,
        tenant_id: int,
        employee_id: int,
        target_employee_id: int,
        call: CurrentCall,
    ) -> dict:
        """Consult a colleague on the Web phone: ring their browser, then bridge.

        Mirrors the SIP consult: unbridge + consult-tone the customer, then ring
        the target's browser off the request path. On accept, the target's own
        WebRTC leg (returned by their accept) is stored as the consult leg and
        bridged to the initiator; on decline / no-answer the customer is resumed.
        The request returns ``ringing_target`` as soon as the target rings.
        """

        await telephony.call_unbridge(call.customer_call_id, call.webrtc_call_id)
        await CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="consult",
        )
        display = await CallControlService._resolve_initiator_display(
            tenant_id, employee_id
        )
        webrtc_call_id = call.webrtc_call_id

        target_name = await CallControlService._resolve_initiator_display(
            tenant_id, target_employee_id
        )

        async def _ring_and_bridge() -> None:
            from app.services.call_center.internal_consult_service import (
                InternalConsultService,
            )
            from app.services.call_center.orchestrator import _get_redis_client

            r = _get_redis_client()
            if r is None:
                await CallControlService._restore_after_consult_failure(
                    telephony, tenant_id, employee_id, call, "", "no_redis",
                )
                await CallControlService._notify_consult_failed(
                    tenant_id, employee_id, "no_redis"
                )
                return
            try:
                result = await InternalConsultService.initiate_webrtc_consult(
                    telephony,
                    r,
                    tenant_id=tenant_id,
                    initiator_employee_id=employee_id,
                    target_employee_id=target_employee_id,
                    initiator_display=display,
                    call_type="internal_consult",
                )
            except Exception as exc:  # noqa: BLE001
                await CallControlService._restore_after_consult_failure(
                    telephony, tenant_id, employee_id, call, "", str(exc),
                )
                await CallControlService._notify_consult_failed(
                    tenant_id, employee_id, str(exc)
                )
                return
            target_leg = result["target_webrtc_call_id"]
            legs = await _legs(tenant_id, employee_id)
            legs.consult_call_id = target_leg
            legs.consult_target_employee_id = target_employee_id
            legs.consult_offer_id = result.get("offer_id")
            await _save_legs(tenant_id, employee_id, legs)
            try:
                await telephony.call_bridge(webrtc_call_id, target_leg)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "internal consult bridge failed agent=%s target=%s",
                    webrtc_call_id, target_leg,
                )
                await CallControlService._notify_consult_failed(
                    tenant_id, employee_id, "bridge_failed"
                )
                return
            # Target answered and the initiator is now bridged to them.
            await CallControlService._notify_control_result(
                tenant_id=tenant_id,
                initiator_employee_id=employee_id,
                method="cc.consult_result",
                payload={"ok": True, "kind": "consult", "target_name": target_name},
            )

        asyncio.create_task(
            _ring_and_bridge(),
            name=f"internal-consult:{tenant_id}:{target_employee_id}",
        )
        logger.info(
            "consult start (webrtc): agent=%s customer=%s held -> employee:%s (ringing browser)",
            employee_id, call.customer_call_id, target_employee_id,
        )
        # Distinct note: the browser stays in "咨询呼叫中" until a cc.consult_result
        # socket event reports the outcome (the ring resolves off the request path).
        return {
            "ok": True,
            "call_id": call.customer_call_id,
            "note": "ringing_webrtc_target",
        }

    @staticmethod
    async def consult_end(
        telephony: BaseTelephonyClient, *, tenant_id: int, employee_id: int
    ) -> dict:
        """End a consultation: drop the third party, resume the customer.

        Un-bridges the agent from the consult leg, hangs the consult leg up,
        stops the consult waiting tone, and un-holds the customer back to the
        agent.
        """

        call = await CallControlService._resolve_current_call(tenant_id, employee_id)
        legs = await _legs(tenant_id, employee_id)
        consult_call_id = legs.consult_call_id
        if not consult_call_id:
            raise NotFoundError("No active consultation")
        target_employee_id = legs.consult_target_employee_id

        if call.webrtc_call_id:
            try:
                await telephony.call_unbridge(call.webrtc_call_id, consult_call_id)
            except Exception:  # noqa: BLE001
                logger.warning("consult unbridge failed", exc_info=True)
        try:
            await telephony.call_hangup(consult_call_id, reason="consult_ended")
        except Exception:  # noqa: BLE001
            logger.warning("consult leg hangup failed", exc_info=True)

        # Internal browser-ring target: we occupied that colleague's call-center
        # resource to ring them for this consult, so free it now that the consult
        # is over — otherwise they stay stuck busy and can't be dialed again.
        if target_employee_id is not None:
            await CallControlService._release_internal_target(
                tenant_id, target_employee_id, reason="internal_consult_ended",
            )
            # Tell the colleague's browser its consult leg is over so it closes
            # the WebRTC peer cleanly. Without this the target stays stuck at
            # "通话中" until the media times out and reports a spurious ICE
            # failure, and a later hangup click resolves to a stale call.
            await CallControlService._notify_browser_call_ended(
                tenant_id, target_employee_id, consult_call_id, reason="consult_ended",
            )

        await CallControlService._stop_tone(telephony, call.customer_call_id)
        if call.webrtc_call_id:
            await telephony.call_bridge(call.customer_call_id, call.webrtc_call_id)
        legs.consult_call_id = None
        legs.consult_target_employee_id = None
        legs.consult_offer_id = None
        await _save_legs(tenant_id, employee_id, legs)
        logger.info(
            "consult end: agent=%s customer=%s resumed (consult_leg=%s dropped)",
            employee_id, call.customer_call_id, consult_call_id,
        )
        return {"ok": True, "call_id": call.customer_call_id}

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

        CallControlService._validate_target(target_type, target_id, number)
        call = await CallControlService._resolve_current_call(tenant_id, employee_id)

        # A colleague on the Web phone (no SIP extension) is reached by ringing
        # their browser, then merged into the room on answer — the SIP-originate
        # path below only handles SIP-extension employees and external numbers.
        if target_type == "employee" and await CallControlService._employee_target_is_webrtc(
            tenant_id, target_id
        ):
            await CallControlService._precheck_webrtc_target_available(
                tenant_id, target_id, action="添加参与人"
            )
            return await CallControlService._conference_webrtc_employee(
                telephony,
                tenant_id=tenant_id,
                employee_id=employee_id,
                target_employee_id=target_id,
                call=call,
            )

        originate_kwargs, desc_str = await CallControlService._resolve_target_originate(
            tenant_id, target_type, target_id, number
        )
        target_call_id = await CallControlService._originate_target(
            telephony, originate_kwargs
        )
        legs = await _legs(tenant_id, employee_id)
        legs.conference_participant_call_id = target_call_id
        await _save_legs(tenant_id, employee_id, legs)

        # Hold the customer with the three-party tone while the participant
        # rings (only after a good originate, so a bad number never disturbs
        # the customer).
        await CallControlService._hold_customer_for_conference(
            telephony, tenant_id=tenant_id, call=call
        )

        async def _on_answer() -> None:
            try:
                await CallControlService._merge_participant_room(
                    telephony,
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    participant_call_id=target_call_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("conference auto-merge failed", exc_info=True)
                await CallControlService._abort_conference_participant(
                    telephony, tenant_id, employee_id, target_call_id, str(exc)
                )
                return
            await CallControlService._notify_conference_result(
                tenant_id, employee_id, ok=True, reason=None
            )

        async def _on_fail(reason: str) -> None:
            await CallControlService._abort_conference_participant(
                telephony, tenant_id, employee_id, target_call_id, reason
            )

        CallControlService._spawn_target_wait(
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
        call: CurrentCall,
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
        display = await CallControlService._resolve_initiator_display(
            tenant_id, employee_id
        )

        # Hold the customer with the three-party tone while the colleague's
        # browser rings; the tone stops on merge, or the customer is restored
        # on the failure paths below.
        await CallControlService._hold_customer_for_conference(
            telephony, tenant_id=tenant_id, call=call
        )

        async def _ring_and_merge() -> None:
            from app.services.call_center.internal_consult_service import (
                InternalConsultService,
            )
            from app.services.call_center.orchestrator import _get_redis_client

            r = _get_redis_client()
            if r is None:
                await CallControlService._restore_customer_from_conference(
                    telephony, tenant_id=tenant_id, employee_id=employee_id
                )
                await CallControlService._notify_conference_result(
                    tenant_id, employee_id, ok=False, reason="no_redis"
                )
                return
            try:
                result = await InternalConsultService.initiate_webrtc_consult(
                    telephony,
                    r,
                    tenant_id=tenant_id,
                    initiator_employee_id=employee_id,
                    target_employee_id=target_employee_id,
                    initiator_display=display,
                    call_type="internal_conference",
                )
            except Exception as exc:  # noqa: BLE001
                # The internal path already released the target on failure.
                await CallControlService._restore_customer_from_conference(
                    telephony, tenant_id=tenant_id, employee_id=employee_id
                )
                await CallControlService._notify_conference_result(
                    tenant_id, employee_id, ok=False, reason=str(exc)
                )
                return
            target_leg = result["target_webrtc_call_id"]
            legs = await _legs(tenant_id, employee_id)
            legs.conference_participant_call_id = target_leg
            legs.conference_target_employee_id = target_employee_id
            await _save_legs(tenant_id, employee_id, legs)
            try:
                await CallControlService._merge_participant_room(
                    telephony,
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    participant_call_id=target_leg,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("conference webrtc merge failed", exc_info=True)
                legs.conference_participant_call_id = None
                legs.conference_target_employee_id = None
                await _save_legs(tenant_id, employee_id, legs)
                await CallControlService._restore_customer_from_conference(
                    telephony, tenant_id=tenant_id, employee_id=employee_id
                )
                await CallControlService._release_internal_target(
                    tenant_id, target_employee_id, reason="conference_merge_failed"
                )
                await CallControlService._notify_browser_call_ended(
                    tenant_id, target_employee_id, target_leg, reason="conference_failed"
                )
                await CallControlService._notify_conference_result(
                    tenant_id, employee_id, ok=False, reason=str(exc)
                )
                return
            await CallControlService._notify_conference_result(
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

        call = await CallControlService._resolve_current_call(tenant_id, employee_id)
        legs = await _legs(tenant_id, employee_id)
        if call.webrtc_call_id is None:
            raise ValidationError("坐席媒体腿不可用，无法合并三方")
        # Stop the three-party waiting tone before the room re-includes the
        # customer — the room already carries the customer's audio, so we only
        # stop the tone here (no re-bridge).
        await CallControlService._stop_tone(telephony, call.customer_call_id)
        leg_ids = [call.customer_call_id, call.webrtc_call_id, participant_call_id]
        try:
            result = await telephony.room_create(leg_call_ids=leg_ids)
        except TelephonyMethodNotFoundError as exc:
            raise NotImplementedApiError("当前通话服务暂不支持三方") from exc
        room_id = result.get("room_id")
        legs.room_id = room_id
        legs.room_legs = list(leg_ids)
        await _save_legs(tenant_id, employee_id, legs)
        # Index the participant leg → host so we can collapse this agent's
        # conference when the participant later hangs up / drops.
        await _register_conference_participant(
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
            raw = await r.get(_conf_host_key(participant_leg))
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
            await r.delete(_conf_host_key(participant_leg))
        except Exception:  # noqa: BLE001
            pass

        # Drop the participant from the host's in-call legs.
        legs = await _legs(tenant_id, host_employee_id)
        changed = False
        if legs.conference_participant_call_id == participant_leg:
            legs.conference_participant_call_id = None
            legs.conference_target_employee_id = None
            changed = True
        if participant_leg in legs.room_legs:
            legs.room_legs.remove(participant_leg)
            changed = True
        if changed:
            await _save_legs(tenant_id, host_employee_id, legs)

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

        legs = await _legs(tenant_id, employee_id)
        if participant_call_id:
            try:
                await telephony.call_hangup(
                    participant_call_id, reason="participant_aborted"
                )
            except Exception:  # noqa: BLE001
                pass
        if legs.conference_participant_call_id == participant_call_id:
            legs.conference_participant_call_id = None
            await _save_legs(tenant_id, employee_id, legs)
        logger.info(
            "conference participant aborted: agent=%s leg=%s reason=%s",
            employee_id, participant_call_id, reason,
        )
        # Stop the three-party tone and re-bridge the held customer back to the
        # agent before telling the browser the invite failed.
        await CallControlService._restore_customer_from_conference(
            telephony, tenant_id=tenant_id, employee_id=employee_id
        )
        await CallControlService._notify_conference_result(
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
        await CallControlService._notify_control_result(
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

        call = await CallControlService._resolve_current_call(tenant_id, employee_id)
        legs = await _legs(tenant_id, employee_id)
        participant = legs.conference_participant_call_id
        if not participant:
            raise NotFoundError("No participant to merge")
        if call.webrtc_call_id is None:
            raise ValidationError("坐席媒体腿不可用，无法合并三方")

        leg_ids = [call.customer_call_id, call.webrtc_call_id, participant]
        await CallControlService._play_scene_tone(
            telephony,
            tenant_id=tenant_id,
            customer_call_id=call.customer_call_id,
            scene="three_party",
        )
        try:
            result = await telephony.room_create(leg_call_ids=leg_ids)
        except TelephonyMethodNotFoundError as exc:
            await CallControlService._stop_tone(telephony, call.customer_call_id)
            raise NotImplementedApiError(
                "当前通话服务暂不支持三方"
            ) from exc

        room_id = result.get("room_id")
        legs.room_id = room_id
        legs.room_legs = list(leg_ids)
        await _save_legs(tenant_id, employee_id, legs)
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

        call = await CallControlService._resolve_current_call(tenant_id, employee_id)
        legs = await _legs(tenant_id, employee_id)
        if not legs.room_id or not legs.conference_participant_call_id:
            raise NotFoundError("No active conference")
        participant = legs.conference_participant_call_id
        await CallControlService._room_remove(telephony, legs, participant)
        try:
            await telephony.call_hangup(participant, reason="participant_removed")
        except Exception:  # noqa: BLE001
            logger.warning("conference participant hangup failed", exc_info=True)
        legs.conference_participant_call_id = None
        await _save_legs(tenant_id, employee_id, legs)
        logger.info(
            "conference remove: agent=%s room=%s participant=%s",
            employee_id, legs.room_id, participant,
        )
        return {"ok": True, "call_id": call.customer_call_id}

    @staticmethod
    async def conference_leave(
        telephony: BaseTelephonyClient, *, tenant_id: int, employee_id: int
    ) -> dict:
        """Agent leaves the conference; customer and participant keep talking."""

        call = await CallControlService._resolve_current_call(tenant_id, employee_id)
        legs = await _legs(tenant_id, employee_id)
        if not legs.room_id:
            raise NotFoundError("No active conference")
        # "Leave" hands the room to a customer + external participant. A
        # Web-phone *colleague* participant is tracked only on this agent's
        # transient state, so leaving would orphan their occupied resource —
        # free them and end their leg instead of stranding them busy.
        webrtc_participant = legs.conference_target_employee_id
        participant_leg = legs.conference_participant_call_id
        if call.webrtc_call_id:
            await CallControlService._room_remove(telephony, legs, call.webrtc_call_id)
            try:
                await telephony.call_hangup(call.webrtc_call_id, reason="agent_left")
            except Exception:  # noqa: BLE001
                logger.warning("conference agent leg hangup failed", exc_info=True)
            # The agent's own browser leg is gone; tell it to close cleanly.
            await CallControlService._notify_browser_call_ended(
                tenant_id, employee_id, call.webrtc_call_id, reason="left_conference",
            )
        if webrtc_participant is not None:
            await CallControlService._release_internal_target(
                tenant_id, webrtc_participant, reason="conference_left"
            )
            if participant_leg:
                try:
                    await telephony.call_hangup(participant_leg, reason="conference_left")
                except Exception:  # noqa: BLE001
                    logger.warning("conference participant hangup failed", exc_info=True)
                await CallControlService._notify_browser_call_ended(
                    tenant_id, webrtc_participant, participant_leg, reason="conference_left",
                )
            legs.conference_target_employee_id = None
            legs.conference_participant_call_id = None
        await _save_legs(tenant_id, employee_id, legs)
        logger.info(
            "conference leave: agent=%s room=%s", employee_id, legs.room_id,
        )
        return {"ok": True, "call_id": call.customer_call_id}

    @staticmethod
    async def conference_end_all(
        telephony: BaseTelephonyClient, *, tenant_id: int, employee_id: int
    ) -> dict:
        """End the call for everyone: close the room (if any) and drop all legs.

        Robust to a participant that is still ringing (no room created yet): we
        never 404 here, because that would leave the agent unable to hang up.
        Whatever legs exist — customer, agent, participant — are torn down.
        """

        call = await CallControlService._resolve_current_call(tenant_id, employee_id)
        legs = await _legs(tenant_id, employee_id)
        room_id = legs.room_id
        participant_leg = legs.conference_participant_call_id
        webrtc_participant = legs.conference_target_employee_id
        # In case the conference is ended mid-invite (participant still ringing,
        # no room yet), stop any lingering three-party waiting tone.
        await CallControlService._stop_tone(telephony, call.customer_call_id)
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
        await _clear_legs(tenant_id, employee_id)
        # Close the agent's own browser leg cleanly and move it to wrap-up.
        if call.webrtc_call_id:
            await CallControlService._notify_browser_call_ended(
                tenant_id, employee_id, call.webrtc_call_id, reason="conference_ended",
            )
        # A Web-phone colleague participant: free their occupied resource and
        # close their browser leg too, or they stay stuck busy.
        if webrtc_participant is not None:
            await CallControlService._release_internal_target(
                tenant_id, webrtc_participant, reason="conference_ended"
            )
            if participant_leg:
                await CallControlService._notify_browser_call_ended(
                    tenant_id, webrtc_participant, participant_leg,
                    reason="conference_ended",
                )
        logger.info("conference end-all: agent=%s room=%s", employee_id, room_id)
        return {"ok": True, "call_id": call.customer_call_id}

    # ───────────────────────── helpers ─────────────────────────

    @staticmethod
    async def _room_remove(
        telephony: BaseTelephonyClient, legs: InCallLegs, call_id: str
    ) -> None:
        try:
            await telephony.room_remove_leg(legs.room_id, call_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "room_remove_leg failed room=%s leg=%s",
                legs.room_id, call_id, exc_info=True,
            )
        if call_id in legs.room_legs:
            legs.room_legs.remove(call_id)

    @staticmethod
    async def _originate_target(
        telephony: BaseTelephonyClient, originate_kwargs: dict
    ) -> str:
        """Originate a transfer/consult/conference target leg.

        Maps typed kernel rejections to ValidationError (→ 400) so the original
        call is never lost on a bad target. Returns the new leg's call_id.
        """

        try:
            result = await telephony.call_originate(**originate_kwargs)
        except TelephonyRPCError as exc:
            logger.warning("target originate rejected code=%s", exc.code)
            raise ValidationError(str(exc)) from exc
        target_call_id = result.get("call_id")
        if not target_call_id:
            raise ValidationError("语音内核未返回目标呼叫标识")
        return target_call_id

    @staticmethod
    def _spawn_target_wait(
        telephony: BaseTelephonyClient,
        *,
        target_call_id: str,
        on_answer,
        on_fail,
    ) -> None:
        """Wait off the request path for `target_call_id` to answer.

        Reuses the orchestrator's leg-wait (fed by call.answered / call.hangup).
        Calls `on_answer()` on pickup, or `on_fail(reason)` on decline / no-answer
        / timeout. Every persistence step inside the callbacks opens its own
        short session — this coroutine holds none.
        """

        from app.services.call_center.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        waiter = orchestrator.register_leg_wait(target_call_id)

        async def _runner() -> None:
            try:
                decision = await asyncio.wait_for(
                    waiter, timeout=_TARGET_ANSWER_TIMEOUT_SEC
                )
            except asyncio.TimeoutError:
                orchestrator.cancel_leg_wait(target_call_id)
                await on_fail("no_answer")
                return
            except Exception:  # noqa: BLE001
                logger.exception("target wait failed leg=%s", target_call_id)
                await on_fail("wait_error")
                return
            if decision.get("answered"):
                await on_answer()
            else:
                await on_fail(decision.get("reason") or "declined")

        asyncio.create_task(_runner(), name=f"call-target-wait:{target_call_id}")

    @staticmethod
    async def _restore_after_target_failure(
        telephony: BaseTelephonyClient,
        call: CurrentCall,
        target_call_id: str,
        reason: str,
    ) -> None:
        """Blind-transfer target never answered — keep the customer with the agent."""

        await CallControlService._stop_tone(telephony, call.customer_call_id)
        # The target leg is usually already gone on decline/timeout; best-effort.
        # Empty for an internal (browser-ring) transfer that failed before any
        # leg existed — the internal path already released the target.
        if target_call_id:
            try:
                await telephony.call_hangup(target_call_id, reason="transfer_aborted")
            except Exception:  # noqa: BLE001
                pass
        logger.info(
            "transfer aborted customer=%s target=%s reason=%s (customer kept)",
            call.customer_call_id, target_call_id, reason,
        )

    @staticmethod
    async def _restore_after_consult_failure(
        telephony: BaseTelephonyClient,
        tenant_id: int,
        employee_id: int,
        call: CurrentCall,
        target_call_id: str,
        reason: str,
    ) -> None:
        """Consult target never answered — resume the held customer.

        `target_call_id` may be empty for an internal (browser-ring) consult that
        failed before any leg existed — the internal path already released the
        target's reservation, so there is nothing to hang up.
        """

        if target_call_id:
            try:
                await telephony.call_hangup(target_call_id, reason="consult_aborted")
            except Exception:  # noqa: BLE001
                pass
        await CallControlService._stop_tone(telephony, call.customer_call_id)
        try:
            if call.webrtc_call_id:
                await telephony.call_bridge(call.customer_call_id, call.webrtc_call_id)
        except Exception:  # noqa: BLE001
            logger.warning("consult abort re-bridge failed", exc_info=True)
        legs = await _legs(tenant_id, employee_id)
        if legs.consult_call_id == target_call_id:
            legs.consult_call_id = None
            await _save_legs(tenant_id, employee_id, legs)
        logger.info(
            "consult aborted customer=%s consult_leg=%s reason=%s (customer resumed)",
            call.customer_call_id, target_call_id, reason,
        )

    @staticmethod
    async def _release_internal_target(
        tenant_id: int, target_employee_id: int, *, reason: str
    ) -> None:
        """Free a colleague we occupied via the internal browser-ring path.

        The consult / transfer machinery reserved and marked that colleague
        ``in_call`` on their own call-center resource to ring their browser. When
        the consult ends (or handover completes with their leg gone) we must
        unconditionally free it — the occupation is keyed on the internal leg, so
        a normal ``release`` would refuse an ``in_call`` state and the colleague
        would stay stuck busy. Runs on Redis only; holds no DB session.
        """

        from app.services.call_center.orchestrator import _get_redis_client

        r = _get_redis_client()
        if r is None:
            logger.warning(
                "internal target release skipped (no redis) target=%s/%s",
                tenant_id, target_employee_id,
            )
            return
        try:
            await CcAgentResourceService.force_release(
                r, tenant_id, target_employee_id, reason=reason,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "internal target release failed target=%s/%s reason=%s",
                tenant_id, target_employee_id, reason, exc_info=True,
            )

    @staticmethod
    async def _rekey_internal_target_to_customer(
        tenant_id: int, target_employee_id: int, customer_call_id: str
    ) -> None:
        """Re-key a handed-over colleague's resource onto the customer call.

        After a blind transfer to an internal browser-ring colleague, that
        colleague becomes the customer's owning agent. Their resource was keyed
        on the internal consult leg; re-point it at the customer call so the
        customer's own ``call.hangup`` finalizes them cleanly instead of raising
        ``Call resource belongs to another call``. Redis only; no DB session.
        """

        from app.services.call_center.orchestrator import _get_redis_client

        r = _get_redis_client()
        if r is None:
            logger.warning(
                "internal target re-key skipped (no redis) target=%s/%s",
                tenant_id, target_employee_id,
            )
            return
        try:
            await CcAgentResourceService.mark_in_call(
                r,
                tenant_id,
                target_employee_id,
                call_id=customer_call_id,
                direction="inbound",
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "internal target re-key failed target=%s/%s call=%s",
                tenant_id, target_employee_id, customer_call_id, exc_info=True,
            )

    @staticmethod
    async def _reassign_call_record_to_agent(
        tenant_id: int, customer_call_id: str, new_agent_id: int
    ) -> None:
        """Re-point the customer's call record to the transfer target.

        After a successful transfer the colleague owns the call, but the CDR
        still names the initiator. Left unchanged, the initiator's hangup would
        resolve to (and kill) the customer call, and the customer's own hangup
        would notify the initiator instead of the colleague (who then stays
        stuck "通话中"). Best-effort; a short session is opened and closed here.
        """

        from sqlalchemy import select
        from app.models.call_record import CallRecord

        try:
            async with AsyncSessionLocal() as db:
                row = (
                    await db.execute(
                        select(CallRecord).where(
                            CallRecord.tenant_id == tenant_id,
                            CallRecord.call_id == customer_call_id,
                        )
                    )
                ).scalar_one_or_none()
                if row is None:
                    row = (
                        await db.execute(
                            select(CallRecord).where(
                                CallRecord.tenant_id == tenant_id,
                                CallRecord.root_call_id == customer_call_id,
                            )
                        )
                    ).scalar_one_or_none()
                if row is not None and row.agent_id != new_agent_id:
                    row.agent_id = new_agent_id
                    await db.commit()
                    logger.info(
                        "transfer: call %s reassigned to agent %s",
                        customer_call_id, new_agent_id,
                    )
        except Exception:  # noqa: BLE001
            logger.warning(
                "transfer: call-record reassign failed call=%s agent=%s",
                customer_call_id, new_agent_id, exc_info=True,
            )

    @staticmethod
    def _validate_target(
        target_type: str, target_id: int | None, number: str | None
    ) -> None:
        """Validate that the target payload matches its type."""

        if target_type in ("employee", "queue"):
            if target_id is None:
                raise ValidationError(f"{target_type} target requires target_id")
        elif target_type == "external":
            if not number:
                raise ValidationError("external target requires number")
        else:
            raise ValidationError(f"Unsupported target_type: {target_type}")
