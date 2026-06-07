"""
Role repository.
"""
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.role import EmployeeRole, Role


class RoleRepository:
    @staticmethod
    async def get_by_id(db: AsyncSession, role_id: int) -> Role | None:
        return await db.get(Role, role_id)

    @staticmethod
    async def get_by_ids(db: AsyncSession, tenant_id: int, role_ids: list[int]) -> list[Role]:
        if not role_ids:
            return []
        result = await db.execute(
            select(Role).where(Role.tenant_id == tenant_id, Role.id.in_(role_ids))
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_active_by_ids(db: AsyncSession, tenant_id: int, role_ids: list[int]) -> list[Role]:
        if not role_ids:
            return []
        result = await db.execute(
            select(Role).where(
                Role.tenant_id == tenant_id,
                Role.id.in_(role_ids),
                Role.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_active_roles_by_employee_id(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
    ) -> list[Role]:
        result = await db.execute(
            select(Role)
            .join(EmployeeRole, EmployeeRole.role_id == Role.id)
            .where(
                EmployeeRole.employee_id == employee_id,
                Role.tenant_id == tenant_id,
                Role.is_active.is_(True),
            )
            .order_by(Role.is_system.desc(), Role.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_key(db: AsyncSession, tenant_id: int, key: str) -> Role | None:
        result = await db.execute(
            select(Role).where(Role.tenant_id == tenant_id, Role.key == key)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_keys(db: AsyncSession, tenant_id: int, keys: list[str]) -> list[Role]:
        if not keys:
            return []
        result = await db.execute(
            select(Role).where(Role.tenant_id == tenant_id, Role.key.in_(keys))
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_name(db: AsyncSession, tenant_id: int, name: str) -> Role | None:
        result = await db.execute(
            select(Role).where(Role.tenant_id == tenant_id, Role.name == name)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 10,
        keyword: str | None = None,
        role_type: str | None = None,
    ) -> tuple[list[Role], int]:
        query = select(Role).where(Role.tenant_id == tenant_id)

        if keyword:
            like_pattern = f"%{keyword.strip()}%"
            query = query.where(
                or_(Role.name.ilike(like_pattern), Role.description.ilike(like_pattern))
            )

        if role_type == "system":
            query = query.where(Role.is_system.is_(True))
        elif role_type == "custom":
            query = query.where(Role.is_system.is_(False))

        total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        offset = (page - 1) * per_page
        data_q = (
            query.order_by(Role.is_system.desc(), Role.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(data_q)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_options(db: AsyncSession, tenant_id: int) -> list[Role]:
        result = await db.execute(
            select(Role)
            .where(Role.tenant_id == tenant_id, Role.is_active.is_(True))
            .order_by(Role.is_system.desc(), Role.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Role:
        role = Role(**data)
        db.add(role)
        await db.commit()
        await db.refresh(role)
        return role

    @staticmethod
    async def update(db: AsyncSession, role: Role, data: dict) -> Role:
        for key, value in data.items():
            if hasattr(role, key):
                setattr(role, key, value)
        await db.commit()
        await db.refresh(role)
        return role

    @staticmethod
    async def delete(db: AsyncSession, role: Role) -> None:
        await db.delete(role)
        await db.commit()

    @staticmethod
    async def get_member_counts(db: AsyncSession, role_ids: list[int]) -> dict[int, int]:
        if not role_ids:
            return {}
        result = await db.execute(
            select(EmployeeRole.role_id, func.count(EmployeeRole.employee_id))
            .where(EmployeeRole.role_id.in_(role_ids))
            .group_by(EmployeeRole.role_id)
        )
        return {role_id: count for role_id, count in result.all()}

    @staticmethod
    async def attach_member_counts(db: AsyncSession, roles: list[Role]) -> list[Role]:
        counts = await RoleRepository.get_member_counts(db, [role.id for role in roles])
        for role in roles:
            role.member_count = counts.get(role.id, 0)
        return roles

    @staticmethod
    async def count_members(db: AsyncSession, role_id: int) -> int:
        result = await db.execute(
            select(func.count()).select_from(EmployeeRole).where(EmployeeRole.role_id == role_id)
        )
        return result.scalar_one()

    @staticmethod
    async def get_employee_role_assignments(
        db: AsyncSession, employee_ids: list[int]
    ) -> dict[int, list[Role]]:
        if not employee_ids:
            return {}
        result = await db.execute(
            select(EmployeeRole.employee_id, Role)
            .join(Role, Role.id == EmployeeRole.role_id)
            .where(EmployeeRole.employee_id.in_(employee_ids))
            .order_by(Role.is_system.desc(), Role.id.asc())
        )
        grouped: dict[int, list[Role]] = {employee_id: [] for employee_id in employee_ids}
        for employee_id, role in result.all():
            grouped.setdefault(employee_id, []).append(role)
        return grouped

    @staticmethod
    async def get_role_ids_by_employee_ids(
        db: AsyncSession, employee_ids: list[int]
    ) -> dict[int, list[int]]:
        assignments = await RoleRepository.get_employee_role_assignments(db, employee_ids)
        return {
            employee_id: [role.id for role in roles]
            for employee_id, roles in assignments.items()
        }

    @staticmethod
    async def replace_employee_role_ids(
        db: AsyncSession, employee_id: int, role_ids: list[int]
    ) -> None:
        await db.execute(delete(EmployeeRole).where(EmployeeRole.employee_id == employee_id))
        for role_id in role_ids:
            db.add(EmployeeRole(employee_id=employee_id, role_id=role_id))
        await db.commit()

    @staticmethod
    async def get_legacy_role_employee_ids(db: AsyncSession, tenant_id: int, key: str) -> list[int]:
        result = await db.execute(select(Employee.id).where(Employee.tenant_id == tenant_id))
        employee_ids = list(result.scalars().all())
        if not employee_ids:
            return []
        employees = (await db.execute(select(Employee).where(Employee.id.in_(employee_ids)))).scalars().all()
        return [
            employee.id
            for employee in employees
            if key in (employee.roles or [])
        ]
