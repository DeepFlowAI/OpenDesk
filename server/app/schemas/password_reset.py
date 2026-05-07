"""
Password reset schemas
"""
from pydantic import BaseModel


class SendVerifyCodeRequest(BaseModel):
    tenant: str
    username: str
    locale: str = "zh"


class SendVerifyCodeResponse(BaseModel):
    message: str = "ok"


class ResetPasswordRequest(BaseModel):
    tenant: str
    username: str
    verify_code: str
    new_password: str


class ResetPasswordResponse(BaseModel):
    message: str = "ok"
