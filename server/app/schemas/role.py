"""
Role Pydantic schemas.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.services.permission_catalog import DATA_SCOPE_KEYS, DATA_SCOPE_VALUES


class PermissionNode(BaseModel):
    key: str
    name: str
    name_en: str
    type: str
    requires: str | None = None
    data_scope_resource: str | None = None


class PermissionModule(BaseModel):
    key: str
    name: str
    name_en: str
    permissions: list[PermissionNode]


class PermissionTab(BaseModel):
    key: str
    name: str
    name_en: str
    modules: list[PermissionModule]


class PermissionTreeResponse(BaseModel):
    tabs: list[PermissionTab]
    data_scope_options: list[str]


class RoleBase(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True
    permissions: list[str] = []
    data_scopes: dict[str, str] = {}

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Role name is required")
        if len(value) > 64:
            raise ValueError("Role name must be at most 64 characters")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) > 255:
            raise ValueError("Description must be at most 255 characters")
        return value or None

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: list[str]) -> list[str]:
        return sorted(dict.fromkeys(value))

    @field_validator("data_scopes")
    @classmethod
    def validate_data_scopes(cls, value: dict[str, str]) -> dict[str, str]:
        for resource, scope in value.items():
            if resource not in DATA_SCOPE_KEYS:
                raise ValueError("Unsupported data scope resource")
            if scope not in DATA_SCOPE_VALUES:
                raise ValueError("Unsupported data scope value")
        return value


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    permissions: list[str] | None = None
    data_scopes: dict[str, str] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Role name cannot be empty")
        if len(value) > 64:
            raise ValueError("Role name must be at most 64 characters")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) > 255:
            raise ValueError("Description must be at most 255 characters")
        return value or None

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return sorted(dict.fromkeys(value))

    @field_validator("data_scopes")
    @classmethod
    def validate_data_scopes(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        for resource, scope in value.items():
            if resource not in DATA_SCOPE_KEYS:
                raise ValueError("Unsupported data scope resource")
            if scope not in DATA_SCOPE_VALUES:
                raise ValueError("Unsupported data scope value")
        return value


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    key: str | None = None
    name: str
    description: str | None = None
    is_system: bool
    is_active: bool
    permissions: list[str]
    data_scopes: dict[str, str]
    member_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RoleListResponse(BaseModel):
    items: list[RoleResponse]
    total: int
    page: int
    per_page: int
    pages: int


class RoleOption(BaseModel):
    id: int
    key: str | None = None
    name: str
    description: str | None = None
    is_system: bool
    is_active: bool
    permissions: list[str]


class RoleOptionsResponse(BaseModel):
    items: list[RoleOption]
