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

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.telephony import BaseTelephonyClient
from app.libs.telephony.base import TelephonyRPCError
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

        # Prefix is a per-DID policy (carrier outbound access code, e.g.
        # "035"). Apply here so FlowKit doesn't need to know about it.
        # Idempotent: don't double-prefix if the user already typed it.
        prefix = (row.called_number_prefix or "").strip()
        dialed = prefix + dest if prefix and not dest.startswith(prefix) else dest

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
        get_orchestrator().register_outbound_call(
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
