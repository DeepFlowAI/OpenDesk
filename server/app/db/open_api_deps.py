"""
Dependencies shared by tenant Open API routers.
"""

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.db.deps import get_db
from app.schemas.open_api import OpenApiContext
from app.services.api_key_service import ApiKeyService


def extract_bearer_api_key(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid API key")
    api_key = authorization[7:].strip()
    if not api_key:
        raise UnauthorizedError("Missing or invalid API key")
    return api_key


async def get_open_api_context(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> OpenApiContext:
    """Authenticate a tenant API Key and return safe Open API context."""
    return await ApiKeyService.authenticate_open_api_context(
        db,
        extract_bearer_api_key(authorization),
    )
