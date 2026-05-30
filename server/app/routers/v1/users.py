"""
Users router — end-user (visitor/customer) CRUD, list & detail APIs
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.user import (
    UserResponse,
    UserCreate,
    UserUpdate,
    UserListResponse,
    UserQueryRequest,
    ViewCountsResponse,
)
from app.schemas.entity_change import EntityChangeListResponse
from app.schemas.user_view import UserViewResponse
from app.schemas.view_group import ViewGroupRequest, ViewGroupResponse
from app.services.entity_change_service import EntityChangeService
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/query", response_model=UserListResponse)
async def query_users(
    body: UserQueryRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Query users with optional view-based system filters + temporary filters.
    System view filters are applied from view_id config;
    temp_conditions are additional client-side filters (session-only, not persisted).
    """
    tenant_id = current_user["tenant_id"]
    return await UserService.query_users(db, tenant_id, body)


@router.get("/views/enabled", response_model=list[UserViewResponse])
async def list_enabled_views(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all enabled user views for the sidebar (ordered by sort_order)."""
    tenant_id = current_user["tenant_id"]
    return await UserService.get_enabled_views(db, tenant_id)


@router.get("/views/counts", response_model=ViewCountsResponse)
async def get_view_counts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user count per enabled view + total (for sidebar numbers)."""
    tenant_id = current_user["tenant_id"]
    return await UserService.get_view_counts(db, tenant_id)


@router.post("/views/{view_id}/groups", response_model=ViewGroupResponse)
async def get_view_groups(
    view_id: int,
    body: ViewGroupRequest | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate users under the given view by its configured group field."""
    tenant_id = current_user["tenant_id"]
    payload = body or ViewGroupRequest()
    return await UserService.get_view_groups(db, tenant_id, view_id, payload)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new end user under the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await UserService.create_user(
        db,
        tenant_id,
        body,
        actor_id=current_user.get("user_id"),
    )


@router.get("/{user_ref}", response_model=UserResponse)
async def get_user(
    user_ref: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single user by public ID, with numeric ID compatibility."""
    tenant_id = current_user["tenant_id"]
    return await UserService.get_by_ref(db, tenant_id, user_ref)


@router.get("/{user_id}/changes", response_model=EntityChangeListResponse)
async def list_user_changes(
    user_id: int,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List field-level changes for a user."""
    tenant_id = current_user["tenant_id"]
    return await EntityChangeService.get_paginated(
        db,
        tenant_id,
        "user",
        user_id,
        page,
        per_page,
    )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: UserUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing end user."""
    tenant_id = current_user["tenant_id"]
    return await UserService.update_user(
        db,
        tenant_id,
        user_id,
        body,
        actor_id=current_user.get("user_id"),
    )


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an existing end user."""
    tenant_id = current_user["tenant_id"]
    await UserService.delete_user(db, tenant_id, user_id)
    return {"message": "Deleted successfully"}
