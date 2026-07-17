"""
Agent-initiated outbound call.

Translates "this tenant's agent dialed N using DID X" into a FlowKit
`call.originate` RPC:

  - Verifies the DID belongs to the agent's tenant
  - Verifies the DID has "outbound" in call_types
  - Resolves PhoneNumber.trunk_id → routes via that Trunk in FlowKit
  - Uses PhoneNumber.phone_number as caller_id (outbound DID)
  - Prepends PhoneNumber.called_number_prefix to destination, if set
    (carrier outbound access codes are a per-DID policy in OpenDesk;
    FlowKit's trunk catalog deliberately knows nothing about it).

Outbound time-window enforcement (PhoneNumber.outbound_time_slots) is
deferred — that's a UX policy on top of this primitive.
"""
from __future__ import annotations

import logging
import re
import uuid

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    NotFoundError,
    NotImplementedApiError,
    ValidationError,
)
from app.libs.telephony import BaseTelephonyClient
from app.libs.telephony.base import (
    TelephonyMethodNotFoundError,
    TelephonyRPCError,
)
from app.repositories.sip_extension_repository import SipExtensionRepository
from app.repositories.tenant_phone_number_repository import (
    TenantPhoneNumberRepository,
)
from app.schemas.call_center import DialOutboundResponse
from app.services.call_record_service import CallRecordService
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService


logger = logging.getLogger(__name__)


# Carrier-local digit strings and +E.164. Visual separators allowed; caller
# is expected to strip them, but we accept and forward as-is — FlowKit
# normalizes the destination on its side.
_DESTINATION_RE = re.compile(r"^[\d+\-*#\s().]+$")


