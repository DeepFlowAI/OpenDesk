"""
Agent call-device service — the agent's current call device (Web phone / SIP
phone / future types).

The device model is generic: every option carries device_type / name /
available / unavailable_reason so the workspace never hardcodes
"not browser → SIP". SIP-phone availability is derived from the agent's uniquely
bound, enabled, registered extension.
"""
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationError
from app.models.sip_extension import SipExtension
from app.repositories.agent_call_device_repository import AgentCallDeviceRepository
from app.repositories.sip_extension_repository import SipExtensionRepository
from app.services.cc_agent_resource_service import (
    ACTIVE_RESOURCE_STATES,
    CcAgentResourceService,
)

DEVICE_WEBRTC = "webrtc"
DEVICE_SIP_PHONE = "sip_phone"
# Device types the tenant currently exposes. Mobile is intentionally absent —
# only the extension-backed types are generated this period.
ENABLED_DEVICE_TYPES = (DEVICE_WEBRTC, DEVICE_SIP_PHONE)


class AgentCallDeviceService:
    # ─────────── availability ───────────

    @staticmethod
    def _webrtc_device() -> dict:
        """Web phone is always offered. Fine-grained mic / WebRTC-connection
        availability is browser-local state the client overlays; the server
        marks it available so it can always be chosen once the client confirms
        its local capability."""
        return {
            "device_type": DEVICE_WEBRTC,
            "name": "Web 电话",
            "available": True,
            "unavailable_reason": None,
            "extension_number": None,
            "registration_status": None,
        }

    @staticmethod
    def _sip_device_from_extension(ext: SipExtension | None) -> dict:
        if ext is None:
            return {
                "device_type": DEVICE_SIP_PHONE,
                "name": "SIP 话机",
                "available": False,
                "unavailable_reason": "未绑定 SIP 分机",
                "extension_number": None,
                "registration_status": None,
            }
        name = f"SIP 话机 · 分机 {ext.extension_number}"
        if not ext.is_active:
            return {
                "device_type": DEVICE_SIP_PHONE,
                "name": name,
                "available": False,
                "unavailable_reason": "分机已停用",
                "extension_number": ext.extension_number,
                "registration_status": ext.registration_status,
            }
        if ext.registration_status != "registered":
            return {
                "device_type": DEVICE_SIP_PHONE,
                "name": name,
                "available": False,
                "unavailable_reason": "分机未注册",
                "extension_number": ext.extension_number,
                "registration_status": ext.registration_status,
            }
        return {
            "device_type": DEVICE_SIP_PHONE,
            "name": name,
            "available": True,
            "unavailable_reason": None,
            "extension_number": ext.extension_number,
            "registration_status": ext.registration_status,
        }

    @staticmethod
    async def list_available_devices(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> dict:
        ext = await SipExtensionRepository.get_by_employee(db, tenant_id, employee_id)
        return {
            "items": [
                AgentCallDeviceService._webrtc_device(),
                AgentCallDeviceService._sip_device_from_extension(ext),
            ]
        }

    @staticmethod
    async def _device_view(
        db: AsyncSession, tenant_id: int, employee_id: int, device_type: str
    ) -> dict:
        if device_type == DEVICE_SIP_PHONE:
            ext = await SipExtensionRepository.get_by_employee(
                db, tenant_id, employee_id
            )
            return AgentCallDeviceService._sip_device_from_extension(ext)
        return AgentCallDeviceService._webrtc_device()

    # ─────────── current device ───────────

    @staticmethod
    async def get_current_device(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> dict:
        """Restore the agent's last selection. Returns an empty selection when
        nothing was chosen; keeps a stored selection even if it is currently
        unavailable so the UI can show why (device unavailable) rather than
        silently switching."""
        row = await AgentCallDeviceRepository.get_for_employee(
            db, tenant_id, employee_id
        )
        if row is None:
            return {
                "device_type": None,
                "name": None,
                "available": False,
                "unavailable_reason": None,
                "extension_number": None,
                "registration_status": None,
            }
        return await AgentCallDeviceService._device_view(
            db, tenant_id, employee_id, row.device_type
        )

    @staticmethod
    async def set_current_device(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        device_type: str,
        r: aioredis.Redis | None = None,
    ) -> dict:
        if device_type not in ENABLED_DEVICE_TYPES:
            raise ValidationError("不支持的设备类型")

        # Only switch while idle — reject during ringing / outbound-setup / call.
        if r is not None:
            try:
                snapshot = await CcAgentResourceService.get_snapshot(
                    r, tenant_id, employee_id
                )
            except Exception:  # noqa: BLE001
                snapshot = None
            if snapshot and snapshot.get("resource_state") in ACTIVE_RESOURCE_STATES:
                raise ConflictError("通话结束后可切换设备")

        # The target device must actually be available to be selected.
        view = await AgentCallDeviceService._device_view(
            db, tenant_id, employee_id, device_type
        )
        if not view["available"]:
            raise ConflictError(view.get("unavailable_reason") or "设备不可用")

        await AgentCallDeviceRepository.upsert(
            db, tenant_id, employee_id, device_type
        )
        return view

    # ─────────── readiness guard ───────────

    @staticmethod
    async def ensure_ready_allowed(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> None:
        """Reject a transition to "ready" when the agent has no available
        current device. Enforced server-side so the client cannot bypass it."""
        current = await AgentCallDeviceService.get_current_device(
            db, tenant_id, employee_id
        )
        if not current.get("device_type") or not current.get("available"):
            raise ConflictError("请选择可用的呼叫设备后再进入就绪状态")
