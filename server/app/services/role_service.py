"""
Role service.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.employee import Employee
from app.models.role import EmployeeRole
from app.models.role import Role
from app.repositories.role_repository import RoleRepository
from app.schemas.role import RoleCreate, RoleUpdate
from app.services.permission_catalog import (
    ALL_PERMISSION_KEYS,
    DATA_SCOPE_KEYS,
    DATA_SCOPE_VALUES,
    PERMISSION_DATA_SCOPE_RESOURCES,
    RESOURCE_CHAT_QUEUE,
    RESOURCE_PEER_CONVERSATION,
    SYSTEM_ROLE_PRESETS,
    missing_required_permissions,
    normalize_data_scopes,
    normalize_permissions,
    permission_tree,
)

LEGACY_SESSION_SCOPED_RESOURCES = {RESOURCE_PEER_CONVERSATION, RESOURCE_CHAT_QUEUE}


class RoleService:
    @staticmethod
    async def ensure_system_roles(db: AsyncSession, tenant_id: int) -> None:
        changed = False
        for key, preset in SYSTEM_ROLE_PRESETS.items():
            preset_permissions = normalize_permissions(preset["permissions"])
            preset_data_scopes = normalize_data_scopes(preset["data_scopes"])
            role = await RoleRepository.get_by_key(db, tenant_id, key)
            if role:
                sync_values = {
                    "name": preset["name"],
                    "description": preset["description"],
                    "is_system": True,
                    "is_active": True,
                    "permissions": preset_permissions,
                    "data_scopes": preset_data_scopes,
                }
                for field, value in sync_values.items():
                    if getattr(role, field) != value:
                        setattr(role, field, value)
                        changed = True
                continue
            db.add(
                Role(
                    tenant_id=tenant_id,
                    key=key,
                    name=preset["name"],
                    description=preset["description"],
                    is_system=True,
                    is_active=True,
                    permissions=preset_permissions,
                    data_scopes=preset_data_scopes,
                )
            )
            changed = True
        if changed:
            await db.flush()

    @staticmethod
    async def backfill_employee_roles(db: AsyncSession, tenant_id: int) -> None:
        await RoleService.ensure_system_roles(db, tenant_id)
        system_roles = await RoleRepository.get_by_keys(db, tenant_id, ["admin", "agent"])
        role_by_key = {role.key: role for role in system_roles}
        employees = (
            await db.execute(select(Employee).where(Employee.tenant_id == tenant_id))
        ).scalars().all()
        if not employees:
            return

        existing = (
            await db.execute(
                select(EmployeeRole.employee_id, EmployeeRole.role_id).where(
                    EmployeeRole.employee_id.in_([employee.id for employee in employees])
                )
            )
        ).all()
        existing_pairs = {(employee_id, role_id) for employee_id, role_id in existing}
        employees_with_assignments = {employee_id for employee_id, _role_id in existing}
        changed = False

        for employee in employees:
            if employee.id in employees_with_assignments:
                continue
            legacy_keys = [key for key in (employee.roles or []) if key in role_by_key]
            if not legacy_keys and "agent" in role_by_key:
                legacy_keys = ["agent"]
            for key in legacy_keys:
                role = role_by_key[key]
                pair = (employee.id, role.id)
                if pair in existing_pairs:
                    continue
                db.add(EmployeeRole(employee_id=employee.id, role_id=role.id))
                changed = True
        if changed:
            await db.commit()

    @staticmethod
    def get_permission_tree() -> dict:
        return {"tabs": permission_tree(), "data_scope_options": ["all", "group", "self"]}

    @staticmethod
    def _normalize_config(
        permissions: list[str],
        data_scopes: dict[str, str],
    ) -> tuple[list[str], dict[str, str]]:
        if not permissions:
            raise ValidationError("At least one permission is required")
        normalized_permissions = normalize_permissions(permissions)
        invalid_permissions = [key for key in normalized_permissions if key not in ALL_PERMISSION_KEYS]
        if invalid_permissions:
            raise ValidationError("Unsupported permission key")

        missing_requirements = missing_required_permissions(normalized_permissions)
        if missing_requirements:
            raise ValidationError(
                "Permission dependency missing",
                details={"missing_requirements": missing_requirements},
            )

        normalized_scopes = dict(data_scopes or {})
        for resource, scope in normalized_scopes.items():
            if resource not in DATA_SCOPE_KEYS or scope not in DATA_SCOPE_VALUES:
                raise ValidationError("Unsupported data scope")
        for permission in normalized_permissions:
            resource = PERMISSION_DATA_SCOPE_RESOURCES.get(permission)
            if resource:
                if resource in normalized_scopes:
                    continue
                if resource in LEGACY_SESSION_SCOPED_RESOURCES and "session_record" in normalized_scopes:
                    normalized_scopes[resource] = normalized_scopes["session_record"]
                else:
                    normalized_scopes[resource] = "self"
        return normalized_permissions, normalize_data_scopes(normalized_scopes)

    @staticmethod
    async def list_roles(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 10,
        keyword: str | None = None,
        role_type: str | None = None,
    ) -> dict:
        await RoleService.ensure_system_roles(db, tenant_id)
        items, total = await RoleRepository.get_paginated(
            db, tenant_id, page, per_page, keyword, role_type
        )
        await RoleRepository.attach_member_counts(db, items)
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_options(db: AsyncSession, tenant_id: int) -> dict:
        await RoleService.ensure_system_roles(db, tenant_id)
        return {"items": await RoleRepository.get_options(db, tenant_id)}

    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, role_id: int) -> Role:
        await RoleService.ensure_system_roles(db, tenant_id)
        role = await RoleRepository.get_by_id(db, role_id)
        if not role or role.tenant_id != tenant_id:
            raise NotFoundError("Role not found")
        await RoleRepository.attach_member_counts(db, [role])
        return role

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: RoleCreate) -> Role:
        await RoleService.ensure_system_roles(db, tenant_id)
        permissions, data_scopes = RoleService._normalize_config(data.permissions, data.data_scopes)
        existing = await RoleRepository.get_by_name(db, tenant_id, data.name)
        if existing:
            raise ValidationError("Role name already exists")
        role = await RoleRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "name": data.name,
                "description": data.description,
                "is_system": False,
                "is_active": data.is_active,
                "permissions": permissions,
                "data_scopes": data_scopes,
            },
        )
        role.member_count = 0
        return role

    @staticmethod
    async def update(db: AsyncSession, tenant_id: int, role_id: int, data: RoleUpdate) -> Role:
        role = await RoleService.get_by_id(db, tenant_id, role_id)
        if role.is_system:
            raise ForbiddenError("System roles are read-only")

        update_data = data.model_dump(exclude_unset=True)
        permissions = update_data.get("permissions", role.permissions or [])
        data_scopes = update_data.get("data_scopes", role.data_scopes or {})
        permissions, data_scopes = RoleService._normalize_config(permissions, data_scopes)
        update_data["permissions"] = permissions
        update_data["data_scopes"] = data_scopes

        if "name" in update_data and update_data["name"] != role.name:
            existing = await RoleRepository.get_by_name(db, tenant_id, update_data["name"])
            if existing:
                raise ValidationError("Role name already exists")

        role = await RoleRepository.update(db, role, update_data)
        await RoleRepository.attach_member_counts(db, [role])
        return role

    @staticmethod
    async def delete(db: AsyncSession, tenant_id: int, role_id: int) -> None:
        role = await RoleService.get_by_id(db, tenant_id, role_id)
        if role.is_system:
            raise ForbiddenError("System roles cannot be deleted")
        member_count = await RoleRepository.count_members(db, role_id)
        if member_count > 0:
            raise ValidationError(f"Role is assigned to {member_count} employees")
        await RoleRepository.delete(db, role)
