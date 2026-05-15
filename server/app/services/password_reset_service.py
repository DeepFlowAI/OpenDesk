"""
Password reset service
"""
import random
import logging

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import NotFoundError, RateLimitedError, InvalidCodeError, ValidationError
from app.core.security import hash_password
from app.repositories.tenant_repository import TenantRepository
from app.repositories.employee_repository import EmployeeRepository
from app.libs.email.factory import create_email_client
from app.schemas.password_reset import SendVerifyCodeRequest, ResetPasswordRequest

logger = logging.getLogger(__name__)

VERIFY_CODE_KEY = "verify_code:{tenant_id}:{user_id}"
VERIFY_COOLDOWN_KEY = "verify_cooldown:{tenant_id}:{user_id}"

ZH_SUBJECT = "【OpenDesk】找回密码验证码"
ZH_BODY = """您好，

您正在找回密码，您的验证码如下：

{code}

验证码 10 分钟内有效。请勿将验证码告知他人。若非本人操作，请忽略本邮件。

OpenDesk"""

EN_SUBJECT = "[OpenDesk] Password reset verification code"
EN_BODY = """Hello,

You are resetting your password. Your verification code is:

{code}

This code expires in 10 minutes. Do not share it with anyone. If you did not request this, please ignore this email.

OpenDesk"""


class PasswordResetService:

    @staticmethod
    async def send_verify_code(
        db: AsyncSession,
        redis: aioredis.Redis,
        data: SendVerifyCodeRequest,
    ) -> None:
        """Generate verification code and send to user email."""
        tenant = await TenantRepository.resolve_by_identifier(db, data.tenant)
        if not tenant or not tenant.is_active:
            raise NotFoundError("Tenant not found")

        user = await EmployeeRepository.get_by_username_or_email(db, tenant.id, data.username)
        if not user:
            raise NotFoundError("Account not found")

        if not user.email:
            raise ValidationError("User has no email configured")

        cooldown_key = VERIFY_COOLDOWN_KEY.format(tenant_id=tenant.id, user_id=user.id)
        if await redis.exists(cooldown_key):
            raise RateLimitedError("Too many attempts. Please try again later.")

        code = f"{random.randint(0, 999999):06d}"

        code_key = VERIFY_CODE_KEY.format(tenant_id=tenant.id, user_id=user.id)
        await redis.setex(code_key, settings.VERIFY_CODE_EXPIRE_SECONDS, code)
        await redis.setex(cooldown_key, settings.VERIFY_CODE_COOLDOWN_SECONDS, "1")

        is_zh = data.locale.startswith("zh")
        subject = ZH_SUBJECT if is_zh else EN_SUBJECT
        body = (ZH_BODY if is_zh else EN_BODY).format(code=code)

        email_client = create_email_client()
        try:
            await email_client.send(to=user.email, subject=subject, body=body)
        except Exception:
            logger.exception("Failed to send verification email to %s", user.email)
            await redis.delete(cooldown_key)
            raise ValidationError("Failed to send email. Please try again later.")

    @staticmethod
    async def reset_password(
        db: AsyncSession,
        redis: aioredis.Redis,
        data: ResetPasswordRequest,
    ) -> None:
        """Verify code and reset user password."""
        tenant = await TenantRepository.resolve_by_identifier(db, data.tenant)
        if not tenant or not tenant.is_active:
            raise NotFoundError("Tenant not found")

        user = await EmployeeRepository.get_by_username_or_email(db, tenant.id, data.username)
        if not user:
            raise NotFoundError("Account not found")

        code_key = VERIFY_CODE_KEY.format(tenant_id=tenant.id, user_id=user.id)
        stored_code = await redis.get(code_key)

        if not stored_code or stored_code != data.verify_code:
            raise InvalidCodeError("Invalid or expired verification code")

        new_hash = hash_password(data.new_password)
        await EmployeeRepository.update_password(db, user, new_hash)

        await redis.delete(code_key)
