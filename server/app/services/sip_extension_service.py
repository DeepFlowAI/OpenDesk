"""
SIP extension service — tenant-admin management of SIP extensions, multi-agent
bindings, and registration credentials.

The password is hashed for SIP authentication and encrypted for tenant admins
who need to configure a phone again later.

Binding grants eligibility only; exclusive occupancy is managed by
``SipExtensionOccupancyService``.
"""
import hashlib
import hmac
import secrets

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.secret_store import decrypt_secret, encrypt_secret
from app.db.session import AsyncSessionLocal
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
from app.services.sip_extension_occupancy_service import SipExtensionOccupancyService

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
        """Registration-domain-unique SIP user id: ``<tenant>-<number>``."""
        base = f"{tenant_slug}-{extension_number}"
        candidate = base
        for _attempt in range(MAX_GENERATION_ATTEMPTS):
            existing = await SipExtensionRepository.get_by_sip_user_id(db, candidate)
            if existing is None:
                return candidate
            candidate = f"{base}-{secrets.token_hex(3)}"
        raise RuntimeError("Failed to generate a unique SIP user id")

    @staticmethod
    async def _resolve_registrar_endpoint() -> tuple[str, int | None, str]:
        from app.libs.telephony import (
            TelephonyError,
            get_telephony_client,
        )

        # Public phone endpoint is a deploy fact (e.g. Kamailio :5070).
        # FlowKit's listen port is an internal backend address and must not
        # override SIP_REGISTRAR_* when those are set.
        host = settings.SIP_REGISTRAR_HOST or ""
        port = settings.SIP_REGISTRAR_PORT
        transport = settings.SIP_REGISTRAR_TRANSPORT or ""
        if host and port is not None and transport:
            return host, port, transport

        try:
            info = await get_telephony_client().registrar_info()
        except TelephonyError:
            info = None
        except Exception:  # noqa: BLE001
            info = None
        if info:
            host = host or (info.get("host") or "")
            if port is None:
                port = info.get("port")
            transport = transport or (info.get("transport") or "")
        return host, port, transport

    @staticmethod
    async def _registration_info(
        record: SipExtension, plaintext_password: str | None
    ) -> SipRegistrationInfo:
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
    async def _ensure_agents_idle(
        cls,
        r: aioredis.Redis | None,
        tenant_id: int,
        employee_ids: list[int],
        *,
        message: str = "该坐席正在通话，请在通话结束后重试",
    ) -> None:
        for emp_id in employee_ids:
            if await cls._agent_is_busy(r, tenant_id, emp_id):
                raise ConflictError(message)

    # ─────────── binding validation ───────────

    @staticmethod
    async def _validate_binding_target(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        current_extension_id: int | None,
    ) -> None:
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

    # ─────────── serialization helpers ───────────

    @staticmethod
    def _employee_brief(emp) -> dict:
        return {
            "id": emp.id,
            "name": emp.display_name or emp.name or emp.username,
            "avatar": emp.avatar,
        }

    @staticmethod
    async def _attach_binding_views(
        db: AsyncSession, items: list[SipExtension]
    ) -> None:
        """Attach bound_employees / current_occupant briefs for serialization."""
        if not items:
            return
        binding_map = await SipExtensionRepository.list_bound_employee_ids_for_extensions(
            db, [i.id for i in items]
        )
        emp_ids: set[int] = set()
        for ids in binding_map.values():
            emp_ids.update(ids)
        for i in items:
            if i.current_occupant_employee_id:
                emp_ids.add(i.current_occupant_employee_id)

        by_id = {}
        if emp_ids:
            employees = await EmployeeRepository.get_by_ids(db, list(emp_ids))
            by_id = {e.id: e for e in employees}

        for i in items:
            bound_ids = binding_map.get(i.id, [])
            i.bound_employee_ids = bound_ids
            i.bound_employees = [
                SipExtensionService._employee_brief(by_id[eid])
                for eid in bound_ids
                if eid in by_id
            ]
            occ_id = i.current_occupant_employee_id
            if occ_id and occ_id in by_id:
                i.current_occupant = SipExtensionService._employee_brief(by_id[occ_id])
            else:
                i.current_occupant = None

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
        await SipExtensionService._attach_binding_views(db, items)
        pages = (total + per_page - 1) // per_page if per_page else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    # ─────────── create ───────────

    @staticmethod
    async def _create_record(
        db: AsyncSession,
        principal: EffectivePrincipal,
        data: SipExtensionCreate,
    ) -> tuple[SipExtension, str]:
        tenant_id = principal.tenant_id
        existing = await SipExtensionRepository.get_by_extension_number(
            db, tenant_id, data.extension_number
        )
        if existing is not None:
            raise ConflictError("该分机号已存在")

        for emp_id in data.bound_employee_ids:
            await SipExtensionService._validate_binding_target(
                db, tenant_id, emp_id, None
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
                "auth_account": sip_user_id,
                "auth_password_hash": SipExtensionService.hash_password(password),
                "auth_password_masked": SipExtensionService.mask_password(password),
                "auth_password_ciphertext": encrypt_secret(password),
                "created_by_actor_type": "employee",
                "created_by_actor_id": principal.user_id,
            },
        )
        if data.bound_employee_ids:
            await SipExtensionRepository.replace_bindings(
                db, tenant_id, record.id, data.bound_employee_ids
            )
        await SipExtensionService._attach_binding_views(db, [record])
        return record, password

    @staticmethod
    async def create(
        db: AsyncSession,
        principal: EffectivePrincipal,
        data: SipExtensionCreate,
    ) -> dict:
        record, password = await SipExtensionService._create_record(
            db, principal, data
        )
        return {
            "record": record,
            "registration_info": await SipExtensionService._registration_info(
                record, password
            ),
        }

    @staticmethod
    async def create_managed(
        principal: EffectivePrincipal,
        data: SipExtensionCreate,
    ) -> dict:
        """Create an extension; registrar lookup runs with no pooled DB session."""
        async with AsyncSessionLocal() as db:
            record, password = await SipExtensionService._create_record(
                db, principal, data
            )
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

    # ─────────── update (name / bindings) ───────────

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

        if "bound_employee_ids" in fields_set and data.bound_employee_ids is not None:
            new_ids = list(data.bound_employee_ids)
            current_ids = await SipExtensionRepository.list_bound_employee_ids(
                db, item.id
            )
            current_set = set(current_ids)
            new_set = set(new_ids)
            removed = current_set - new_set
            added = new_set - current_set

            for emp_id in added:
                await SipExtensionService._validate_binding_target(
                    db, tenant_id, emp_id, item.id
                )

            # Removing an agent who is mid-call is forbidden.
            await SipExtensionService._ensure_agents_idle(
                r,
                tenant_id,
                list(removed),
                message="该坐席正在通话，请在通话结束后重试",
            )

            occupant_id = item.current_occupant_employee_id
            if occupant_id is not None and occupant_id in removed:
                from app.services.agent_status_service import AgentStatusService

                online = False
                if r is not None:
                    try:
                        online = await AgentStatusService.is_connected(
                            r, tenant_id, occupant_id
                        )
                    except Exception:  # noqa: BLE001
                        online = True
                if online:
                    name = await SipExtensionOccupancyService._employee_display_name(
                        db, occupant_id
                    )
                    raise ConflictError(
                        f"{name} 当前正在使用该话机，请先下线后重试"
                    )
                updates["current_occupant_employee_id"] = None

            if updates:
                updates["updated_by_actor_type"] = "employee"
                updates["updated_by_actor_id"] = principal.user_id
                item = await SipExtensionRepository.update(db, item, updates)
                updates = {}

            await SipExtensionRepository.replace_bindings(
                db, tenant_id, item.id, new_ids
            )

            # Unbound agents who had sip_phone selected must re-choose a device.
            for emp_id in removed:
                await SipExtensionService._clear_agent_sip_device(
                    db, tenant_id, emp_id
                )

            await SipExtensionService._attach_binding_views(db, [item])
            return item

        if not updates:
            await SipExtensionService._attach_binding_views(db, [item])
            return item

        updates["updated_by_actor_type"] = "employee"
        updates["updated_by_actor_id"] = principal.user_id
        record = await SipExtensionRepository.update(db, item, updates)
        await SipExtensionService._attach_binding_views(db, [record])
        return record

    @staticmethod
    async def _clear_agent_sip_device(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> None:
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
    async def _reset_password_record(
        db: AsyncSession,
        principal: EffectivePrincipal,
        extension_id: int,
        r: aioredis.Redis | None = None,
    ) -> tuple[SipExtension, str]:
        tenant_id = principal.tenant_id
        item = await SipExtensionService.get_scoped(db, principal, extension_id)
        await SipExtensionService._reject_destructive_while_in_use(
            db, r, tenant_id, item
        )

        password = SipExtensionService._generate_password()
        record = await SipExtensionRepository.update(
            db,
            item,
            {
                "auth_password_hash": SipExtensionService.hash_password(password),
                "auth_password_masked": SipExtensionService.mask_password(password),
                "auth_password_ciphertext": encrypt_secret(password),
                "registration_status": "unregistered",
                "last_registered_at": None,
                "updated_by_actor_type": "employee",
                "updated_by_actor_id": principal.user_id,
            },
        )
        await SipExtensionService._attach_binding_views(db, [record])
        return record, password

    @staticmethod
    async def reset_password(
        db: AsyncSession,
        principal: EffectivePrincipal,
        extension_id: int,
        r: aioredis.Redis | None = None,
    ) -> dict:
        record, password = await SipExtensionService._reset_password_record(
            db, principal, extension_id, r
        )
        return {
            "record": record,
            "registration_info": await SipExtensionService._registration_info(
                record, password
            ),
        }

    @staticmethod
    async def reset_password_managed(
        principal: EffectivePrincipal,
        extension_id: int,
        r: aioredis.Redis | None = None,
    ) -> dict:
        """Reset password; registrar lookup runs with no pooled DB session."""
        async with AsyncSessionLocal() as db:
            record, password = await SipExtensionService._reset_password_record(
                db, principal, extension_id, r
            )
        return {
            "record": record,
            "registration_info": await SipExtensionService._registration_info(
                record, password
            ),
        }

    @classmethod
    async def _reject_destructive_while_in_use(
        cls,
        db: AsyncSession,
        r: aioredis.Redis | None,
        tenant_id: int,
        item: SipExtension,
    ) -> None:
        """Block reset/disable while occupant is online or any bound agent is busy."""
        bound_ids = await SipExtensionRepository.list_bound_employee_ids(db, item.id)
        await cls._ensure_agents_idle(
            r,
            tenant_id,
            bound_ids,
            message="该坐席正在使用此分机通话，请在通话结束后重试",
        )
        occupant_id = item.current_occupant_employee_id
        if occupant_id is None:
            return
        from app.services.agent_status_service import AgentStatusService

        if r is not None:
            try:
                online = await AgentStatusService.is_connected(r, tenant_id, occupant_id)
            except Exception:  # noqa: BLE001
                online = True
            if online:
                raise ConflictError(
                    "当前使用人在线，请先让其下线后重试"
                )

    # ─────────── copy registration info ───────────

    @staticmethod
    async def get_registration_info(
        db: AsyncSession, principal: EffectivePrincipal, extension_id: int
    ) -> SipRegistrationInfo:
        item = await SipExtensionService.get_scoped(db, principal, extension_id)
        ciphertext = item.auth_password_ciphertext
        if not ciphertext:
            raise ValidationError("历史分机密码无法恢复，请先重置密码后再复制")
        try:
            password = decrypt_secret(ciphertext)
        except ValueError as exc:
            raise ValidationError("分机密码无法读取，请重置密码后再复制") from exc
        return await SipExtensionService._registration_info(item, password)

    @staticmethod
    async def get_registration_info_managed(
        principal: EffectivePrincipal, extension_id: int
    ) -> SipRegistrationInfo:
        """Copy registration info; registrar lookup runs with no pooled DB session."""
        async with AsyncSessionLocal() as db:
            item = await SipExtensionService.get_scoped(db, principal, extension_id)
            ciphertext = item.auth_password_ciphertext
            if not ciphertext:
                raise ValidationError("历史分机密码无法恢复，请先重置密码后再复制")
            try:
                password = decrypt_secret(ciphertext)
            except ValueError as exc:
                raise ValidationError("分机密码无法读取，请重置密码后再复制") from exc
        return await SipExtensionService._registration_info(item, password)

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
            await SipExtensionService._attach_binding_views(db, [item])
            return item

        await SipExtensionService._reject_destructive_while_in_use(
            db, r, tenant_id, item
        )

        record = await SipExtensionRepository.update(
            db,
            item,
            {
                "is_active": False,
                "disabled_at": datetime.now(timezone.utc),
                "current_occupant_employee_id": None,
                "updated_by_actor_type": "employee",
                "updated_by_actor_id": principal.user_id,
            },
        )
        bound_ids = await SipExtensionRepository.list_bound_employee_ids(db, record.id)
        for emp_id in bound_ids:
            await SipExtensionService._clear_agent_sip_device(db, tenant_id, emp_id)
        await SipExtensionService._attach_binding_views(db, [record])
        return record

    @staticmethod
    async def enable(
        db: AsyncSession, principal: EffectivePrincipal, extension_id: int
    ) -> SipExtension:
        item = await SipExtensionService.get_scoped(db, principal, extension_id)
        if item.is_active:
            await SipExtensionService._attach_binding_views(db, [item])
            return item
        # Re-enable does not restore a previous occupant.
        record = await SipExtensionRepository.update(
            db,
            item,
            {
                "is_active": True,
                "disabled_at": None,
                "current_occupant_employee_id": None,
                "updated_by_actor_type": "employee",
                "updated_by_actor_id": principal.user_id,
            },
        )
        await SipExtensionService._attach_binding_views(db, [record])
        return record

    # ─────────── registration status writeback (kernel events) ───────────

    @staticmethod
    async def apply_registration_event(
        db: AsyncSession,
        *,
        sip_user_id: str,
        registered: bool,
    ) -> SipExtension | None:
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
        from datetime import datetime, timezone

        from sqlalchemy import or_, select

        # Candidates: currently registered (may need downgrade) or present in
        # the live registrar (may need upgrade). An empty live set makes
        # ``in_([])`` false, so only the registered branch matches.
        rows = (
            await db.execute(
                select(SipExtension).where(
                    or_(
                        SipExtension.registration_status == "registered",
                        SipExtension.sip_user_id.in_(live_sip_user_ids),
                    )
                )
            )
        ).scalars().all()
        flipped: list[SipExtension] = []
        for record in rows:
            in_live = record.sip_user_id in live_sip_user_ids
            if record.registration_status == "registered" and not in_live:
                flipped.append(
                    await SipExtensionRepository.update(
                        db, record, {"registration_status": "unregistered"}
                    )
                )
            elif record.registration_status != "registered" and in_live:
                flipped.append(
                    await SipExtensionRepository.update(
                        db,
                        record,
                        {
                            "registration_status": "registered",
                            "last_registered_at": datetime.now(timezone.utc),
                        },
                    )
                )
        return flipped

    @staticmethod
    async def list_bound_employee_ids_for_notify(
        db: AsyncSession, extension: SipExtension
    ) -> list[int]:
        return await SipExtensionRepository.list_bound_employee_ids(db, extension.id)

    # ─────────── bindable employees ───────────

    @staticmethod
    async def list_bindable_employees(
        db: AsyncSession,
        principal: EffectivePrincipal,
        keyword: str | None,
        for_extension_id: int | None = None,
    ) -> list[dict]:
        if for_extension_id is not None:
            scoped = await SipExtensionRepository.get_scoped(
                db, principal.tenant_id, for_extension_id
            )
            if scoped is None:
                raise NotFoundError("SIP extension not found")
        candidates = await SipExtensionRepository.list_bindable_employees(
            db,
            principal.tenant_id,
            keyword,
            for_extension_id=for_extension_id,
        )
        return [
            {
                "id": emp.id,
                "name": emp.display_name or emp.name or emp.username,
                "avatar": emp.avatar,
            }
            for emp in candidates
        ]
