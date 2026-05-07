"""
Auth schemas
"""
from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    tenant: str
    username: str
    password: str


class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str | None = None
    avatar: str | None = None
    roles: list[str]
    tenant_id: int


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
