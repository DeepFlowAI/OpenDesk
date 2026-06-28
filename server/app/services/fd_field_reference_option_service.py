"""
Read-only reference option queries for field value editors.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.employee_group_repository import EmployeeGroupRepository
from app.repositories.employee_repository import EmployeeRepository


class FdFieldReferenceOptionService:
    @staticmethod
    def _pagination(total: int, page: int, per_page: int) -> dict:
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if total > 0 else 0,
        }

    @staticmethod
    async def list_employee_groups(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        keyword: str | None = None,
        member_id: int | None = None,
    ) -> dict:
        items, total = await EmployeeGroupRepository.get_paginated(
            db, tenant_id, page, per_page, keyword, member_id
        )
        return {
            "items": items,
            **FdFieldReferenceOptionService._pagination(total, page, per_page),
        }

    @staticmethod
    async def get_employee_group(
        db: AsyncSession,
        tenant_id: int,
        group_id: int,
    ) -> dict:
        group = await EmployeeGroupRepository.get_by_id(db, group_id)
        if not group or group.tenant_id != tenant_id:
            raise NotFoundError("Employee group not found")
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "member_count": len(group.members),
            "created_at": group.created_at,
            "updated_at": group.updated_at,
        }

    @staticmethod
    async def list_employees(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        keyword: str | None = None,
        group_id: int | None = None,
    ) -> dict:
        items, total = await EmployeeRepository.get_paginated(
            db,
            tenant_id,
            page,
            per_page,
            keyword,
            status="active",
            group_id=group_id,
        )
        return {
            "items": items,
            **FdFieldReferenceOptionService._pagination(total, page, per_page),
        }

    @staticmethod
    async def get_employee(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
    ):
        employee = await EmployeeRepository.get_by_id(db, employee_id)
        if not employee or employee.tenant_id != tenant_id:
            raise NotFoundError("Employee not found")
        return employee
