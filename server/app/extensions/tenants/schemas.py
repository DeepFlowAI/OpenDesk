"""
Tenant schemas — matching Tenant Platform API spec
"""
import re
from datetime import datetime
from pydantic import BaseModel, field_validator

from app.repositories.tenant_repository import (
    TENANT_SLUG_MAX_LENGTH,
    is_valid_tenant_slug,
    normalize_tenant_slug,
)


class TenantCreate(BaseModel):
    name: str
    slug: str | None = None
    remark: str | None = None
    admin_username: str
    admin_password: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 64):
            raise ValueError("name must be 1–64 characters")
        return v

    @field_validator("remark")
    @classmethod
    def validate_remark(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 256:
            raise ValueError("remark must be at most 256 characters")
        return v

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        normalized = normalize_tenant_slug(v)
        if normalized is None:
            return None
        if len(normalized) > TENANT_SLUG_MAX_LENGTH or not is_valid_tenant_slug(normalized):
            raise ValueError("slug must be 2-128 chars and may contain letters, digits, -, _, . and /")
        return normalized

    @field_validator("admin_username")
    @classmethod
    def validate_admin_username(cls, v: str) -> str:
        v = v.strip()
        if not (3 <= len(v) <= 64):
            raise ValueError("admin_username must be 3–64 characters")
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("admin_username may only contain letters, digits and underscores")
        return v

    @field_validator("admin_password")
    @classmethod
    def validate_admin_password(cls, v: str) -> str:
        if not (8 <= len(v) <= 64):
            raise ValueError("admin_password must be 8–64 characters")
        return v


class TenantUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    remark: str | None = None
    admin_username: str | None = None
    admin_password: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not (1 <= len(v) <= 64):
                raise ValueError("name must be 1–64 characters")
        return v

    @field_validator("remark")
    @classmethod
    def validate_remark(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 256:
            raise ValueError("remark must be at most 256 characters")
        return v

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        normalized = normalize_tenant_slug(v)
        if normalized is None:
            return None
        if len(normalized) > TENANT_SLUG_MAX_LENGTH or not is_valid_tenant_slug(normalized):
            raise ValueError("slug must be 2-128 chars and may contain letters, digits, -, _, . and /")
        return normalized

    @field_validator("admin_username")
    @classmethod
    def validate_admin_username(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not (3 <= len(v) <= 64):
                raise ValueError("admin_username must be 3–64 characters")
            if not re.match(r"^[a-zA-Z0-9_]+$", v):
                raise ValueError("admin_username may only contain letters, digits and underscores")
        return v

    @field_validator("admin_password")
    @classmethod
    def validate_admin_password(cls, v: str | None) -> str | None:
        if v is not None and v != "" and not (8 <= len(v) <= 64):
            raise ValueError("admin_password must be 8–64 characters")
        return v


class TenantStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("enabled", "disabled"):
            raise ValueError("status must be 'enabled' or 'disabled'")
        return v


class TenantResponse(BaseModel):
    id: str
    slug: str | None = None
    name: str
    remark: str | None = None
    status: str
    admin_username: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class TenantListResponse(BaseModel):
    items: list[TenantResponse]
    total: int
    page: int
    per_page: int
    pages: int
