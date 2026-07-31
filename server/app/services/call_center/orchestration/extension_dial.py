"""Outbound calls an agent places by dialling on their desk phone.

The workstation dials by asking the kernel to ring the agent first and calling
the customer once they pick up. Dialling on the handset inverts that: the agent
is already off-hook and the kernel reports their call as an incoming leg, so all
that is left is to place the customer leg and let the two be bridged.
"""
from __future__ import annotations

import base64
import io
import logging
import math
import struct
import uuid
import wave
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.sip_extension import SipExtension

logger = logging.getLogger(__name__)

# Ringback cadence used on Chinese networks: a 450 Hz tone for one second,
# then four seconds of silence.
_RINGBACK_HZ = 450.0
_RINGBACK_TONE_MS = 1000
_RINGBACK_GAP_MS = 4000


@lru_cache(maxsize=1)
def _ringback_wav_b64() -> str:
    """One second of ringback tone as base64 WAV.

    The kernel answers the handset the moment the agent lifts it, but the
    customer may then ring for ten seconds or more. Without this the agent
    holds a connected-but-silent line: no indication the call is being placed,
    and no way to tell when the customer picks up.

    Generated in-process rather than shipped as an audio asset so it works on
    the first call after deploy, with nothing to upload and no tenant setting
    to switch on.
    """

    rate = 16000
    total = rate * _RINGBACK_TONE_MS // 1000
    # Ramp the first and last few milliseconds: an abruptly truncated sine
    # clicks each time the loop restarts.
    ramp = rate // 100
    frames = bytearray()
    for i in range(total):
        gain = 0.3
        if i < ramp:
            gain *= i / ramp
        elif i >= total - ramp:
            gain *= (total - i) / ramp
        frames += struct.pack(
            "<h", int(gain * 32767 * math.sin(2 * math.pi * _RINGBACK_HZ * i / rate))
        )

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(frames))
    return base64.b64encode(buf.getvalue()).decode()


