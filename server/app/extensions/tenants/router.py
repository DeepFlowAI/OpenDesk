"""Tenants router — external API for Tenant Platform integration.

Authenticated via the X-API-Key header.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_platform_auth import verify_tenant_api_key
from app.db.deps import get_db

from .schemas import (
    TenantCreate,
    TenantUpdate,
    TenantStatusUpdate,
    TenantResponse,
    TenantListResponse,
)
from .service import TenantService

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    page: int = 1,
    per_page: int = 10,
    _key: str = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await TenantService.list_tenants(db, page, per_page)


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    _key: str = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await TenantService.create(db, body)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    _key: str = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await TenantService.get_by_id(db, tenant_id)


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    _key: str = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await TenantService.update(db, tenant_id, body)


@router.patch("/{tenant_id}/status", response_model=TenantResponse)
async def update_tenant_status(
    tenant_id: str,
    body: TenantStatusUpdate,
    _key: str = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await TenantService.update_status(db, tenant_id, body)
