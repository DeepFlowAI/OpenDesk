"""
Runtime permission schemas.
"""
from pydantic import BaseModel, Field


class EffectivePrincipal(BaseModel):
    user_id: int
    tenant_id: int
    is_super_admin: bool = False
    role_ids: list[int] = Field(default_factory=list)
    legacy_roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    data_scopes: dict[str, str] = Field(default_factory=dict)
    group_ids: list[int] = Field(default_factory=list)

    def has_permission(self, permission: str) -> bool:
        return self.is_super_admin or permission in self.permissions

    def has_any_permission(self, permissions: list[str]) -> bool:
        return self.is_super_admin or any(permission in self.permissions for permission in permissions)

    def has_all_permissions(self, permissions: list[str]) -> bool:
        return self.is_super_admin or all(permission in self.permissions for permission in permissions)
