"""
TicketChange service — business logic for ticket change timeline.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.employee import Employee
from app.repositories.ticket_change_repository import TicketChangeRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.ticket_change import TicketChangeEntryItem, TicketChangeResponse
from app.services.ticket_service import (
    TicketService,
    TICKET_CHANGE_BATCH_FIELD_KEY,
    TICKET_CHANGE_CREATE_FIELD_KEY,
)


class TicketChangeService:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        ticket_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        ticket = await TicketRepository.get_by_id(db, ticket_id)
        if not ticket or ticket.tenant_id != tenant_id:
            raise NotFoundError("Ticket not found")

        items, total = await TicketChangeRepository.get_paginated(
            db, tenant_id, ticket_id, page, per_page
        )
        pages = (total + per_page - 1) // per_page if per_page > 0 else 0

        user_ids = {
            c.actor_id
            for c in items
            if c.actor_id is not None and c.actor_type == "user"
        }
        emp_by_id: dict[int, Employee] = {}
        if user_ids:
            r = await db.execute(
                select(Employee).where(
                    Employee.tenant_id == tenant_id,
                    Employee.id.in_(user_ids),
                )
            )
            for e in r.scalars().all():
                emp_by_id[e.id] = e

        enriched: list[dict] = []
        for c in items:
            row = TicketChangeResponse.model_validate(c).model_dump()
            if c.field_key in (
                TICKET_CHANGE_BATCH_FIELD_KEY,
                TICKET_CHANGE_CREATE_FIELD_KEY,
            ) and isinstance(
                c.new_value, list
            ):
                row["entries"] = [
                    TicketChangeEntryItem.model_validate(x).model_dump() for x in c.new_value
                ]
                row["old_value"] = None
                row["new_value"] = None
            else:
                row["entries"] = None
            aid = c.actor_id
            row["actor_avatar"] = None
            if aid is not None and c.actor_type == "user" and aid in emp_by_id:
                emp = emp_by_id[aid]
                label = TicketService._actor_display_name(emp)
                if label:
                    row["actor_name"] = label
                if emp.avatar:
                    row["actor_avatar"] = emp.avatar
            enriched.append(row)

        return {
            "items": enriched,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }
