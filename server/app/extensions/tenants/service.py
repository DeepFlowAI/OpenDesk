"""Tenant service — business logic for tenant CRUD (Tenant Platform API)."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ConflictError
from app.core.security import hash_password
from app.models.employee import Employee
from app.repositories.tenant_repository import TenantRepository
from app.repositories.employee_repository import EmployeeRepository
from app.services.tenant_init_service import init_tenant_data

from .schemas import (
    TenantCreate,
    TenantUpdate,
    TenantStatusUpdate,
    TenantResponse,
)


def _tenant_to_response(tenant, admin_username: str | None = None) -> TenantResponse:
    return TenantResponse(
        id=tenant.tenant_id,
        slug=tenant.slug,
        name=tenant.name,
        remark=tenant.remark,
        status="enabled" if tenant.is_active else "disabled",
        admin_username=admin_username,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )


async def _get_admin_user(db: AsyncSession, tenant_pk: int) -> Employee | None:
    """Get the super-admin employee for a tenant."""
    from sqlalchemy import select
    from app.models.employee import Employee as EmployeeModel

    result = await db.execute(
        select(EmployeeModel)
        .where(EmployeeModel.tenant_id == tenant_pk, EmployeeModel.is_super_admin.is_(True))
        .limit(1)
    )
    return result.scalar_one_or_none()


class TenantService:

    @staticmethod
    async def _ensure_slug_available(
        db: AsyncSession,
        slug: str | None,
        current_tenant_pk: int | None = None,
    ) -> None:
        """Ensure slug does not conflict with another tenant slug or tenant_id."""
        if slug is None:
            return
        conflict = await TenantRepository.get_slug_conflict(db, slug, current_tenant_pk)
        if conflict:
            raise ConflictError("Tenant slug already exists")

    @staticmethod
    async def list_tenants(db: AsyncSession, page: int = 1, per_page: int = 10) -> dict:
        per_page = max(1, min(per_page, 100))
        page = max(1, page)

        tenants, total = await TenantRepository.get_paginated(db, page, per_page)
        pages = (total + per_page - 1) // per_page if total > 0 else 0

        items = []
        for t in tenants:
            admin = await _get_admin_user(db, t.id)
            items.append(_tenant_to_response(t, admin.username if admin else None))

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def create(db: AsyncSession, data: TenantCreate) -> TenantResponse:
        existing = await TenantRepository.get_by_name(db, data.name)
        if existing:
            raise ConflictError("Tenant name already exists")

        await TenantService._ensure_slug_available(db, data.slug)

        tenant_id = uuid.uuid4().hex[:16]
        tenant = await TenantRepository.create(db, {
            "tenant_id": tenant_id,
            "slug": data.slug,
            "name": data.name,
            "remark": data.remark,
            "is_active": True,
        })

        admin_user = await EmployeeRepository.create(db, {
            "tenant_id": tenant.id,
            "username": data.admin_username,
            "name": data.admin_username,
            "password_hash": hash_password(data.admin_password),
            "roles": ["admin"],
            "is_super_admin": True,
            "is_active": True,
        })

        await init_tenant_data(db, tenant.id)

        return _tenant_to_response(tenant, admin_user.username)

    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: str) -> TenantResponse:
        tenant = await TenantRepository.get_by_tenant_id(db, tenant_id)
        if not tenant:
            raise NotFoundError("Tenant not found")
        admin = await _get_admin_user(db, tenant.id)
        return _tenant_to_response(tenant, admin.username if admin else None)

    @staticmethod
    async def update(
        db: AsyncSession, tenant_id: str, data: TenantUpdate
    ) -> TenantResponse:
        tenant = await TenantRepository.get_by_tenant_id(db, tenant_id)
        if not tenant:
            raise NotFoundError("Tenant not found")

        update_fields: dict = {}
        if data.name is not None:
            dup = await TenantRepository.get_by_name(db, data.name)
            if dup and dup.id != tenant.id:
                raise ConflictError("Tenant name already exists")
            update_fields["name"] = data.name
        if data.remark is not None:
            update_fields["remark"] = data.remark
        if "slug" in data.model_fields_set:
            await TenantService._ensure_slug_available(db, data.slug, tenant.id)
            update_fields["slug"] = data.slug

        if update_fields:
            tenant = await TenantRepository.update(db, tenant, update_fields)

        admin = await _get_admin_user(db, tenant.id)

        if data.admin_username is not None and admin:
            if data.admin_username != admin.username:
                existing = await EmployeeRepository.get_by_username_in_tenant(
                    db, tenant.id, data.admin_username
                )
                if existing:
                    raise ConflictError("Admin username already occupied")
                await EmployeeRepository.update(db, admin, {"username": data.admin_username, "name": data.admin_username})

        if data.admin_password and admin:
            await EmployeeRepository.update(
                db, admin, {"password_hash": hash_password(data.admin_password)}
            )

        admin = await _get_admin_user(db, tenant.id)
        return _tenant_to_response(tenant, admin.username if admin else None)

    @staticmethod
    async def update_status(
        db: AsyncSession, tenant_id: str, data: TenantStatusUpdate
    ) -> TenantResponse:
        tenant = await TenantRepository.get_by_tenant_id(db, tenant_id)
        if not tenant:
            raise NotFoundError("Tenant not found")

        is_active = data.status == "enabled"
        tenant = await TenantRepository.update(db, tenant, {"is_active": is_active})
        admin = await _get_admin_user(db, tenant.id)
        return _tenant_to_response(tenant, admin.username if admin else None)
