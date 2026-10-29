"""Bounded reads for ticket exports and complete-file authorization."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket
from app.models.ticket_view import TicketView
from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup
from app.models.user import User
from app.models.organization import Organization
from app.models.conversation import Conversation
from app.models.call_record import CallRecord


class TicketExportRepository:
    @staticmethod
    async def view(db: AsyncSession, tenant_id: int, view_id: int) -> TicketView | None:
        return (await db.execute(select(TicketView).where(
            TicketView.id == view_id, TicketView.tenant_id == tenant_id,
            TicketView.is_enabled.is_(True),
        ))).scalar_one_or_none()

    @staticmethod
    async def rows(db: AsyncSession, tenant_id: int, ids: list[int], predicate: object,
                   ids_only: bool = False) -> list:
        query = select(Ticket.id if ids_only else Ticket).where(
            Ticket.tenant_id == tenant_id, Ticket.id.in_(ids),
        )
        if predicate is not None:
            query = query.where(predicate)
        return list((await db.execute(query)).scalars().all())

    @staticmethod
    async def names(db: AsyncSession, tenant_id: int, entity: str, ids: set[int]) -> dict[int, str]:
        models = {"employee_select": Employee, "group_select": EmployeeGroup,
                  "user_select": User, "organization_select": Organization,
                  "conversation": Conversation, "call": CallRecord}
        model = models[entity]
        if not ids:
            return {}
        if entity == "employee_select":
            columns = (model.id, model.nickname, model.name, model.display_name, model.username)
        else:
            columns = (model.id, model.public_id if entity in ("conversation", "call") else model.name)
        rows = (await db.execute(select(*columns).where(
            model.tenant_id == tenant_id, model.id.in_(ids),
        ))).all()
        return {row[0]: str(next((value for value in row[1:] if value), "")) for row in rows}
