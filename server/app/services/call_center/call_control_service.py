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
import uuid
from dataclasses import dataclass, field

from sqlalchemy import desc, select

from app.constants.call_center import (
    INCALL_LEGS_KEY_PREFIX,
    ConsultState,
    incall_legs_key,
)
from app.services.call_center import consult_session
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
from app.repositories.tenant_phone_number_repository import (
    TenantPhoneNumberRepository,
)
from app.services.agent_call_device_service import AgentCallDeviceService
from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
from app.services.call_prompt_tone_service import CallPromptToneService
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.call_center.call_control.basic_controls import BasicControlsMixin
from app.services.call_center.call_control.conference import ConferenceMixin
from app.services.call_center.call_control.consult import ConsultMixin
from app.services.call_center.call_control.helpers import HelpersMixin
from app.services.call_center.call_control.queue_transfer import QueueTransferMixin
from app.services.call_center.call_control.resolution import ResolutionMixin
from app.services.call_center.call_control.targets import TargetResolutionMixin
from app.services.call_center.call_control.transfer import TransferMixin

logger = logging.getLogger(__name__)

# How long (seconds) we wait off the request path for a freshly-originated
# transfer / consult / conference target leg to answer before giving up and
# restoring the original call.
_TARGET_ANSWER_TIMEOUT_SEC = 45.0

# Looping waiting-tone cadence for hold / consult / three-party scenes.
_TONE_LOOP_INTERVAL_MS = 15000

# After a consult-target WebRTC leg dies (page refresh / media_eof), wait this
# long for the target to media-reconnect before ending the consult for the host.
_CONSULT_TARGET_RECONNECT_GRACE_SEC = 15.0

# Hangup reasons that mean the consulted colleague intentionally left (not a
# refresh). Those end the consult immediately instead of waiting for reconnect.
_CONSULT_TARGET_INTENTIONAL_HANGUP = frozenset({
    "agent_hangup",
    "user_hangup",
    "rejected",
    "consult_ended",
    "declined",
})

# Hangup of the old consult leg during a successful target media-reconnect.
_CONSULT_TARGET_REPLACED_REASON = "media_replaced"

# Grace tasks keyed by "{tenant}:{host}:{dead_consult_leg}".
_consult_target_grace_tasks: dict[str, asyncio.Task] = {}

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

    # Live media leg currently bridged to the customer (WebRTC or SIP-extension).
    # Prefer this over AgentWebRTCSession — softphone presence sessions can be
    # stale while the real call uses a fresh per-call leg.
    agent_media_call_id: str | None = None
    customer_held: bool = False
    consult_call_id: str | None = None
    conference_participant_call_id: str | None = None
    conference_operation_id: str | None = None
    room_id: str | None = None
    room_legs: list[str] = field(default_factory=list)
    # Set only when the consult / transfer target is a colleague reached via the
    # internal browser-ring path. We reserved & occupied that colleague's own
    # call-center resource to ring their browser, so we must release (consult) or
    # re-key it to the customer call (transfer) when the operation ends —
    # otherwise the colleague stays stuck busy and can't be dialed again.
    consult_target_employee_id: int | None = None
    consult_offer_id: str | None = None
    # Explicit consult lifecycle: none | ringing | active. Prefer
    # consult_session.transition over writing this field directly.
    consult_state: str | None = None
    # Set when a conference participant is a colleague reached via the internal
    # browser-ring path (not a SIP extension / external number). Their own
    # call-center resource is occupied for the conference, so it must be freed
    # when the conference ends.
    conference_target_employee_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "agent_media_call_id": self.agent_media_call_id,
            "customer_held": self.customer_held,
            "consult_call_id": self.consult_call_id,
            "conference_participant_call_id": self.conference_participant_call_id,
            "conference_operation_id": self.conference_operation_id,
            "room_id": self.room_id,
            "room_legs": list(self.room_legs),
            "consult_target_employee_id": self.consult_target_employee_id,
            "consult_offer_id": self.consult_offer_id,
            "consult_state": self.consult_state,
            "conference_target_employee_id": self.conference_target_employee_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InCallLegs":
        return cls(
            agent_media_call_id=d.get("agent_media_call_id"),
            customer_held=bool(d.get("customer_held", False)),
            consult_call_id=d.get("consult_call_id"),
            conference_participant_call_id=d.get("conference_participant_call_id"),
            conference_operation_id=d.get("conference_operation_id"),
            room_id=d.get("room_id"),
            room_legs=list(d.get("room_legs") or []),
            consult_target_employee_id=d.get("consult_target_employee_id"),
            consult_offer_id=d.get("consult_offer_id"),
            consult_state=d.get("consult_state"),
            conference_target_employee_id=d.get("conference_target_employee_id"),
        )


# In-process cache keyed by (tenant_id, employee_id). Backed by Redis so the
# state is durable across process restarts and shared across blue/green
# containers; this cache is just a fast local mirror in front of Redis.
_in_call_state: dict[tuple[int, int], InCallLegs] = {}

# TTL for durable in-call leg state. Longer than any real call so the key never
# expires mid-call; refreshed on every save. Key shape: constants.incall_legs_key.
_INCALL_TTL_SEC = 6 * 60 * 60


def _incall_redis_key(tenant_id: int, employee_id: int) -> str:
    return incall_legs_key(tenant_id, employee_id)


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


class CallControlService(
    ResolutionMixin,
    TargetResolutionMixin,
    BasicControlsMixin,
    TransferMixin,
    QueueTransferMixin,
    ConsultMixin,
    ConferenceMixin,
    HelpersMixin,
):
    """In-call control for the current agent's own call.

    All methods take an explicit telephony client so the router can inject the
    shared singleton and tests can inject a mock. DB access uses short sessions
    opened only around the lookup, then closed before any kernel RPC.
    """
