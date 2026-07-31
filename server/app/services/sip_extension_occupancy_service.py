"""
Shared SIP extension occupancy — exclusive current-user lock for multi-bound
extensions.

Occupancy is independent of binding (eligibility) and of the agent's chosen
call-center status. Online presence uses ``AgentStatusService.is_connected``
(socket connection + offline grace). Redis unavailability refuses acquire.
"""
from __future__ import annotations

import logging

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.sip_extension import SipExtension
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.sip_extension_repository import SipExtensionRepository
from app.services.agent_status_service import AgentStatusService
from app.services.cc_agent_resource_service import (
    ACTIVE_RESOURCE_STATES,
    CcAgentResourceService,
)

logger = logging.getLogger(__name__)


class SipExtensionOccupancyService:
    @staticmethod
    async def _agent_is_busy(
        r: aioredis.Redis | None, tenant_id: int, employee_id: int
    ) -> bool:
        if r is None:
            return False
        try:
            snapshot = await CcAgentResourceService.get_snapshot(
                r, tenant_id, employee_id
            )
        except Exception:  # noqa: BLE001
            return False
        if snapshot is None:
            return False
        return snapshot.get("resource_state") in ACTIVE_RESOURCE_STATES

    @staticmethod
    async def _agent_is_online(
        r: aioredis.Redis | None, tenant_id: int, employee_id: int
    ) -> bool | None:
        """Return True/False when Redis is usable; None when unknown."""
        if r is None:
            return None
        try:
            return await AgentStatusService.is_connected(r, tenant_id, employee_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to check agent online status employee=%s", employee_id
            )
            return None

    @staticmethod
    async def _employee_display_name(
        db: AsyncSession, employee_id: int
    ) -> str:
        emp = await EmployeeRepository.get_by_id(db, employee_id)
        if emp is None:
            return str(employee_id)
        return emp.display_name or emp.name or emp.username or str(employee_id)

    @classmethod
    async def occupant_still_holds(
        cls,
        db: AsyncSession,
        r: aioredis.Redis | None,
        tenant_id: int,
        occupant_id: int,
    ) -> bool:
        """Whether the current occupant still blocks others from taking over."""
        online = await cls._agent_is_online(r, tenant_id, occupant_id)
        if online is True:
            return True
        if online is None:
            # Cannot confirm offline — keep lock to avoid dual occupancy.
            return True
        # Offline after grace: still holds while a live call is in progress.
        return await cls._agent_is_busy(r, tenant_id, occupant_id)

    @classmethod
    async def list_online_bound_blockers(
        cls,
        db: AsyncSession,
        r: aioredis.Redis | None,
        tenant_id: int,
        extension_id: int,
        exclude_employee_id: int,
    ) -> list[int]:
        """Bound agents (excluding requester) that are currently online."""
        bound_ids = await SipExtensionRepository.list_bound_employee_ids(
            db, extension_id
        )
        blockers: list[int] = []
        for emp_id in bound_ids:
            if emp_id == exclude_employee_id:
                continue
            online = await cls._agent_is_online(r, tenant_id, emp_id)
            if online is None:
                raise ConflictError("暂时无法确认话机占用状态，请稍后重试")
            if online:
                blockers.append(emp_id)
        return blockers

    @classmethod
    async def describe_sip_availability(
        cls,
        db: AsyncSession,
        r: aioredis.Redis | None,
        tenant_id: int,
        employee_id: int,
        ext: SipExtension | None,
    ) -> dict:
        """Build the SIP device view including occupancy status messages."""
        base = {
            "device_type": "sip_phone",
            "name": "SIP 话机",
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
        if ext is None:
            base["unavailable_reason"] = "未绑定 SIP 分机"
            return base

        name = f"SIP 话机 · 分机 {ext.extension_number}"
        base["name"] = name
        base["extension_number"] = ext.extension_number
        base["registration_status"] = ext.registration_status
        base["current_occupant_employee_id"] = ext.current_occupant_employee_id

        if not ext.is_active:
            base["unavailable_reason"] = "分机已停用"
            return base
        if ext.registration_status != "registered":
            base["unavailable_reason"] = "分机未注册"
            return base

        occupant_id = ext.current_occupant_employee_id
        if occupant_id == employee_id:
            base["available"] = True
            base["status_message"] = "当前由你使用"
            base["current_occupant_name"] = await cls._employee_display_name(
                db, employee_id
            )
            return base

        if occupant_id is not None:
            holds = await cls.occupant_still_holds(db, r, tenant_id, occupant_id)
            if holds:
                occupant_name = await cls._employee_display_name(db, occupant_id)
                base["current_occupant_name"] = occupant_name
                base["unavailable_reason"] = f"当前由 {occupant_name} 使用"
                return base
            # Stale occupant — treat as free for availability display; acquire
            # will clear under row lock.

        # No effective occupant: blocked if any other bound agent is online.
        try:
            blockers = await cls.list_online_bound_blockers(
                db, r, tenant_id, ext.id, employee_id
            )
        except ConflictError as exc:
            base["unavailable_reason"] = str(exc.message if hasattr(exc, "message") else exc)
            return base

        if blockers:
            first_name = await cls._employee_display_name(db, blockers[0])
            base["blocking_agent_name"] = first_name
            base["blocking_agent_count"] = len(blockers)
            if len(blockers) == 1:
                base["unavailable_reason"] = (
                    f"{first_name} 在线，暂时无法使用共享话机"
                )
            else:
                base["unavailable_reason"] = (
                    f"{first_name} 等 {len(blockers)} 人在线，暂时无法使用共享话机"
                )
            return base

        base["available"] = True
        return base

    @classmethod
    async def acquire_for_employee(
        cls,
        db: AsyncSession,
        r: aioredis.Redis | None,
        tenant_id: int,
        employee_id: int,
    ) -> SipExtension:
        """Atomically acquire shared-phone occupancy for ``employee_id``.

        Must be called before persisting ``device_type=sip_phone``.
        """
        if r is None:
            raise ConflictError("暂时无法确认话机占用状态，请稍后重试")

        ext = await SipExtensionRepository.get_by_employee_for_update(
            db, tenant_id, employee_id
        )
        if ext is None:
            raise ConflictError("未绑定 SIP 分机")
        if not ext.is_active:
            raise ConflictError("分机已停用")
        if ext.registration_status != "registered":
            raise ConflictError("分机未注册")

        occupant_id = ext.current_occupant_employee_id
        if occupant_id == employee_id:
            return ext

        if occupant_id is not None:
            if await cls.occupant_still_holds(db, r, tenant_id, occupant_id):
                name = await cls._employee_display_name(db, occupant_id)
                raise ConflictError(f"话机已被 {name} 占用")
            # Stale occupant may be overwritten below; do not mutate until
            # blockers are checked so a failed acquire leaves no dirty state.

        blockers = await cls.list_online_bound_blockers(
            db, r, tenant_id, ext.id, employee_id
        )
        if blockers:
            first_name = await cls._employee_display_name(db, blockers[0])
            if len(blockers) == 1:
                raise ConflictError(
                    f"{first_name} 在线，暂时无法使用共享话机"
                )
            raise ConflictError(
                f"{first_name} 等 {len(blockers)} 人在线，暂时无法使用共享话机"
            )

        ext.current_occupant_employee_id = employee_id
        await db.commit()
        await db.refresh(ext)
        return ext

    @classmethod
    async def maybe_release_for_employee(
        cls,
        db: AsyncSession,
        r: aioredis.Redis | None,
        tenant_id: int,
        employee_id: int,
    ) -> SipExtension | None:
        """Release occupancy when the occupant is offline and not in a call.

        Returns the updated extension when released, else None.
        """
        ext = await SipExtensionRepository.get_by_employee_for_update(
            db, tenant_id, employee_id
        )
        if ext is None or ext.current_occupant_employee_id != employee_id:
            return None

        if await cls._agent_is_busy(r, tenant_id, employee_id):
            return None

        online = await cls._agent_is_online(r, tenant_id, employee_id)
        if online is True:
            return None
        if online is None:
            return None

        ext.current_occupant_employee_id = None
        await db.commit()
        await db.refresh(ext)
        logger.info(
            "Released SIP occupancy extension=%s employee=%s",
            ext.extension_number,
            employee_id,
        )
        return ext

    @classmethod
    async def clear_occupant(
        cls,
        db: AsyncSession,
        extension: SipExtension,
        *,
        commit: bool = True,
    ) -> SipExtension:
        extension.current_occupant_employee_id = None
        if commit:
            await db.commit()
            await db.refresh(extension)
        return extension
