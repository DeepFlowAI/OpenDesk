"""Kernel event handlers: inbound call routing and workflow startup, live
transcript relay, WebRTC ICE forwarding, SIP extension registration,
hangup finalization, recording persistence, and reconnect reconciliation."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.libs.telephony import CallEvent


def _recording_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


class EventHandlersMixin:

    async def _reconcile_active_call_ids(self) -> tuple[set[str], bool]:
        """Return active calls across every configured blue/green color.

        The stable entry only sees the newly active color. A short-lived,
        read-only query of both color endpoints prevents an API restart during
        drain from declaring old-color calls ended. Cleanup is allowed only
        when every configured endpoint answered successfully.
        """
        from app.configs.settings import settings
        from app.libs.telephony.providers.flowkit.client import FlowKitTelephonyClient

        urls = [
            value.strip()
            for value in settings.TELEPHONY_RECONCILE_WS_URLS.split(",")
            if value.strip()
        ]
        if not urls:
            calls = await self.telephony.call_list()
            return {str(c["call_id"]) for c in calls if c.get("call_id")}, True

        active: set[str] = set()
        complete = True
        for url in urls:
            client = FlowKitTelephonyClient(
                ws_url=url,
                sdk_name=f"{settings.TELEPHONY_SDK_NAME}-reconcile",
                sdk_version=settings.TELEPHONY_SDK_VERSION,
                rpc_timeout=min(settings.TELEPHONY_RPC_TIMEOUT, 5.0),
            )
            try:
                await asyncio.wait_for(client._open_and_handshake(), timeout=5.0)
                client._start_recv_loop()
                calls = await client.call_list()
                active.update(str(c["call_id"]) for c in calls if c.get("call_id"))
            except ConnectionRefusedError:
                # A stopped color has no surviving calls. This is the normal
                # single-active steady state, not an incomplete snapshot.
                continue
            except Exception as exc:  # noqa: BLE001
                complete = False
                _orch.logger.warning(
                    "Reconnect reconcile endpoint unavailable url=%s err=%s; "
                    "stale calls will not be released in this pass",
                    url,
                    exc,
                )
            finally:
                await client.disconnect()
        return active, complete

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
        async with _orch.AsyncSessionLocal() as db:
            for slug in candidates:
                if not slug:
                    continue
                row = (
                    await db.execute(select(Tenant).where(Tenant.tenant_id == slug))
                ).scalar_one_or_none()
                if row is not None:
                    self._cached_tenant_id = int(row.id)
                    _orch.logger.info(
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
                _orch.logger.warning(
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

        async with _orch.AsyncSessionLocal() as db:
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
            _orch.logger.info(
                "Inbound DID %s routed to tenant id=%s slug=%s",
                to_number, tenant.id, phone.tenant_id,
            )
            return int(tenant.id)

    async def _on_incoming(self, event: CallEvent) -> None:
        data = event.data
        call_id = data.get("call_id")
        if not call_id:
            return

        to_extension = data.get("to", "").replace("sip:", "").split("@")[0]
        if self._personal_outbound_extensions and not to_extension:
            pending_extension = next(iter(self._personal_outbound_extensions))
            self._personal_outbound_extensions.discard(pending_extension)
            _orch.logger.info(
                "Skipping call.incoming for pending personal outbound extension=%s call_id=%s",
                pending_extension,
                call_id,
            )
            return
        if to_extension in self._personal_outbound_extensions:
            self._personal_outbound_extensions.discard(to_extension)
            _orch.logger.info(
                "Skipping call.incoming for personal outbound extension=%s call_id=%s",
                to_extension,
                call_id,
            )
            return

        if self.personal_auto_outbound.owns_call(call_id):
            _orch.logger.info(
                "Skipping call.incoming for personal outbound call_id=%s", call_id
            )
            return

        if data.get("direction") == "outbound":
            _orch.logger.info(
                "Skipping call.incoming for outbound call_id=%s", call_id
            )
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
            _orch.logger.info(
                "Skipping call.incoming for non-SIP transport=%s call_id=%s",
                transport, call_id,
            )
            return

        # Blue/green drain: do not claim new inbound — a sibling node that is
        # still accepting traffic should own the call instead.
        if self._draining:
            _orch.logger.info(
                "Skipping call.incoming call_id=%s — orchestrator draining", call_id
            )
            return

        # Multi-node safety: FlowKit broadcasts call.incoming to every connected
        # orchestrator. Exactly one node owns each call — the rest skip — so we
        # don't answer/route the same call more than once.
        if not await self._claim_call(call_id):
            _orch.logger.info(
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
        trace_id = _orch.set_trace_id(_orch.parse_traceparent(traceparent))
        if _orch.parse_traceparent(traceparent) is None:
            traceparent = _orch.build_traceparent(trace_id)
        trace_call_id = data.get("root_call_id") or call_id
        _orch.set_call_id(trace_call_id)
        self._register_call_trace(call_id, trace_id, trace_call_id)
        if trace_call_id != call_id:
            self._register_call_trace(trace_call_id, trace_id, trace_call_id)

        from_number = data.get("from", "").replace("sip:", "").split("@")[0]
        to_number = data.get("to", "").replace("sip:", "").split("@")[0]

        # A call from one of our own phones is an agent dialling out, not a
        # customer calling in: `to` is the number they keyed in rather than a
        # DID of ours, so routing it as inbound would answer the handset with
        # whatever IVR the fallback tenant happens to have.
        caller_extension = data.get("caller_extension")
        if caller_extension:
            await self.handle_extension_dialed_out(
                handset_call_id=call_id,
                caller_extension=caller_extension,
                dialed=to_number,
            )
            return

        t0 = time.perf_counter()
        routing_started_at = datetime.now(timezone.utc)

        # Per-DID tenant routing: bind the call to the tenant that owns the
        # dialed number. When this environment shares FlowKit with another
        # OpenDesk, skip unknown/unassigned DIDs so the owner environment
        # can answer. Otherwise fall back to the default tenant (OSS).
        tenant_id = await self._resolve_tenant_id_for_did(to_number)
        if tenant_id is None:
            from app.configs.settings import settings

            if settings.CALL_CENTER_SKIP_UNOWNED_DID:
                _orch.logger.info(
                    "Skipping call.incoming call_id=%s to=%s — DID not assigned here",
                    call_id,
                    to_number,
                )
                await self._release_call(call_id)
                return
            tenant_id = await self._resolve_tenant_id()
        if tenant_id is None:
            _orch.logger.warning("Inbound call %s: no tenant resolved; hanging up", call_id)
            await self.telephony.call_hangup(call_id, reason="no_tenant")
            return
        t_did_ms = (time.perf_counter() - t0) * 1000

        async with _orch.AsyncSessionLocal() as db:
            matched = await _orch.match_routing_rule(
                db, tenant_id, from_number=from_number, to_number=to_number,
            )
            if matched is None:
                _orch.logger.warning("No routing rule matched call_id=%s; hanging up", call_id)
                await self.telephony.call_hangup(call_id, reason="no_route")
                return
            rule, flow = matched

            if rule.target_type == "voicespeed_agent":
                graph = _orch.build_voicespeed_direct_graph(
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

            # Skip caller identification here — it scans every user with a phone
            # and historically delayed answer/first prompt by several seconds.
            await _orch.CallRecordService.create_for_incoming(
                db,
                tenant_id,
                call_id=call_id,
                conversation_id=data.get("conversation_id"),
                root_call_id=data.get("root_call_id"),
                from_number=from_number or None,
                to_number=to_number or None,
                voice_flow_id=voice_flow_id,
                voice_flow_version_id=voice_flow_version_id,
                identify_user=False,
            )
            from app.services.call_trajectory_service import CallTrajectoryService

            await CallTrajectoryService.append_for_call_id_best_effort(
                tenant_id=tenant_id,
                call_id=call_id,
                event_id=f"opendesk:routing-started:{call_id}",
                event_type="routing_started",
                event_category="routing",
                actor_type="system",
                source="opendesk",
                occurred_at=routing_started_at,
                trace_id=trace_id,
            )
            await CallTrajectoryService.append_for_call_id_best_effort(
                tenant_id=tenant_id,
                call_id=call_id,
                event_id=f"opendesk:route-matched:{call_id}",
                event_type="route_matched",
                event_category="routing",
                actor_type="system",
                source="opendesk",
                occurred_at=datetime.now(timezone.utc),
                target_type=("bot" if rule.target_type == "voicespeed_agent" else "voice_flow"),
                target_id=str(
                    rule.voicespeed_agent_id
                    if rule.target_type == "voicespeed_agent"
                    else voice_flow_version_id or voice_flow_id or getattr(rule, "id", "")
                ),
                target_name_snapshot=(
                    rule.voicespeed_agent_name
                    if rule.target_type == "voicespeed_agent"
                    else getattr(rule, "name", None)
                ),
                result="succeeded",
                trace_id=trace_id,
                details={
                    "voice_flow_id": voice_flow_id,
                    "voice_flow_version_id": voice_flow_version_id,
                    "routing_rule_id": getattr(rule, "id", None),
                },
            )
            if any(
                node.get("type") in {"play", "collect", "condition"}
                for node in graph.get("nodes", [])
            ):
                await CallTrajectoryService.append_for_call_id_best_effort(
                    tenant_id=tenant_id,
                    call_id=call_id,
                    event_id=f"opendesk:ivr-entered:{call_id}",
                    event_type="ivr_entered",
                    event_category="ivr",
                    actor_type="system",
                    source="opendesk",
                    occurred_at=datetime.now(timezone.utc),
                    target_type="voice_flow",
                    target_id=str(
                        voice_flow_version_id or voice_flow_id or getattr(rule, "id", "")
                    ),
                    result="succeeded",
                    trace_id=trace_id,
                )
        t_route_ms = (time.perf_counter() - t0) * 1000 - t_did_ms

        workflow = _orch.VoiceFlowWorkflow(
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
        from app.services.call_trajectory_service import CallTrajectoryService

        await CallTrajectoryService.append_for_call_id_best_effort(
            tenant_id=tenant_id,
            call_id=call_id,
            event_id=f"flowkit:customer-connected:{call_id}",
            event_type="customer_connected",
            event_category="lifecycle",
            actor_type="customer",
            source="flowkit",
            occurred_at=datetime.now(timezone.utc),
            call_leg_id=call_id,
            participant_role="customer",
            result="succeeded",
            trace_id=trace_id,
        )
        t_answer_ms = (time.perf_counter() - t0) * 1000
        # Identify in parallel with RTP warmup — never block the greeting.
        asyncio.create_task(
            self._identify_incoming_user(tenant_id, call_id),
            name=f"identify-inbound-{call_id}",
        )
        # Warm up the media path once before the first prompt (see above).
        if _orch._RTP_WARMUP_SECONDS > 0:
            await asyncio.sleep(_orch._RTP_WARMUP_SECONDS)
        _orch.logger.info(
            "Inbound ready call_id=%s did_ms=%.0f route_cdr_ms=%.0f answer_ms=%.0f warmup_s=%s",
            call_id, t_did_ms, t_route_ms, t_answer_ms, _orch._RTP_WARMUP_SECONDS,
        )
        try:
            await workflow.start()
        except Exception:  # noqa: BLE001
            _orch.logger.exception("Workflow start failed call_id=%s", call_id)
            await self.telephony.call_hangup(call_id, reason="workflow_error")

    async def _identify_incoming_user(self, tenant_id: int, call_id: str) -> None:
        """Background caller→user match for an inbound CDR (non-critical path)."""
        try:
            await _orch.CallRecordService.identify_user_for_call_managed(tenant_id, call_id)
        except Exception:  # noqa: BLE001
            _orch.logger.exception(
                "Background inbound user identify failed call_id=%s", call_id
            )

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
            _orch.set_trace_id(trace_id)
        _orch.set_call_id(trace_call_id or call_id)

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
        if wf is not None:
            agent = wf.bridged_agent_info()
        else:
            # Agent-dialed outbound calls run without a workflow; their bridge
            # transcript belongs to whichever agent currently owns the call.
            originator = await self._peek_outbound_originator(call_id)
            agent = (
                {"tenant_id": originator[0], "employee_id": originator[1]}
                if originator is not None
                else None
            )
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
            await _orch.emit_to_agent(
                tenant_id=agent["tenant_id"],
                employee_id=agent["employee_id"],
                method="cc.transcript",
                payload={
                    "call_id": call_id,
                    "role": role,
                    "text": text,
                    "final": final,
                    "seq": event.data.get("seq"),
                },
                transport=_orch.get_realtime_transport(),
            )
        except Exception:  # noqa: BLE001
            _orch.logger.exception("cc.transcript push failed call_id=%s", call_id)

        # Persist finalized lines so the transcript survives a refresh and is
        # viewable from call history. Partials are transient and not stored.
        if final:
            try:
                async with _orch.AsyncSessionLocal() as db:
                    await _orch.CallTranscriptService.append(
                        db,
                        tenant_id=agent["tenant_id"],
                        call_id=call_id,
                        role=role,
                        text=text,
                        seq=event.data.get("seq"),
                    )
            except Exception:  # noqa: BLE001
                _orch.logger.exception("transcript persist failed call_id=%s", call_id)

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
            async with _orch.AsyncSessionLocal() as db:
                info = await _orch.AgentWebRTCSessionService.get_employee_for_call_id(db, call_id)
        except Exception:  # noqa: BLE001
            _orch.logger.exception("webrtc.ice lookup failed call_id=%s", call_id)
            return
        if not info:
            return
        try:
            await _orch.emit_to_agent(
                tenant_id=info["tenant_id"],
                employee_id=info["employee_id"],
                method="cc.webrtc.ice",
                payload={"call_id": call_id, "candidate": candidate},
                transport=_orch.get_realtime_transport(),
            )
        except Exception:  # noqa: BLE001
            _orch.logger.exception("webrtc.ice emit failed")

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
            async with _orch.AsyncSessionLocal() as db:
                updated = await SipExtensionService.apply_registration_event(
                    db, sip_user_id=sip_user_id, registered=registered,
                )
        except Exception:  # noqa: BLE001
            _orch.logger.exception(
                "extension registration writeback failed sip_user_id=%s", sip_user_id,
            )
            return
        if updated is None:
            _orch.logger.info(
                "extension %s event ignored (no matching extension) registered=%s",
                sip_user_id, registered,
            )
            return
        _orch.logger.info(
            "extension %s registration → %s",
            sip_user_id, "registered" if registered else "unregistered",
        )
        try:
            async with _orch.AsyncSessionLocal() as db:
                bound_ids = await SipExtensionService.list_bound_employee_ids_for_notify(
                    db, updated
                )
        except Exception:  # noqa: BLE001
            _orch.logger.exception("list bound employees for registration notify failed")
            return
        if not bound_ids:
            return
        try:
            payload = {
                "extension_number": updated.extension_number,
                "registration_status": updated.registration_status,
            }
            for emp_id in bound_ids:
                await _orch.emit_to_agent(
                    tenant_id=updated.tenant_id,
                    employee_id=emp_id,
                    method="cc.device_registration_changed",
                    payload=payload,
                    transport=_orch.get_realtime_transport(),
                )
        except Exception:  # noqa: BLE001
            _orch.logger.exception("cc.device_registration_changed push failed")

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
                _orch.logger.warning(
                    "caller hangup: cancel ringing handset leg=%s failed",
                    pending_ext, exc_info=True,
                )
            self._resolve_leg_wait(
                pending_ext, {"answered": False, "reason": "caller_hangup"}
            )
        # Customer hung up while a queue blind-transfer was still waiting /
        # ringing: cancel the background task so the reserved agent is released
        # (the task's CancelledError path frees the reservation).
        pending_queue_task = self.pop_pending_queue_transfer(call_id)
        if pending_queue_task is not None and not pending_queue_task.done():
            pending_queue_task.cancel()
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
            _orch.logger.warning(
                "conference participant-departed handling failed call=%s",
                call_id, exc_info=True,
            )

        # Consulted colleague hung up / media lost: resume initiator↔customer
        # (or wait for target media-reconnect after a page refresh).
        # Host media hangup during consult: drop B and clean up so B leaves 通话中.
        try:
            from app.services.call_center.call_control_service import CallControlService
            hangup_reason = event.data.get("reason")
            handled = await CallControlService.on_consult_target_departed(
                call_id, reason=hangup_reason,
            )
            if not handled:
                await CallControlService.on_consult_host_media_departed(
                    call_id, reason=hangup_reason,
                )
        except Exception:  # noqa: BLE001
            _orch.logger.warning(
                "consult hangup handling failed call=%s",
                call_id, exc_info=True,
            )

        # Outbound originator path: if this call_id was an agent-initiated
        # outbound, notify the agent's browser. We MARK the entry as ended
        # (so a late /dial-webrtc/offer returns 410 Gone with the SIP reason
        # rather than a misleading 404) and schedule deletion in 60s — this
        # race is common when the carrier rejects in <50ms, faster than the
        # browser can complete getUserMedia + createOffer.
        outbound_info = await self._peek_outbound_originator(call_id)
        await self._pop_outbound_webrtc(call_id)
        getattr(self, "_outbound_answered", set()).discard(call_id)
        getattr(self, "_outbound_bridge_claims", set()).discard(call_id)
        reason = event.data.get("reason")
        sip_status = event.data.get("sip_status")
        hangup_details = {
            key: event.data.get(key)
            for key in (
                "sip_status",
                "sip_reason",
                "sip_warning",
                "sip_reason_hdr",
                "sip_call_id",
            )
            if event.data.get(key) is not None
        }
        # Auto-outbound dial engine: finalize target/record when this call_id
        # was originated by the system dialer (Redis session mapping).
        try:
            from app.services.auto_outbound import try_handle_auto_outbound_ended

            await try_handle_auto_outbound_ended(
                call_id, reason, sip_status, event.data.get("request_id")
            )
        except Exception:  # noqa: BLE001
            _orch.logger.exception(
                "auto_outbound ended hook failed call_id=%s", call_id
            )
        early_fail = self._is_outbound_early_fail(reason, sip_status)
        if outbound_info is not None or early_fail:
            # Supplier-facing SIP detail from FlowKit (status phrase / Warning /
            # Reason / Call-ID). Keep in OpenDesk logs so triage can paste it
            # without SSHing into the kernel host. Failures stay WARNING;
            # normal outbound ends are INFO.
            (_orch.logger.warning if early_fail else _orch.logger.info)(
                "outbound SIP ended: call_id=%s reason=%s sip_status=%s "
                "sip_reason=%s sip_warning=%s sip_reason_hdr=%s sip_call_id=%s",
                call_id,
                reason,
                sip_status,
                event.data.get("sip_reason"),
                event.data.get("sip_warning"),
                event.data.get("sip_reason_hdr"),
                event.data.get("sip_call_id"),
            )

        if outbound_info is not None:
            await self._mark_outbound_ended(
                call_id, reason, sip_status, hangup_details=hangup_details
            )
            import asyncio as _aio
            _aio.create_task(self._delayed_outbound_cleanup(call_id))
            # Push cc.outbound_hangup only after Redis/PG status is restored
            # below. The workbench refetches on that event; notifying first
            # leaves the agent stuck on busy until the next 30s poll.
        elif early_fail:
            # Hangup beat register_outbound_call: still remember the SIP
            # failure so dial-webrtc returns 410 with the real reason.
            await self._mark_outbound_ended(
                call_id, reason, sip_status, hangup_details=hangup_details
            )
            import asyncio as _aio
            _aio.create_task(self._delayed_outbound_cleanup(call_id))
            _orch.logger.info(
                "outbound early fail before originator registered: "
                "call_id=%s reason=%s sip_status=%s",
                call_id, reason, sip_status,
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
            async with _orch.AsyncSessionLocal() as db:
                from sqlalchemy import select
                from app.models.call_record import CallRecord
                row = (
                    await db.execute(select(CallRecord).where(CallRecord.call_id == call_id))
                ).scalar_one_or_none()
                was_answered = bool(row and row.customer_connected_at)
                if row is not None:
                    await _orch.CallRecordService.mark_completed(
                        db,
                        row.tenant_id,
                        call_id,
                        hangup_reason=event.data.get("reason"),
                        hangup_party=event.data.get("hangup_party"),
                        hangup_details=hangup_details,
                    )

                redis = _orch._get_redis_client()
                if outbound_info is not None:
                    tenant_id_out, employee_id_out, _did = outbound_info
                    if was_answered:
                        from app.services.call_wrapup_service import (
                            apply_post_call_agent_status,
                            resolve_effective_wrapup_seconds,
                        )

                        wrapup_seconds = await resolve_effective_wrapup_seconds(
                            db, tenant_id_out, call_id
                        )
                        await apply_post_call_agent_status(
                            db,
                            redis,
                            tenant_id_out,
                            employee_id_out,
                            call_id=call_id,
                            reason=event.data.get("reason") or "call_hangup",
                            wrapup_seconds=wrapup_seconds,
                        )
                    elif redis is not None:
                        released = await _orch.CcAgentResourceService.release(
                            redis,
                            tenant_id_out,
                            employee_id_out,
                            reason=event.data.get("reason") or "outbound_hangup",
                            expected_call_id=call_id,
                        )
                        await _orch.CcAgentStatusService.sync_pg_status(
                            db,
                            tenant_id_out,
                            employee_id_out,
                            released["visible_status"],
                            None,
                        )

                # Status auto-transition: bridge agent goes from busy →
                # after_call_work, and their webrtc session goes back to idle.
                if bridged_agent:
                    # Customer (or host) call ended while a consult was active —
                    # drop B's consult UI/resource so they don't stay 「通话中」.
                    try:
                        from app.services.call_center.call_control_service import (
                            CallControlService,
                        )

                        await CallControlService.cleanup_consult_for_host(
                            bridged_agent["tenant_id"],
                            bridged_agent["employee_id"],
                            reason=event.data.get("reason") or "call_hangup",
                            hangup_customer=False,
                        )
                    except Exception:  # noqa: BLE001
                        _orch.logger.warning(
                            "consult cleanup on host call end failed agent=%s",
                            bridged_agent.get("employee_id"),
                            exc_info=True,
                        )
                    # Customer hangup during a 3-way conference: free the
                    # Web-phone colleague so they are not stuck in_call.
                    try:
                        from app.services.call_center.call_control_service import (
                            CallControlService,
                        )

                        await CallControlService.cleanup_conference_for_host(
                            bridged_agent["tenant_id"],
                            bridged_agent["employee_id"],
                            reason=event.data.get("reason") or "call_hangup",
                        )
                    except Exception:  # noqa: BLE001
                        _orch.logger.warning(
                            "conference cleanup on host call end failed agent=%s",
                            bridged_agent.get("employee_id"),
                            exc_info=True,
                        )
                    # Customer↔agent bridges are keepalive so an agent browser
                    # refresh cannot drop the caller. When the customer leg is
                    # the one that ended, FlowKit keeps the agent leg up for a
                    # reconnect that will never come — hang it up explicitly or
                    # the browser stays in-call until FlowKit's survivor sweep.
                    try:
                        from app.services.call_center.call_control_service import (
                            _legs,
                        )

                        agent_legs = await _legs(
                            bridged_agent["tenant_id"],
                            bridged_agent["employee_id"],
                        )
                        agent_media_leg = agent_legs.agent_media_call_id
                    except Exception:  # noqa: BLE001
                        agent_media_leg = None
                    if agent_media_leg:
                        try:
                            await self.telephony.call_hangup(
                                agent_media_leg, reason="customer_hangup"
                            )
                        except Exception:  # noqa: BLE001
                            _orch.logger.debug(
                                "agent leg already gone leg=%s",
                                agent_media_leg,
                                exc_info=True,
                            )
                    from app.services.call_wrapup_service import (
                        apply_post_call_agent_status,
                        resolve_effective_wrapup_seconds,
                    )

                    wrapup_seconds = await resolve_effective_wrapup_seconds(
                        db, bridged_agent["tenant_id"], call_id
                    )
                    await apply_post_call_agent_status(
                        db,
                        redis,
                        bridged_agent["tenant_id"],
                        bridged_agent["employee_id"],
                        call_id=call_id,
                        reason=event.data.get("reason") or "call_hangup",
                        wrapup_seconds=wrapup_seconds,
                    )
                    await _orch.AgentWebRTCSessionService.set_busy(
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
                    await self._maybe_release_sip_occupancy(
                        redis,
                        bridged_agent["tenant_id"],
                        bridged_agent["employee_id"],
                    )
                # The workflow is gone but the CDR names a serving agent —
                # e.g. an auto-outbound reception popped its workflow right
                # after the bridge, or the process restarted mid-call. Settle
                # that agent only when their resource is still in_call on this
                # exact call, so an agent who already moved on is untouched.
                if (
                    bridged_agent is None
                    and outbound_info is None
                    and row is not None
                    and was_answered
                    and row.last_serving_agent_id is not None
                    and redis is not None
                ):
                    await self._settle_orphaned_serving_agent(
                        db,
                        redis,
                        tenant_id=row.tenant_id,
                        employee_id=int(row.last_serving_agent_id),
                        call_id=call_id,
                        reason=event.data.get("reason") or "call_hangup",
                    )
                # No workflow (e.g. an agent-dialled outbound call), so the
                # bridged-agent cleanup above never ran: still release / withdraw
                # the serving agent's conference colleague.
                if (
                    bridged_agent is None
                    and row is not None
                    and row.last_serving_agent_id is not None
                ):
                    try:
                        from app.services.call_center.call_control_service import (
                            CallControlService,
                        )

                        await CallControlService.cleanup_conference_for_host(
                            row.tenant_id,
                            int(row.last_serving_agent_id),
                            reason=event.data.get("reason") or "call_hangup",
                        )
                    except Exception:  # noqa: BLE001
                        _orch.logger.warning(
                            "conference cleanup on call end failed agent=%s",
                            row.last_serving_agent_id,
                            exc_info=True,
                        )
                if outbound_info:
                    _tid, _eid, _ = outbound_info
                    await self._maybe_release_sip_occupancy(redis, _tid, _eid)
        except Exception:  # noqa: BLE001
            _orch.logger.exception("Failed to finalize CDR / status for call_id=%s", call_id)

        if outbound_info is not None:
            tenant_id_out, employee_id_out, _did = outbound_info
            await self.notify_agent_outbound_event(
                tenant_id=tenant_id_out,
                employee_id=employee_id_out,
                method="cc.outbound_hangup",
                payload={
                    "call_id": call_id,
                    "reason": reason,
                    "sip_status": sip_status,
                    "sip_reason": event.data.get("sip_reason"),
                    "sip_warning": event.data.get("sip_warning"),
                    "sip_reason_hdr": event.data.get("sip_reason_hdr"),
                    "sip_call_id": event.data.get("sip_call_id"),
                },
            )

    async def _settle_orphaned_serving_agent(
        self,
        db,
        redis,
        *,
        tenant_id: int,
        employee_id: int,
        call_id: str,
        reason: str,
    ) -> None:
        """Best-effort post-call reset for a serving agent whose call has no
        live workflow left to drive the normal bridged-agent path."""
        try:
            snapshot = await _orch.CcAgentResourceService.get_snapshot(
                redis, tenant_id, employee_id
            )
        except Exception:  # noqa: BLE001
            _orch.logger.warning(
                "orphaned serving-agent settle: snapshot failed agent=%s/%s call=%s",
                tenant_id,
                employee_id,
                call_id,
                exc_info=True,
            )
            return
        if (
            not snapshot
            or snapshot.get("resource_state") != "in_call"
            or snapshot.get("current_call_id") != call_id
        ):
            return
        try:
            from app.services.call_wrapup_service import (
                apply_post_call_agent_status,
                resolve_effective_wrapup_seconds,
            )

            wrapup_seconds = await resolve_effective_wrapup_seconds(
                db, tenant_id, call_id
            )
            await apply_post_call_agent_status(
                db,
                redis,
                tenant_id,
                employee_id,
                call_id=call_id,
                reason=reason,
                wrapup_seconds=wrapup_seconds,
            )
            await _orch.AgentWebRTCSessionService.set_busy(
                db, tenant_id, employee_id, busy=False
            )
        except Exception:  # noqa: BLE001
            _orch.logger.warning(
                "orphaned serving-agent settle failed agent=%s/%s call=%s",
                tenant_id,
                employee_id,
                call_id,
                exc_info=True,
            )
            return
        await self.notify_agent_call_ended(
            tenant_id=tenant_id,
            employee_id=employee_id,
            call_id=call_id,
            reason=reason,
        )
        await self._maybe_release_sip_occupancy(redis, tenant_id, employee_id)

    async def _maybe_release_sip_occupancy(
        self,
        redis,
        tenant_id: int,
        employee_id: int,
    ) -> None:
        """Best-effort release after a call ends while the agent is offline."""
        if redis is None:
            return
        try:
            from app.services.sip_extension_occupancy_service import (
                SipExtensionOccupancyService,
            )

            async with _orch.AsyncSessionLocal() as db:
                await SipExtensionOccupancyService.maybe_release_for_employee(
                    db, redis, tenant_id, employee_id
                )
        except Exception:  # noqa: BLE001
            _orch.logger.exception(
                "SIP occupancy release after hangup failed agent=%s/%s",
                tenant_id,
                employee_id,
            )

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
        redis = _orch._get_redis_client()
        if redis is not None:
            try:
                await _orch.CcAgentResourceService.release(
                    redis,
                    tenant_id,
                    employee_id,
                    reason=reason,
                    expected_offer_id=offer_id,
                )
            except Exception:  # noqa: BLE001
                _orch.logger.exception(
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
        # Satisfaction handoff also ends here (agent → after-call-work) while
        # the customer stays on the survey. Dropping that live workflow would
        # leave play_end / DTMF / hangup with nowhere to go — the first prompt
        # plays, then the survey freezes and the execution never finalizes.
        current = self.active_workflow(call_id)
        from app.services.call_center.satisfaction_workflow import SatisfactionWorkflow

        if not (isinstance(current, SatisfactionWorkflow) and not current.done.is_set()):
            await self.discard_call_state(call_id)
        redis = _orch._get_redis_client()
        try:
            async with _orch.AsyncSessionLocal() as db:
                if mark_cdr_completed:
                    from sqlalchemy import select
                    from app.models.call_record import CallRecord
                    row = (
                        await db.execute(
                            select(CallRecord).where(CallRecord.call_id == call_id)
                        )
                    ).scalar_one_or_none()
                    if row is not None:
                        await _orch.CallRecordService.mark_completed(
                            db, row.tenant_id, call_id, hangup_reason=reason,
                        )
                from app.services.call_wrapup_service import (
                    apply_post_call_agent_status,
                    resolve_effective_wrapup_seconds,
                )

                wrapup_seconds = await resolve_effective_wrapup_seconds(
                    db, tenant_id, call_id
                )
                await apply_post_call_agent_status(
                    db,
                    redis,
                    tenant_id,
                    employee_id,
                    call_id=call_id,
                    reason=reason or "call_hangup",
                    wrapup_seconds=wrapup_seconds,
                )
                await _orch.AgentWebRTCSessionService.set_busy(
                    db, tenant_id, employee_id, busy=False,
                )
        except Exception:  # noqa: BLE001
            _orch.logger.exception(
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
        (FlowKit -32002 "call not found"), reset the agent's status here so they
        are not stuck on 忙碌. A `call.hangup` event may still arrive when the
        -32002 is a race with remote BYE; that event owns CDR finalization.
        Short DB session for the lookup is closed before the RPCs.
        """

        from sqlalchemy import desc, select
        from app.libs.telephony.base import TelephonyRPCError
        from app.models.call_record import CallRecord

        async with _orch.AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(CallRecord)
                    .where(
                        CallRecord.tenant_id == tenant_id,
                        (
                            (CallRecord.last_serving_agent_id == employee_id)
                            | (CallRecord.initiator_agent_id == employee_id)
                        ),
                        CallRecord.lifecycle_status == "active",
                    )
                    .order_by(desc(CallRecord.started_at))
                    .limit(1)
                )
            ).scalar_one_or_none()
            session = await _orch.AgentWebRTCSessionService.get_active(db, tenant_id, employee_id)
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
            _orch.logger.info(
                "Agent %s hangup of internal leg=%s (no CDR)",
                employee_id, webrtc_call_id,
            )
            try:
                await self.telephony.call_hangup(webrtc_call_id, reason="agent_hangup")
            except TelephonyRPCError as exc:
                if exc.code != -32002:
                    _orch.logger.warning(
                        "agent hangup: internal leg %s rejected code=%s",
                        webrtc_call_id, exc.code,
                    )
            except Exception:  # noqa: BLE001
                _orch.logger.warning("agent hangup: internal leg hangup raised", exc_info=True)
            redis = _orch._get_redis_client()
            if redis is not None:
                try:
                    await _orch.CcAgentResourceService.force_release(
                        redis, tenant_id, employee_id, reason="agent_hangup",
                    )
                except Exception:  # noqa: BLE001
                    _orch.logger.warning(
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
        _orch.logger.info(
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
                    _orch.logger.warning(
                        "agent hangup: agent leg %s hangup rejected code=%s",
                        webrtc_call_id, exc.code,
                    )
            except Exception:  # noqa: BLE001
                _orch.logger.warning("agent hangup: agent leg hangup raised", exc_info=True)

        customer_gone = False
        try:
            await self.telephony.call_hangup(target_call_id, reason="agent_hangup")
        except TelephonyRPCError as exc:
            if exc.code == -32002:
                customer_gone = True
            else:
                _orch.logger.warning("agent hangup: call.hangup rejected code=%s", exc.code)
                return {"ok": False, "error": "rpc_error", "code": exc.code}

        if customer_gone:
            # SIP is already gone. A call.hangup event is often still in flight
            # (agent hangup raced with remote BYE) and that path owns CDR
            # finalization. Reset the agent here so they are not stuck busy if
            # the event never arrives; do not mark the CDR completed or the two
            # writers deadlock / abort the same transaction.
            await self.finalize_agent_call(
                tenant_id=tenant_id,
                employee_id=employee_id,
                call_id=target_call_id,
                reason="agent_hangup",
                mark_cdr_completed=False,
            )
            return {"ok": True, "note": "already_ended", "call_id": target_call_id}
        return {"ok": True, "call_id": target_call_id}

    async def _on_recording_completed(self, event: CallEvent) -> None:
        """Persist one telephony recording artifact onto the target CDR model."""

        data = event.data
        call_id = data.get("call_id")
        recording_id = data.get("recording_id")
        storage_key = data.get("storage_key")
        source_event_id = data.get("event_id")
        if not call_id or not recording_id or not source_event_id:
            _orch.logger.warning(
                "call.recording.completed missing call_id/recording_id/event_id: %s",
                data,
            )
            return
        # Recording finalization normally arrives after call.ended has released
        # the transient call owner. Persist on every consumer and let the stable
        # recording/event identifiers converge through database upserts.
        self.bind_call_trace(call_id)
        try:
            from app.db.retry import run_db_op_with_deadlock_retry

            async def _persist() -> bool:
                async with _orch.AsyncSessionLocal() as db:
                    return await _orch.CallRecordService.save_recording(
                        db,
                        call_id=call_id,
                        recording_id=str(recording_id),
                        storage_key=str(storage_key) if storage_key else None,
                        source_event_id=str(source_event_id),
                        status="partial" if bool(data.get("partial", False)) else "completed",
                        call_leg_id=data.get("call_leg_id") or call_id,
                        phase=data.get("phase"),
                        started_at=_recording_datetime(data.get("started_at")),
                        ended_at=_recording_datetime(data.get("ended_at")),
                        duration_ms=data.get("duration_ms"),
                    )

            saved = await run_db_op_with_deadlock_retry(
                _persist,
                log_label=f"save_recording call_id={call_id}",
            )
            if saved:
                _orch.logger.info(
                    "Recording saved call_id=%s phase=%s partial=%s",
                    call_id, data.get("phase"), data.get("partial", False),
                )
            else:
                # Agent / media-reconnect legs never own a CDR; FlowKit still
                # broadcasts recording events for those legs — skip, not fail.
                _orch.logger.info(
                    "call.recording.completed: skipping call_id=%s; "
                    "call leg has no CDR (agent or reconnect legs do not own one)",
                    call_id,
                )
        except Exception:  # noqa: BLE001
            _orch.logger.exception(
                "Failed to save recording for call_id=%s", call_id,
            )

    async def _on_reconnect(self) -> None:
        """After WS reconnect, query active calls so we don't lose state."""

        try:
            active_ids, complete = await self._reconcile_active_call_ids()
            _orch.logger.info(
                "Reconnect: %d active calls across reconcile endpoints complete=%s",
                len(active_ids),
                complete,
            )
            await self.personal_auto_outbound.restore_running_sessions(
                active_ids, complete=complete
            )
            # Any agent left in_call whose call is no longer in the kernel lost
            # its end event while the WS was down — free it so the agent isn't
            # stranded on "busy" forever.
            released = await _orch.CcAgentResourceService.reconcile_in_call(
                _orch._get_redis_client(), active_ids, release_missing=complete
            )
            if released:
                _orch.logger.info(
                    "Reconnect reconcile: freed %d stranded agent resource(s)",
                    len(released),
                )
                # Close the stale call records too, otherwise the next status
                # poll would resurrect the in_call resource from them.
                from app.services.call_record_service import CallRecordService

                async with _orch.AsyncSessionLocal() as db:
                    for tenant_id, _employee_id, call_id in released:
                        try:
                            await CallRecordService.mark_completed(
                                db, tenant_id, call_id,
                                hangup_reason="reconnect_reconcile",
                            )
                        except Exception:  # noqa: BLE001
                            _orch.logger.exception(
                                "reconcile: mark_completed failed call_id=%s", call_id
                            )
                    await db.commit()
        except Exception:  # noqa: BLE001
            _orch.logger.exception("call_list after reconnect failed")

        # Align SIP-extension registration_status with the kernel's live
        # registrar (both directions). A kernel restart or color switch can
        # leave the in-memory registrar and the DB out of sync: bindings may
        # disappear without unregister events (stale "registered"), or be
        # restored while OpenDesk is still reconnecting (missed register
        # events → stale "unregistered"). Re-REGISTER with the same contact
        # only refreshes the lease and emits no event, so the DB cannot heal
        # itself without this reconcile.
        #
        # Blue/green cutover starts the idle color empty, then hot-migrates
        # bindings a moment later. Dual-WS OpenDesk may reconnect to the new
        # color in that window and see an empty list — retry once before
        # aligning, so we don't flash every desk phone as unregistered.
        try:
            import asyncio

            from app.libs.telephony.base import TelephonyMethodNotFoundError
            from app.services.sip_extension_service import SipExtensionService

            live = await self.telephony.extension_list()
            if not live:
                await asyncio.sleep(2)
                live = await self.telephony.extension_list()
            live_ids = {
                (e.get("extension") or "").strip()
                for e in live
                if e.get("extension")
            }
            async with _orch.AsyncSessionLocal() as db:
                flipped = await SipExtensionService.reconcile_registrations(db, live_ids)
                await db.commit()
            if flipped:
                n_registered = sum(
                    1 for e in flipped if e.registration_status == "registered"
                )
                n_unregistered = sum(
                    1 for e in flipped if e.registration_status == "unregistered"
                )
                _orch.logger.info(
                    "Reconnect reconcile: %d extension(s) aligned "
                    "(%d → registered, %d → unregistered)",
                    len(flipped),
                    n_registered,
                    n_unregistered,
                )
                for ext in flipped:
                    try:
                        async with _orch.AsyncSessionLocal() as db:
                            bound_ids = (
                                await SipExtensionService.list_bound_employee_ids_for_notify(
                                    db, ext
                                )
                            )
                        payload = {
                            "extension_number": ext.extension_number,
                            "registration_status": ext.registration_status,
                        }
                        for emp_id in bound_ids:
                            await _orch.emit_to_agent(
                                tenant_id=ext.tenant_id,
                                employee_id=emp_id,
                                method="cc.device_registration_changed",
                                payload=payload,
                                transport=_orch.get_realtime_transport(),
                            )
                    except Exception:  # noqa: BLE001
                        _orch.logger.exception("device_registration_changed push failed")
        except TelephonyMethodNotFoundError:
            pass  # kernel build without extension registrar
        except Exception:  # noqa: BLE001
            _orch.logger.exception("extension reconcile after reconnect failed")


# Imported after the mixin class so this module can be imported directly
# without a circular-import error (orchestrator imports the mixins).
from app.services.call_center import orchestrator as _orch  # noqa: E402