class OutboundDialService:

    @staticmethod
    async def dial(
        db: AsyncSession,
        telephony: BaseTelephonyClient,
        *,
        tenant_pk: int,
        employee_id: int,
        outbound_phone_number_id: str,
        destination: str,
        r: aioredis.Redis | None = None,
    ) -> DialOutboundResponse:
        dest = destination.strip()
        if not dest or not _DESTINATION_RE.match(dest):
            raise ValidationError("Invalid destination format")

        # Tenant-scoped lookup; SET NULL FK means dropped tenants get filtered.
        tenant = await TenantPhoneNumberRepository.get_tenant(db, tenant_pk)
        if tenant is None:
            raise NotFoundError("Tenant not found")
        row = await TenantPhoneNumberRepository.get_assigned_by_id(
            db, tenant.tenant_id, outbound_phone_number_id
        )
        if row is None:
            raise NotFoundError("Outbound phone number not found")
        call_types = row.call_types if isinstance(row.call_types, list) else []
        if "outbound" not in call_types:
            raise ValidationError("Phone number is not outbound-capable")
        if not row.trunk_id:
            raise ValidationError("Phone number is not bound to a SIP trunk")

        # Resolve the agent's current call device so the media path — and the
        # CDR attribution snapshot — follow the selected device instead of a
        # fixed "not browser → SIP" assumption.
        from app.services.agent_call_device_service import (
            DEVICE_SIP_PHONE,
            DEVICE_WEBRTC,
            AgentCallDeviceService,
        )

        try:
            current_device = await AgentCallDeviceService.get_current_device(
                db, tenant_pk, employee_id
            )
        except Exception:  # noqa: BLE001 — never block a dial on device lookup
            logger.exception("Current-device lookup failed; defaulting to web phone")
            current_device = {}
        device_type = current_device.get("device_type") or DEVICE_WEBRTC
        device_identifier = current_device.get("extension_number")

        # Prefix is a per-DID policy (carrier outbound access code, e.g.
        # "035"). Apply here so FlowKit doesn't need to know about it.
        # Idempotent: don't double-prefix if the user already typed it.
        prefix = (row.called_number_prefix or "").strip()
        dialed = prefix + dest if prefix and not dest.startswith(prefix) else dest

        # SIP-phone agents run a two-stage originate that is entirely event
        # driven: this request rings the agent's registered physical extension
        # and returns immediately, WITHOUT waiting for the phone to go off-hook.
        # The customer is dialed later, off the request path, by the
        # orchestrator's extension-answer handler. This keeps the request from
        # holding a pooled DB connection for the full ring timeout, which would
        # otherwise starve the connection pool under concurrent outbound dials.
        # Web-phone (WebRTC) agents keep the original single-stage path below,
        # fully unchanged.
        if device_type == DEVICE_SIP_PHONE:
            return await OutboundDialService._dial_sip_phone_ringing(
                db,
                telephony,
                tenant_pk=tenant_pk,
                employee_id=employee_id,
                extension_number=device_identifier,
                dialed=dialed,
                destination=dest,
                caller_id=row.phone_number,
                trunk_id=row.trunk_id,
                device_type=device_type,
                device_identifier=device_identifier,
                r=r,
            )

        reservation_id = f"outbound:{uuid.uuid4().hex}"
        if r is not None:
            try:
                await CcAgentStatusService.get_resource_snapshot(
                    db, r, tenant_pk, employee_id
                )
            except Exception:  # noqa: BLE001
                logger.exception("Outbound resource recovery skipped before dial")
            await CcAgentResourceService.reserve_outbound(
                r,
                tenant_pk,
                employee_id,
                reservation_id=reservation_id,
            )

        try:
            result = await telephony.call_originate(
                uri=dialed,
                caller_id=row.phone_number,
                trunk_id=row.trunk_id,
            )
        except TelephonyRPCError as exc:
            if r is not None:
                await CcAgentResourceService.release(
                    r,
                    tenant_pk,
                    employee_id,
                    reason="outbound_failed",
                    expected_call_id=reservation_id,
                )
            # Surface FlowKit's typed errors as 400 so the agent UI can show
            # a precise reason rather than a generic 500.
            logger.warning(
                "call.originate rejected: code=%s msg=%s trunk_id=%s",
                exc.code, exc, row.trunk_id,
            )
            raise ValidationError(str(exc)) from exc
        except Exception:
            if r is not None:
                await CcAgentResourceService.release(
                    r,
                    tenant_pk,
                    employee_id,
                    reason="outbound_failed",
                    expected_call_id=reservation_id,
                )
            raise

        call_id = result.get("call_id")
        if not call_id:
            if r is not None:
                await CcAgentResourceService.release(
                    r,
                    tenant_pk,
                    employee_id,
                    reason="outbound_failed",
                    expected_call_id=reservation_id,
                )
            # Should never happen on a compliant FlowKit response, but
            # surface it loudly if it does.
            raise ValidationError("FlowKit returned no call_id")

        if r is not None:
            await CcAgentResourceService.bind_outbound_call(
                r,
                tenant_pk,
                employee_id,
                reservation_id=reservation_id,
                call_id=call_id,
            )
        try:
            await CcAgentStatusService.sync_pg_status(
                db, tenant_pk, employee_id, "busy", None
            )
        except Exception:  # noqa: BLE001
            logger.exception("Agent status busy sync failed for outbound call_id=%s", call_id)

        # Register so subsequent call.ringing / call.answered / call.hangup
        # FlowKit events get pushed back to this agent's browser.
        from app.services.call_center.orchestrator import get_orchestrator
        orchestrator = get_orchestrator()
        orchestrator.register_outbound_call(
            call_id=call_id,
            tenant_id=tenant_pk,
            employee_id=employee_id,
            outbound_did=row.phone_number,
        )

        # CDR row: created in "ringing" state up-front so the agent's
        # workspace history sees the call immediately. mark_answered fires
        # from orchestrator._on_outbound_answered; mark_completed fires
        # from the shared _on_hangup path (it already lookups by call_id).
        try:
            await CallRecordService.create_for_outbound(
                db, tenant_pk,
                call_id=call_id,
                conversation_id=result.get("conversation_id"),
                root_call_id=result.get("root_call_id") or call_id,
                from_number=row.phone_number,
                to_number=dest,  # what the agent typed; pre-prefix
                agent_id=employee_id,
                device_type=device_type,
                device_identifier=device_identifier,
            )
            await db.commit()
        except Exception:  # noqa: BLE001 — CDR failure must not abort the call
            logger.exception("CDR create_for_outbound failed call_id=%s", call_id)

        logger.info(
            "outbound dial: tenant=%s employee=%s caller=%s -> %s (dialed=%s) "
            "call_id=%s trunk=%s prefix=%s",
            tenant_pk, employee_id, row.phone_number, dest, dialed, call_id,
            row.trunk_id, prefix or "—",
        )
        return DialOutboundResponse(
            call_id=call_id,
            conversation_id=result.get("conversation_id"),
            status=result.get("status", "originating"),
        )

    # ─────────── SIP-phone two-stage (event-driven) fast path ───────────

    # How long the orchestrator waits for the physical phone to go off-hook
    # before aborting. Enforced OFF the request path by the orchestrator's
    # background dial task — the request never waits this long.
    _EXTENSION_ANSWER_TIMEOUT_SEC = 45.0

    @staticmethod
    async def _dial_sip_phone_ringing(
        db: AsyncSession,
        telephony: BaseTelephonyClient,
        *,
        tenant_pk: int,
        employee_id: int,
        extension_number: str | None,
        dialed: str,
        destination: str,
        caller_id: str,
        trunk_id: str,
        device_type: str,
        device_identifier: str | None,
        r: aioredis.Redis | None,
    ) -> DialOutboundResponse:
        """Request-side fast path for a SIP-phone outbound dial.

        Validates the extension, reserves the agent resource, originates the
        agent's physical extension leg, hands the extension-answer wait off to
        the orchestrator, and returns immediately with status
        ``ringing_extension``. The customer is NOT dialed here — that happens
        off the request path once the phone goes off-hook.

        The only long-lived thing the request touches is a short DB read for the
        extension row; the ``db`` session is not held across any long wait, and
        no ``asyncio.wait_for`` on the ring runs in this coroutine. Raises
        ValidationError (→ 400) when the extension is unbound / inactive /
        unregistered (synchronous originate rejection included), or
        NotImplementedApiError (→ 501) when the kernel has extensions disabled —
        in all of these the customer is never dialed.
        """

        from app.services.call_center.orchestrator import (
            SipOutboundDialParams,
            get_orchestrator,
        )

        ext = await SipExtensionRepository.get_by_employee(db, tenant_pk, employee_id)
        if ext is None:
            raise ValidationError("当前坐席未绑定 SIP 分机")
        if not ext.is_active:
            raise ValidationError("SIP 分机已停用")
        if ext.registration_status != "registered":
            raise ValidationError("SIP 分机未注册，请先在话机上注册后重试")

        # Reserve the agent resource up-front so a concurrent dial can't grab
        # the same agent while their phone is ringing. Released by the
        # orchestrator's abort path if the extension never answers.
        reservation_id = f"outbound:{uuid.uuid4().hex}"
        if r is not None:
            try:
                await CcAgentStatusService.get_resource_snapshot(
                    db, r, tenant_pk, employee_id
                )
            except Exception:  # noqa: BLE001
                logger.exception("Outbound resource recovery skipped before dial")
            await CcAgentResourceService.reserve_outbound(
                r, tenant_pk, employee_id, reservation_id=reservation_id,
            )

        try:
            result = await telephony.call_originate(extension=ext.sip_user_id)
        except TelephonyMethodNotFoundError as exc:
            await OutboundDialService._release_reservation(
                r, tenant_pk, employee_id, reservation_id, "sip_extensions_disabled",
            )
            # Kernel deployed without TELECOM_EXTENSIONS_ENABLED — degrade to a
            # clear "not supported" rather than a broken call.
            raise NotImplementedApiError(
                "SIP 话机外呼未在语音内核启用，请切换为 Web 电话或联系管理员"
            ) from exc
        except TelephonyRPCError as exc:
            await OutboundDialService._release_reservation(
                r, tenant_pk, employee_id, reservation_id, "outbound_failed",
            )
            if exc.code == -32602:
                raise ValidationError(
                    "SIP 分机未注册，请先在话机上注册后重试"
                ) from exc
            raise ValidationError(str(exc)) from exc
        except Exception:
            await OutboundDialService._release_reservation(
                r, tenant_pk, employee_id, reservation_id, "outbound_failed",
            )
            raise

        extension_leg_call_id = result.get("call_id")
        if not extension_leg_call_id:
            await OutboundDialService._release_reservation(
                r, tenant_pk, employee_id, reservation_id, "outbound_failed",
            )
            raise ValidationError("语音内核未返回分机呼叫标识")

        # Hand the off-hook wait to the orchestrator; it dials the customer once
        # the phone answers and tears everything down on no-answer/timeout. The
        # request returns here without ever awaiting the ring.
        get_orchestrator().start_sip_outbound_dial(
            extension_leg_call_id=extension_leg_call_id,
            params=SipOutboundDialParams(
                tenant_pk=tenant_pk,
                employee_id=employee_id,
                reservation_id=reservation_id,
                dialed=dialed,
                destination=destination,
                caller_id=caller_id,
                trunk_id=trunk_id,
                device_type=device_type,
                device_identifier=device_identifier,
            ),
            timeout_sec=OutboundDialService._EXTENSION_ANSWER_TIMEOUT_SEC,
        )

        logger.info(
            "sip outbound dial (ringing extension): tenant=%s employee=%s ext=%s "
            "ext_leg=%s -> %s (dialed=%s) trunk=%s",
            tenant_pk, employee_id, ext.sip_user_id, extension_leg_call_id,
            destination, dialed, trunk_id,
        )
        return DialOutboundResponse(
            call_id=extension_leg_call_id,
            conversation_id=None,
            status="ringing_extension",
        )

    @staticmethod
    async def _release_reservation(
        r: aioredis.Redis | None,
        tenant_pk: int,
        employee_id: int,
        reservation_id: str,
        reason: str,
    ) -> None:
        if r is None:
            return
        try:
            await CcAgentResourceService.release(
                r, tenant_pk, employee_id,
                reason=reason, expected_call_id=reservation_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning("outbound reservation release failed", exc_info=True)
