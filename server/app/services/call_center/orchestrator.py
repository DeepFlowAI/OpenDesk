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

from app.configs.settings import settings
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
from app.services.call_center.routing import match_routing_rule
from app.services.call_center.workflow import VoiceFlowWorkflow
from app.services.call_record_service import CallRecordService
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService


logger = logging.getLogger(__name__)


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

    # Time we keep an ended call_id around so late /dial-webrtc/offer
    # requests can be answered with 410 Gone instead of a confusing 404.
    _OUTBOUND_CLEANUP_DELAY_SEC = 60

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

    async def start(self) -> None:
        if self._started:
            return
        await self.telephony.connect()
        self.telephony.on_event("call.incoming", self._on_incoming)
        self.telephony.on_event("call.dtmf", self._route_event)
        self.telephony.on_event("call.play_end", self._route_event)
        self.telephony.on_event("call.speech_end", self._route_event)
        self.telephony.on_event("call.bridged", self._route_event)
        self.telephony.on_event("call.hangup", self._on_hangup)
        self.telephony.on_event("call.recording.completed", self._on_recording_completed)
        # Outbound originate emits these three; we forward them to the
        # initiating agent's browser via Socket.IO.
        self.telephony.on_event("call.ringing", self._on_outbound_ringing)
        self.telephony.on_event("call.answered", self._on_outbound_answered)
        self.telephony.on_event("call.early_media", self._on_outbound_ringing)
        self.telephony.on_event("webrtc.ice", self._on_webrtc_ice)
        self.telephony.on_reconnected(self._on_reconnect)
        await self._start_catalog_sync()
        self._started = True
        logger.info("Call center orchestrator started")

    async def stop(self) -> None:
        if not self._started:
            return
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

        tenant_id = await self._resolve_tenant_id()
        if tenant_id is None:
            logger.warning("Inbound call %s: no tenant resolved; hanging up", call_id)
            await self.telephony.call_hangup(call_id, reason="no_tenant")
            return

        from_number = data.get("from", "").replace("sip:", "").split("@")[0]
        to_number = data.get("to", "").replace("sip:", "").split("@")[0]

        async with AsyncSessionLocal() as db:
            matched = await match_routing_rule(
                db, tenant_id, from_number=from_number, to_number=to_number,
            )
            if matched is None:
                logger.warning("No routing rule matched call_id=%s; hanging up", call_id)
                await self.telephony.call_hangup(call_id, reason="no_route")
                return
            rule, flow = matched
            _ = rule
            version = flow.current_version
            if version is None:
                await self.telephony.call_hangup(call_id, reason="no_flow_version")
                return
            graph = dict(version.graph_json)

            await CallRecordService.create_for_incoming(
                db,
                tenant_id,
                call_id=call_id,
                conversation_id=data.get("conversation_id"),
                root_call_id=data.get("root_call_id"),
                from_number=from_number or None,
                to_number=to_number or None,
                voice_flow_id=flow.id,
                voice_flow_version_id=version.id,
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
            },
        )
        self._workflows[call_id] = workflow

        await self.telephony.call_answer(call_id)
        try:
            await workflow.start()
        except Exception:  # noqa: BLE001
            logger.exception("Workflow start failed call_id=%s", call_id)
            await self.telephony.call_hangup(call_id, reason="workflow_error")

    async def _route_event(self, event: CallEvent) -> None:
        call_id = event.data.get("call_id")
        wf = self._workflows.get(call_id) if call_id else None
        if wf is None:
            return
        await wf.handle_event(event.method, event.data)

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

    async def _on_hangup(self, event: CallEvent) -> None:
        call_id = event.data.get("call_id")
        if not call_id:
            return

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
        if wf is not None:
            bridged_agent = wf.bridged_agent_info()
            await wf.on_call_hangup(event.data)

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
        except Exception:  # noqa: BLE001
            logger.exception("call_list after reconnect failed")

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
        """Bind the outbound SIP leg to the agent's WebRTC leg. The pairing
        is consumed in _on_outbound_answered to fire call.bridge."""

        self._outbound_webrtc_pairs[outbound_call_id] = webrtc_call_id

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
        tenant_id, employee_id, _did = info
        await self.notify_agent_outbound_event(
            tenant_id=tenant_id, employee_id=employee_id,
            method="cc.outbound_ringing",
            payload={"call_id": call_id, "event": event.method},
        )

    async def _on_outbound_answered(self, event: CallEvent) -> None:
        call_id = event.data.get("call_id") or ""
        info = self._peek_outbound_originator(call_id)
        if info is None:
            return
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
            try:
                await self.telephony.call_bridge(call_id, webrtc_call_id)
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
