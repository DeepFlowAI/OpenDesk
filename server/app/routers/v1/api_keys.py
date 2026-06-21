"""
API Key management router.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_current_principal, get_db
from app.schemas.api_key import ApiKeyCreate, ApiKeyResponse, ApiKeySecretResponse
from app.schemas.permission import EffectivePrincipal
from app.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/api-keys", tags=["APIKeys"])


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """List API keys for the current tenant."""
    return await ApiKeyService.list_by_tenant(db, principal)


@router.post("", response_model=ApiKeySecretResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreate,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Create a tenant API key and return the secret once."""
    return await ApiKeyService.create(db, principal, body)


@router.post("/{api_key_id}/disable", response_model=ApiKeyResponse)
async def disable_api_key(
    api_key_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Disable an API key."""
    return await ApiKeyService.disable(db, principal, api_key_id)


@router.post("/{api_key_id}/enable", response_model=ApiKeyResponse)
async def enable_api_key(
    api_key_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Enable an API key."""
    return await ApiKeyService.enable(db, principal, api_key_id)


@router.post("/{api_key_id}/rotate", response_model=ApiKeySecretResponse)
async def rotate_api_key(
    api_key_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Rotate an API key and return the new secret once."""
    return await ApiKeyService.rotate(db, principal, api_key_id)


@router.delete("/{api_key_id}", status_code=status.HTTP_200_OK)
async def delete_api_key(
    api_key_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Delete a disabled API key."""
    await ApiKeyService.delete(db, principal, api_key_id)
    return {"message": "Deleted successfully"}
