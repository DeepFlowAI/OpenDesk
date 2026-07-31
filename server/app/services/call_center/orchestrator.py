"""
Call center orchestrator — single long-running entity that:
  1. Connects to the telephony kernel (FlowKit by default).
  2. Subscribes to all relevant kernel events.
  3. On `call.incoming`: matches a routing rule → loads the voice flow →
     creates a `VoiceFlowWorkflow` keyed by `call_id` → starts it.
  4. Routes subsequent events (call.dtmf / call.play_end / call.bridged /
     call.hangup) to the matching workflow by `call_id`.
  5. On `call.hangup`: marks the CDR completed, flips agent state back to
     after_call_work, and discards the workflow.
  6. On `call.recording.completed`: persists FlowKit `oss_url` onto the CDR.
  7. On downstream `webrtc.ice`: resolves the agent that owns that leg and
     pushes the candidate to their browser through Socket.IO.

Startup is gated by `settings.CALL_CENTER_ENABLED` — local dev without a
FlowKit kernel keeps it disabled so the app boots cleanly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

from app.configs.settings import settings
from app.constants.call_center import ACTIVE_CALL_RECORD_STATES, CcSocketEvent
from app.services.call_center.agent_notify import emit_to_agent
from app.core.trace import (
    build_traceparent,
    get_trace_id,
    parse_traceparent,
    set_call_id,
    set_trace_id,
)
from app.db.session import AsyncSessionLocal
from app.libs.realtime import get_realtime_transport
from app.libs.telephony import (
    BaseTelephonyClient,
    CallEvent,
    get_telephony_client,
)
from app.libs.telephony.providers.flowkit.telecom_client import (
    FlowKitTelecomClient,
)
from app.services.agent_webrtc_session_service import AgentWebRTCSessionService
from app.services.call_center.catalog_sync import CatalogSyncService
from app.services.call_center.nodes import build_voicespeed_direct_graph
from app.services.call_center.routing import match_routing_rule
from app.services.call_center.workflow import VoiceFlowWorkflow
from app.services.call_record_service import CallRecordService
from app.services.call_transcript_service import CallTranscriptService
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService
from app.services.call_center.orchestration.agent_push import AgentPushMixin
from app.services.call_center.orchestration.events import EventHandlersMixin
from app.services.call_center.orchestration.extension_dial import ExtensionDialMixin
from app.services.call_center.orchestration.offers import OffersMixin
from app.services.call_center.orchestration.outbound import OutboundMixin


logger = logging.getLogger(__name__)

# One-time pause after answering an inbound call, before the first prompt, so
# the SIP media path is established before we start playing. The carrier drops
# the opening RTP right after answer; without this the caller misses the start
# of the welcome (the kernel-side recording is unaffected). Only the first
# prompt needs it — once media is flowing, later prompts play normally.
_RTP_WARMUP_SECONDS = 0.8


@dataclass(frozen=True)
class SipOutboundDialParams:
    """Everything the extension-answer handler needs to originate the customer
    leg once the SIP-phone agent's physical extension goes off-hook. Captured in
    the `/dial` request (which returns immediately) and consumed off the request
    path by the orchestrator's background dial task — so no ORM objects or DB
    session are carried across the ring wait."""

    tenant_pk: int
    employee_id: int
    reservation_id: str
    dialed: str          # destination with per-DID prefix applied
    destination: str     # what the agent typed (pre-prefix), stored on the CDR
    caller_id: str       # outbound DID
    trunk_id: str
    device_type: str
    device_identifier: str | None


class CallCenterOrchestrator(
    OffersMixin,
    EventHandlersMixin,
    ExtensionDialMixin,
    OutboundMixin,
    AgentPushMixin,
):

    def __init__(self, telephony: BaseTelephonyClient | None = None) -> None:
        import asyncio as _asyncio

        self.telephony: BaseTelephonyClient = telephony or get_telephony_client()
        self._workflows: dict[str, VoiceFlowWorkflow] = {}
        self._started = False
        # True while this process is draining for blue/green shutdown: skip
        # claiming new inbound calls so a sibling node can own them.
        self._draining = False
        self._cached_tenant_id: int | None = None
        # Catalog sync (FlowKit) — created lazily in start() when
        # FLOWKIT_TELECOM_API_URL is configured. None on single-trunk
        # deployments that stick with FlowKit's env-loaded `system` Provider.
        self._catalog_sync: CatalogSyncService | None = None
        # Pending agent-side decisions for `assign_queue`. When the executor
        # selects an agent, it `register_offer(offer_id)` to get a Future,
        # pushes a `cc.call_offer` Socket.IO notification, then awaits the
        # Future. The browser POSTs `/current-call/{accept,reject}` with the
        # offer_id, which calls `resolve_offer(offer_id, decision)` and the
        # workflow continues.
        self._pending_offers: dict[str, _asyncio.Future[dict]] = {}
        # Track agent-initiated outbound calls so subsequent call.ringing /
        # call.answered / call.hangup events can be pushed back to the right
        # agent's browser. Cleared in _on_hangup (delayed — see _CLEANUP_DELAY).
        # Shape: call_id → (tenant_id, employee_id, outbound_did)
        self._outbound_originators: dict[str, tuple[int, int, str]] = {}
        # Same call_id as above, set to a non-None tuple of (reason, sip_status)
        # when the SIP leg has already ended. Lets /dial-webrtc/offer return
        # 410 Gone with a useful reason instead of 404 when the carrier
        # rejects faster than the agent's browser can complete WebRTC setup
        # (sub-100ms 480/486 responses are common on misconfigured trunks).
        self._outbound_ended: dict[str, tuple[str | None, int | None]] = {}
        # Pairs an outbound SIP call_id with the agent's WebRTC leg call_id.
        # Set when the agent's browser POSTs /dial-webrtc/offer right after
        # dial. Consumed by _on_outbound_answered to fire call.bridge so
        # audio flows the instant the carrier picks up. Cleared in _on_hangup.
        self._outbound_webrtc_pairs: dict[str, str] = {}
        # Legs whose answered/hangup a caller is awaiting (SIP-phone agent leg
        # in the two-stage originate). call_id → Future resolved with
        # {"answered": bool} on call.answered / call.hangup. Only used for the
        # extension-leg wait; WebRTC-only outbound never populates this.
        self._leg_waiters: dict[str, "_asyncio.Future[dict]"] = {}
        # call_id → Future resolved on the next call.play_end for that call. Lets
        # the assign path let an in-flight prompt (e.g. "正在为您转接") finish
        # cleanly before bridging, instead of cutting it mid-word.
        self._play_waiters: dict[str, "_asyncio.Future[dict]"] = {}
        # customer call_id → the agent extension leg being rung for it, while a
        # SIP-phone assign is still ringing the handset. Lets a caller hangup
        # cancel the ring immediately instead of waiting out the assign timeout.
        self._pending_sip_originate: dict[str, str] = {}
        # customer call_id → background asyncio.Task waiting/ringing for a
        # queue blind-transfer. Cancelled on customer hangup; self-cleared when
        # the task finishes.
        self._pending_queue_transfer: dict[str, _asyncio.Task] = {}
        # Per-call trace context: call_id → (trace_id, trace_call_id). Lets any
        # async handler that did NOT go through _route_event (hangup, recording,
        # outbound lifecycle, agent-side finalize) re-bind the call's trace_id
        # before emitting logs, so every log for one call shares one trace_id.
        # Outlives the workflow (recording.completed can arrive after hangup);
        # cleaned up on a delay after hangup.
        self._call_traces: dict[str, tuple[str, str]] = {}

        import os
        import socket
        # Unique per orchestrator process. FlowKit broadcasts call.incoming to
        # every connected node; this id is written to the per-call owner lock so
        # exactly one node handles each call in a multi-node deployment.
        self._node_id = f"{socket.gethostname()}:{os.getpid()}"
        # Background subscriber that resolves agent offer decisions forwarded
        # from other nodes (an agent's accept can hit any node, but the offer's
        # Future lives on the call's owner node).
        self._offer_sub_task: _asyncio.Task | None = None

    def active_workflow(self, call_id: str) -> VoiceFlowWorkflow | None:
        """The live workflow driving a call, or None once the call has ended."""

        return self._workflows.get(call_id)

    # A call is owned by exactly one orchestrator node. TTL only needs to
    # outlive event delivery for the call; the owner clears it on hangup.
    _CALL_OWNER_TTL_SEC = 6 * 60 * 60

    # Pub/sub channel carrying cross-node agent offer decisions.
    _OFFER_RESOLVE_CHANNEL = "cc:offer:resolve"

    @staticmethod
    def _call_owner_key(call_id: str) -> str:
        return f"cc:call:owner:{call_id}"

    # Time we keep an ended call_id around so late /dial-webrtc/offer
    # requests can be answered with 410 Gone instead of a confusing 404.
    _OUTBOUND_CLEANUP_DELAY_SEC = 60

    # Redis keys for outbound state shared across nodes (local dicts are L1).
    _OUTBOUND_ORIGINATOR_PREFIX = "cc:outbound:originator"
    _OUTBOUND_ENDED_PREFIX = "cc:outbound:ended"
    _OUTBOUND_WEBRTC_PREFIX = "cc:outbound:webrtc"
    _OUTBOUND_STATE_TTL_SEC = 6 * 60 * 60

    # Time we keep a call's trace context after hangup so late events
    # (notably call.recording.completed) can still bind the call's trace_id.
    _TRACE_CLEANUP_DELAY_SEC = 300

    @staticmethod
    def _outbound_originator_key(call_id: str) -> str:
        return f"{CallCenterOrchestrator._OUTBOUND_ORIGINATOR_PREFIX}:{call_id}"

    @staticmethod
    def _outbound_ended_key(call_id: str) -> str:
        return f"{CallCenterOrchestrator._OUTBOUND_ENDED_PREFIX}:{call_id}"

    @staticmethod
    def _outbound_webrtc_key(outbound_call_id: str) -> str:
        return f"{CallCenterOrchestrator._OUTBOUND_WEBRTC_PREFIX}:{outbound_call_id}"


# ────────────────── Singleton accessor ──────────────────


_instance: CallCenterOrchestrator | None = None


def get_orchestrator() -> CallCenterOrchestrator:
    global _instance
    if _instance is None:
        _instance = CallCenterOrchestrator()
    return _instance


def reset_orchestrator() -> None:
    """Test helper."""

    global _instance
    _instance = None


def _get_redis_client():
    try:
        from app.db.redis import redis_client

        return redis_client.client
    except RuntimeError:
        return None
