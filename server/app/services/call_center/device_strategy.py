"""
Device strategy — SIP desk-phone vs WebRTC browser seat.

Call-control / media-reconnect paths branch on device type. Keep those
rules here instead of scattering ``if device_type == "sip_phone"`` checks.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.agent_call_device_service import DEVICE_SIP_PHONE, DEVICE_WEBRTC


@dataclass(frozen=True)
class DeviceStrategy:
    """Capability flags for the agent's current call device."""

    device_type: str

    @property
    def is_sip_phone(self) -> bool:
        return self.device_type == DEVICE_SIP_PHONE

    @property
    def is_webrtc(self) -> bool:
        return self.device_type == DEVICE_WEBRTC

    def browser_owns_media(self) -> bool:
        """True when the browser WebRTC peer is the agent's media path."""
        return not self.is_sip_phone

    def should_request_browser_media_reconnect(self) -> bool:
        """SIP handset media must not be stolen by a browser rebuild."""
        return self.browser_owns_media()

    def browser_accepts_offers(self) -> bool:
        """SIP rings/answers on the handset — no browser Accept click."""
        return self.browser_owns_media()


def strategy_for_device_type(device_type: str | None) -> DeviceStrategy:
    """Build a strategy from a device_type string (defaults to WebRTC)."""
    if device_type == DEVICE_SIP_PHONE:
        return DeviceStrategy(device_type=DEVICE_SIP_PHONE)
    return DeviceStrategy(device_type=device_type or DEVICE_WEBRTC)


async def resolve_agent_strategy(
    tenant_id: int, employee_id: int
) -> DeviceStrategy:
    """Load the agent's current device and return its strategy."""
    from app.db.redis import redis_client
    from app.db.session import AsyncSessionLocal
    from app.services.agent_call_device_service import AgentCallDeviceService

    try:
        async with AsyncSessionLocal() as db:
            current = await AgentCallDeviceService.get_current_device(
                db, tenant_id, employee_id, redis_client.client
            )
    except Exception:  # noqa: BLE001
        return strategy_for_device_type(DEVICE_WEBRTC)
    return strategy_for_device_type((current or {}).get("device_type"))
