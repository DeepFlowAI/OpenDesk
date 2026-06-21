"""
Auth router
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.db.deps import get_current_user, get_db, get_redis
from app.schemas.auth import LoginRequest, LoginResponse, RefreshResponse, UserInfo, UserPreferencesUpdate
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


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid access token for a fresh one (sliding expiry)."""
    new_token = await AuthService.refresh_token(db, current_user)
    return RefreshResponse(access_token=new_token)


@router.get("/me", response_model=UserInfo)
async def get_me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user profile with fresh effective permissions."""
    return await AuthService.get_current_user_info(db, current_user)


@router.patch("/me/preferences", response_model=UserInfo)
async def update_me_preferences(
    body: UserPreferencesUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current employee UI preferences."""
    return await AuthService.update_current_user_preferences(db, current_user, body)


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
