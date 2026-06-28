"""
Auth schemas
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    tenant: str
    username: str
    password: str


class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str
    display_name: str | None = None
    avatar: str | None = None
    roles: list[str]
    tenant_id: int
    role_ids: list[int] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    data_scopes: dict[str, str] = Field(default_factory=dict)
    is_super_admin: bool = False
    group_ids: list[int] = Field(default_factory=list)
    preferences: dict[str, Any] = Field(default_factory=dict)


class UserPreferencesUpdate(BaseModel):
    preferences: dict[str, Any] = Field(default_factory=dict)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
