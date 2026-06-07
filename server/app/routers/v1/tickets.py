"""
Tickets router — ticket CRUD + workspace list & detail APIs
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_principal, require_permission
from app.schemas.permission import EffectivePrincipal
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


@router.post(
    "/query",
    response_model=TicketListResponse,
    dependencies=[Depends(require_permission("ticket.workspace.view"))],
)
async def query_tickets(
    body: TicketQueryRequest,
    principal: EffectivePrincipal = Depends(require_permission("ticket.workspace.view")),
    db: AsyncSession = Depends(get_db),
):
    """Query tickets with optional view-based system filters + temporary filters."""
    return await TicketService.query_tickets(db, principal.tenant_id, body, principal)


@router.get(
    "/views/enabled",
    response_model=list[TicketViewResponse],
    dependencies=[Depends(require_permission("ticket.workspace.view"))],
)
async def list_enabled_views(
    principal: EffectivePrincipal = Depends(require_permission("ticket.workspace.view")),
    db: AsyncSession = Depends(get_db),
):
    """Get all enabled ticket views for the sidebar."""
    return await TicketService.get_enabled_views(db, principal.tenant_id)


@router.get(
    "/views/counts",
    response_model=TicketViewCountsResponse,
    dependencies=[Depends(require_permission("ticket.workspace.view"))],
)
async def get_view_counts(
    principal: EffectivePrincipal = Depends(require_permission("ticket.workspace.view")),
    db: AsyncSession = Depends(get_db),
):
    """Get ticket count per enabled view + total."""
    return await TicketService.get_view_counts(db, principal.tenant_id, principal)


@router.post(
    "/views/{view_id}/groups",
    response_model=ViewGroupResponse,
    dependencies=[Depends(require_permission("ticket.workspace.view"))],
)
async def get_view_groups(
    view_id: int,
    body: ViewGroupRequest | None = None,
    principal: EffectivePrincipal = Depends(require_permission("ticket.workspace.view")),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate tickets under the given view by its configured group field.

    Returns per-group counts for rendering the workspace group bar. Counts
    use the same filter set as the list (search + temp filters) plus the
    view's saved conditions, but never apply the group_value filter itself.
    """
    payload = body or ViewGroupRequest()
    return await TicketService.get_view_groups(db, principal.tenant_id, view_id, payload, principal)


@router.post(
    "",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("ticket.workspace.create"))],
)
async def create_ticket(
    body: TicketCreate,
    principal: EffectivePrincipal = Depends(require_permission("ticket.workspace.create")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new ticket."""
    return await TicketService.create_ticket(
        db,
        principal.tenant_id,
        body,
        actor_id=principal.user_id,
    )


@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
    dependencies=[Depends(require_permission("ticket.workspace.view"))],
)
async def get_ticket(
    ticket_id: int,
    principal: EffectivePrincipal = Depends(require_permission("ticket.workspace.view")),
    db: AsyncSession = Depends(get_db),
):
    """Get a single ticket by ID."""
    return await TicketService.get_by_id(db, principal.tenant_id, ticket_id, principal)


@router.get(
    "/{ticket_id}/changes",
    response_model=TicketChangeListResponse,
    dependencies=[Depends(require_permission("ticket.workspace.view"))],
)
async def list_ticket_changes(
    ticket_id: int,
    page: int = 1,
    per_page: int = 20,
    principal: EffectivePrincipal = Depends(require_permission("ticket.workspace.view")),
    db: AsyncSession = Depends(get_db),
):
    """List field-level changes for a ticket."""
    return await TicketChangeService.get_paginated(
        db,
        principal.tenant_id,
        ticket_id,
        page=page,
        per_page=per_page,
        principal=principal,
    )


@router.get(
    "/{ticket_id}/comments",
    response_model=TicketCommentListResponse,
    dependencies=[Depends(require_permission("ticket.workspace.view"))],
)
async def list_ticket_comments(
    ticket_id: int,
    page: int = 1,
    per_page: int = 20,
    principal: EffectivePrincipal = Depends(require_permission("ticket.workspace.view")),
    db: AsyncSession = Depends(get_db),
):
    """List comments on a ticket, newest first, paginated."""
    page = max(1, page)
    per_page = max(1, min(per_page, 100))
    return await TicketCommentService.get_paginated(
        db,
        principal.tenant_id,
        ticket_id,
        page=page,
        per_page=per_page,
        principal=principal,
    )


@router.post(
    "/{ticket_id}/comments",
    response_model=TicketCommentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("ticket.workspace.comment"))],
)
async def create_ticket_comment(
    ticket_id: int,
    body: TicketCommentCreate,
    principal: EffectivePrincipal = Depends(require_permission("ticket.workspace.comment")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new comment on a ticket. Body or attachments must be present."""
    return await TicketCommentService.create(
        db,
        principal.tenant_id,
        ticket_id,
        author_id=principal.user_id,
        data=body,
        principal=principal,
    )


@router.put(
    "/{ticket_id}",
    response_model=TicketResponse,
    dependencies=[Depends(require_permission("ticket.workspace.edit"))],
)
async def update_ticket(
    ticket_id: int,
    body: TicketUpdate,
    principal: EffectivePrincipal = Depends(require_permission("ticket.workspace.edit")),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing ticket."""
    return await TicketService.update_ticket(
        db,
        principal.tenant_id,
        ticket_id,
        body,
        actor_id=principal.user_id,
        principal=principal,
    )


@router.delete(
    "/{ticket_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("ticket.workspace.delete"))],
)
async def delete_ticket(
    ticket_id: int,
    principal: EffectivePrincipal = Depends(require_permission("ticket.workspace.delete")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a ticket."""
    await TicketService.delete_ticket(db, principal.tenant_id, ticket_id, principal)
    return {"message": "Deleted successfully"}
