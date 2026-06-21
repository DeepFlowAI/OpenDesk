"""
Open API router authenticated by tenant API keys.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db
from app.db.open_api_deps import get_open_api_context
from app.schemas.api_key import ContextTokenRequest, ContextTokenResponse
from app.schemas.open_api import OpenApiContext
from app.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/open", tags=["OpenAPI"])


@router.post(
    "/context-token",
    response_model=ContextTokenResponse,
    response_model_by_alias=True,
)
async def issue_context_token(
    body: ContextTokenRequest,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Issue a short-lived Web SDK context token."""
    return await ApiKeyService.issue_context_token(
        db,
        context,
        body,
    )
