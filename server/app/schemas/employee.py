"""
Employee Pydantic schemas
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator


VALID_ROLES = {"admin", "agent"}
VALID_LANGUAGES = {"system", "zh", "en"}


class EmployeeRoleAssignment(BaseModel):
    id: int
    key: str | None = None
    name: str
    is_system: bool
    is_active: bool
    permissions: list[str] = []


class EmployeeCreate(BaseModel):
    name: str
    nickname: str | None = None
    job_number: str | None = None
    username: str
    email: str
    phone: str | None = None
    password: str
    avatar: str | None = None
    roles: list[str] = ["agent"]
    role_ids: list[int] | None = None
    max_concurrent: int = 10
    default_language: str = "system"
    group_ids: list[int] = []

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        if len(v) > 64:
            raise ValueError("Name must be at most 64 characters")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Username is required")
        if len(v) > 32:
            raise ValueError("Username must be at most 32 characters")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Email is required")
        if "@" not in v:
            raise ValueError("Invalid email format")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8 or len(v) > 32:
            raise ValueError("Password must be 8-32 characters")
        return v

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one role is required")
        for role in v:
            if role not in VALID_ROLES:
                raise ValueError(f"Each role must be one of: {', '.join(VALID_ROLES)}")
        return sorted(set(v))

    @field_validator("max_concurrent")
    @classmethod
    def validate_max_concurrent(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Max concurrent must be at least 1")
        return v

    @field_validator("default_language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v not in VALID_LANGUAGES:
            raise ValueError(f"Language must be one of: {', '.join(VALID_LANGUAGES)}")
        return v

    @field_validator("group_ids")
    @classmethod
    def validate_group_ids(cls, v: list[int]) -> list[int]:
        for group_id in v:
            if group_id <= 0:
                raise ValueError("Group ID must be positive")
        return list(dict.fromkeys(v))

    @field_validator("role_ids")
    @classmethod
    def validate_role_ids(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        if not v:
            raise ValueError("At least one role is required")
        for role_id in v:
            if role_id <= 0:
                raise ValueError("Role ID must be positive")
        return list(dict.fromkeys(v))


class EmployeeUpdate(BaseModel):
    name: str | None = None
    nickname: str | None = None
    job_number: str | None = None
    username: str | None = None
    email: str | None = None
    phone: str | None = None
    password: str | None = None
    avatar: str | None = None
    roles: list[str] | None = None
    role_ids: list[int] | None = None
    max_concurrent: int | None = None
    default_language: str | None = None
    group_ids: list[int] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Name cannot be empty")
            if len(v) > 64:
                raise ValueError("Name must be at most 64 characters")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Username cannot be empty")
            if len(v) > 32:
                raise ValueError("Username must be at most 32 characters")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Email cannot be empty")
            if "@" not in v:
                raise ValueError("Invalid email format")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str | None) -> str | None:
        if v is not None and v != "":
            if len(v) < 8 or len(v) > 32:
                raise ValueError("Password must be 8-32 characters")
        return v

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            if not v:
                raise ValueError("At least one role is required")
            for role in v:
                if role not in VALID_ROLES:
                    raise ValueError(f"Each role must be one of: {', '.join(VALID_ROLES)}")
            return sorted(set(v))
        return v

    @field_validator("max_concurrent")
    @classmethod
    def validate_max_concurrent(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("Max concurrent must be at least 1")
        return v

    @field_validator("default_language")
    @classmethod
    def validate_language(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_LANGUAGES:
            raise ValueError(f"Language must be one of: {', '.join(VALID_LANGUAGES)}")
        return v

    @field_validator("group_ids")
    @classmethod
    def validate_group_ids(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        for group_id in v:
            if group_id <= 0:
                raise ValueError("Group ID must be positive")
        return list(dict.fromkeys(v))

    @field_validator("role_ids")
    @classmethod
    def validate_role_ids(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("At least one role is required")
        for role_id in v:
            if role_id <= 0:
                raise ValueError("Role ID must be positive")
        return list(dict.fromkeys(v))


class StatusUpdate(BaseModel):
    is_active: bool


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    nickname: str | None = None
    job_number: str | None = None
    username: str
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None
    roles: list[str]
    role_ids: list[int] = []
    role_assignments: list[EmployeeRoleAssignment] = []
    is_active: bool
    max_concurrent: int
    default_language: str
    is_super_admin: bool
    group_ids: list[int] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EmployeeListResponse(BaseModel):
    items: list[EmployeeResponse]
    total: int
    page: int
    per_page: int
    pages: int
