"""
Dependencies shared by tenant Open API routers.
"""

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.db.deps import get_db
from app.db.session import AsyncSessionLocal
from app.schemas.open_api import OpenApiContext, OpenApiTaskPrincipal
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


async def get_open_api_context_short_session(
    authorization: str | None = Header(None),
) -> OpenApiContext:
    """Authenticate an API Key without retaining a request-scoped DB session."""
    async with AsyncSessionLocal() as db:
        return await ApiKeyService.authenticate_open_api_context(
            db,
            extract_bearer_api_key(authorization),
        )


async def get_open_api_task_principal(
    context: OpenApiContext = Depends(get_open_api_context),
) -> OpenApiTaskPrincipal:
    """Adapt the authenticated API Key context for task management services."""
    return OpenApiTaskPrincipal.from_context(context)


async def get_open_api_task_principal_short_session(
    context: OpenApiContext = Depends(get_open_api_context_short_session),
) -> OpenApiTaskPrincipal:
    """Build a task principal without retaining a DB session during uploads."""
    return OpenApiTaskPrincipal.from_context(context)
