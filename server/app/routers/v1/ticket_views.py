"""
TicketView router — API endpoints for ticket view management
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.ticket_view import (
    TicketViewCreate,
    TicketViewUpdate,
    TicketViewResponse,
    TicketViewListResponse,
    TicketViewToggleRequest,
    TicketViewSortRequest,
)
from app.services.ticket_view_service import TicketViewService

router = APIRouter(prefix="/ticket-views", tags=["TicketViews"])


@router.put("/sort", status_code=status.HTTP_200_OK)
async def sort_ticket_views(
    body: TicketViewSortRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch update sort order for ticket views"""
    tenant_id = current_user["tenant_id"]
    await TicketViewService.update_sort(db, tenant_id, body)
    return {"message": "Sort order updated"}


@router.get("", response_model=TicketViewListResponse)
async def list_ticket_views(
    page: int = 1,
    per_page: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all ticket views for the current tenant"""
    tenant_id = current_user["tenant_id"]
    return await TicketViewService.get_paginated(db, tenant_id, page, per_page)


@router.post("", response_model=TicketViewResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket_view(
    body: TicketViewCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new ticket view"""
    tenant_id = current_user["tenant_id"]
    return await TicketViewService.create(db, tenant_id, body)


@router.get("/{view_id}", response_model=TicketViewResponse)
async def get_ticket_view(
    view_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a ticket view by ID"""
    tenant_id = current_user["tenant_id"]
    return await TicketViewService.get_by_id(db, view_id, tenant_id)


@router.put("/{view_id}", response_model=TicketViewResponse)
async def update_ticket_view(
    view_id: int,
    body: TicketViewUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a ticket view"""
    tenant_id = current_user["tenant_id"]
    return await TicketViewService.update(db, view_id, tenant_id, body)


@router.put("/{view_id}/toggle", response_model=TicketViewResponse)
async def toggle_ticket_view(
    view_id: int,
    body: TicketViewToggleRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle ticket view enabled/disabled"""
    tenant_id = current_user["tenant_id"]
    return await TicketViewService.toggle_enabled(db, view_id, tenant_id, body.is_enabled)


@router.delete("/{view_id}", status_code=status.HTTP_200_OK)
async def delete_ticket_view(
    view_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a ticket view"""
    tenant_id = current_user["tenant_id"]
    await TicketViewService.delete(db, view_id, tenant_id)
    return {"message": "Deleted successfully"}
