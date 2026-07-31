"""Resolution of transfer/consult/conference targets and agent-facing notifications."""
from __future__ import annotations

import logging

from app.core.exceptions import (
    NotFoundError,
    NotImplementedApiError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class TargetResolutionMixin:
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
            from app.db.redis import redis_client
            from app.services.agent_call_device_service import AgentCallDeviceService

            async with _ccs.AsyncSessionLocal() as db:
                endpoint = await AgentCallDeviceService.resolve_employee_call_endpoint(
                    db, tenant_id, target_id, redis_client.client
                )
            if endpoint.get("kind") != "sip":
                raise ValidationError(
                    endpoint.get("reason")
                    or "目标坐席未绑定 SIP 分机，且当前无可用 Web 电话"
                )
            return {"extension": endpoint["extension"]}, f"employee:{target_id}"

        if target_type == "external":
            async with _ccs.AsyncSessionLocal() as db:
                tenant = await _ccs.TenantPhoneNumberRepository.get_tenant(db, tenant_id)
                if tenant is None:
                    raise NotFoundError("Tenant not found")
                dids = await _ccs.TenantPhoneNumberRepository.list_assigned(
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

        True when the colleague's current device is an available Web phone —
        even if they are bound to a registered shared SIP extension. Shared
        phones are only dialed when the target is the current occupant and has
        selected SIP. A short session is opened and closed here.
        """

        if target_id is None:
            return False
        from app.db.redis import redis_client
        from app.services.agent_call_device_service import AgentCallDeviceService

        async with _ccs.AsyncSessionLocal() as db:
            endpoint = await AgentCallDeviceService.resolve_employee_call_endpoint(
                db, tenant_id, target_id, redis_client.client
            )
        return endpoint.get("kind") == "webrtc"

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
        async with _ccs.AsyncSessionLocal() as db:
            row = await AgentStatusRepository.get_for_employee(
                db, tenant_id, target_employee_id
            )
        if getattr(row, "status", None) != "ready":
            return None
        from app.core.exceptions import ConflictError

        try:
            return await _ccs.CcAgentResourceService.set_visible_status(
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

        snapshot = await _ccs.CcAgentResourceService.get_snapshot(
            r, tenant_id, target_employee_id
        )
        # Only reconcile when the snapshot looks unavailable and the agent isn't
        # mid-call; a healthy or busy snapshot is already authoritative.
        if snapshot is None or (
            snapshot.get("visible_status") == "offline"
            and snapshot.get("resource_state") not in ACTIVE_RESOURCE_STATES
        ):
            healed = await _ccs.CallControlService._reconcile_target_presence(
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
    async def _cancel_pending_consult_offer(offer_id: str, reason: str) -> None:
        """Cancel a still-ringing browser consult offer.

        Used when the host ends/tears down a consult during RINGING so the
        background ``initiate_webrtc_consult`` wait exits promptly instead of
        racing a late accept against the restored customer call.

        Two mechanisms cover both sides of the register_offer race:
        - a Redis tombstone aborts the ring task if it has NOT yet registered
          its pending offer (it checks the key before pushing the ring);
        - resolve_offer wakes the wait with a decline if it HAS registered.
        """

        from app.constants.call_center import consult_cancel_key
        from app.services.call_center.orchestrator import (
            _get_redis_client,
            get_orchestrator,
        )

        r = _get_redis_client()
        if r is not None:
            try:
                await r.set(consult_cancel_key(offer_id), "1", ex=120)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "consult cancel: tombstone write failed offer=%s",
                    offer_id, exc_info=True,
                )
        try:
            get_orchestrator().resolve_offer(
                offer_id, {"accept": False, "reason": reason},
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "consult cancel: resolve offer failed offer=%s",
                offer_id, exc_info=True,
            )

    @staticmethod
    async def _notify_consult_failed(
        tenant_id: int, initiator_employee_id: int, reason: str
    ) -> None:
        """Tell the initiator their WebRTC consult ring failed."""

        await _ccs.CallControlService._notify_control_result(
            tenant_id=tenant_id,
            initiator_employee_id=initiator_employee_id,
            method="cc.consult_result",
            payload={
                "ok": False,
                "kind": "consult",
                "reason": _ccs.CallControlService._friendly_fail_reason(reason),
            },
        )

    @staticmethod
    async def _notify_transfer_failed(
        tenant_id: int, initiator_employee_id: int, reason: str
    ) -> None:
        """Tell the initiator their WebRTC transfer ring failed."""

        await _ccs.CallControlService._notify_control_result(
            tenant_id=tenant_id,
            initiator_employee_id=initiator_employee_id,
            method="cc.transfer_result",
            payload={
                "ok": False,
                "kind": "transfer",
                "reason": _ccs.CallControlService._friendly_fail_reason(reason),
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

        async with _ccs.AsyncSessionLocal() as db:
            emp = await _ccs.EmployeeRepository.get_by_id(db, employee_id)
        if emp is None:
            return ""
        return emp.display_name or emp.nickname or emp.name or emp.username or ""

# Imported after the mixin class so this module can be imported directly
# without a circular-import error (call_control_service imports the mixins).
from app.services.call_center import call_control_service as _ccs  # noqa: E402
