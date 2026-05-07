"""
OrganizationView router — API endpoints for organization view management
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.organization_view import (
    OrganizationViewCreate,
    OrganizationViewUpdate,
    OrganizationViewResponse,
    OrganizationViewListResponse,
    OrganizationViewToggleRequest,
    OrganizationViewSortRequest,
)
from app.services.organization_view_service import OrganizationViewService

router = APIRouter(prefix="/organization-views", tags=["OrganizationViews"])


@router.put("/sort", status_code=status.HTTP_200_OK)
async def sort_organization_views(
    body: OrganizationViewSortRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch update sort order for organization views"""
    tenant_id = current_user["tenant_id"]
    await OrganizationViewService.update_sort(db, tenant_id, body)
    return {"message": "Sort order updated"}


@router.get("", response_model=OrganizationViewListResponse)
async def list_organization_views(
    page: int = 1,
    per_page: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all organization views for the current tenant"""
    tenant_id = current_user["tenant_id"]
    return await OrganizationViewService.get_paginated(db, tenant_id, page, per_page)


@router.post("", response_model=OrganizationViewResponse, status_code=status.HTTP_201_CREATED)
async def create_organization_view(
    body: OrganizationViewCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new organization view"""
    tenant_id = current_user["tenant_id"]
    return await OrganizationViewService.create(db, tenant_id, body)


@router.get("/{view_id}", response_model=OrganizationViewResponse)
async def get_organization_view(
    view_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an organization view by ID"""
    tenant_id = current_user["tenant_id"]
    return await OrganizationViewService.get_by_id(db, view_id, tenant_id)


@router.put("/{view_id}", response_model=OrganizationViewResponse)
async def update_organization_view(
    view_id: int,
    body: OrganizationViewUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an organization view"""
    tenant_id = current_user["tenant_id"]
    return await OrganizationViewService.update(db, view_id, tenant_id, body)


@router.put("/{view_id}/toggle", response_model=OrganizationViewResponse)
async def toggle_organization_view(
    view_id: int,
    body: OrganizationViewToggleRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle organization view enabled/disabled"""
    tenant_id = current_user["tenant_id"]
    return await OrganizationViewService.toggle_enabled(db, view_id, tenant_id, body.is_enabled)


@router.delete("/{view_id}", status_code=status.HTTP_200_OK)
async def delete_organization_view(
    view_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an organization view"""
    tenant_id = current_user["tenant_id"]
    await OrganizationViewService.delete(db, view_id, tenant_id)
    return {"message": "Deleted successfully"}
