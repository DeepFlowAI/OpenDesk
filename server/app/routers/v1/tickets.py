"""
Tickets router — ticket CRUD + workspace list & detail APIs
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.ticket import (
    TicketResponse,
    TicketCreate,
    TicketUpdate,
    TicketListResponse,
    TicketQueryRequest,
    TicketViewCountsResponse,
)
from app.schemas.ticket_change import TicketChangeListResponse
from app.schemas.ticket_comment import (
    TicketCommentCreate,
    TicketCommentListResponse,
    TicketCommentResponse,
)
from app.schemas.ticket_view import TicketViewResponse
from app.schemas.view_group import ViewGroupRequest, ViewGroupResponse
from app.services.ticket_change_service import TicketChangeService
from app.services.ticket_comment_service import TicketCommentService
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.post("/query", response_model=TicketListResponse)
async def query_tickets(
    body: TicketQueryRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query tickets with optional view-based system filters + temporary filters."""
    tenant_id = current_user["tenant_id"]
    return await TicketService.query_tickets(db, tenant_id, body)


@router.get("/views/enabled", response_model=list[TicketViewResponse])
async def list_enabled_views(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all enabled ticket views for the sidebar."""
    tenant_id = current_user["tenant_id"]
    return await TicketService.get_enabled_views(db, tenant_id)


@router.get("/views/counts", response_model=TicketViewCountsResponse)
async def get_view_counts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get ticket count per enabled view + total."""
    tenant_id = current_user["tenant_id"]
    return await TicketService.get_view_counts(db, tenant_id)


@router.post("/views/{view_id}/groups", response_model=ViewGroupResponse)
async def get_view_groups(
    view_id: int,
    body: ViewGroupRequest | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate tickets under the given view by its configured group field.

    Returns per-group counts for rendering the workspace group bar. Counts
    use the same filter set as the list (search + temp filters) plus the
    view's saved conditions, but never apply the group_value filter itself.
    """
    tenant_id = current_user["tenant_id"]
    payload = body or ViewGroupRequest()
    return await TicketService.get_view_groups(db, tenant_id, view_id, payload)


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    body: TicketCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new ticket."""
    tenant_id = current_user["tenant_id"]
    return await TicketService.create_ticket(
        db,
        tenant_id,
        body,
        actor_id=current_user.get("user_id"),
    )


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single ticket by ID."""
    tenant_id = current_user["tenant_id"]
    return await TicketService.get_by_id(db, tenant_id, ticket_id)


@router.get("/{ticket_id}/changes", response_model=TicketChangeListResponse)
async def list_ticket_changes(
    ticket_id: int,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List field-level changes for a ticket."""
    tenant_id = current_user["tenant_id"]
    return await TicketChangeService.get_paginated(
        db,
        tenant_id,
        ticket_id,
        page=page,
        per_page=per_page,
    )


@router.get("/{ticket_id}/comments", response_model=TicketCommentListResponse)
async def list_ticket_comments(
    ticket_id: int,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List comments on a ticket, newest first, paginated."""
    tenant_id = current_user["tenant_id"]
    page = max(1, page)
    per_page = max(1, min(per_page, 100))
    return await TicketCommentService.get_paginated(
        db,
        tenant_id,
        ticket_id,
        page=page,
        per_page=per_page,
    )


@router.post(
    "/{ticket_id}/comments",
    response_model=TicketCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket_comment(
    ticket_id: int,
    body: TicketCommentCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new comment on a ticket. Body or attachments must be present."""
    tenant_id = current_user["tenant_id"]
    return await TicketCommentService.create(
        db,
        tenant_id,
        ticket_id,
        author_id=current_user.get("user_id"),
        data=body,
    )


@router.put("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: int,
    body: TicketUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing ticket."""
    tenant_id = current_user["tenant_id"]
    return await TicketService.update_ticket(
        db,
        tenant_id,
        ticket_id,
        body,
        actor_id=current_user.get("user_id"),
    )


@router.delete("/{ticket_id}", status_code=status.HTTP_200_OK)
async def delete_ticket(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a ticket."""
    tenant_id = current_user["tenant_id"]
    await TicketService.delete_ticket(db, tenant_id, ticket_id)
    return {"message": "Deleted successfully"}
