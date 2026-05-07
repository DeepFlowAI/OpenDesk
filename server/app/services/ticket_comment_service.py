"""
TicketComment service — business logic for the ticket comment thread.

Handles validation (body / attachments at-least-one rule, attachment count cap),
tenant scoping, author resolution and pagination response shaping.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.employee import Employee
from app.repositories.ticket_comment_repository import TicketCommentRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.ticket_comment import (
    TicketCommentCreate,
    TicketCommentResponse,
)
from app.services.ticket_service import TicketService


# Soft caps mirrored in the API contract; validated server-side regardless of
# what the client UI exposes (defense-in-depth).
MAX_ATTACHMENTS_PER_COMMENT = 10
MAX_BODY_LENGTH = 50000


class TicketCommentService:

    @staticmethod
    async def _ensure_ticket(db: AsyncSession, tenant_id: int, ticket_id: int) -> None:
        """Load the ticket and assert it belongs to the current tenant."""
        ticket = await TicketRepository.get_by_id(db, ticket_id)
        if not ticket or ticket.tenant_id != tenant_id:
            raise NotFoundError("Ticket not found")

    @staticmethod
    def _normalize_body(body: str | None) -> str | None:
        """Treat blank rich-text payloads as empty (matches editor output)."""
        if body is None:
            return None
        stripped = body.strip()
        return stripped or None

    @staticmethod
    async def _resolve_author_name(
        db: AsyncSession, tenant_id: int, author_id: int | None
    ) -> str | None:
        if author_id is None:
            return None
        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.tenant_id == tenant_id,
                    Employee.id == author_id,
                )
            )
        ).scalar_one_or_none()
        return TicketService._actor_display_name(employee)

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        tenant_id: int,
        ticket_id: int,
        author_id: int | None,
        data: TicketCommentCreate,
    ) -> TicketCommentResponse:
        await cls._ensure_ticket(db, tenant_id, ticket_id)

        body = cls._normalize_body(data.body)
        attachments = data.attachments or None
        if attachments is not None and len(attachments) == 0:
            attachments = None

        if body is None and not attachments:
            raise ValidationError("Comment body or attachments must be provided")

        if body is not None and len(body) > MAX_BODY_LENGTH:
            raise ValidationError("Comment body exceeds the maximum allowed length")

        if attachments is not None and len(attachments) > MAX_ATTACHMENTS_PER_COMMENT:
            raise ValidationError(
                f"Too many attachments (max {MAX_ATTACHMENTS_PER_COMMENT})"
            )

        author_name = await cls._resolve_author_name(db, tenant_id, author_id)

        item = await TicketCommentRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "ticket_id": ticket_id,
                "author_id": author_id,
                "author_name": author_name,
                "body": body,
                "body_format": data.body_format,
                "attachments": (
                    [a.model_dump() for a in attachments] if attachments else None
                ),
            },
        )
        row = TicketCommentResponse.model_validate(item).model_dump()
        row["author_avatar"] = None
        if author_id is not None:
            r = await db.execute(
                select(Employee).where(
                    Employee.tenant_id == tenant_id,
                    Employee.id == author_id,
                )
            )
            emp = r.scalar_one_or_none()
            if emp is not None and emp.avatar:
                row["author_avatar"] = emp.avatar
        return TicketCommentResponse.model_validate(row)

    @classmethod
    async def get_paginated(
        cls,
        db: AsyncSession,
        tenant_id: int,
        ticket_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        await cls._ensure_ticket(db, tenant_id, ticket_id)

        items, total = await TicketCommentRepository.get_paginated(
            db, tenant_id, ticket_id, page, per_page
        )
        pages = (total + per_page - 1) // per_page if per_page > 0 else 0

        # Refresh author display names from the live employee row so renames
        # are reflected without a backfill job.
        author_ids = {c.author_id for c in items if c.author_id is not None}
        emp_by_id: dict[int, Employee] = {}
        if author_ids:
            r = await db.execute(
                select(Employee).where(
                    Employee.tenant_id == tenant_id,
                    Employee.id.in_(author_ids),
                )
            )
            for e in r.scalars().all():
                emp_by_id[e.id] = e

        rows: list[dict] = []
        for c in items:
            row = TicketCommentResponse.model_validate(c).model_dump()
            row["author_avatar"] = None
            if c.author_id is not None and c.author_id in emp_by_id:
                emp = emp_by_id[c.author_id]
                live_name = TicketService._actor_display_name(emp)
                if live_name:
                    row["author_name"] = live_name
                if emp.avatar:
                    row["author_avatar"] = emp.avatar
            rows.append(row)

        return {
            "items": rows,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }
