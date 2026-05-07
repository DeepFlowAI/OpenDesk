"""
EmployeeGroup service — business logic layer
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.employee_group_repository import EmployeeGroupRepository, EmployeeQueryRepository
from app.schemas.employee_group import (
    EmployeeGroupCreate,
    EmployeeGroupUpdate,
    EmployeeGroupMemberInfo,
)


class EmployeeGroupService:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 10,
        keyword: str | None = None,
        member_id: int | None = None,
    ) -> dict:
        items, total = await EmployeeGroupRepository.get_paginated(
            db, tenant_id, page, per_page, keyword, member_id
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, group_id: int, tenant_id: int) -> dict:
        group = await EmployeeGroupRepository.get_by_id(db, group_id)
        if not group or group.tenant_id != tenant_id:
            raise NotFoundError("Employee group not found")

        members = []
        for m in group.members:
            emp = m.employee
            members.append(EmployeeGroupMemberInfo(
                employee_id=m.employee_id,
                username=emp.username if emp else "",
                display_name=emp.display_name if emp else None,
            ))

        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "member_count": len(members),
            "members": members,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
        }

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: EmployeeGroupCreate) -> dict:
        existing = await EmployeeGroupRepository.get_by_name(db, tenant_id, data.name)
        if existing:
            raise ValidationError("Employee group name already exists")

        payload = data.model_dump()
        payload["tenant_id"] = tenant_id
        group = await EmployeeGroupRepository.create(db, payload)

        return await EmployeeGroupService.get_by_id(db, group.id, tenant_id)

    @staticmethod
    async def update(
        db: AsyncSession, group_id: int, tenant_id: int, data: EmployeeGroupUpdate
    ) -> dict:
        group = await EmployeeGroupRepository.get_by_id(db, group_id)
        if not group or group.tenant_id != tenant_id:
            raise NotFoundError("Employee group not found")

        existing = await EmployeeGroupRepository.get_by_name(db, tenant_id, data.name)
        if existing and existing.id != group_id:
            raise ValidationError("Employee group name already exists")

        payload = data.model_dump()
        await EmployeeGroupRepository.update(db, group, payload)

        return await EmployeeGroupService.get_by_id(db, group_id, tenant_id)

    @staticmethod
    async def delete(db: AsyncSession, group_id: int, tenant_id: int) -> None:
        group = await EmployeeGroupRepository.get_by_id(db, group_id)
        if not group or group.tenant_id != tenant_id:
            raise NotFoundError("Employee group not found")
        await EmployeeGroupRepository.delete(db, group)


class EmployeeQueryService:
    """Service for querying employees (for member selection)."""

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        keyword: str | None = None,
    ) -> dict:
        employees, total = await EmployeeQueryRepository.get_paginated(
            db, tenant_id, page, per_page, keyword
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        items = [
            {
                "id": e.id,
                "username": e.username,
                "display_name": e.display_name,
            }
            for e in employees
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }
