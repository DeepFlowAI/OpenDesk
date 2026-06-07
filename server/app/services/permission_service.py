"""
Runtime permission resolution service.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.models.role import Role
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.role_repository import RoleRepository
from app.schemas.permission import EffectivePrincipal
from app.services.permission_catalog import (
    ALL_PERMISSION_KEYS,
    ADMIN_DATA_SCOPES,
    DATA_SCOPE_KEYS,
    PERMISSION_DATA_SCOPE_RESOURCES,
    SYSTEM_ROLE_KEYS,
    filter_effective_permissions,
    merge_data_scope,
    normalize_data_scopes,
    normalize_permissions,
)
from app.services.role_service import RoleService


class PermissionService:
    @staticmethod
    async def get_current_principal(
        db: AsyncSession,
        user_payload: dict,
    ) -> EffectivePrincipal:
        user_id = int(user_payload["user_id"])
        tenant_id = int(user_payload["tenant_id"])

        employee = await EmployeeRepository.get_by_id(db, user_id)
        if not employee or employee.tenant_id != tenant_id or not employee.is_active:
            raise UnauthorizedError("Invalid or disabled account")

        group_ids_by_employee = await EmployeeRepository.get_group_ids_by_employee_ids(db, [user_id])
        group_ids = group_ids_by_employee.get(user_id, [])
        legacy_roles = list(employee.roles or [])

        if employee.is_super_admin:
            return EffectivePrincipal(
                user_id=user_id,
                tenant_id=tenant_id,
                is_super_admin=True,
                role_ids=[],
                legacy_roles=legacy_roles,
                permissions=sorted(ALL_PERMISSION_KEYS),
                data_scopes=normalize_data_scopes(ADMIN_DATA_SCOPES),
                group_ids=group_ids,
            )

        roles = await RoleRepository.get_active_roles_by_employee_id(db, tenant_id, user_id)
        if not roles:
            roles = await PermissionService.get_legacy_system_roles(db, tenant_id, legacy_roles)
        permissions = PermissionService.merge_role_permissions(roles)
        data_scopes = PermissionService.merge_role_data_scopes(roles, permissions)

        return EffectivePrincipal(
            user_id=user_id,
            tenant_id=tenant_id,
            is_super_admin=False,
            role_ids=[role.id for role in roles],
            legacy_roles=legacy_roles,
            permissions=permissions,
            data_scopes=data_scopes,
            group_ids=group_ids,
        )

    @staticmethod
    def merge_role_permissions(roles: list[Role]) -> list[str]:
        raw_permissions: list[str] = []
        for role in roles:
            raw_permissions.extend(role.permissions or [])
        return filter_effective_permissions(normalize_permissions(raw_permissions))

    @staticmethod
    async def get_legacy_system_roles(
        db: AsyncSession,
        tenant_id: int,
        legacy_roles: list[str],
    ) -> list[Role]:
        role_keys = [role for role in dict.fromkeys(legacy_roles) if role in SYSTEM_ROLE_KEYS]
        if not role_keys:
            return []
        await RoleService.ensure_system_roles(db, tenant_id)
        roles = await RoleRepository.get_by_keys(db, tenant_id, role_keys)
        return [role for role in roles if role.is_active]

    @staticmethod
    def merge_role_data_scopes(roles: list[Role], permissions: list[str]) -> dict[str, str]:
        effective_permissions = set(permissions)
        required_resources = {
            resource
            for permission, resource in PERMISSION_DATA_SCOPE_RESOURCES.items()
            if permission in effective_permissions
        }
        merged: dict[str, str] = {}

        for role in roles:
            role_permissions = set(role.permissions or [])
            role_scopes = role.data_scopes or {}
            for permission, resource in PERMISSION_DATA_SCOPE_RESOURCES.items():
                if permission not in effective_permissions or permission not in role_permissions:
                    continue
                merged_scope = merge_data_scope(merged.get(resource), role_scopes.get(resource, "self"))
                if merged_scope:
                    merged[resource] = merged_scope

        for resource in required_resources:
            merged.setdefault(resource, "self")

        return normalize_data_scopes({key: value for key, value in merged.items() if key in DATA_SCOPE_KEYS})
