"""
Employee service — business logic for employee management
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError, ForbiddenError
from app.core.security import hash_password
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, StatusUpdate


class EmployeeService:

    @staticmethod
    async def _validate_group_ids(
        db: AsyncSession, tenant_id: int, group_ids: list[int]
    ) -> None:
        """Ensure all selected employee groups belong to the current tenant."""
        existing_ids = await EmployeeRepository.get_existing_group_ids(db, tenant_id, group_ids)
        missing_ids = [group_id for group_id in group_ids if group_id not in existing_ids]
        if missing_ids:
            raise ValidationError("Employee group not found")

    @staticmethod
    async def list_employees(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 10,
        keyword: str | None = None,
        role: list[str] | None = None,
        status: str | None = None,
        group_id: int | None = None,
    ) -> dict:
        """List employees with filtering and pagination."""
        items, total = await EmployeeRepository.get_paginated(
            db,
            tenant_id,
            page,
            per_page,
            keyword,
            role_filters=role,
            status=status,
            group_id=group_id,
        )
        await EmployeeRepository.attach_group_ids(db, items)
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, employee_id: int):
        """Get single employee by ID, scoped to tenant."""
        user = await EmployeeRepository.get_by_id(db, employee_id)
        if not user or user.tenant_id != tenant_id:
            raise NotFoundError("Employee not found")
        await EmployeeRepository.attach_group_ids(db, [user])
        return user

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: EmployeeCreate):
        """Create a new employee."""
        existing = await EmployeeRepository.get_by_username_in_tenant(db, tenant_id, data.username)
        if existing:
            raise ValidationError("Username already exists in this tenant")

        await EmployeeService._validate_group_ids(db, tenant_id, data.group_ids)

        create_data = {
            "tenant_id": tenant_id,
            "name": data.name,
            "nickname": data.nickname,
            "job_number": data.job_number,
            "username": data.username,
            "email": data.email,
            "phone": data.phone,
            "password_hash": hash_password(data.password),
            "avatar": data.avatar,
            "roles": data.roles,
            "max_concurrent": data.max_concurrent,
            "default_language": data.default_language,
        }
        user = await EmployeeRepository.create(db, create_data)
        if data.group_ids:
            await EmployeeRepository.replace_group_ids(db, user.id, data.group_ids)
        user.group_ids = data.group_ids
        return user

    @staticmethod
    async def update(
        db: AsyncSession, tenant_id: int, employee_id: int, data: EmployeeUpdate
    ):
        """Update an existing employee."""
        user = await EmployeeRepository.get_by_id(db, employee_id)
        if not user or user.tenant_id != tenant_id:
            raise NotFoundError("Employee not found")

        update_data = data.model_dump(exclude_unset=True)
        group_ids = update_data.pop("group_ids", None)
        if group_ids is not None:
            await EmployeeService._validate_group_ids(db, tenant_id, group_ids)

        if "username" in update_data and update_data["username"] != user.username:
            existing = await EmployeeRepository.get_by_username_in_tenant(
                db, tenant_id, update_data["username"]
            )
            if existing:
                raise ValidationError("Username already exists in this tenant")

        if "password" in update_data:
            pwd = update_data.pop("password")
            if pwd:
                update_data["password_hash"] = hash_password(pwd)

        user = await EmployeeRepository.update(db, user, update_data)
        if group_ids is not None:
            await EmployeeRepository.replace_group_ids(db, user.id, group_ids)
            user.group_ids = group_ids
        else:
            await EmployeeRepository.attach_group_ids(db, [user])
        return user

    @staticmethod
    async def delete(db: AsyncSession, tenant_id: int, employee_id: int) -> None:
        """Delete an employee. Super admins cannot be deleted."""
        user = await EmployeeRepository.get_by_id(db, employee_id)
        if not user or user.tenant_id != tenant_id:
            raise NotFoundError("Employee not found")
        if user.is_super_admin:
            raise ForbiddenError("Cannot delete super admin account")
        await EmployeeRepository.delete(db, user)

    @staticmethod
    async def update_status(
        db: AsyncSession, tenant_id: int, employee_id: int, data: StatusUpdate
    ):
        """Toggle employee active status."""
        user = await EmployeeRepository.get_by_id(db, employee_id)
        if not user or user.tenant_id != tenant_id:
            raise NotFoundError("Employee not found")
        user = await EmployeeRepository.update(db, user, {"is_active": data.is_active})
        await EmployeeRepository.attach_group_ids(db, [user])
        return user
