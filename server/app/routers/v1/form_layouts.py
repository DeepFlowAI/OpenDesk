"""
Form layout router — CRUD endpoints for ticket form layouts
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.fd_form_layout import (
    FdFormLayoutCreate,
    FdFormLayoutUpdate,
    FdFormLayoutResponse,
    FdFormLayoutSummaryListResponse,
)
from app.services.fd_form_layout_service import FdFormLayoutService

router = APIRouter(prefix="/form-layouts", tags=["FormLayouts"])


@router.get("", response_model=FdFormLayoutSummaryListResponse)
async def list_form_layouts(
    page: int = 1,
    per_page: int = 50,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all form layouts for the tenant"""
    return await FdFormLayoutService.get_paginated(db, user["tenant_id"], page, per_page)


@router.post("", response_model=FdFormLayoutResponse, status_code=status.HTTP_201_CREATED)
async def create_form_layout(
    body: FdFormLayoutCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a form layout with nested sections/tabs/fields"""
    return await FdFormLayoutService.create(db, user["tenant_id"], body)


@router.get("/by-scene/{scene}", response_model=FdFormLayoutResponse)
async def get_form_layout_by_scene(
    scene: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get form layout by scene name (e.g. new_ticket, ticket_detail)"""
    from app.repositories.fd_form_layout_repository import FdFormLayoutRepository
    item = await FdFormLayoutRepository.get_by_scene(db, user["tenant_id"], scene)
    if not item:
        from app.core.exceptions import NotFoundError
        raise NotFoundError(f"No form layout found for scene '{scene}'")
    return item


@router.get("/{layout_id}", response_model=FdFormLayoutResponse)
async def get_form_layout(
    layout_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get form layout by ID with full nested data"""
    return await FdFormLayoutService.get_by_id(db, layout_id, user["tenant_id"])


@router.put("/{layout_id}", response_model=FdFormLayoutResponse)
async def update_form_layout(
    layout_id: int,
    body: FdFormLayoutUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update form layout (replace sections/fields if provided)"""
    return await FdFormLayoutService.update(db, layout_id, user["tenant_id"], body)


@router.delete("/{layout_id}", status_code=status.HTTP_200_OK)
async def delete_form_layout(
    layout_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete a form layout"""
    await FdFormLayoutService.delete(db, layout_id, user["tenant_id"])
    return {"message": "Deleted successfully"}
