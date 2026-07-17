"""
SIP extension repository.
"""
from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.role import EmployeeRole, Role
from app.models.sip_extension import SipExtension
from app.models.tenant import Tenant


class SipExtensionRepository:
    @staticmethod
    async def get_tenant_slug(db: AsyncSession, tenant_id: int) -> str | None:
        result = await db.execute(select(Tenant.tenant_id).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_bindable_employees(
        db: AsyncSession, tenant_id: int, keyword: str | None, limit: int = 200
    ) -> list[Employee]:
        """Active employees holding ``call.workspace.use`` effectively and not
        currently bound to any SIP extension in the tenant."""
        permissions_jsonb = cast(Role.permissions, JSONB)
        eligible_ids = (
            select(Employee.id)
            .outerjoin(EmployeeRole, EmployeeRole.employee_id == Employee.id)
            .outerjoin(Role, Role.id == EmployeeRole.role_id)
            .where(
                Employee.tenant_id == tenant_id,
                Employee.is_active.is_(True),
                or_(
                    Employee.is_super_admin.is_(True),
                    and_(
                        Role.tenant_id == tenant_id,
                        Role.is_active.is_(True),
                        permissions_jsonb.contains(["call.workspace.use"]),
                    ),
                ),
            )
            .distinct()
        )
        # Exclude employees already bound to an extension.
        bound_ids = (
            select(SipExtension.bound_employee_id)
            .where(
                SipExtension.tenant_id == tenant_id,
                SipExtension.bound_employee_id.isnot(None),
            )
        )
        base = select(Employee).where(
            Employee.id.in_(eligible_ids),
            Employee.id.notin_(bound_ids),
        )
        if keyword:
            like = f"%{keyword.strip()}%"
            base = base.where(
                or_(
                    Employee.name.ilike(like),
                    Employee.display_name.ilike(like),
                    Employee.username.ilike(like),
                    Employee.email.ilike(like),
                    Employee.job_number.ilike(like),
                )
            )
        base = base.order_by(Employee.name.asc()).limit(limit)
        result = await db.execute(base)
        return list(result.scalars().all())

    @staticmethod
    async def list_workspace_agents(
        db: AsyncSession,
        tenant_id: int,
        keyword: str | None,
        exclude_employee_id: int | None = None,
        limit: int = 200,
    ) -> list[Employee]:
        """Active employees holding ``call.workspace.use`` effectively.

        Unlike ``list_bindable_employees`` this does *not* filter out agents
        already bound to an extension — every workspace agent is a valid target
        for consult / transfer / conference, regardless of their SIP binding.
        ``keyword`` matches by display name / name / username. When
        ``exclude_employee_id`` is set that agent is dropped (a caller cannot
        consult / transfer to themselves).
        """
        permissions_jsonb = cast(Role.permissions, JSONB)
        eligible_ids = (
            select(Employee.id)
            .outerjoin(EmployeeRole, EmployeeRole.employee_id == Employee.id)
            .outerjoin(Role, Role.id == EmployeeRole.role_id)
            .where(
                Employee.tenant_id == tenant_id,
                Employee.is_active.is_(True),
                or_(
                    Employee.is_super_admin.is_(True),
                    and_(
                        Role.tenant_id == tenant_id,
                        Role.is_active.is_(True),
                        permissions_jsonb.contains(["call.workspace.use"]),
                    ),
                ),
            )
            .distinct()
        )
        base = select(Employee).where(Employee.id.in_(eligible_ids))
        if exclude_employee_id is not None:
            base = base.where(Employee.id != exclude_employee_id)
        if keyword:
            like = f"%{keyword.strip()}%"
            base = base.where(
                or_(
                    Employee.name.ilike(like),
                    Employee.display_name.ilike(like),
                    Employee.username.ilike(like),
                )
            )
        base = base.order_by(Employee.name.asc()).limit(limit)
        result = await db.execute(base)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, extension_id: int) -> SipExtension | None:
        return await db.get(SipExtension, extension_id)

    @staticmethod
    async def get_scoped(
        db: AsyncSession, tenant_id: int, extension_id: int
    ) -> SipExtension | None:
        item = await db.get(SipExtension, extension_id)
        if item is None or item.tenant_id != tenant_id:
            return None
        return item

    @staticmethod
    async def get_by_extension_number(
        db: AsyncSession, tenant_id: int, extension_number: str
    ) -> SipExtension | None:
        result = await db.execute(
            select(SipExtension).where(
                SipExtension.tenant_id == tenant_id,
                SipExtension.extension_number == extension_number,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_sip_user_id(
        db: AsyncSession, sip_user_id: str
    ) -> SipExtension | None:
        result = await db.execute(
            select(SipExtension).where(SipExtension.sip_user_id == sip_user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_employee(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> SipExtension | None:
        result = await db.execute(
            select(SipExtension).where(
                SipExtension.tenant_id == tenant_id,
                SipExtension.bound_employee_id == employee_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int,
        per_page: int,
        keyword: str | None,
        registration_status: str | None,
        active_status: str | None,
    ) -> tuple[list[SipExtension], int]:
        # Join employees so keyword can match the bound agent name.
        base = (
            select(SipExtension)
            .outerjoin(Employee, Employee.id == SipExtension.bound_employee_id)
            .where(SipExtension.tenant_id == tenant_id)
        )

        if keyword:
            like = f"%{keyword.strip()}%"
            base = base.where(
                or_(
                    SipExtension.extension_number.ilike(like),
                    SipExtension.name.ilike(like),
                    SipExtension.sip_user_id.ilike(like),
                    SipExtension.auth_account.ilike(like),
                    Employee.name.ilike(like),
                    Employee.display_name.ilike(like),
                )
            )

        if registration_status == "registered":
            # A disabled extension never counts as registered regardless of
            # historical status.
            base = base.where(
                SipExtension.registration_status == "registered",
                SipExtension.is_active.is_(True),
            )
        elif registration_status == "unregistered":
            base = base.where(
                or_(
                    SipExtension.registration_status == "unregistered",
                    SipExtension.is_active.is_(False),
                )
            )

        if active_status == "active":
            base = base.where(SipExtension.is_active.is_(True))
        elif active_status == "inactive":
            base = base.where(SipExtension.is_active.is_(False))

        count_q = select(func.count()).select_from(base.subquery())
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        data_q = (
            base.order_by(SipExtension.created_at.desc(), SipExtension.id.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(data_q)
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SipExtension:
        item = SipExtension(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: SipExtension, data: dict) -> SipExtension:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item
