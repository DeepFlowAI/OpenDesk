"""
Auth router
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.db.deps import get_db, get_redis
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.password_reset import (
    SendVerifyCodeRequest,
    SendVerifyCodeResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from app.services.auth_service import AuthService
from app.services.password_reset_service import PasswordResetService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """User login endpoint"""
    return await AuthService.login(db, body)


@router.post("/send-verify-code", response_model=SendVerifyCodeResponse)
async def send_verify_code(
    body: SendVerifyCodeRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Send password reset verification code to user email"""
    await PasswordResetService.send_verify_code(db, redis, body)
    return SendVerifyCodeResponse()


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Reset password with verification code"""
    await PasswordResetService.reset_password(db, redis, body)
    return ResetPasswordResponse()
