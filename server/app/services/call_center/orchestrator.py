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

import logging
from dataclasses import dataclass

from app.configs.settings import settings
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


class CallCenterOrchestrator:

    def __init__(self, telephony: BaseTelephonyClient | None = None) -> None:
        import asyncio as _asyncio

        self.telephony: BaseTelephonyClient = telephony or get_telephony_client()
        self._workflows: dict[str, VoiceFlowWorkflow] = {}
        self._started = False
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

    # Time we keep a call's trace context after hangup so late events
    # (notably call.recording.completed) can still bind the call's trace_id.
    _TRACE_CLEANUP_DELAY_SEC = 300

    # ────────────────── Pending-offer registry ──────────────────

    def register_offer(self, offer_id: str):
        """Returns an asyncio.Future the workflow can await for a decision."""

        import asyncio
        fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending_offers[offer_id] = fut
        return fut

    def resolve_offer(self, offer_id: str, decision: dict) -> bool:
        """Called by the accept/reject HTTP endpoints. Idempotent."""

        fut = self._pending_offers.pop(offer_id, None)
        if fut is None or fut.done():
            return False
        fut.set_result(decision)
        return True

    def cancel_offer(self, offer_id: str) -> None:
        """Best-effort cleanup if a workflow gives up (e.g. timeout)."""

        self._pending_offers.pop(offer_id, None)

    # ────────────────── Per-call ownership (multi-node) ──────────────────

    async def _claim_call(self, call_id: str) -> bool:
        """Claim ownership of an inbound call for this node.

        Returns True if we own it (proceed), False if another node already does
        (skip). Single-node deployments (or Redis unavailable) always own it.
        """
        r = _get_redis_client()
        if r is None:
            return True
        try:
            acquired = await r.set(
                self._call_owner_key(call_id),
                self._node_id,
                ex=self._CALL_OWNER_TTL_SEC,
                nx=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "call owner claim failed call_id=%s; handling locally", call_id
            )
            return True
        return bool(acquired)

    async def _owns_call(self, call_id: str) -> bool:
        """Whether this node owns the call. Non-owner nodes skip its events."""
        r = _get_redis_client()
        if r is None:
            return True
        try:
            owner = await r.get(self._call_owner_key(call_id))
        except Exception:  # noqa: BLE001
            return True
        if isinstance(owner, bytes):
            owner = owner.decode()
        # Unknown owner (lock expired / never claimed): fall back to whether we
        # have local state for the call, so a lone node still works.
        if owner is None:
            return call_id in self._workflows or call_id in self._call_traces
        return owner == self._node_id

    async def _release_call(self, call_id: str) -> None:
        r = _get_redis_client()
        if r is None:
            return
        try:
            owner = await r.get(self._call_owner_key(call_id))
            if isinstance(owner, bytes):
                owner = owner.decode()
            if owner == self._node_id:
                await r.delete(self._call_owner_key(call_id))
        except Exception:  # noqa: BLE001
            pass

    # ─────────── Cross-node agent offer resolution (multi-node) ───────────

    async def deliver_offer_decision(self, offer_id: str, decision: dict) -> bool:
        """Resolve an agent's accept/reject decision.

        The offer's Future lives on the call's owner node, but the agent's HTTP
        request can land on any node. Resolve locally when we hold the offer;
        otherwise forward the decision over Redis and wait for the owner to ack.
        """
        # Fast path: the offer was registered on this node.
        if self.resolve_offer(offer_id, decision):
            return True
        r = _get_redis_client()
        if r is None:
            return False  # single-node and not found → genuinely gone
        import asyncio
        import json
        import uuid

        reply_key = f"cc:offer:reply:{uuid.uuid4().hex}"
        try:
            await r.publish(
                self._OFFER_RESOLVE_CHANNEL,
                json.dumps(
                    {"offer_id": offer_id, "decision": decision, "reply_key": reply_key}
                ),
            )
            got = await r.blpop(reply_key, timeout=5)
        except Exception:  # noqa: BLE001
            logger.exception("cross-node offer resolve failed offer_id=%s", offer_id)
            return False
        if not got:
            return False
        value = got[1]
        if isinstance(value, bytes):
            value = value.decode()
        return value == "1"

    async def _offer_resolve_loop(self) -> None:
        """Resolve offer decisions forwarded from other nodes. Only the node
        that holds the offer's Future resolves it and acks the caller."""
        import asyncio
        import json

        r = _get_redis_client()
        if r is None:
            return
        while True:
            try:
                pubsub = r.pubsub()
                await pubsub.subscribe(self._OFFER_RESOLVE_CHANNEL)
                async for msg in pubsub.listen():
                    if msg.get("type") != "message":
                        continue
                    try:
                        data = msg["data"]
                        if isinstance(data, bytes):
                            data = data.decode()
                        payload = json.loads(data)
                    except Exception:  # noqa: BLE001
                        continue
                    offer_id = payload.get("offer_id")
                    if not offer_id or offer_id not in self._pending_offers:
                        continue  # not our offer — another node holds it
                    resolved = self.resolve_offer(offer_id, payload.get("decision") or {})
                    reply_key = payload.get("reply_key")
                    if reply_key:
                        try:
                            await r.rpush(reply_key, "1" if resolved else "0")
                            await r.expire(reply_key, 30)
                        except Exception:  # noqa: BLE001
                            pass
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("offer-resolve subscriber error; retrying")
                await asyncio.sleep(1.0)

    async def start(self) -> None:
        if self._started:
            return
        await self.telephony.connect()
        self.telephony.on_event("call.incoming", self._on_incoming)
        self.telephony.on_event("call.dtmf", self._route_event)
        self.telephony.on_event("call.play_end", self._route_event)
        self.telephony.on_event("call.speech_end", self._route_event)
        self.telephony.on_event("call.bridged", self._route_event)
        # Mirror live ASR/TTS text to the bridged agent's browser for the
        # real-time transcript display. These run alongside the routing above
        # and never persist anything.
        self.telephony.on_event("call.speech_partial", self._on_transcript_event)
        self.telephony.on_event("call.speech_end", self._on_transcript_event)
        self.telephony.on_event("call.user_text", self._on_transcript_event)
        self.telephony.on_event("call.assistant_text", self._on_transcript_event)
        # Dual-leg transcript of a bridged (human↔human) call — carries an
        # explicit speaker and is anchored on the user-leg call_id.
        self.telephony.on_event("call.bridge_transcript", self._on_transcript_event)
        # External realtime-agent (VoiceSpeed) bridge lifecycle.
        self.telephony.on_event("call.external_agent.connected", self._route_event)
        self.telephony.on_event("call.external_agent.handoff", self._route_event)
        self.telephony.on_event("call.external_agent.failed", self._route_event)
        self.telephony.on_event("call.external_agent.ended", self._route_event)
        self.telephony.on_event("call.hangup", self._on_hangup)
        self.telephony.on_event("call.recording.completed", self._on_recording_completed)
        # Outbound originate emits these three; we forward them to the
        # initiating agent's browser via Socket.IO.
        self.telephony.on_event("call.ringing", self._on_outbound_ringing)
        self.telephony.on_event("call.answered", self._on_outbound_answered)
        self.telephony.on_event("call.early_media", self._on_outbound_ringing)
        self.telephony.on_event("webrtc.ice", self._on_webrtc_ice)
        # SIP extension registration lifecycle (kernel registrar). Kept behind
        # the same event bus; no-ops on kernels that don't emit them (extensions
        # disabled), so WebRTC-only deployments are unaffected.
        self.telephony.on_event("extension.registered", self._on_extension_registered)
        self.telephony.on_event("extension.unregistered", self._on_extension_unregistered)
        self.telephony.on_reconnected(self._on_reconnect)
        await self._start_catalog_sync()
        import asyncio as _aio_offer
        self._offer_sub_task = _aio_offer.create_task(
            self._offer_resolve_loop(), name="cc-offer-resolve"
        )
        self._started = True
        logger.info("Call center orchestrator started")

    async def stop(self) -> None:
        if not self._started:
            return
        if self._offer_sub_task is not None:
            self._offer_sub_task.cancel()
            self._offer_sub_task = None
        if self._catalog_sync is not None:
            await self._catalog_sync.stop()
            self._catalog_sync = None
        await self.telephony.disconnect()
        self._workflows.clear()
        self._started = False
        logger.info("Call center orchestrator stopped")

    async def _start_catalog_sync(self) -> None:
        """Wire FlowKit Catalog sync if configured (multi-trunk deployments).

        Skipped when FLOWKIT_TELECOM_API_URL is empty — single-trunk
        deployments rely on FlowKit's env-loaded `system` Provider and
        don't need OpenDesk to push anything.
        """
        if not settings.FLOWKIT_TELECOM_API_URL or not settings.FLOWKIT_TELECOM_API_KEY:
            logger.info(
                "FlowKit Catalog sync disabled (FLOWKIT_TELECOM_API_URL/_KEY unset)"
            )
            return
        telecom = FlowKitTelecomClient(
            base_url=settings.FLOWKIT_TELECOM_API_URL,
            api_key=settings.FLOWKIT_TELECOM_API_KEY,
            provider_id=settings.FLOWKIT_TELECOM_PROVIDER_ID,
        )
        sync = CatalogSyncService(
            telecom_client=telecom,
            lease_ttl_sec=settings.FLOWKIT_TELECOM_LEASE_SEC,
            stale_acceptable_sec=settings.FLOWKIT_TELECOM_STALE_ACCEPTABLE_SEC,
        )
        # Subscribe to FlowKit lifecycle events for visibility.
        self.telephony.on_event("telecom.trunk.registered", sync.on_trunk_registered)
        self.telephony.on_event("telecom.trunk.deregistered", sync.on_trunk_deregistered)
        self.telephony.on_event("telecom.lease.stale", sync.on_lease_stale)
        try:
            await sync.start()
        except Exception:  # noqa: BLE001
            # Don't crash orchestrator if FlowKit register API is down at
            # startup. Inbound calls still flow via FlowKit's env Provider
            # and we'll retry on the next admin trunk edit.
            logger.exception("Catalog sync start failed; continuing without sync")
            await sync.stop()
            return
        self._catalog_sync = sync

    async def reload_catalog(self) -> None:
        """Admin entry-point: re-push snapshot after SipTrunk CRUD."""

        if self._catalog_sync is None:
            return
        try:
            await self._catalog_sync.reload()
        except Exception:  # noqa: BLE001
            logger.exception("Catalog reload failed")

    def catalog_health(self) -> dict | None:
        """Health snapshot for /health. None when sync is not configured."""

        if self._catalog_sync is None:
            return None
        return self._catalog_sync.health_snapshot()

    # ────────────────── Event handlers ──────────────────

    async def _resolve_tenant_id(self) -> int | None:
        """
        Resolve the integer Tenant.id that owns inbound SIP calls. Lookup order:
          1. CALL_CENTER_DEFAULT_TENANT_SLUG (explicit, recommended)
          2. DEFAULT_TENANT_ID (seed slug, works on a fresh OSS install)
          3. The first tenant in the DB by id (single-tenant fallback so OSS
             users with a renamed default tenant don't get stuck)

        Cached after first success. Multi-tenant per-DID routing would replace
        this with a lookup keyed on `to_number`.
        """

        if self._cached_tenant_id is not None:
            return self._cached_tenant_id

        from sqlalchemy import select

        from app.configs.settings import settings
        from app.models.tenant import Tenant

        candidates = [
            settings.CALL_CENTER_DEFAULT_TENANT_SLUG,
            settings.DEFAULT_TENANT_ID,
        ]
        async with AsyncSessionLocal() as db:
            for slug in candidates:
                if not slug:
                    continue
                row = (
                    await db.execute(select(Tenant).where(Tenant.tenant_id == slug))
                ).scalar_one_or_none()
                if row is not None:
                    self._cached_tenant_id = int(row.id)
                    logger.info(
                        "Inbound calls bound to tenant id=%s slug=%s",
                        row.id, slug,
                    )
                    return self._cached_tenant_id
            # Fallback: first tenant in DB. Safe for single-tenant OSS.
            first = (
                await db.execute(select(Tenant).order_by(Tenant.id.asc()).limit(1))
            ).scalar_one_or_none()
            if first is not None:
                self._cached_tenant_id = int(first.id)
                logger.warning(
                    "Inbound calls: configured slugs not found; falling back "
                    "to first tenant id=%s slug=%s. Set "
                    "CALL_CENTER_DEFAULT_TENANT_SLUG to silence this warning.",
                    first.id, first.tenant_id,
                )
                return self._cached_tenant_id
        return None

    async def _resolve_tenant_id_for_did(self, to_number: str) -> int | None:
        """Resolve the tenant that owns a dialed number (DID).

        Looks the inbound `to` number up in the platform phone-number catalog
        and returns its assigned tenant's numeric id, or None when the number is
        unknown or unassigned — in which case the caller falls back to the
        single default tenant (so single-tenant deployments keep working).
        """
        if not to_number:
            return None

        from sqlalchemy import select

        from app.models.tenant import Tenant
        from app.repositories.phone_number_repository import PhoneNumberRepository
        from app.services.call_user_association_service import normalize_phone_digits

        async with AsyncSessionLocal() as db:
            phone = await PhoneNumberRepository.get_by_phone_number(db, to_number)
            if phone is None:
                normalized = normalize_phone_digits(to_number)
                if normalized and normalized != to_number:
                    phone = await PhoneNumberRepository.get_by_phone_number(db, normalized)
            if phone is None or not phone.tenant_id:
                return None
            tenant = (
                await db.execute(select(Tenant).where(Tenant.tenant_id == phone.tenant_id))
            ).scalar_one_or_none()
            if tenant is None:
                return None
            logger.info(
                "Inbound DID %s routed to tenant id=%s slug=%s",
                to_number, tenant.id, phone.tenant_id,
            )
            return int(tenant.id)

    async def _on_incoming(self, event: CallEvent) -> None:
        data = event.data
        call_id = data.get("call_id")
        if not call_id:
            return

        # FlowKit pushes `call.incoming` for BOTH inbound SIP calls AND any
        # agent-side `webrtc.offer`. We only orchestrate the customer-side
        # orchestrate the customer-side SIP legs here; agent WebRTC legs are
        # registered via the `/agents/me/webrtc/offer` HTTP endpoint and must
        # be left alone — otherwise we'd hang up the agent's own media leg
        # the moment they go online (no routing rule matches a WebRTC offer
        # since there's no inbound caller number).
        transport = data.get("transport", "sip")
        if transport != "sip":
            logger.info(
                "Skipping call.incoming for non-SIP transport=%s call_id=%s",
                transport, call_id,
            )
            return

        # Multi-node safety: FlowKit broadcasts call.incoming to every connected
        # orchestrator. Exactly one node owns each call — the rest skip — so we
        # don't answer/route the same call more than once.
        if not await self._claim_call(call_id):
            logger.info(
                "Skipping call.incoming call_id=%s — owned by another node", call_id
            )
            return

        # Continue the W3C trace started by the kernel on the real phone entry
        # so all OpenDesk logs/spans for this call share one trace_id; also bind
        # the business call_id for log queries. When the kernel didn't send a
        # (valid) traceparent, set_trace_id mints a fresh 32-hex trace_id — we
        # then synthesize a traceparent from it so the SAME trace_id propagates
        # downstream (kernel RPCs + VoiceSpeed mint), never an empty trace.
        traceparent = data.get("traceparent")
        trace_id = set_trace_id(parse_traceparent(traceparent))
        if parse_traceparent(traceparent) is None:
            traceparent = build_traceparent(trace_id)
        trace_call_id = data.get("root_call_id") or call_id
        set_call_id(trace_call_id)
        self._register_call_trace(call_id, trace_id, trace_call_id)
        if trace_call_id != call_id:
            self._register_call_trace(trace_call_id, trace_id, trace_call_id)

        from_number = data.get("from", "").replace("sip:", "").split("@")[0]
        to_number = data.get("to", "").replace("sip:", "").split("@")[0]

        # Per-DID tenant routing: bind the call to the tenant that owns the
        # dialed number. Fall back to the single default tenant when the DID
        # isn't in the catalog (keeps single-tenant deployments working).
        tenant_id = await self._resolve_tenant_id_for_did(to_number)
        if tenant_id is None:
            tenant_id = await self._resolve_tenant_id()
        if tenant_id is None:
            logger.warning("Inbound call %s: no tenant resolved; hanging up", call_id)
            await self.telephony.call_hangup(call_id, reason="no_tenant")
            return

        async with AsyncSessionLocal() as db:
            matched = await match_routing_rule(
                db, tenant_id, from_number=from_number, to_number=to_number,
            )
            if matched is None:
                logger.warning("No routing rule matched call_id=%s; hanging up", call_id)
                await self.telephony.call_hangup(call_id, reason="no_route")
                return
            rule, flow = matched

            if rule.target_type == "voicespeed_agent":
                graph = build_voicespeed_direct_graph(
                    agent_id=rule.voicespeed_agent_id or "",
                    agent_name=rule.voicespeed_agent_name,
                    transfer_target=rule.transfer_target,
                )
                voice_flow_id = None
                voice_flow_version_id = None
            else:
                if flow is None:
                    await self.telephony.call_hangup(call_id, reason="no_route")
                    return
                version = flow.current_version
                if version is None:
                    await self.telephony.call_hangup(call_id, reason="no_flow_version")
                    return
                graph = dict(version.graph_json)
                voice_flow_id = flow.id
                voice_flow_version_id = version.id

            await CallRecordService.create_for_incoming(
                db,
                tenant_id,
                call_id=call_id,
                conversation_id=data.get("conversation_id"),
                root_call_id=data.get("root_call_id"),
                from_number=from_number or None,
                to_number=to_number or None,
                voice_flow_id=voice_flow_id,
                voice_flow_version_id=voice_flow_version_id,
            )

        workflow = VoiceFlowWorkflow(
            call_id=call_id,
            tenant_id=tenant_id,
            graph=graph,
            telephony=self.telephony,
            orchestrator=self,
            initial_variables={
                "sys.caller_number": from_number or "",
                "sys.called_number": to_number or "",
                "sys._traceparent": traceparent,
                "sys._trace_id": trace_id,
                "sys._trace_call_id": trace_call_id,
            },
        )
        self._workflows[call_id] = workflow

        await self.telephony.call_answer(call_id)
        # Warm up the media path once before the first prompt (see above).
        if _RTP_WARMUP_SECONDS > 0:
            import asyncio

            await asyncio.sleep(_RTP_WARMUP_SECONDS)
        try:
            await workflow.start()
        except Exception:  # noqa: BLE001
            logger.exception("Workflow start failed call_id=%s", call_id)
            await self.telephony.call_hangup(call_id, reason="workflow_error")

    def _register_call_trace(
        self, call_id: str | None, trace_id: str, trace_call_id: str
    ) -> None:
        if call_id:
            self._call_traces[call_id] = (trace_id, trace_call_id)

    def bind_call_trace(self, call_id: str | None) -> None:
        """Re-bind a call's trace_id + call_id into the contextvars.

        Kernel events arrive on fresh asyncio tasks that do NOT inherit the
        contextvars set in `_on_incoming`, so every handler that does not go
        through `_route_event` must call this before logging — otherwise its
        logs carry an empty trace_id and can't be correlated with the rest of
        the call. Looks the call up in the live workflow first, then the
        per-call trace map (which outlives the workflow).
        """

        trace_id: str | None = None
        trace_call_id: str | None = None
        wf = self._workflows.get(call_id) if call_id else None
        wf_ctx = getattr(wf, "ctx", None)
        if wf_ctx is not None:
            trace_id = wf_ctx.variables.get("sys._trace_id")
            trace_call_id = wf_ctx.variables.get("sys._trace_call_id")
        if not trace_id and call_id in self._call_traces:
            trace_id, trace_call_id = self._call_traces[call_id]
        if trace_id:
            set_trace_id(trace_id)
        set_call_id(trace_call_id or call_id)

    async def _route_event(self, event: CallEvent) -> None:
        call_id = event.data.get("call_id")
        # An in-flight prompt finished — wake any assign path waiting to bridge
        # only after the prompt completes (kept separate from the workflow's own
        # WaitForEvent routing below).
        if call_id and event.method == "call.play_end":
            self._resolve_play_wait(call_id, event.data)
        wf = self._workflows.get(call_id) if call_id else None
        if wf is None:
            return
        # Re-establish this call's trace context — kernel events arrive on fresh
        # asyncio tasks that don't inherit the contextvars set in _on_incoming.
        self.bind_call_trace(call_id)
        await wf.handle_event(event.method, event.data)

    # Kernel event → (transcript role, is-final). Partials stream into the
    # in-progress bubble; finals close it.
    _TRANSCRIPT_EVENT_ROLES: dict[str, tuple[str, bool]] = {
        "call.speech_partial": ("user", False),
        "call.speech_end": ("user", True),
        "call.user_text": ("user", True),
        "call.assistant_text": ("agent", True),
    }

    async def _on_transcript_event(self, event: CallEvent) -> None:
        """Relay live ASR/TTS text to the bridged agent's browser.

        Pure passthrough for the real-time transcript UI — nothing is stored.
        Stays a silent no-op until the call is bridged to an agent, so text
        only flows once an agent has actually joined the call.
        """

        call_id = event.data.get("call_id")
        if not call_id:
            return
        self.bind_call_trace(call_id)
        wf = self._workflows.get(call_id)
        if wf is None:
            return
        agent = wf.bridged_agent_info()
        if agent is None:
            return
        text = (event.data.get("text") or "").strip()
        if not text:
            return
        if event.method == "call.bridge_transcript":
            role = "agent" if event.data.get("speaker") == "agent" else "user"
            final = bool(event.data.get("final"))
        else:
            role, final = self._TRANSCRIPT_EVENT_ROLES.get(event.method, ("user", True))
        try:
            rt = get_realtime_transport()
            room = f"agent:{agent['tenant_id']}:{agent['employee_id']}"
            await rt.emit(
                "cc.transcript",
                {
                    "call_id": call_id,
                    "role": role,
                    "text": text,
                    "final": final,
                    "seq": event.data.get("seq"),
                },
                room=room,
                namespace="/chat",
            )
        except Exception:  # noqa: BLE001
            logger.exception("cc.transcript push failed call_id=%s", call_id)

        # Persist finalized lines so the transcript survives a refresh and is
        # viewable from call history. Partials are transient and not stored.
        if final:
            try:
                async with AsyncSessionLocal() as db:
                    await CallTranscriptService.append(
                        db,
                        tenant_id=agent["tenant_id"],
                        call_id=call_id,
                        role=role,
                        text=text,
                        seq=event.data.get("seq"),
                    )
            except Exception:  # noqa: BLE001
                logger.exception("transcript persist failed call_id=%s", call_id)

    async def _on_webrtc_ice(self, event: CallEvent) -> None:
        """
        FlowKit-side ICE candidate destined for an agent's browser leg.
        Resolve the owning employee via agent_webrtc_sessions, then push
        through Socket.IO to that agent's room.
        """

        call_id = event.data.get("call_id")
        candidate = event.data.get("candidate")
        if not call_id or candidate is None:
            return
        self.bind_call_trace(call_id)
        try:
            async with AsyncSessionLocal() as db:
                info = await AgentWebRTCSessionService.get_employee_for_call_id(db, call_id)
        except Exception:  # noqa: BLE001
            logger.exception("webrtc.ice lookup failed call_id=%s", call_id)
            return
        if not info:
            return
        try:
            rt = get_realtime_transport()
            room = f"agent:{info['tenant_id']}:{info['employee_id']}"
            await rt.emit(
                "cc.webrtc.ice",
                {"call_id": call_id, "candidate": candidate},
                room=room,
                namespace="/chat",
            )
        except Exception:  # noqa: BLE001
            logger.exception("webrtc.ice emit failed")

    async def _on_extension_registered(self, event: CallEvent) -> None:
        await self._apply_extension_registration(event.data, registered=True)

    async def _on_extension_unregistered(self, event: CallEvent) -> None:
        await self._apply_extension_registration(event.data, registered=False)

    async def _apply_extension_registration(
        self, data: dict, *, registered: bool
    ) -> None:
        """Persist a kernel extension.registered/unregistered event.

        The event's ``extension`` field is the AOR user-part, which is the
        extension's registration-domain-unique ``sip_user_id``. We open a fresh
        short session (this handler runs on its own task and holds no session
        across I/O), update the row, then push a best-effort refresh to the
        bound agent's browser so their device-availability view updates live.
        """

        from app.services.sip_extension_service import SipExtensionService

        sip_user_id = (data.get("extension") or "").strip()
        if not sip_user_id:
            return
        updated = None
        try:
            async with AsyncSessionLocal() as db:
                updated = await SipExtensionService.apply_registration_event(
                    db, sip_user_id=sip_user_id, registered=registered,
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "extension registration writeback failed sip_user_id=%s", sip_user_id,
            )
            return
        if updated is None:
            logger.info(
                "extension %s event ignored (no matching extension) registered=%s",
                sip_user_id, registered,
            )
            return
        logger.info(
            "extension %s registration → %s",
            sip_user_id, "registered" if registered else "unregistered",
        )
        if updated.bound_employee_id is None:
            return
        try:
            rt = get_realtime_transport()
            room = f"agent:{updated.tenant_id}:{updated.bound_employee_id}"
            await rt.emit(
                "cc.device_registration_changed",
                {
                    "extension_number": updated.extension_number,
                    "registration_status": updated.registration_status,
                },
                room=room,
                namespace="/chat",
            )
        except Exception:  # noqa: BLE001
            logger.exception("cc.device_registration_changed push failed")

    async def _on_hangup(self, event: CallEvent) -> None:
        call_id = event.data.get("call_id")
        if not call_id:
            return
        # Free the per-call ownership lock (owner-only; non-owners no-op). The
        # rest of this handler operates on in-memory state that only the owner
        # populated, so non-owner nodes fall through harmlessly.
        await self._release_call(call_id)
        # Drop any prompt-completion waiter for this call so it can't linger.
        self.cancel_play_wait(call_id)
        # Caller hung up while their SIP handset was still ringing (assign
        # originate not yet answered): tear the handset leg down now so it stops
        # ringing, and resolve the assign wait, instead of ringing out the full
        # assign timeout.
        pending_ext = self.pop_pending_sip_originate(call_id)
        if pending_ext:
            try:
                await self.telephony.call_hangup(pending_ext, reason="caller_hangup")
            except Exception:  # noqa: BLE001
                logger.warning(
                    "caller hangup: cancel ringing handset leg=%s failed",
                    pending_ext, exc_info=True,
                )
            self._resolve_leg_wait(
                pending_ext, {"answered": False, "reason": "caller_hangup"}
            )
        # SIP-phone two-stage: agent extension leg ended (declined / no answer /
        # unregistered) before answering. Wake the dialer so it aborts and does
        # NOT dial the customer.
        self._resolve_leg_wait(
            call_id, {"answered": False, "reason": event.data.get("reason")}
        )
        self.bind_call_trace(call_id)
        # Keep the trace mapping alive briefly so a trailing
        # call.recording.completed can still bind this call's trace_id, then
        # drop it to bound memory.
        import asyncio as _aio_trace
        _aio_trace.create_task(self._delayed_trace_cleanup(call_id))

        # If this hung-up leg was a conference participant, collapse the host's
        # 3-way back to the two-party call (else the host stays stuck at "3人").
        # No-op for any non-participant leg (customer / agent / outbound).
        try:
            from app.services.call_center.call_control_service import CallControlService
            await CallControlService.on_conference_participant_departed(call_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "conference participant-departed handling failed call=%s",
                call_id, exc_info=True,
            )

        # Outbound originator path: if this call_id was an agent-initiated
        # outbound, notify the agent's browser. We MARK the entry as ended
        # (so a late /dial-webrtc/offer returns 410 Gone with the SIP reason
        # rather than a misleading 404) and schedule deletion in 60s — this
        # race is common when the carrier rejects in <50ms, faster than the
        # browser can complete getUserMedia + createOffer.
        outbound_info = self._peek_outbound_originator(call_id)
        self._pop_outbound_webrtc(call_id)
        if outbound_info is not None:
            self._outbound_ended[call_id] = (
                event.data.get("reason"),
                event.data.get("sip_status"),
            )
            import asyncio as _aio
            _aio.create_task(self._delayed_outbound_cleanup(call_id))
            tenant_id_out, employee_id_out, _did = outbound_info
            await self.notify_agent_outbound_event(
                tenant_id=tenant_id_out,
                employee_id=employee_id_out,
                method="cc.outbound_hangup",
                payload={
                    "call_id": call_id,
                    "reason": event.data.get("reason"),
                    "sip_status": event.data.get("sip_status"),
                },
            )

        wf = self._workflows.pop(call_id, None)
        bridged_agent: dict | None = None
        pending_offer: dict | None = None
        if wf is not None:
            bridged_agent = wf.bridged_agent_info()
            pending_offer = wf.pending_offer_info()
            await wf.on_call_hangup(event.data)

        # Caller hung up while an assign_queue offer was still ringing an agent
        # (offer not yet accepted). Withdraw it so the agent's browser stops
        # ringing and the reserved agent is freed immediately instead of waiting
        # out the full offer timeout.
        if wf is not None and pending_offer and not bridged_agent:
            await self._withdraw_pending_offer(
                tenant_id=wf.tenant_id,
                call_id=call_id,
                pending_offer=pending_offer,
                reason=event.data.get("reason") or "caller_hangup",
            )

        try:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select
                from app.models.call_record import CallRecord
                row = (
                    await db.execute(select(CallRecord).where(CallRecord.call_id == call_id))
                ).scalar_one_or_none()
                was_answered = bool(row and row.answered_at)
                if row is not None:
                    await CallRecordService.mark_completed(
                        db, row.tenant_id, call_id, hangup_reason=event.data.get("reason"),
                    )

                redis = _get_redis_client()
                if outbound_info is not None:
                    tenant_id_out, employee_id_out, _did = outbound_info
                    if was_answered:
                        if redis is not None:
                            await CcAgentResourceService.mark_after_call_work(
                                redis,
                                tenant_id_out,
                                employee_id_out,
                                call_id=call_id,
                                reason=event.data.get("reason") or "call_hangup",
                            )
                        await CcAgentStatusService.sync_pg_status(
                            db, tenant_id_out, employee_id_out, "after_call_work", None
                        )
                    elif redis is not None:
                        released = await CcAgentResourceService.release(
                            redis,
                            tenant_id_out,
                            employee_id_out,
                            reason=event.data.get("reason") or "outbound_hangup",
                            expected_call_id=call_id,
                        )
                        await CcAgentStatusService.sync_pg_status(
                            db,
                            tenant_id_out,
                            employee_id_out,
                            released["visible_status"],
                            None,
                        )

                # Status auto-transition: bridge agent goes from busy →
                # after_call_work, and their webrtc session goes back to idle.
                if bridged_agent:
                    if redis is not None:
                        await CcAgentResourceService.mark_after_call_work(
                            redis,
                            bridged_agent["tenant_id"],
                            bridged_agent["employee_id"],
                            call_id=call_id,
                            reason=event.data.get("reason") or "call_hangup",
                        )
                    await CcAgentStatusService.set_status(
                        db,
                        bridged_agent["tenant_id"],
                        bridged_agent["employee_id"],
                        "after_call_work",
                        None,
                    )
                    await AgentWebRTCSessionService.set_busy(
                        db,
                        bridged_agent["tenant_id"],
                        bridged_agent["employee_id"],
                        busy=False,
                    )
                    await self.notify_agent_call_ended(
                        tenant_id=bridged_agent["tenant_id"],
                        employee_id=bridged_agent["employee_id"],
                        call_id=call_id,
                        reason=event.data.get("reason"),
                    )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to finalize CDR / status for call_id=%s", call_id)

    async def _withdraw_pending_offer(
        self,
        *,
        tenant_id: int,
        call_id: str,
        pending_offer: dict,
        reason: str,
    ) -> None:
        """Cancel an offer that was still ringing when the caller hung up.

        Resolves the workflow's pending decision (so the assign_queue executor
        stops awaiting), releases the reserved agent's Redis resource, and pings
        the agent's browser via Socket.IO so the incoming-call UI stops ringing.
        Holds no DB session — Redis + Socket.IO only.
        """

        employee_id = int(pending_offer["employee_id"])
        offer_id = str(pending_offer["offer_id"])
        # Wake the assign_queue executor so it exits its node promptly instead
        # of blocking until the offer timeout fires.
        self.resolve_offer(offer_id, {"accept": False, "reason": reason})
        redis = _get_redis_client()
        if redis is not None:
            try:
                await CcAgentResourceService.release(
                    redis,
                    tenant_id,
                    employee_id,
                    reason=reason,
                    expected_offer_id=offer_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "withdraw offer: release failed agent=%s/%s", tenant_id, employee_id,
                )
        await self.notify_agent_call_ended(
            tenant_id=tenant_id,
            employee_id=employee_id,
            call_id=call_id,
            reason=reason,
        )

    async def finalize_agent_call(
        self,
        *,
        tenant_id: int,
        employee_id: int,
        call_id: str,
        reason: str | None,
        mark_cdr_completed: bool = False,
    ) -> None:
        """Reset an agent back out of the in-call state and notify their browser.

        Used by terminal paths that are NOT driven by a customer `call.hangup`
        event (bridge aborted because the caller was already gone; agent-
        initiated hangup of an already-ended call). Opens its own short DB
        session for the writes and holds none across the Socket.IO emit.
        """

        self.bind_call_trace(call_id)
        redis = _get_redis_client()
        try:
            async with AsyncSessionLocal() as db:
                if mark_cdr_completed:
                    from sqlalchemy import select
                    from app.models.call_record import CallRecord
                    row = (
                        await db.execute(
                            select(CallRecord).where(CallRecord.call_id == call_id)
                        )
                    ).scalar_one_or_none()
                    if row is not None:
                        await CallRecordService.mark_completed(
                            db, row.tenant_id, call_id, hangup_reason=reason,
                        )
                if redis is not None:
                    await CcAgentResourceService.mark_after_call_work(
                        redis,
                        tenant_id,
                        employee_id,
                        call_id=call_id,
                        reason=reason or "call_hangup",
                    )
                await CcAgentStatusService.sync_pg_status(
                    db, tenant_id, employee_id, "after_call_work", None,
                )
                await AgentWebRTCSessionService.set_busy(
                    db, tenant_id, employee_id, busy=False,
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "finalize_agent_call failed agent=%s/%s call_id=%s",
                tenant_id, employee_id, call_id,
            )
        await self.notify_agent_call_ended(
            tenant_id=tenant_id,
            employee_id=employee_id,
            call_id=call_id,
            reason=reason,
        )

    async def hangup_agent_current_call(
        self,
        *,
        tenant_id: int,
        employee_id: int,
    ) -> dict:
        """Hang up whatever call the current agent is on, robustly.

        Tears down the agent's OWN WebRTC leg (so the browser call always ends)
        in addition to the customer SIP leg. If the customer leg is already gone
        (FlowKit -32002 "call not found"), that's treated as already-ended and we
        reset the agent's status directly — no customer `call.hangup` event will
        arrive to drive the usual cleanup, so without this the agent stays stuck
        on 忙碌. Short DB session for the lookup is closed before the RPCs.
        """

        from sqlalchemy import desc, select
        from app.libs.telephony.base import TelephonyRPCError
        from app.models.call_record import CallRecord

        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(CallRecord)
                    .where(
                        CallRecord.tenant_id == tenant_id,
                        CallRecord.agent_id == employee_id,
                        CallRecord.state.in_(("ringing", "queued", "in_progress")),
                    )
                    .order_by(desc(CallRecord.started_at))
                    .limit(1)
                )
            ).scalar_one_or_none()
            session = await AgentWebRTCSessionService.get_active(db, tenant_id, employee_id)
            webrtc_call_id = session["webrtc_call_id"] if session else None
            target_call_id = (row.root_call_id or row.call_id) if row is not None else None
            record_id = row.id if row is not None else None

        # An internal-ring participant (a consult / conference target reached in
        # their browser) holds a WebRTC leg but has no CDR of their own, so the
        # lookup above finds nothing. Let them hang up that leg and reset instead
        # of returning "no_active_call" and stranding them "通话中".
        if row is None:
            if webrtc_call_id is None:
                return {"ok": False, "error": "no_active_call"}
            self.bind_call_trace(webrtc_call_id)
            logger.info(
                "Agent %s hangup of internal leg=%s (no CDR)",
                employee_id, webrtc_call_id,
            )
            try:
                await self.telephony.call_hangup(webrtc_call_id, reason="agent_hangup")
            except TelephonyRPCError as exc:
                if exc.code != -32002:
                    logger.warning(
                        "agent hangup: internal leg %s rejected code=%s",
                        webrtc_call_id, exc.code,
                    )
            except Exception:  # noqa: BLE001
                logger.warning("agent hangup: internal leg hangup raised", exc_info=True)
            redis = _get_redis_client()
            if redis is not None:
                try:
                    await CcAgentResourceService.force_release(
                        redis, tenant_id, employee_id, reason="agent_hangup",
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "internal participant release failed agent=%s/%s",
                        tenant_id, employee_id, exc_info=True,
                    )
            await self.finalize_agent_call(
                tenant_id=tenant_id,
                employee_id=employee_id,
                call_id=webrtc_call_id,
                reason="agent_hangup",
                mark_cdr_completed=False,
            )
            return {"ok": True, "note": "left_internal_call", "call_id": webrtc_call_id}

        self.bind_call_trace(target_call_id)
        logger.info(
            "Agent %s requested hangup; target SIP call_id=%s (record id=%s)",
            employee_id, target_call_id, record_id,
        )

        # Always tear down the agent's own WebRTC leg so the browser call ends,
        # even when the customer SIP leg is already gone.
        if webrtc_call_id:
            try:
                await self.telephony.call_hangup(webrtc_call_id, reason="agent_hangup")
            except TelephonyRPCError as exc:
                if exc.code != -32002:
                    logger.warning(
                        "agent hangup: agent leg %s hangup rejected code=%s",
                        webrtc_call_id, exc.code,
                    )
            except Exception:  # noqa: BLE001
                logger.warning("agent hangup: agent leg hangup raised", exc_info=True)

        customer_gone = False
        try:
            await self.telephony.call_hangup(target_call_id, reason="agent_hangup")
        except TelephonyRPCError as exc:
            if exc.code == -32002:
                customer_gone = True
            else:
                logger.warning("agent hangup: call.hangup rejected code=%s", exc.code)
                return {"ok": False, "error": "rpc_error", "code": exc.code}

        if customer_gone:
            # No customer call.hangup event will arrive — reset the agent here.
            await self.finalize_agent_call(
                tenant_id=tenant_id,
                employee_id=employee_id,
                call_id=target_call_id,
                reason="agent_hangup",
                mark_cdr_completed=True,
            )
            return {"ok": True, "note": "already_ended", "call_id": target_call_id}
        return {"ok": True, "call_id": target_call_id}

    async def _on_recording_completed(self, event: CallEvent) -> None:
        """Persist telephony kernel recording URL onto the CDR."""

        data = event.data
        call_id = data.get("call_id")
        oss_url = data.get("oss_url")
        if not call_id or not oss_url:
            logger.warning(
                "call.recording.completed missing call_id/oss_url: %s", data,
            )
            return
        # Broadcast to every node; only the call's owner persists it (others
        # would double-write the same CDR).
        if not await self._owns_call(call_id):
            return
        self.bind_call_trace(call_id)
        try:
            async with AsyncSessionLocal() as db:
                saved = await CallRecordService.save_recording(
                    db,
                    call_id=call_id,
                    url=oss_url,
                    partial=bool(data.get("partial", False)),
                    phase=data.get("phase"),
                    header_patched=data.get("header_patched"),
                )
            if saved:
                logger.info(
                    "Recording saved call_id=%s phase=%s partial=%s",
                    call_id, data.get("phase"), data.get("partial", False),
                )
            else:
                logger.warning(
                    "call.recording.completed: no CDR for call_id=%s", call_id,
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to save recording for call_id=%s", call_id,
            )

    async def _on_reconnect(self) -> None:
        """After WS reconnect, query active calls so we don't lose state."""

        try:
            calls = await self.telephony.call_list()
            logger.info("Reconnect: %d active calls in kernel", len(calls))
            # Any agent left in_call whose call is no longer in the kernel lost
            # its end event while the WS was down — free it so the agent isn't
            # stranded on "busy" forever.
            active_ids = {c.get("call_id") for c in calls if c.get("call_id")}
            released = await CcAgentResourceService.reconcile_in_call(
                _get_redis_client(), active_ids
            )
            if released:
                logger.info(
                    "Reconnect reconcile: freed %d stranded agent resource(s)",
                    len(released),
                )
                # Close the stale call records too, otherwise the next status
                # poll would resurrect the in_call resource from them.
                from app.services.call_record_service import CallRecordService

                async with AsyncSessionLocal() as db:
                    for tenant_id, _employee_id, call_id in released:
                        try:
                            await CallRecordService.mark_completed(
                                db, tenant_id, call_id,
                                hangup_reason="reconnect_reconcile",
                            )
                        except Exception:  # noqa: BLE001
                            logger.exception(
                                "reconcile: mark_completed failed call_id=%s", call_id
                            )
                    await db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("call_list after reconnect failed")

        # Reconcile SIP-extension registrations against the kernel's live
        # registrar. A kernel restart clears its in-memory bindings without
        # emitting per-AOR unregister events, so an agent's heartbeat dot would
        # stay green while their handset is actually offline. Re-query the live
        # AOR set and flip any stale-registered extension to unregistered.
        try:
            from app.libs.telephony.base import TelephonyMethodNotFoundError
            from app.services.sip_extension_service import SipExtensionService

            live = await self.telephony.extension_list()
            live_ids = {
                (e.get("extension") or "").strip()
                for e in live
                if e.get("extension")
            }
            async with AsyncSessionLocal() as db:
                flipped = await SipExtensionService.reconcile_registrations(db, live_ids)
                await db.commit()
            if flipped:
                logger.info(
                    "Reconnect reconcile: %d extension(s) → unregistered", len(flipped),
                )
                rt = get_realtime_transport()
                for ext in flipped:
                    if ext.bound_employee_id is None:
                        continue
                    try:
                        await rt.emit(
                            "cc.device_registration_changed",
                            {
                                "extension_number": ext.extension_number,
                                "registration_status": ext.registration_status,
                            },
                            room=f"agent:{ext.tenant_id}:{ext.bound_employee_id}",
                            namespace="/chat",
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("device_registration_changed push failed")
        except TelephonyMethodNotFoundError:
            pass  # kernel build without extension registrar
        except Exception:  # noqa: BLE001
            logger.exception("extension reconcile after reconnect failed")

    # ────────────────── Outbound (agent-initiated) tracking ──────────────────

    def register_outbound_call(
        self,
        *,
        call_id: str,
        tenant_id: int,
        employee_id: int,
        outbound_did: str,
    ) -> None:
        """Remember which agent dialed which call_id so subsequent
        call.ringing / call.answered / call.hangup events can be routed
        back to that agent's browser. Cleared by _on_hangup."""

        self._outbound_originators[call_id] = (tenant_id, employee_id, outbound_did)
        # Capture the dialing request's trace so outbound kernel events
        # (which arrive on fresh tasks) can re-bind the same trace_id.
        trace_id = get_trace_id()
        if trace_id and trace_id != "-":
            self._register_call_trace(call_id, trace_id, call_id)

    def outbound_ended_reason(self, call_id: str) -> tuple[str | None, int | None] | None:
        """If the outbound SIP leg has already ended, return its (reason,
        sip_status). Else None. Used by /dial-webrtc/offer to surface a
        clean 410 Gone when the race fires."""
        return self._outbound_ended.get(call_id)

    async def _delayed_outbound_cleanup(self, call_id: str) -> None:
        import asyncio as _aio
        await _aio.sleep(self._OUTBOUND_CLEANUP_DELAY_SEC)
        self._outbound_originators.pop(call_id, None)
        self._outbound_ended.pop(call_id, None)

    async def _delayed_trace_cleanup(self, call_id: str) -> None:
        import asyncio as _aio
        entry = self._call_traces.get(call_id)
        await _aio.sleep(self._TRACE_CLEANUP_DELAY_SEC)
        self._call_traces.pop(call_id, None)
        # Also drop the root/media key that maps to the same trace, if any.
        if entry is not None:
            _trace_id, trace_call_id = entry
            if trace_call_id and trace_call_id != call_id:
                self._call_traces.pop(trace_call_id, None)

    async def cancel_outbound(self, call_id: str) -> None:
        """Best-effort hangup of an in-flight outbound SIP leg.

        Used by the agent's UI cancel button. The call may already be ended
        (carrier rejected before the user reacted, lease expired, etc.);
        we swallow downstream errors because the UX is "either way, the
        call is now over" — the cleanup (originator pop + WebRTC tear) is
        driven by the call.hangup event which will eventually arrive even
        if our explicit hangup races with the carrier rejection."""

        try:
            await self.telephony.call_hangup(call_id, reason="agent_cancel")
        except Exception:  # noqa: BLE001
            logger.warning("cancel_outbound: call_hangup raised", exc_info=True)

    def pair_outbound_webrtc(self, *, outbound_call_id: str, webrtc_call_id: str) -> None:
        """Bind the outbound SIP leg to the agent's media leg. The pairing is
        consumed in _on_outbound_answered to fire call.bridge.

        `webrtc_call_id` is the agent's leg to bridge the customer to — a
        browser WebRTC leg for Web-phone agents, or the physical SIP-extension
        leg for SIP-phone agents. The bridge logic is identical either way."""

        self._outbound_webrtc_pairs[outbound_call_id] = webrtc_call_id

    def register_leg_wait(self, call_id: str) -> "_asyncio.Future[dict]":
        """Await a leg's first answered/hangup. Returns a Future resolved with
        {"answered": True} on call.answered or {"answered": False, "reason":...}
        on call.hangup. Used by the SIP-phone two-stage originate to know when
        the agent's physical phone goes off-hook before dialing the customer."""

        import asyncio
        fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._leg_waiters[call_id] = fut
        return fut

    def register_play_wait(self, call_id: str) -> "_asyncio.Future[dict]":
        """Await the next ``call.play_end`` on this call. Used so the assign path
        can let an in-flight prompt finish before bridging. Register it right
        after starting the prompt; if the prompt has already ended, the returned
        future simply resolves at that point instead of blocking."""

        import asyncio
        fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._play_waiters[call_id] = fut
        return fut

    def _resolve_play_wait(self, call_id: str, data: dict) -> None:
        fut = self._play_waiters.pop(call_id, None)
        if fut is not None and not fut.done():
            fut.set_result(data)

    def cancel_play_wait(self, call_id: str) -> None:
        self._play_waiters.pop(call_id, None)

    def set_pending_sip_originate(self, call_id: str, agent_leg_call_id: str) -> None:
        """Record that a SIP-phone handset is being rung for this caller, so a
        caller hangup can cancel the ring."""
        self._pending_sip_originate[call_id] = agent_leg_call_id

    def pop_pending_sip_originate(self, call_id: str) -> str | None:
        return self._pending_sip_originate.pop(call_id, None)

    def start_sip_outbound_dial(
        self,
        *,
        extension_leg_call_id: str,
        params: "SipOutboundDialParams",
        timeout_sec: float,
    ) -> None:
        """Own the SIP-phone extension-answer wait entirely off the request path.

        The `/dial` request originates the agent's physical extension leg
        synchronously and returns immediately (status ``ringing_extension``); it
        never awaits the phone going off-hook. This method spawns a background
        task that waits on the extension leg's first answered/hangup event (via
        `register_leg_wait`) and:

          * on **answer** → originates the customer leg on a fresh short DB
            session, pairs it to the extension leg, and registers it as an
            outbound originator so the shared `_on_outbound_answered` path
            bridges the two the instant the customer picks up;
          * on **hangup / decline / timeout** → tears down the extension leg,
            releases the agent's reserved resource, and notifies the agent's
            browser — the customer is never dialed.

        No DB session is held across the wait; every persistence step opens its
        own short session. This is the event-driven replacement for the old
        in-request `asyncio.wait_for(...)` that held a pooled connection for up
        to the full ring timeout.
        """

        import asyncio

        waiter = self.register_leg_wait(extension_leg_call_id)
        asyncio.create_task(
            self._run_sip_outbound_dial(
                extension_leg_call_id=extension_leg_call_id,
                waiter=waiter,
                params=params,
                timeout_sec=timeout_sec,
            ),
            name=f"sip-outbound-dial:{extension_leg_call_id}",
        )

    async def _run_sip_outbound_dial(
        self,
        *,
        extension_leg_call_id: str,
        waiter: "_asyncio.Future[dict]",
        params: "SipOutboundDialParams",
        timeout_sec: float,
    ) -> None:
        import asyncio

        self.bind_call_trace(extension_leg_call_id)
        try:
            decision = await asyncio.wait_for(waiter, timeout=timeout_sec)
        except asyncio.TimeoutError:
            self.cancel_leg_wait(extension_leg_call_id)
            await self._abort_sip_outbound_dial(
                extension_leg_call_id, params, reason="no_answer",
            )
            return
        except Exception:  # noqa: BLE001
            logger.exception(
                "sip outbound dial wait failed ext_leg=%s", extension_leg_call_id,
            )
            await self._abort_sip_outbound_dial(
                extension_leg_call_id, params, reason="wait_error",
            )
            return

        if not decision.get("answered"):
            # Declined / hung up before answering — the extension leg is already
            # gone, so only release the reserved agent and notify the browser.
            await self._abort_sip_outbound_dial(
                extension_leg_call_id,
                params,
                reason=decision.get("reason") or "extension_declined",
                teardown_leg=False,
            )
            return

        await self._originate_sip_outbound_customer(extension_leg_call_id, params)

    async def _originate_sip_outbound_customer(
        self, extension_leg_call_id: str, params: "SipOutboundDialParams",
    ) -> None:
        """Extension answered → dial the customer and pair the legs.

        Runs off the request path on a fresh short session. On originate failure
        the extension leg is torn down, the agent resource released, and the
        browser told the outbound failed.
        """

        from app.libs.telephony.base import TelephonyRPCError

        try:
            result = await self.telephony.call_originate(
                uri=params.dialed,
                caller_id=params.caller_id,
                trunk_id=params.trunk_id,
            )
        except Exception as exc:  # noqa: BLE001
            reason = "originate_rejected"
            if isinstance(exc, TelephonyRPCError):
                logger.warning(
                    "sip outbound customer originate rejected code=%s trunk_id=%s",
                    exc.code, params.trunk_id,
                )
            else:
                logger.exception(
                    "sip outbound customer originate failed ext_leg=%s",
                    extension_leg_call_id,
                )
            await self._abort_sip_outbound_dial(
                extension_leg_call_id, params, reason=reason,
            )
            return

        call_id = result.get("call_id")
        if not call_id:
            logger.warning(
                "sip outbound customer originate returned no call_id ext_leg=%s",
                extension_leg_call_id,
            )
            await self._abort_sip_outbound_dial(
                extension_leg_call_id, params, reason="no_call_id",
            )
            return

        redis = _get_redis_client()
        if redis is not None:
            try:
                await CcAgentResourceService.bind_outbound_call(
                    redis,
                    params.tenant_pk,
                    params.employee_id,
                    reservation_id=params.reservation_id,
                    call_id=call_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "sip outbound bind_outbound_call failed call_id=%s", call_id,
                )

        # Register the customer leg so its ringing/answered/hangup events route
        # back to the agent, and pair it to the already-answered extension leg so
        # _on_outbound_answered bridges them when the customer picks up.
        self.register_outbound_call(
            call_id=call_id,
            tenant_id=params.tenant_pk,
            employee_id=params.employee_id,
            outbound_did=params.caller_id,
        )
        self.pair_outbound_webrtc(
            outbound_call_id=call_id, webrtc_call_id=extension_leg_call_id,
        )

        try:
            async with AsyncSessionLocal() as db:
                await CcAgentStatusService.sync_pg_status(
                    db, params.tenant_pk, params.employee_id, "busy", None,
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "sip outbound status busy sync failed call_id=%s", call_id,
            )

        try:
            async with AsyncSessionLocal() as db:
                await CallRecordService.create_for_outbound(
                    db, params.tenant_pk,
                    call_id=call_id,
                    conversation_id=result.get("conversation_id"),
                    root_call_id=result.get("root_call_id") or call_id,
                    from_number=params.caller_id,
                    to_number=params.destination,
                    agent_id=params.employee_id,
                    device_type=params.device_type,
                    device_identifier=params.device_identifier,
                )
                await db.commit()
        except Exception:  # noqa: BLE001
            logger.exception(
                "sip outbound CDR create_for_outbound failed call_id=%s", call_id,
            )

        await self.notify_agent_outbound_event(
            tenant_id=params.tenant_pk, employee_id=params.employee_id,
            method="cc.outbound_customer_dialing",
            payload={"call_id": call_id, "extension_call_id": extension_leg_call_id},
        )
        logger.info(
            "sip outbound: extension %s answered → customer leg %s (dialed=%s)",
            extension_leg_call_id, call_id, params.dialed,
        )

    async def _abort_sip_outbound_dial(
        self,
        extension_leg_call_id: str,
        params: "SipOutboundDialParams",
        *,
        reason: str,
        teardown_leg: bool = True,
    ) -> None:
        """Failure path for a SIP-phone outbound dial before the customer leg
        exists: tear down the extension leg (unless already gone), release the
        agent's reserved resource, and notify the browser. Holds no DB session
        across the RPC/Redis/Socket.IO calls."""

        if teardown_leg:
            try:
                await self.telephony.call_hangup(
                    extension_leg_call_id, reason="outbound_aborted",
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "sip outbound abort: extension leg teardown failed ext_leg=%s",
                    extension_leg_call_id, exc_info=True,
                )

        redis = _get_redis_client()
        if redis is not None:
            try:
                released = await CcAgentResourceService.release(
                    redis,
                    params.tenant_pk,
                    params.employee_id,
                    reason=reason,
                    expected_call_id=params.reservation_id,
                )
                async with AsyncSessionLocal() as db:
                    await CcAgentStatusService.sync_pg_status(
                        db,
                        params.tenant_pk,
                        params.employee_id,
                        released["visible_status"],
                        None,
                    )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "sip outbound abort: resource release failed agent=%s/%s",
                    params.tenant_pk, params.employee_id,
                )

        await self.notify_agent_outbound_event(
            tenant_id=params.tenant_pk, employee_id=params.employee_id,
            method="cc.outbound_hangup",
            payload={
                "call_id": extension_leg_call_id,
                "reason": reason,
                "stage": "extension",
            },
        )
        logger.info(
            "sip outbound aborted ext_leg=%s reason=%s (customer not dialed)",
            extension_leg_call_id, reason,
        )

    def cancel_leg_wait(self, call_id: str) -> None:
        self._leg_waiters.pop(call_id, None)

    def _resolve_leg_wait(self, call_id: str, result: dict) -> None:
        fut = self._leg_waiters.pop(call_id, None)
        if fut is not None and not fut.done():
            fut.set_result(result)

    def _pop_outbound_webrtc(self, outbound_call_id: str) -> str | None:
        return self._outbound_webrtc_pairs.pop(outbound_call_id, None)

    def _pop_outbound_originator(self, call_id: str) -> tuple[int, int, str] | None:
        return self._outbound_originators.pop(call_id, None)

    def _peek_outbound_originator(self, call_id: str) -> tuple[int, int, str] | None:
        return self._outbound_originators.get(call_id)

    async def _on_outbound_ringing(self, event: CallEvent) -> None:
        """call.ringing (180) or call.early_media (183) for an outbound call."""

        call_id = event.data.get("call_id") or ""
        info = self._peek_outbound_originator(call_id)
        if info is None:
            return  # not an agent-initiated outbound, ignore
        self.bind_call_trace(call_id)
        tenant_id, employee_id, _did = info
        await self.notify_agent_outbound_event(
            tenant_id=tenant_id, employee_id=employee_id,
            method="cc.outbound_ringing",
            payload={"call_id": call_id, "event": event.method},
        )

    async def _on_outbound_answered(self, event: CallEvent) -> None:
        call_id = event.data.get("call_id") or ""
        # SIP-phone two-stage: the agent's extension leg answered. Wake the
        # dialer waiting on it so it proceeds to originate the customer.
        self._resolve_leg_wait(call_id, {"answered": True})
        info = self._peek_outbound_originator(call_id)
        if info is None:
            return
        self.bind_call_trace(call_id)
        tenant_id, employee_id, _did = info

        redis = _get_redis_client()
        if redis is not None:
            try:
                await CcAgentResourceService.mark_in_call(
                    redis,
                    tenant_id,
                    employee_id,
                    call_id=call_id,
                    direction="outbound",
                )
            except Exception:  # noqa: BLE001
                logger.exception("outbound resource mark_in_call failed call_id=%s", call_id)

        # CDR transition: ringing → in_progress with answered_at + agent_id.
        # Best-effort; failures here MUST NOT block the bridge that follows.
        try:
            async with AsyncSessionLocal() as db:
                await CallRecordService.mark_answered(
                    db, tenant_id, call_id, agent_id=employee_id,
                )
                await db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("CDR mark_answered (outbound) failed call_id=%s", call_id)

        # Bridge to the agent's pre-built WebRTC leg so audio flows instantly.
        # No pairing means the agent never POSTed /dial-webrtc/offer — call
        # still goes through SIP but agent has no media path. We surface the
        # answered event regardless so the UI advances.
        webrtc_call_id = self._pop_outbound_webrtc(call_id)
        if webrtc_call_id:
            # Read the tenant's live-transcription toggle on a short session that
            # closes before the bridge RPC (no DB session held across I/O).
            from app.services.system_settings_service import SystemSettingsService

            transcribe = await SystemSettingsService.is_bridge_asr_enabled_managed(tenant_id)
            try:
                await self.telephony.call_bridge(call_id, webrtc_call_id, transcribe=transcribe)
                logger.info(
                    "outbound auto-bridge: sip=%s webrtc=%s", call_id, webrtc_call_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "outbound auto-bridge failed sip=%s webrtc=%s",
                    call_id, webrtc_call_id,
                )
        else:
            logger.warning(
                "outbound answered without WebRTC pairing (no audio path): %s",
                call_id,
            )
        await self.notify_agent_outbound_event(
            tenant_id=tenant_id, employee_id=employee_id,
            method="cc.outbound_answered",
            payload={"call_id": call_id},
        )

    # ────────────────── Outbound push to agent browsers ──────────────────

    async def notify_agent_incoming(
        self,
        *,
        tenant_id: int,
        employee_id: int,
        payload: dict,
    ) -> bool:
        try:
            rt = get_realtime_transport()
            room = f"agent:{tenant_id}:{employee_id}"
            await rt.emit("cc.call_incoming", payload, room=room, namespace="/chat")
            return True
        except Exception:  # noqa: BLE001
            logger.exception("cc.call_incoming push failed agent=%s/%s", tenant_id, employee_id)
            return False

    async def notify_agent_call_ended(
        self,
        *,
        tenant_id: int,
        employee_id: int,
        call_id: str,
        reason: str | None,
    ) -> None:
        try:
            rt = get_realtime_transport()
            room = f"agent:{tenant_id}:{employee_id}"
            await rt.emit(
                "cc.call_hangup",
                {"call_id": call_id, "reason": reason},
                room=room,
                namespace="/chat",
            )
        except Exception:  # noqa: BLE001
            logger.exception("cc.call_hangup push failed")

    async def notify_agent_call_answered(
        self, *, tenant_id: int, employee_id: int, call_id: str
    ) -> None:
        """Tell an agent's browser the call was answered on their physical phone.

        For SIP-phone agents the off-hook happens on the handset, not in the
        browser, so the workspace must be moved to 通话中 by this push instead of
        by a browser "接听" click.
        """
        try:
            rt = get_realtime_transport()
            room = f"agent:{tenant_id}:{employee_id}"
            await rt.emit(
                "cc.call_answered",
                {"call_id": call_id},
                room=room,
                namespace="/chat",
            )
        except Exception:  # noqa: BLE001
            logger.exception("cc.call_answered push failed")

    async def notify_conference_participant_left(
        self, *, tenant_id: int, employee_id: int
    ) -> None:
        """Tell a conference host their participant left → collapse the 3-way."""
        try:
            rt = get_realtime_transport()
            room = f"agent:{tenant_id}:{employee_id}"
            await rt.emit(
                "cc.conference_participant_left", {}, room=room, namespace="/chat",
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "cc.conference_participant_left push failed agent=%s/%s",
                tenant_id, employee_id,
            )

    async def notify_agent_outbound_event(
        self,
        *,
        tenant_id: int,
        employee_id: int,
        method: str,
        payload: dict,
    ) -> None:
        """Push an outbound-lifecycle event to the agent's browser.

        Used for cc.outbound_ringing / cc.outbound_answered / cc.outbound_hangup.
        Same room/namespace convention as the inbound notifications.
        """
        try:
            rt = get_realtime_transport()
            room = f"agent:{tenant_id}:{employee_id}"
            await rt.emit(method, payload, room=room, namespace="/chat")
        except Exception:  # noqa: BLE001
            logger.exception("%s push failed agent=%s/%s", method, tenant_id, employee_id)

    async def notify_agent_control_result(
        self,
        *,
        tenant_id: int,
        employee_id: int,
        method: str,
        payload: dict,
    ) -> None:
        """Push a consult / transfer result to the initiating agent's browser.

        Used for cc.consult_result / cc.transfer_result so the initiator's UI
        leaves the "咨询中/转接中" state once the background ring resolves
        (target answered, declined, timed out, or errored). Same room/namespace
        convention as the inbound notifications.
        """
        try:
            rt = get_realtime_transport()
            room = f"agent:{tenant_id}:{employee_id}"
            await rt.emit(method, payload, room=room, namespace="/chat")
        except Exception:  # noqa: BLE001
            logger.exception("%s push failed agent=%s/%s", method, tenant_id, employee_id)


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
