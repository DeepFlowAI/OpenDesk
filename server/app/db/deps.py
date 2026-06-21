from collections.abc import AsyncGenerator
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from app.core.exceptions import ForbiddenError
from app.db.session import AsyncSessionLocal
from app.schemas.permission import EffectivePrincipal
from app.services.permission_service import PermissionService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_redis() -> aioredis.Redis:
    from app.db.redis import redis_client
    return redis_client.client


async def get_current_user(authorization: str | None = Header(None)) -> dict:
    """Extract user payload from JWT Bearer token.

    Normalizes the payload so all consumers can use ``user["user_id"]``
    and ``user["tenant_id"]`` regardless of the raw JWT claim names.
    """
    from app.core.security import decode_access_token
    from app.core.exceptions import UnauthorizedError

    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid authorization header")
    token = authorization[7:]
    payload = decode_access_token(token)
    if not payload:
        raise UnauthorizedError("Invalid or expired token")

    # JWT stores user id in "sub" as a string — normalize to int "user_id"
    if "sub" in payload and "user_id" not in payload:
        payload["user_id"] = int(payload["sub"])

    # Ensure tenant_id is always the integer PK.
    # Old tokens may contain a string slug — force re-login in that case.
    if "tenant_id" in payload:
        try:
            payload["tenant_id"] = int(payload["tenant_id"])
        except (ValueError, TypeError):
            raise UnauthorizedError("Token contains invalid tenant_id, please re-login")

    return payload


async def get_optional_current_user(authorization: str | None = Header(None)) -> dict | None:
    """Best-effort JWT decode for optional auth (e.g. client telemetry)."""
    from app.core.security import decode_access_token

    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = decode_access_token(authorization[7:])
    if not payload:
        return None
    if "sub" in payload and "user_id" not in payload:
        try:
            payload["user_id"] = int(payload["sub"])
        except (ValueError, TypeError):
            return None
    if "tenant_id" in payload:
        try:
            payload["tenant_id"] = int(payload["tenant_id"])
        except (ValueError, TypeError):
            return None
    return payload


async def get_current_principal(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EffectivePrincipal:
    return await PermissionService.get_current_principal(db, current_user)


def require_permission(permission: str):
    async def dependency(
        principal: EffectivePrincipal = Depends(get_current_principal),
    ) -> EffectivePrincipal:
        if not principal.has_permission(permission):
            raise ForbiddenError("Permission denied")
        return principal

    return dependency


def require_any_permission(permissions: list[str]):
    async def dependency(
        principal: EffectivePrincipal = Depends(get_current_principal),
    ) -> EffectivePrincipal:
        if not principal.has_any_permission(permissions):
            raise ForbiddenError("Permission denied")
        return principal

    return dependency


def require_all_permissions(permissions: list[str]):
    async def dependency(
        principal: EffectivePrincipal = Depends(get_current_principal),
    ) -> EffectivePrincipal:
        if not principal.has_all_permissions(permissions):
            raise ForbiddenError("Permission denied")
        return principal

    return dependency


require_admin_access = require_permission("admin.access")
