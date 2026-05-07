from collections.abc import AsyncGenerator
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from app.db.session import AsyncSessionLocal


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
