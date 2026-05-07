"""
UserView router — API endpoints for user view management
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.user_view import (
    UserViewCreate,
    UserViewUpdate,
    UserViewResponse,
    UserViewListResponse,
    UserViewToggleRequest,
    UserViewSortRequest,
)
from app.services.user_view_service import UserViewService

router = APIRouter(prefix="/user-views", tags=["UserViews"])


@router.put("/sort", status_code=status.HTTP_200_OK)
async def sort_user_views(
    body: UserViewSortRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch update sort order for user views"""
    tenant_id = current_user["tenant_id"]
    await UserViewService.update_sort(db, tenant_id, body)
    return {"message": "Sort order updated"}


@router.get("", response_model=UserViewListResponse)
async def list_user_views(
    page: int = 1,
    per_page: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all user views for the current tenant"""
    tenant_id = current_user["tenant_id"]
    return await UserViewService.get_paginated(db, tenant_id, page, per_page)


@router.post("", response_model=UserViewResponse, status_code=status.HTTP_201_CREATED)
async def create_user_view(
    body: UserViewCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user view"""
    tenant_id = current_user["tenant_id"]
    return await UserViewService.create(db, tenant_id, body)


@router.get("/{view_id}", response_model=UserViewResponse)
async def get_user_view(
    view_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a user view by ID"""
    tenant_id = current_user["tenant_id"]
    return await UserViewService.get_by_id(db, view_id, tenant_id)


@router.put("/{view_id}", response_model=UserViewResponse)
async def update_user_view(
    view_id: int,
    body: UserViewUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a user view"""
    tenant_id = current_user["tenant_id"]
    return await UserViewService.update(db, view_id, tenant_id, body)


@router.put("/{view_id}/toggle", response_model=UserViewResponse)
async def toggle_user_view(
    view_id: int,
    body: UserViewToggleRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle user view enabled/disabled"""
    tenant_id = current_user["tenant_id"]
    return await UserViewService.toggle_enabled(db, view_id, tenant_id, body.is_enabled)


@router.delete("/{view_id}", status_code=status.HTTP_200_OK)
async def delete_user_view(
    view_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user view"""
    tenant_id = current_user["tenant_id"]
    await UserViewService.delete(db, view_id, tenant_id)
    return {"message": "Deleted successfully"}
