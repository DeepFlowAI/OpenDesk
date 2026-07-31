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
from dataclasses import dataclass

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    NotFoundError,
    NotImplementedApiError,
    ValidationError,
)
from app.db.session import AsyncSessionLocal
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


@dataclass(frozen=True)
class _DialContext:
    dest: str
    dialed: str
    caller_id: str
    trunk_id: str
    prefix: str
    device_type: str
    device_identifier: str | None
    sip_user_id: str | None = None


class OutboundDialService:

    @staticmethod
    async def dial_managed(
        telephony: BaseTelephonyClient,
        *,
        tenant_pk: int,
        employee_id: int,
        outbound_phone_number_id: str,
        destination: str,
        r: aioredis.Redis | None = None,
    ) -> DialOutboundResponse:
        """Dial without holding a DB session across FlowKit RPCs (CLAUDE.md §8)."""
        async with AsyncSessionLocal() as db:
            ctx = await OutboundDialService._load_dial_context(
                db,
                tenant_pk=tenant_pk,
                employee_id=employee_id,
                outbound_phone_number_id=outbound_phone_number_id,
                destination=destination,
            )
            if r is not None:
                try:
                    await CcAgentStatusService.get_resource_snapshot(
                        db, r, tenant_pk, employee_id
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("Outbound resource recovery skipped before dial")

        from app.services.agent_call_device_service import DEVICE_SIP_PHONE

        if ctx.device_type == DEVICE_SIP_PHONE:
            return await OutboundDialService._dial_sip_phone_ringing_managed(
                telephony,
                tenant_pk=tenant_pk,
                employee_id=employee_id,
                ctx=ctx,
                r=r,
            )
        return await OutboundDialService._dial_webrtc_managed(
            telephony,
            tenant_pk=tenant_pk,
            employee_id=employee_id,
            ctx=ctx,
            r=r,
        )

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
        """Injected-session entry for unit tests. Production uses ``dial_managed``."""
        ctx = await OutboundDialService._load_dial_context(
            db,
            tenant_pk=tenant_pk,
            employee_id=employee_id,
            outbound_phone_number_id=outbound_phone_number_id,
            destination=destination,
        )
        if r is not None:
            try:
                await CcAgentStatusService.get_resource_snapshot(
                    db, r, tenant_pk, employee_id
                )
            except Exception:  # noqa: BLE001
                logger.exception("Outbound resource recovery skipped before dial")

        from app.services.agent_call_device_service import DEVICE_SIP_PHONE

        if ctx.device_type == DEVICE_SIP_PHONE:
            return await OutboundDialService._dial_sip_phone_ringing_managed(
                telephony,
                tenant_pk=tenant_pk,
                employee_id=employee_id,
                ctx=ctx,
                r=r,
            )
        return await OutboundDialService._dial_webrtc_with_db(
            db,
            telephony,
            tenant_pk=tenant_pk,
            employee_id=employee_id,
            ctx=ctx,
            r=r,
        )

    @staticmethod
    async def _persist_webrtc_outbound(
        db: AsyncSession,
        *,
        tenant_pk: int,
        employee_id: int,
        ctx: _DialContext,
        call_id: str,
        result: dict,
    ) -> None:
        try:
            await CcAgentStatusService.sync_pg_status(
                db, tenant_pk, employee_id, "busy", None
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Agent status busy sync failed for outbound call_id=%s", call_id
            )

        try:
            await CallRecordService.create_for_outbound(
                db, tenant_pk,
                call_id=call_id,
                conversation_id=result.get("conversation_id"),
                root_call_id=result.get("root_call_id") or call_id,
                from_number=ctx.caller_id,
                to_number=ctx.dest,
                agent_id=employee_id,
                device_type=ctx.device_type,
                device_identifier=ctx.device_identifier,
            )
            await db.commit()
        except Exception:  # noqa: BLE001 — CDR failure must not abort the call
            logger.exception("CDR create_for_outbound failed call_id=%s", call_id)

    @staticmethod
    async def _load_dial_context(
        db: AsyncSession,
        *,
        tenant_pk: int,
        employee_id: int,
        outbound_phone_number_id: str,
        destination: str,
    ) -> _DialContext:
        dest = destination.strip()
        if not dest or not _DESTINATION_RE.match(dest):
            raise ValidationError("Invalid destination format")

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

        prefix = (row.called_number_prefix or "").strip()
        dialed = prefix + dest if prefix and not dest.startswith(prefix) else dest

        sip_user_id: str | None = None
        if device_type == DEVICE_SIP_PHONE:
            ext = await SipExtensionRepository.get_by_employee(db, tenant_pk, employee_id)
            if ext is None:
                raise ValidationError("当前坐席未绑定 SIP 分机")
            if ext.current_occupant_employee_id != employee_id:
                raise ValidationError(
                    "你已不是该话机的当前使用人，请重新选择呼叫设备"
                )
            if not ext.is_active:
                raise ValidationError("SIP 分机已停用")
            if ext.registration_status != "registered":
                raise ValidationError("SIP 分机未注册，请先在话机上注册后重试")
            sip_user_id = ext.sip_user_id

        return _DialContext(
            dest=dest,
            dialed=dialed,
            caller_id=row.phone_number,
            trunk_id=row.trunk_id,
            prefix=prefix,
            device_type=device_type,
            device_identifier=device_identifier,
            sip_user_id=sip_user_id,
        )

    @staticmethod
    async def _originate_webrtc(
        telephony: BaseTelephonyClient,
        *,
        tenant_pk: int,
        employee_id: int,
        ctx: _DialContext,
        r: aioredis.Redis | None,
    ) -> tuple[str, dict]:
        reservation_id = f"outbound:{uuid.uuid4().hex}"
        if r is not None:
            await CcAgentResourceService.reserve_outbound(
                r,
                tenant_pk,
                employee_id,
                reservation_id=reservation_id,
            )

        try:
            result = await telephony.call_originate(
                uri=ctx.dialed,
                caller_id=ctx.caller_id,
                trunk_id=ctx.trunk_id,
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
            logger.warning(
                "call.originate rejected: code=%s msg=%s trunk_id=%s",
                exc.code, exc, ctx.trunk_id,
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
            raise ValidationError("FlowKit returned no call_id")

        # Register before any further await: carrier rejects often arrive in
        # <50ms and must still resolve to this agent for cc.outbound_hangup /
        # dial-webrtc 410.
        from app.services.call_center.orchestrator import get_orchestrator
        await get_orchestrator().register_outbound_call(
            call_id=call_id,
            tenant_id=tenant_pk,
            employee_id=employee_id,
            outbound_did=ctx.caller_id,
        )

        if r is not None:
            await CcAgentResourceService.bind_outbound_call(
                r,
                tenant_pk,
                employee_id,
                reservation_id=reservation_id,
                call_id=call_id,
            )
        return call_id, result

    @staticmethod
    async def _dial_webrtc_managed(
        telephony: BaseTelephonyClient,
        *,
        tenant_pk: int,
        employee_id: int,
        ctx: _DialContext,
        r: aioredis.Redis | None,
    ) -> DialOutboundResponse:
        call_id, result = await OutboundDialService._originate_webrtc(
            telephony,
            tenant_pk=tenant_pk,
            employee_id=employee_id,
            ctx=ctx,
            r=r,
        )
        async with AsyncSessionLocal() as db:
            await OutboundDialService._persist_webrtc_outbound(
                db,
                tenant_pk=tenant_pk,
                employee_id=employee_id,
                ctx=ctx,
                call_id=call_id,
                result=result,
            )
        logger.info(
            "outbound dial: tenant=%s employee=%s caller=%s -> %s (dialed=%s) "
            "call_id=%s trunk=%s prefix=%s",
            tenant_pk, employee_id, ctx.caller_id, ctx.dest, ctx.dialed, call_id,
            ctx.trunk_id, ctx.prefix or "—",
        )
        return DialOutboundResponse(
            call_id=call_id,
            conversation_id=result.get("conversation_id"),
            status=result.get("status", "originating"),
        )

    @staticmethod
    async def _dial_webrtc_with_db(
        db: AsyncSession,
        telephony: BaseTelephonyClient,
        *,
        tenant_pk: int,
        employee_id: int,
        ctx: _DialContext,
        r: aioredis.Redis | None,
    ) -> DialOutboundResponse:
        """WebRTC dial using an injected session for post-RPC persistence (tests)."""
        call_id, result = await OutboundDialService._originate_webrtc(
            telephony,
            tenant_pk=tenant_pk,
            employee_id=employee_id,
            ctx=ctx,
            r=r,
        )
        await OutboundDialService._persist_webrtc_outbound(
            db,
            tenant_pk=tenant_pk,
            employee_id=employee_id,
            ctx=ctx,
            call_id=call_id,
            result=result,
        )
        logger.info(
            "outbound dial: tenant=%s employee=%s caller=%s -> %s (dialed=%s) "
            "call_id=%s trunk=%s prefix=%s",
            tenant_pk, employee_id, ctx.caller_id, ctx.dest, ctx.dialed, call_id,
            ctx.trunk_id, ctx.prefix or "—",
        )
        return DialOutboundResponse(
            call_id=call_id,
            conversation_id=result.get("conversation_id"),
            status=result.get("status", "originating"),
        )

    @staticmethod
    async def _dial_sip_phone_ringing_managed(
        telephony: BaseTelephonyClient,
        *,
        tenant_pk: int,
        employee_id: int,
        ctx: _DialContext,
        r: aioredis.Redis | None,
    ) -> DialOutboundResponse:
        """SIP-phone fast path with no DB session across call.originate."""
        assert ctx.sip_user_id is not None

        from app.services.call_center.orchestrator import (
            SipOutboundDialParams,
            get_orchestrator,
        )

        reservation_id = f"outbound:{uuid.uuid4().hex}"
        if r is not None:
            await CcAgentResourceService.reserve_outbound(
                r, tenant_pk, employee_id, reservation_id=reservation_id,
            )

        try:
            result = await telephony.call_originate(extension=ctx.sip_user_id)
        except TelephonyMethodNotFoundError as exc:
            await OutboundDialService._release_reservation(
                r, tenant_pk, employee_id, reservation_id, "sip_extensions_disabled",
            )
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

        get_orchestrator().start_sip_outbound_dial(
            extension_leg_call_id=extension_leg_call_id,
            params=SipOutboundDialParams(
                tenant_pk=tenant_pk,
                employee_id=employee_id,
                reservation_id=reservation_id,
                dialed=ctx.dialed,
                destination=ctx.dest,
                caller_id=ctx.caller_id,
                trunk_id=ctx.trunk_id,
                device_type=ctx.device_type,
                device_identifier=ctx.device_identifier,
            ),
            timeout_sec=OutboundDialService._EXTENSION_ANSWER_TIMEOUT_SEC,
        )

        logger.info(
            "sip outbound dial (ringing extension): tenant=%s employee=%s ext=%s "
            "ext_leg=%s -> %s (dialed=%s) trunk=%s",
            tenant_pk, employee_id, ctx.sip_user_id, extension_leg_call_id,
            ctx.dest, ctx.dialed, ctx.trunk_id,
        )
        return DialOutboundResponse(
            call_id=extension_leg_call_id,
            conversation_id=None,
            status="ringing_extension",
        )

    # How long the orchestrator waits for the physical phone to go off-hook
    # before aborting. Enforced OFF the request path by the orchestrator's
    # background dial task — the request never waits this long.
    _EXTENSION_ANSWER_TIMEOUT_SEC = 45.0

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
