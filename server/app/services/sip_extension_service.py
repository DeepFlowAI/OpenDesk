"""
SIP extension service — tenant-admin management of SIP extensions and their
unique binding to an agent.

Credential handling mirrors the API-key one-time-secret pattern: the plaintext
password is generated, hashed for storage and shown to the admin exactly once
(on create / reset). Only a hash + a masked form are persisted.
"""
import hashlib
import hmac
import secrets

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.sip_extension import SipExtension
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.sip_extension_repository import SipExtensionRepository
from app.schemas.permission import EffectivePrincipal
from app.schemas.sip_extension import (
    SipExtensionCreate,
    SipExtensionUpdate,
    SipRegistrationInfo,
)
from app.services.cc_agent_resource_service import (
    ACTIVE_RESOURCE_STATES,
    CcAgentResourceService,
)

# Permission an agent must hold to be bindable / to use a SIP phone.
WORKSPACE_PERMISSION = "call.workspace.use"

PASSWORD_BYTES = 18
MAX_GENERATION_ATTEMPTS = 10


class SipExtensionService:
    # ─────────── credential helpers ───────────

    @staticmethod
    def _generate_password() -> str:
        return secrets.token_urlsafe(PASSWORD_BYTES)

    @staticmethod
    def hash_password(password: str) -> str:
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            password.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def mask_password(password: str) -> str:
        return f"{password[:4]}********"

    @staticmethod
    async def _generate_unique_sip_user_id(
        db: AsyncSession, tenant_slug: str, extension_number: str
    ) -> str:
        """Registration-domain-unique SIP user id: ``<tenant>-<number>``.

        Falls back to a random suffix on the (rare) collision so a re-created
        number in another tenant slug cannot clash.
        """
        base = f"{tenant_slug}-{extension_number}"
        candidate = base
        for attempt in range(MAX_GENERATION_ATTEMPTS):
            existing = await SipExtensionRepository.get_by_sip_user_id(db, candidate)
            if existing is None:
                return candidate
            candidate = f"{base}-{secrets.token_hex(3)}"
        raise RuntimeError("Failed to generate a unique SIP user id")

    @staticmethod
    async def _resolve_registrar_endpoint() -> tuple[str, int | None, str]:
        """Registrar endpoint shown to admins: (host, port, transport).

        Prefers the live endpoint reported by the media kernel
        (``system.registrar_info``) so the admin sees the real address a phone
        must register against. Falls back to the deployment settings when the
        kernel is unreachable, has extensions disabled, or returns nothing —
        and finally to empty strings so operators know to fill them in.
        """
        from app.libs.telephony import (
            TelephonyError,
            get_telephony_client,
        )

        try:
            info = await get_telephony_client().registrar_info()
        except TelephonyError:
            info = None
        except Exception:  # noqa: BLE001 — never fail admin read on kernel issues
            info = None
        if info:
            host = info.get("host") or settings.SIP_REGISTRAR_HOST
            port = info.get("port")
            if port is None:
                port = settings.SIP_REGISTRAR_PORT
            transport = info.get("transport") or settings.SIP_REGISTRAR_TRANSPORT
            return host or "", port, transport or ""
        return (
            settings.SIP_REGISTRAR_HOST,
            settings.SIP_REGISTRAR_PORT,
            settings.SIP_REGISTRAR_TRANSPORT,
        )

    @staticmethod
    async def _registration_info(
        record: SipExtension, plaintext_password: str | None
    ) -> SipRegistrationInfo:
        """Assemble the registration info block.

        Endpoint fields prefer the kernel's live registrar over deployment
        settings; when neither is available they are returned empty so
        operators fill them from their own deployment rather than seeing a
        guessed value.
        """
        host, port, transport = await SipExtensionService._resolve_registrar_endpoint()
        return SipRegistrationInfo(
            registration_server=host,
            registration_port=port,
            transport=transport,
            sip_user_id=record.sip_user_id,
            auth_account=record.auth_account,
            auth_password=plaintext_password,
            auth_password_masked=record.auth_password_masked,
            registration_status=record.registration_status,
        )

    # ─────────── busy-state guard ───────────

    @staticmethod
    async def _agent_is_busy(
        r: aioredis.Redis | None, tenant_id: int, employee_id: int
    ) -> bool:
        """Whether the agent is ringing / establishing outbound / in a call.

        Uses the Redis resource snapshot (reserved / ringing / in_call). When
        Redis is unavailable we cannot prove the agent is idle, so we treat the
        state as unknown-but-safe (not busy) — the destructive-op guard is a
        best-effort protection, and FlowKit itself rejects mid-call teardown.
        """
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

    @classmethod
    async def _ensure_bound_agent_idle(
        cls,
        r: aioredis.Redis | None,
        tenant_id: int,
        item: SipExtension,
    ) -> None:
        """Reject destructive ops while the bound agent is on / setting up a call."""
        if item.bound_employee_id is None:
            return
        if await cls._agent_is_busy(r, tenant_id, item.bound_employee_id):
            raise ConflictError(
                "该坐席正在使用此分机通话，请在通话结束后重试"
            )

    # ─────────── binding validation ───────────

    @staticmethod
    async def _validate_binding_target(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        current_extension_id: int | None,
    ) -> None:
        """Ensure the target employee may be bound to this extension.

        - employee must be active + hold ``call.workspace.use`` effectively
        - employee must not already be bound to a different extension
        """
        employee = await EmployeeRepository.get_by_id(db, employee_id)
        if employee is None or employee.tenant_id != tenant_id or not employee.is_active:
            raise ValidationError("坐席不存在或已停用")
        has_perm = await EmployeeRepository.has_effective_permission(
            db, tenant_id, employee_id, WORKSPACE_PERMISSION
        )
        if not has_perm:
            raise ValidationError("该坐席没有呼叫中心工作台权限")
        existing = await SipExtensionRepository.get_by_employee(
            db, tenant_id, employee_id
        )
        if existing is not None and existing.id != current_extension_id:
            raise ConflictError(
                f"该坐席已绑定分机 {existing.extension_number}"
            )

    # ─────────── list ───────────

    @staticmethod
    async def list_paginated(
        db: AsyncSession,
        principal: EffectivePrincipal,
        page: int,
        per_page: int,
        keyword: str | None,
        registration_status: str | None,
        active_status: str | None,
    ) -> dict:
        reg = registration_status if registration_status in {"registered", "unregistered"} else None
        act = active_status if active_status in {"active", "inactive"} else None
        items, total = await SipExtensionRepository.get_paginated(
            db, principal.tenant_id, page, per_page, keyword, reg, act
        )
        await SipExtensionService._attach_bound_employees(db, items)
        pages = (total + per_page - 1) // per_page if per_page else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def _attach_bound_employees(
        db: AsyncSession, items: list[SipExtension]
    ) -> None:
        """Attach a ``bound_employee`` brief to each row for serialization."""
        emp_ids = [i.bound_employee_id for i in items if i.bound_employee_id]
        if not emp_ids:
            for i in items:
                i.bound_employee = None
            return
        employees = await EmployeeRepository.get_by_ids(db, list(set(emp_ids)))
        by_id = {e.id: e for e in employees}
        for i in items:
            emp = by_id.get(i.bound_employee_id) if i.bound_employee_id else None
            if emp is not None:
                i.bound_employee = {
                    "id": emp.id,
                    "name": emp.display_name or emp.name or emp.username,
                    "avatar": emp.avatar,
                }
            else:
                i.bound_employee = None

    # ─────────── create ───────────

    @staticmethod
    async def create(
        db: AsyncSession,
        principal: EffectivePrincipal,
        data: SipExtensionCreate,
    ) -> dict:
        tenant_id = principal.tenant_id
        existing = await SipExtensionRepository.get_by_extension_number(
            db, tenant_id, data.extension_number
        )
        if existing is not None:
            raise ConflictError("该分机号已存在")

        if data.bound_employee_id is not None:
            await SipExtensionService._validate_binding_target(
                db, tenant_id, data.bound_employee_id, None
            )

        tenant_slug = (
            await SipExtensionRepository.get_tenant_slug(db, tenant_id)
        ) or str(tenant_id)
        sip_user_id = await SipExtensionService._generate_unique_sip_user_id(
            db, tenant_slug, data.extension_number
        )
        password = SipExtensionService._generate_password()

        record = await SipExtensionRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "name": data.name,
                "extension_number": data.extension_number,
                "sip_user_id": sip_user_id,
                "auth_account": sip_user_id,  # same value this period
                "auth_password_hash": SipExtensionService.hash_password(password),
                "auth_password_masked": SipExtensionService.mask_password(password),
                "bound_employee_id": data.bound_employee_id,
                "created_by_actor_type": "employee",
                "created_by_actor_id": principal.user_id,
            },
        )
        await SipExtensionService._attach_bound_employees(db, [record])
        return {
            "record": record,
            "registration_info": await SipExtensionService._registration_info(
                record, password
            ),
        }

    # ─────────── get scoped ───────────

    @staticmethod
    async def get_scoped(
        db: AsyncSession, principal: EffectivePrincipal, extension_id: int
    ) -> SipExtension:
        item = await SipExtensionRepository.get_scoped(
            db, principal.tenant_id, extension_id
        )
        if item is None:
            raise NotFoundError("SIP extension not found")
        return item

    # ─────────── update (name / binding) ───────────

    @staticmethod
    async def update(
        db: AsyncSession,
        principal: EffectivePrincipal,
        extension_id: int,
        data: SipExtensionUpdate,
        fields_set: set[str],
        r: aioredis.Redis | None = None,
    ) -> SipExtension:
        tenant_id = principal.tenant_id
        item = await SipExtensionService.get_scoped(db, principal, extension_id)

        updates: dict = {}
        if "name" in fields_set and data.name is not None:
            updates["name"] = data.name

        if "bound_employee_id" in fields_set:
            new_binding = data.bound_employee_id
            current_binding = item.bound_employee_id
            if new_binding != current_binding:
                # Changing/removing a binding on a busy agent is forbidden.
                await SipExtensionService._ensure_bound_agent_idle(r, tenant_id, item)
                if new_binding is not None:
                    # Cannot silently overwrite an extension already bound to
                    # a *different* agent — that is the current row itself, so
                    # the check is really "is the new agent free?".
                    await SipExtensionService._validate_binding_target(
                        db, tenant_id, new_binding, item.id
                    )
                    # If the new agent is themselves busy, block the rebind.
                    if await SipExtensionService._agent_is_busy(r, tenant_id, new_binding):
                        raise ConflictError(
                            "该坐席正在使用此分机通话，请在通话结束后重试"
                        )
                updates["bound_employee_id"] = new_binding
                # Unbinding clears the (now-orphaned) agent's device selection
                # so they are prompted to pick a new device.
                if new_binding is None and current_binding is not None:
                    await SipExtensionService._clear_agent_sip_device(
                        db, tenant_id, current_binding
                    )

        if not updates:
            await SipExtensionService._attach_bound_employees(db, [item])
            return item

        updates["updated_by_actor_type"] = "employee"
        updates["updated_by_actor_id"] = principal.user_id
        record = await SipExtensionRepository.update(db, item, updates)
        await SipExtensionService._attach_bound_employees(db, [record])
        return record

    @staticmethod
    async def _clear_agent_sip_device(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> None:
        """Drop the agent's persisted device selection if it was sip_phone."""
        from app.repositories.agent_call_device_repository import (
            AgentCallDeviceRepository,
        )

        row = await AgentCallDeviceRepository.get_for_employee(
            db, tenant_id, employee_id
        )
        if row is not None and row.device_type == "sip_phone":
            await AgentCallDeviceRepository.clear_for_employee(
                db, tenant_id, employee_id
            )

    # ─────────── reset password ───────────

    @staticmethod
    async def reset_password(
        db: AsyncSession,
        principal: EffectivePrincipal,
        extension_id: int,
        r: aioredis.Redis | None = None,
    ) -> dict:
        tenant_id = principal.tenant_id
        item = await SipExtensionService.get_scoped(db, principal, extension_id)
        # Resetting mid-call would drop the live registration — block it.
        await SipExtensionService._ensure_bound_agent_idle(r, tenant_id, item)

        password = SipExtensionService._generate_password()
        record = await SipExtensionRepository.update(
            db,
            item,
            {
                "auth_password_hash": SipExtensionService.hash_password(password),
                "auth_password_masked": SipExtensionService.mask_password(password),
                # Old credentials are dead; the phone must re-register.
                "registration_status": "unregistered",
                "last_registered_at": None,
                "updated_by_actor_type": "employee",
                "updated_by_actor_id": principal.user_id,
            },
        )
        await SipExtensionService._attach_bound_employees(db, [record])
        return {
            "record": record,
            "registration_info": await SipExtensionService._registration_info(
                record, password
            ),
        }

    # ─────────── copy registration info (masked) ───────────

    @staticmethod
    async def get_registration_info(
        db: AsyncSession, principal: EffectivePrincipal, extension_id: int
    ) -> SipRegistrationInfo:
        item = await SipExtensionService.get_scoped(db, principal, extension_id)
        # No plaintext — copy shows the masked password only.
        return await SipExtensionService._registration_info(item, None)

    # ─────────── enable / disable ───────────

    @staticmethod
    async def disable(
        db: AsyncSession,
        principal: EffectivePrincipal,
        extension_id: int,
        r: aioredis.Redis | None = None,
    ) -> SipExtension:
        from datetime import datetime, timezone

        tenant_id = principal.tenant_id
        item = await SipExtensionService.get_scoped(db, principal, extension_id)
        if not item.is_active:
            await SipExtensionService._attach_bound_employees(db, [item])
            return item
        # Cannot disable while the bound agent is ringing / in a call, or while
        # it is actively selected as their current device.
        await SipExtensionService._ensure_bound_agent_idle(r, tenant_id, item)
        if item.bound_employee_id is not None:
            await SipExtensionService._reject_if_current_sip_device(
                db, tenant_id, item.bound_employee_id
            )
        record = await SipExtensionRepository.update(
            db,
            item,
            {
                "is_active": False,
                "disabled_at": datetime.now(timezone.utc),
                "updated_by_actor_type": "employee",
                "updated_by_actor_id": principal.user_id,
            },
        )
        # A disabled extension can no longer serve as anyone's device.
        if record.bound_employee_id is not None:
            await SipExtensionService._clear_agent_sip_device(
                db, tenant_id, record.bound_employee_id
            )
        await SipExtensionService._attach_bound_employees(db, [record])
        return record

    @staticmethod
    async def _reject_if_current_sip_device(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> None:
        from app.repositories.agent_call_device_repository import (
            AgentCallDeviceRepository,
        )

        row = await AgentCallDeviceRepository.get_for_employee(
            db, tenant_id, employee_id
        )
        if row is not None and row.device_type == "sip_phone":
            raise ConflictError(
                "该分机正被坐席用作当前呼叫设备，请先让坐席切换设备后重试"
            )

    @staticmethod
    async def enable(
        db: AsyncSession, principal: EffectivePrincipal, extension_id: int
    ) -> SipExtension:
        item = await SipExtensionService.get_scoped(db, principal, extension_id)
        if item.is_active:
            await SipExtensionService._attach_bound_employees(db, [item])
            return item
        record = await SipExtensionRepository.update(
            db,
            item,
            {
                "is_active": True,
                "disabled_at": None,
                "updated_by_actor_type": "employee",
                "updated_by_actor_id": principal.user_id,
            },
        )
        await SipExtensionService._attach_bound_employees(db, [record])
        return record

    # ─────────── registration status writeback (kernel events) ───────────

    @staticmethod
    async def apply_registration_event(
        db: AsyncSession,
        *,
        sip_user_id: str,
        registered: bool,
    ) -> SipExtension | None:
        """Reflect a kernel ``extension.registered/unregistered`` event.

        Matches the extension by its registration-domain-unique ``sip_user_id``
        (the AOR user-part) and flips ``registration_status`` accordingly. The
        caller is expected to pass a fresh short-lived session and to have
        re-fetched nothing itself — this method does its own lookup by id so no
        detached ORM object is reused across sessions. Returns the updated row,
        or None when no extension matches (foreign registration / unknown AOR).
        """
        from datetime import datetime, timezone

        record = await SipExtensionRepository.get_by_sip_user_id(db, sip_user_id)
        if record is None:
            return None
        updates: dict = {
            "registration_status": "registered" if registered else "unregistered",
        }
        if registered:
            updates["last_registered_at"] = datetime.now(timezone.utc)
        return await SipExtensionRepository.update(db, record, updates)

    @staticmethod
    async def reconcile_registrations(
        db: AsyncSession, live_sip_user_ids: set[str]
    ) -> list[SipExtension]:
        """Flip to ``unregistered`` any extension the DB believes is registered
        but that the kernel no longer knows about.

        A kernel restart clears its in-memory registrar without emitting a
        per-AOR ``extension.unregistered`` event, leaving the DB (and the
        agent's heartbeat dot) stale-green. On WS reconnect we pass the kernel's
        live AOR set here; a brief WS blip that left the registrar intact returns
        the full set, so nothing is flipped. Returns the rows flipped so the
        caller can notify the bound agents.
        """
        from sqlalchemy import select

        rows = (
            await db.execute(
                select(SipExtension).where(
                    SipExtension.registration_status == "registered"
                )
            )
        ).scalars().all()
        flipped: list[SipExtension] = []
        for record in rows:
            if record.sip_user_id in live_sip_user_ids:
                continue
            flipped.append(
                await SipExtensionRepository.update(
                    db, record, {"registration_status": "unregistered"}
                )
            )
        return flipped

    # ─────────── bindable employees ───────────

    @staticmethod
    async def list_bindable_employees(
        db: AsyncSession, principal: EffectivePrincipal, keyword: str | None
    ) -> list[dict]:
        """Active employees holding ``call.workspace.use`` and not yet bound
        to any SIP extension (dropdown source for admin binding)."""
        candidates = await SipExtensionRepository.list_bindable_employees(
            db, principal.tenant_id, keyword
        )
        return [
            {
                "id": emp.id,
                "name": emp.display_name or emp.name or emp.username,
                "avatar": emp.avatar,
            }
            for emp in candidates
        ]
