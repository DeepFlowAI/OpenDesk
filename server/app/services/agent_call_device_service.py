"""
Agent call-device service — the agent's current call device (Web phone / SIP
phone / future types).

SIP-phone selection acquires exclusive occupancy on a shared extension via
``SipExtensionOccupancyService``. Switching back to Web phone keeps occupancy
while the agent remains online.
"""
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationError
from app.repositories.agent_call_device_repository import AgentCallDeviceRepository
from app.repositories.sip_extension_repository import SipExtensionRepository
from app.services.cc_agent_resource_service import (
    ACTIVE_RESOURCE_STATES,
    CcAgentResourceService,
)
from app.services.sip_extension_occupancy_service import SipExtensionOccupancyService

DEVICE_WEBRTC = "webrtc"
DEVICE_SIP_PHONE = "sip_phone"
ENABLED_DEVICE_TYPES = (DEVICE_WEBRTC, DEVICE_SIP_PHONE)


class AgentCallDeviceService:
    # ─────────── availability ───────────

    @staticmethod
    def _webrtc_device() -> dict:
        return {
            "device_type": DEVICE_WEBRTC,
            "name": "Web 电话",
            "available": True,
            "unavailable_reason": None,
            "extension_number": None,
            "registration_status": None,
            "status_message": None,
            "current_occupant_employee_id": None,
            "current_occupant_name": None,
            "blocking_agent_name": None,
            "blocking_agent_count": None,
        }

    @staticmethod
    async def list_available_devices(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        r: aioredis.Redis | None = None,
    ) -> dict:
        ext = await SipExtensionRepository.get_by_employee(db, tenant_id, employee_id)
        sip_view = await SipExtensionOccupancyService.describe_sip_availability(
            db, r, tenant_id, employee_id, ext
        )
        return {
            "items": [
                AgentCallDeviceService._webrtc_device(),
                sip_view,
            ]
        }

    @staticmethod
    async def _device_view(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        device_type: str,
        r: aioredis.Redis | None = None,
    ) -> dict:
        if device_type == DEVICE_SIP_PHONE:
            ext = await SipExtensionRepository.get_by_employee(
                db, tenant_id, employee_id
            )
            return await SipExtensionOccupancyService.describe_sip_availability(
                db, r, tenant_id, employee_id, ext
            )
        return AgentCallDeviceService._webrtc_device()

    # ─────────── current device ───────────

    @staticmethod
    async def get_current_device(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        r: aioredis.Redis | None = None,
    ) -> dict:
        """Restore the agent's last selection.

        When a stored SIP selection is no longer held by this agent as
        occupant, clear the stale selection so the workspace asks again.
        """
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
                "status_message": None,
                "current_occupant_employee_id": None,
                "current_occupant_name": None,
                "blocking_agent_name": None,
                "blocking_agent_count": None,
            }

        if row.device_type == DEVICE_SIP_PHONE:
            ext = await SipExtensionRepository.get_by_employee(
                db, tenant_id, employee_id
            )
            # SIP selection is valid only while this agent is the occupant.
            # Occupant None (offline release) or another agent must force re-select.
            if ext is None or ext.current_occupant_employee_id != employee_id:
                await AgentCallDeviceRepository.clear_for_employee(
                    db, tenant_id, employee_id
                )
                view = await SipExtensionOccupancyService.describe_sip_availability(
                    db, r, tenant_id, employee_id, ext
                )
                taken_over = False
                if (
                    ext is not None
                    and ext.current_occupant_employee_id is not None
                    and ext.current_occupant_employee_id != employee_id
                ):
                    taken_over = await SipExtensionOccupancyService.occupant_still_holds(
                        db, r, tenant_id, ext.current_occupant_employee_id
                    )
                reason = (
                    "共享话机已由其他坐席接管，请重新选择呼叫设备"
                    if taken_over
                    else "共享话机占用已释放，请重新选择呼叫设备"
                )
                return {
                    "device_type": None,
                    "name": None,
                    "available": False,
                    "unavailable_reason": reason,
                    "extension_number": view.get("extension_number"),
                    "registration_status": view.get("registration_status"),
                    "status_message": None,
                    "current_occupant_employee_id": view.get(
                        "current_occupant_employee_id"
                    ),
                    "current_occupant_name": view.get("current_occupant_name"),
                    "blocking_agent_name": view.get("blocking_agent_name"),
                    "blocking_agent_count": view.get("blocking_agent_count"),
                }

        return await AgentCallDeviceService._device_view(
            db, tenant_id, employee_id, row.device_type, r
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

        if r is not None:
            try:
                snapshot = await CcAgentResourceService.get_snapshot(
                    r, tenant_id, employee_id
                )
            except Exception:  # noqa: BLE001
                snapshot = None
            if snapshot and snapshot.get("resource_state") in ACTIVE_RESOURCE_STATES:
                raise ConflictError("通话结束后可切换设备")

        acquired_ext = None
        if device_type == DEVICE_SIP_PHONE:
            # Acquire occupancy first; failure keeps the previous device.
            acquired_ext = await SipExtensionOccupancyService.acquire_for_employee(
                db, r, tenant_id, employee_id
            )

        view = await AgentCallDeviceService._device_view(
            db, tenant_id, employee_id, device_type, r
        )
        if not view["available"]:
            # Roll back a just-acquired occupancy if the device view races to unavailable.
            if (
                acquired_ext is not None
                and acquired_ext.current_occupant_employee_id == employee_id
            ):
                await SipExtensionOccupancyService.clear_occupant(db, acquired_ext)
            raise ConflictError(view.get("unavailable_reason") or "设备不可用")

        await AgentCallDeviceRepository.upsert(
            db, tenant_id, employee_id, device_type
        )
        return view

    # ─────────── readiness guard ───────────

    @staticmethod
    async def ensure_ready_allowed(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        r: aioredis.Redis | None = None,
    ) -> None:
        current = await AgentCallDeviceService.get_current_device(
            db, tenant_id, employee_id, r
        )
        if not current.get("device_type") or not current.get("available"):
            raise ConflictError("请选择可用的呼叫设备后再进入就绪状态")

    @staticmethod
    async def resolve_employee_call_endpoint(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        r: aioredis.Redis | None = None,
    ) -> dict:
        """Resolve how to ring an employee for inbound / transfer / consult.

        Returns:
          ``{"kind": "webrtc"}`` or
          ``{"kind": "sip", "extension": sip_user_id, "extension_number": ...}``
          or ``{"kind": "unavailable", "reason": ...}``.
        """
        current = await AgentCallDeviceService.get_current_device(
            db, tenant_id, employee_id, r
        )
        device_type = current.get("device_type")
        if device_type == DEVICE_WEBRTC and current.get("available"):
            return {"kind": "webrtc"}
        if device_type == DEVICE_SIP_PHONE:
            ext = await SipExtensionRepository.get_by_employee(
                db, tenant_id, employee_id
            )
            if ext is None:
                return {"kind": "unavailable", "reason": "未绑定 SIP 分机"}
            if ext.current_occupant_employee_id != employee_id:
                return {
                    "kind": "unavailable",
                    "reason": "目标坐席当前未取得 SIP 话机使用权",
                }
            if not ext.is_active:
                return {"kind": "unavailable", "reason": "分机已停用"}
            if ext.registration_status != "registered":
                return {"kind": "unavailable", "reason": "分机未注册"}
            return {
                "kind": "sip",
                "extension": ext.sip_user_id,
                "extension_number": ext.extension_number,
            }
        reason = current.get("unavailable_reason") or "目标坐席设备不可用"
        return {"kind": "unavailable", "reason": reason}
