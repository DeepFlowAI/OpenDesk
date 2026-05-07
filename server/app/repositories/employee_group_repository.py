"""
EmployeeGroup repository — data access layer
"""
from sqlalchemy import select, func, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.employee_group import EmployeeGroup, EmployeeGroupMember
from app.models.employee import Employee


class EmployeeGroupRepository:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 10,
        keyword: str | None = None,
        member_id: int | None = None,
    ) -> tuple[list[dict], int]:
        """Get paginated groups with member count."""
        base_query = (
            select(EmployeeGroup)
            .where(EmployeeGroup.tenant_id == tenant_id)
        )
        if member_id is not None:
            base_query = base_query.join(
                EmployeeGroupMember,
                EmployeeGroupMember.group_id == EmployeeGroup.id,
            ).where(EmployeeGroupMember.employee_id == member_id)
        if keyword:
            like_pattern = f"%{keyword}%"
            base_query = base_query.where(
                or_(
                    EmployeeGroup.name.ilike(like_pattern),
                    EmployeeGroup.description.ilike(like_pattern),
                )
            )

        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        items_query = (
            base_query
            .options(selectinload(EmployeeGroup.members))
            .order_by(EmployeeGroup.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(items_query)
        groups = list(result.scalars().all())

        items = []
        for g in groups:
            items.append({
                "id": g.id,
                "name": g.name,
                "description": g.description,
                "member_count": len(g.members),
                "created_at": g.created_at,
                "updated_at": g.updated_at,
            })

        return items, total

    @staticmethod
    async def get_by_id(db: AsyncSession, group_id: int) -> EmployeeGroup | None:
        result = await db.execute(
            select(EmployeeGroup)
            .options(selectinload(EmployeeGroup.members).selectinload(EmployeeGroupMember.employee))
            .where(EmployeeGroup.id == group_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_name(db: AsyncSession, tenant_id: int, name: str) -> EmployeeGroup | None:
        result = await db.execute(
            select(EmployeeGroup).where(
                EmployeeGroup.tenant_id == tenant_id,
                EmployeeGroup.name == name,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def has_member(db: AsyncSession, group_id: int, employee_id: int) -> bool:
        """Check whether an employee belongs to a group."""
        result = await db.execute(
            select(EmployeeGroupMember.id).where(
                EmployeeGroupMember.group_id == group_id,
                EmployeeGroupMember.employee_id == employee_id,
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> EmployeeGroup:
        member_ids = data.pop("member_ids", [])
        group = EmployeeGroup(**data)
        db.add(group)
        await db.flush()

        if member_ids:
            for eid in member_ids:
                db.add(EmployeeGroupMember(group_id=group.id, employee_id=eid))

        await db.commit()
        await db.refresh(group)
        return group

    @staticmethod
    async def update(db: AsyncSession, group: EmployeeGroup, data: dict) -> EmployeeGroup:
        member_ids = data.pop("member_ids", None)
        for key, value in data.items():
            if hasattr(group, key):
                setattr(group, key, value)

        if member_ids is not None:
            await db.execute(
                delete(EmployeeGroupMember).where(EmployeeGroupMember.group_id == group.id)
            )
            for eid in member_ids:
                db.add(EmployeeGroupMember(group_id=group.id, employee_id=eid))

        await db.commit()
        await db.refresh(group)
        return group

    @staticmethod
    async def delete(db: AsyncSession, group: EmployeeGroup) -> None:
        await db.delete(group)
        await db.commit()


class EmployeeQueryRepository:
    """Read-only repository for querying employees (for member selection)."""

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        keyword: str | None = None,
    ) -> tuple[list[Employee], int]:
        base_query = select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.is_active == True,  # noqa: E712
        )
        if keyword:
            base_query = base_query.where(
                Employee.display_name.ilike(f"%{keyword}%")
                | Employee.username.ilike(f"%{keyword}%")
            )

        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            base_query.order_by(Employee.id.asc()).offset(offset).limit(per_page)
        )
        return list(result.scalars().all()), total
