"""
SIP extension repository — extensions, multi-agent bindings, occupancy.
"""
from sqlalchemy import and_, cast, delete, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.role import EmployeeRole, Role
from app.models.sip_extension import SipExtension
from app.models.sip_extension_binding import SipExtensionBinding
from app.models.tenant import Tenant


class SipExtensionRepository:
    @staticmethod
    async def get_tenant_slug(db: AsyncSession, tenant_id: int) -> str | None:
        result = await db.execute(select(Tenant.tenant_id).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    @staticmethod
    def _eligible_workspace_employee_ids(tenant_id: int):
        permissions_jsonb = cast(Role.permissions, JSONB)
        return (
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

    @staticmethod
    async def list_bindable_employees(
        db: AsyncSession,
        tenant_id: int,
        keyword: str | None,
        limit: int = 200,
        for_extension_id: int | None = None,
    ) -> list[Employee]:
        """Active employees with ``call.workspace.use`` not bound to another
        extension. When ``for_extension_id`` is set, agents already bound to
        that extension remain selectable (edit form)."""
        eligible_ids = SipExtensionRepository._eligible_workspace_employee_ids(tenant_id)
        bound_elsewhere = select(SipExtensionBinding.employee_id).where(
            SipExtensionBinding.tenant_id == tenant_id,
        )
        if for_extension_id is not None:
            bound_elsewhere = bound_elsewhere.where(
                SipExtensionBinding.extension_id != for_extension_id
            )
        base = select(Employee).where(
            Employee.id.in_(eligible_ids),
            Employee.id.notin_(bound_elsewhere),
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
        """Active employees holding ``call.workspace.use`` effectively."""
        eligible_ids = SipExtensionRepository._eligible_workspace_employee_ids(tenant_id)
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
        """Extension the employee is bound to (eligibility), if any."""
        result = await db.execute(
            select(SipExtension)
            .join(
                SipExtensionBinding,
                SipExtensionBinding.extension_id == SipExtension.id,
            )
            .where(
                SipExtension.tenant_id == tenant_id,
                SipExtensionBinding.employee_id == employee_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_employee_for_update(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> SipExtension | None:
        """Lock the bound extension row for occupancy updates."""
        result = await db.execute(
            select(SipExtension)
            .join(
                SipExtensionBinding,
                SipExtensionBinding.extension_id == SipExtension.id,
            )
            .where(
                SipExtension.tenant_id == tenant_id,
                SipExtensionBinding.employee_id == employee_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_for_update(
        db: AsyncSession, tenant_id: int, extension_id: int
    ) -> SipExtension | None:
        result = await db.execute(
            select(SipExtension)
            .where(
                SipExtension.tenant_id == tenant_id,
                SipExtension.id == extension_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_bound_employee_ids(
        db: AsyncSession, extension_id: int
    ) -> list[int]:
        result = await db.execute(
            select(SipExtensionBinding.employee_id).where(
                SipExtensionBinding.extension_id == extension_id
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_bound_employee_ids_for_extensions(
        db: AsyncSession, extension_ids: list[int]
    ) -> dict[int, list[int]]:
        if not extension_ids:
            return {}
        result = await db.execute(
            select(
                SipExtensionBinding.extension_id, SipExtensionBinding.employee_id
            ).where(SipExtensionBinding.extension_id.in_(extension_ids))
        )
        out: dict[int, list[int]] = {eid: [] for eid in extension_ids}
        for ext_id, emp_id in result.all():
            out.setdefault(ext_id, []).append(emp_id)
        return out

    @staticmethod
    async def replace_bindings(
        db: AsyncSession,
        tenant_id: int,
        extension_id: int,
        employee_ids: list[int],
        *,
        commit: bool = True,
    ) -> None:
        await db.execute(
            delete(SipExtensionBinding).where(
                SipExtensionBinding.extension_id == extension_id
            )
        )
        if employee_ids:
            await db.execute(
                insert(SipExtensionBinding),
                [
                    {
                        "tenant_id": tenant_id,
                        "extension_id": extension_id,
                        "employee_id": emp_id,
                    }
                    for emp_id in employee_ids
                ],
            )
        if commit:
            await db.commit()

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
        bound_emp = Employee.__table__.alias("bound_emp")
        occupant_emp = Employee.__table__.alias("occupant_emp")
        base = (
            select(SipExtension)
            .outerjoin(
                SipExtensionBinding,
                SipExtensionBinding.extension_id == SipExtension.id,
            )
            .outerjoin(bound_emp, bound_emp.c.id == SipExtensionBinding.employee_id)
            .outerjoin(
                occupant_emp,
                occupant_emp.c.id == SipExtension.current_occupant_employee_id,
            )
            .where(SipExtension.tenant_id == tenant_id)
            .distinct()
        )

        if keyword:
            like = f"%{keyword.strip()}%"
            base = base.where(
                or_(
                    SipExtension.extension_number.ilike(like),
                    SipExtension.name.ilike(like),
                    SipExtension.sip_user_id.ilike(like),
                    SipExtension.auth_account.ilike(like),
                    bound_emp.c.name.ilike(like),
                    bound_emp.c.display_name.ilike(like),
                    occupant_emp.c.name.ilike(like),
                    occupant_emp.c.display_name.ilike(like),
                )
            )

        if registration_status == "registered":
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
        return list(result.scalars().unique().all()), total

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