class ExtensionDialMixin:

    async def handle_extension_dialed_out(
        self,
        *,
        handset_call_id: str,
        caller_extension: str,
        dialed: str,
    ) -> None:
        """Place the call an agent dialled on their desk phone.

        `caller_extension` is the SIP identity the kernel verified the call came
        from, and `dialed` is the number the agent keyed in. Any failure hangs
        the handset up: leaving it connected to nothing sounds like the system
        answered and then went silent.
        """

        ext = await self._load_dialling_extension(caller_extension)
        if ext is None:
            await self._reject_handset(handset_call_id, "unknown_extension")
            return
        employee_id = ext.current_occupant_employee_id
        if employee_id is None:
            logger.warning(
                "extension dial: %s has no current occupant; hanging up call_id=%s",
                caller_extension, handset_call_id,
            )
            await self._reject_handset(handset_call_id, "extension_unoccupied")
            return

        outbound = await self._resolve_outbound_did(ext.tenant_id)
        if outbound is None:
            logger.warning(
                "extension dial: tenant id=%s has no outbound-capable number; "
                "hanging up call_id=%s", ext.tenant_id, handset_call_id,
            )
            await self._reject_handset(handset_call_id, "no_outbound_number")
            return
        caller_id, trunk_id, prefix = outbound

        from app.services.agent_call_device_service import DEVICE_SIP_PHONE

        params = _orch.SipOutboundDialParams(
            tenant_pk=ext.tenant_id,
            employee_id=employee_id,
            reservation_id=f"outbound:{uuid.uuid4().hex}",
            dialed=prefix + dialed if prefix and not dialed.startswith(prefix) else dialed,
            destination=dialed,
            caller_id=caller_id,
            trunk_id=trunk_id,
            device_type=DEVICE_SIP_PHONE,
            device_identifier=ext.extension_number,
        )

        redis = _orch._get_redis_client()
        if redis is not None:
            from app.core.exceptions import ConflictError

            try:
                await _orch.CcAgentResourceService.reserve_outbound(
                    redis,
                    params.tenant_pk,
                    params.employee_id,
                    reservation_id=params.reservation_id,
                )
            except ConflictError:
                # Already on a call. The workstation dial refuses this too; the
                # handset just has no dialog to refuse it in, so it hangs up.
                logger.warning(
                    "extension dial: employee_id=%s already occupied; "
                    "hanging up call_id=%s", params.employee_id, handset_call_id,
                )
                await self._reject_handset(handset_call_id, "agent_busy")
                return
            except Exception:  # noqa: BLE001 — never block a dial on bookkeeping
                logger.exception(
                    "extension dial: reserve_outbound failed employee_id=%s",
                    params.employee_id,
                )

        logger.info(
            "extension dial: ext=%s employee_id=%s dialing=%s caller_id=%s "
            "trunk_id=%s handset_leg=%s",
            caller_extension, params.employee_id, params.dialed,
            params.caller_id, params.trunk_id, handset_call_id,
        )
        await self._start_handset_ringback(handset_call_id)
        # From here the handset leg plays the part the ringing extension plays in
        # a workstation dial: originate the customer, pair the two, and the
        # answered handler bridges them.
        await self._originate_sip_outbound_customer(handset_call_id, params)

    async def _start_handset_ringback(self, call_id: str) -> None:
        """Give the agent something to listen to while the customer rings.

        Stopped by the answered handler just before the legs are joined. Purely
        cosmetic, so a failure here is logged and the dial continues — a silent
        wait is worse than no call.
        """

        try:
            await self.telephony.call_play(
                call_id,
                audio=_ringback_wav_b64(),
                loop=True,
                interval_ms=_RINGBACK_GAP_MS,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "extension dial: ringback failed call_id=%s", call_id, exc_info=True,
            )

    # ─────────────────────────── lookups ───────────────────────────

    async def _load_dialling_extension(self, sip_user_id: str) -> "SipExtension | None":
        from app.repositories.sip_extension_repository import SipExtensionRepository

        try:
            async with _orch.AsyncSessionLocal() as db:
                ext = await SipExtensionRepository.get_by_sip_user_id(db, sip_user_id)
        except Exception:  # noqa: BLE001
            logger.exception("extension dial: lookup failed sip_user_id=%s", sip_user_id)
            return None
        if ext is None:
            logger.warning("extension dial: no extension for sip_user_id=%s", sip_user_id)
            return None
        if not ext.is_active:
            logger.warning("extension dial: extension %s is disabled", ext.extension_number)
            return None
        return ext

    async def _resolve_outbound_did(
        self, tenant_pk: int
    ) -> tuple[str, str, str] | None:
        """The tenant's default outbound number as (caller_id, trunk_id, prefix).

        A handset has no way to offer the agent a choice of caller ID, so it
        gets the same first outbound-capable number that transfers and consults
        to external numbers already use.
        """

        from app.repositories.tenant_phone_number_repository import (
            TenantPhoneNumberRepository,
        )

        try:
            async with _orch.AsyncSessionLocal() as db:
                tenant = await TenantPhoneNumberRepository.get_tenant(db, tenant_pk)
                if tenant is None:
                    return None
                dids = await TenantPhoneNumberRepository.list_assigned(
                    db, tenant.tenant_id, limit=50
                )
        except Exception:  # noqa: BLE001
            logger.exception("extension dial: DID lookup failed tenant_pk=%s", tenant_pk)
            return None

        did = next(
            (
                d for d in dids
                if isinstance(d.call_types, list)
                and "outbound" in d.call_types
                and d.trunk_id
            ),
            None,
        )
        if did is None:
            return None
        return did.phone_number, did.trunk_id, (did.called_number_prefix or "").strip()

    async def _reject_handset(self, call_id: str, reason: str) -> None:
        try:
            await self.telephony.call_hangup(call_id, reason=reason)
        except Exception:  # noqa: BLE001
            logger.exception("extension dial: hangup failed call_id=%s", call_id)


# Imported after the mixin class so this module can be imported directly
# without a circular-import error (orchestrator imports the mixins).
from app.services.call_center import orchestrator as _orch  # noqa: E402
