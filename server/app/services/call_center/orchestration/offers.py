"""Pending-offer registry, per-call node ownership, cross-node agent offer
resolution, and the orchestrator start/drain/stop lifecycle including the
FlowKit catalog sync wiring."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class OffersMixin:

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
        r = _orch._get_redis_client()
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
        r = _orch._get_redis_client()
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
        r = _orch._get_redis_client()
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
        r = _orch._get_redis_client()
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

        r = _orch._get_redis_client()
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
        self._draining = False
        # Register handlers before connect so events are not missed once the
        # WS comes up (including after a deferred initial reconnect).
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
        await self.telephony.connect()
        await self._start_catalog_sync()
        import asyncio as _aio_offer
        self._offer_sub_task = _aio_offer.create_task(
            self._offer_resolve_loop(), name="cc-offer-resolve"
        )
        self._started = True
        if self.telephony.is_ready:
            logger.info("Call center orchestrator started")
        else:
            logger.warning(
                "Call center orchestrator started (FlowKit WS not ready yet; reconnecting)"
            )

    async def drain(self, timeout: float) -> int:
        """Stop claiming new calls; wait for in-flight workflows to finish.

        Keeps the telephony WebSocket connected so hangup / play_end events
        for active calls still arrive. Returns the number of calls that were
        force-finalized after ``timeout`` (0 if every workflow ended
        naturally).
        """
        if not self._started:
            return 0
        self._draining = True
        logger.info(
            "Call center orchestrator draining; active_workflows=%d timeout=%.0fs",
            len(self._workflows),
            timeout,
        )
        import time as _time

        import asyncio as _aio

        deadline = _time.monotonic() + max(0.0, float(timeout))
        while self._workflows:
            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                break
            await _aio.sleep(min(1.0, remaining))

        leftover = list(self._workflows.keys())
        if not leftover:
            logger.info("Call center orchestrator drain complete — all calls finished")
            return 0

        logger.warning(
            "Call center orchestrator drain timeout — force-finalizing %d call(s)",
            len(leftover),
        )
        for call_id in leftover:
            await self._force_finalize_drained_call(call_id)
        return len(leftover)

    async def _force_finalize_drained_call(self, call_id: str) -> None:
        """Best-effort OpenDesk-side cleanup when drain times out.

        Does not hang up the media leg on the kernel — media may still be
        live; we only close CDR / agent resource / owner state so the process
        can exit.
        """
        await self._release_call(call_id)
        self.cancel_play_wait(call_id)
        wf = self._workflows.pop(call_id, None)
        bridged_agent: dict | None = None
        pending_offer: dict | None = None
        if wf is not None:
            bridged_agent = wf.bridged_agent_info()
            pending_offer = wf.pending_offer_info()
            try:
                await wf.on_call_hangup({"call_id": call_id, "reason": "drain_timeout"})
            except Exception:  # noqa: BLE001
                logger.exception("drain finalize: workflow hangup failed call_id=%s", call_id)
            if pending_offer and not bridged_agent:
                try:
                    await self._withdraw_pending_offer(
                        tenant_id=wf.tenant_id,
                        call_id=call_id,
                        pending_offer=pending_offer,
                        reason="drain_timeout",
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "drain finalize: withdraw offer failed call_id=%s", call_id
                    )
        try:
            async with _orch.AsyncSessionLocal() as db:
                from sqlalchemy import select
                from app.models.call_record import CallRecord

                row = (
                    await db.execute(select(CallRecord).where(CallRecord.call_id == call_id))
                ).scalar_one_or_none()
                if row is not None:
                    await _orch.CallRecordService.mark_completed(
                        db, row.tenant_id, call_id, hangup_reason="drain_timeout",
                    )
                redis = _orch._get_redis_client()
                if bridged_agent and redis is not None:
                    released = await _orch.CcAgentResourceService.force_release(
                        redis,
                        bridged_agent["tenant_id"],
                        bridged_agent["employee_id"],
                        reason="drain_timeout",
                    )
                    await _orch.CcAgentStatusService.sync_pg_status(
                        db,
                        bridged_agent["tenant_id"],
                        bridged_agent["employee_id"],
                        released["visible_status"],
                        None,
                    )
        except Exception:  # noqa: BLE001
            logger.exception("drain finalize: CDR/agent cleanup failed call_id=%s", call_id)

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
        self._draining = False
        logger.info("Call center orchestrator stopped")

    async def _start_catalog_sync(self) -> None:
        """Wire FlowKit Catalog sync if configured (multi-trunk deployments).

        Skipped when FLOWKIT_TELECOM_API_URL is empty — single-trunk
        deployments rely on FlowKit's env-loaded `system` Provider and
        don't need OpenDesk to push anything.
        """
        if not _orch.settings.FLOWKIT_TELECOM_API_URL or not _orch.settings.FLOWKIT_TELECOM_API_KEY:
            logger.info(
                "FlowKit Catalog sync disabled (FLOWKIT_TELECOM_API_URL/_KEY unset)"
            )
            return
        telecom = _orch.FlowKitTelecomClient(
            base_url=_orch.settings.FLOWKIT_TELECOM_API_URL,
            api_key=_orch.settings.FLOWKIT_TELECOM_API_KEY,
            provider_id=_orch.settings.FLOWKIT_TELECOM_PROVIDER_ID,
        )
        sync = _orch.CatalogSyncService(
            telecom_client=telecom,
            lease_ttl_sec=_orch.settings.FLOWKIT_TELECOM_LEASE_SEC,
            stale_acceptable_sec=_orch.settings.FLOWKIT_TELECOM_STALE_ACCEPTABLE_SEC,
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


# Imported after the mixin class so this module can be imported directly
# without a circular-import error (orchestrator imports the mixins).
from app.services.call_center import orchestrator as _orch  # noqa: E402
