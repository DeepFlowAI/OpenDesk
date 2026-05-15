"""
Employee repository — data access for employees / admins
"""
from datetime import datetime, timezone

from sqlalchemy import cast, select, or_, func, delete
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup, EmployeeGroupMember
from app.schemas.employee import VALID_ROLES


class EmployeeRepository:

    @staticmethod
    async def get_by_username_or_email(
        db: AsyncSession, tenant_pk: int, username: str
    ) -> Employee | None:
        """Find employee by username or email within a tenant."""
        result = await db.execute(
            select(Employee).where(
                Employee.tenant_id == tenant_pk,
                or_(Employee.username == username, Employee.email == username),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_last_login(db: AsyncSession, emp: Employee) -> None:
        """Update last_login_at timestamp."""
        emp.last_login_at = datetime.now(timezone.utc)
        await db.commit()

    @staticmethod
    async def update_password(db: AsyncSession, emp: Employee, password_hash: str) -> None:
        """Update employee password hash."""
        emp.password_hash = password_hash
        await db.commit()

    @staticmethod
    async def get_by_id(db: AsyncSession, employee_id: int) -> Employee | None:
        """Get employee by primary key."""
        return await db.get(Employee, employee_id)

    @staticmethod
    async def get_by_ids(db: AsyncSession, employee_ids: list[int]) -> list[Employee]:
        """Get employees by primary keys."""
        if not employee_ids:
            return []
        result = await db.execute(
            select(Employee).where(Employee.id.in_(employee_ids))
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_group_ids_by_employee_ids(
        db: AsyncSession, employee_ids: list[int]
    ) -> dict[int, list[int]]:
        """Get employee group IDs keyed by employee ID."""
        if not employee_ids:
            return {}
        result = await db.execute(
            select(EmployeeGroupMember.employee_id, EmployeeGroupMember.group_id)
            .where(EmployeeGroupMember.employee_id.in_(employee_ids))
            .order_by(EmployeeGroupMember.group_id.asc())
        )
        grouped: dict[int, list[int]] = {employee_id: [] for employee_id in employee_ids}
        for employee_id, group_id in result.all():
            grouped.setdefault(employee_id, []).append(group_id)
        return grouped

    @staticmethod
    async def attach_group_ids(db: AsyncSession, employees: list[Employee]) -> list[Employee]:
        """Attach group_ids attributes for API serialization."""
        grouped = await EmployeeRepository.get_group_ids_by_employee_ids(
            db, [employee.id for employee in employees]
        )
        for employee in employees:
            employee.group_ids = grouped.get(employee.id, [])
        return employees

    @staticmethod
    async def get_existing_group_ids(
        db: AsyncSession, tenant_id: int, group_ids: list[int]
    ) -> set[int]:
        """Return group IDs that exist in the tenant."""
        if not group_ids:
            return set()
        result = await db.execute(
            select(EmployeeGroup.id).where(
                EmployeeGroup.tenant_id == tenant_id,
                EmployeeGroup.id.in_(group_ids),
            )
        )
        return set(result.scalars().all())

    @staticmethod
    async def replace_group_ids(
        db: AsyncSession, employee_id: int, group_ids: list[int]
    ) -> None:
        """Replace all group memberships for an employee."""
        await db.execute(
            delete(EmployeeGroupMember).where(EmployeeGroupMember.employee_id == employee_id)
        )
        for group_id in group_ids:
            db.add(EmployeeGroupMember(group_id=group_id, employee_id=employee_id))
        await db.commit()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 10,
        keyword: str | None = None,
        role_filters: list[str] | None = None,
        status: str | None = None,
        group_id: int | None = None,
    ) -> tuple[list[Employee], int]:
        """List employees with filtering, searching and pagination."""
        base = select(Employee).where(Employee.tenant_id == tenant_id)

        if group_id is not None:
            base = base.join(
                EmployeeGroupMember,
                EmployeeGroupMember.employee_id == Employee.id,
            ).where(EmployeeGroupMember.group_id == group_id)

        if keyword:
            like_pattern = f"%{keyword}%"
            base = base.where(
                or_(
                    Employee.name.ilike(like_pattern),
                    Employee.job_number.ilike(like_pattern),
                    Employee.username.ilike(like_pattern),
                    Employee.email.ilike(like_pattern),
                    Employee.phone.ilike(like_pattern),
                )
            )

        # JSON column `.contains()` compiles to LIKE on PG and misses multi-role arrays
        # (e.g. ["admin","agent"] does not contain the substring '["admin"]'). Use jsonb @>.
        if role_filters:
            normalized = [r for r in dict.fromkeys(role_filters) if r in VALID_ROLES]
            if normalized:
                roles_jsonb = cast(Employee.roles, JSONB)
                base = base.where(
                    or_(*(roles_jsonb.contains([r]) for r in normalized))
                )

        if status == "active":
            base = base.where(Employee.is_active.is_(True))
        elif status == "inactive":
            base = base.where(Employee.is_active.is_(False))

        count_q = select(func.count()).select_from(base.subquery())
        total_result = await db.execute(count_q)
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        data_q = base.order_by(Employee.created_at.desc()).offset(offset).limit(per_page)
        result = await db.execute(data_q)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_by_username_in_tenant(
        db: AsyncSession, tenant_id: int, username: str
    ) -> Employee | None:
        """Find employee by exact username within a tenant."""
        result = await db.execute(
            select(Employee).where(Employee.tenant_id == tenant_id, Employee.username == username)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Employee:
        """Create a new employee."""
        emp = Employee(**data)
        db.add(emp)
        await db.commit()
        await db.refresh(emp)
        return emp

    @staticmethod
    async def update(db: AsyncSession, emp: Employee, data: dict) -> Employee:
        """Update employee attributes."""
        for key, value in data.items():
            if hasattr(emp, key):
                setattr(emp, key, value)
        await db.commit()
        await db.refresh(emp)
        return emp

    @staticmethod
    async def delete(db: AsyncSession, emp: Employee) -> None:
        """Delete an employee."""
        await db.delete(emp)
        await db.commit()

    @staticmethod
    async def get_active_by_tenant(db: AsyncSession, tenant_id: int) -> list[Employee]:
        """Get all active employees in a tenant (for routing fallback)."""
        result = await db.execute(
            select(Employee).where(Employee.tenant_id == tenant_id, Employee.is_active.is_(True))
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_transfer_candidates(
        db: AsyncSession,
        tenant_id: int,
        exclude_user_ids: list[int] | None = None,
        keyword: str | None = None,
        limit: int = 200,
    ) -> list[Employee]:
        """Active employees in the tenant who can take a transferred conversation.

        Constraints:
            - is_active = True
            - has the ``agent`` role (admin-only accounts that do not serve are excluded)
            - exclude any ids in ``exclude_user_ids`` (typically the requester
              and the conversation's current owner)
            - optional keyword filters name/job_number/username/email/phone
        """
        roles_jsonb = cast(Employee.roles, JSONB)
        excluded = [eid for eid in (exclude_user_ids or []) if eid is not None]
        base = (
            select(Employee)
            .where(
                Employee.tenant_id == tenant_id,
                Employee.is_active.is_(True),
                roles_jsonb.contains(["agent"]),
            )
        )
        if excluded:
            base = base.where(Employee.id.notin_(excluded))

        if keyword:
            like_pattern = f"%{keyword.strip()}%"
            base = base.where(
                or_(
                    Employee.name.ilike(like_pattern),
                    Employee.display_name.ilike(like_pattern),
                    Employee.job_number.ilike(like_pattern),
                    Employee.username.ilike(like_pattern),
                    Employee.email.ilike(like_pattern),
                    Employee.phone.ilike(like_pattern),
                )
            )

        base = base.order_by(Employee.name.asc()).limit(limit)
        result = await db.execute(base)
        return list(result.scalars().all())
