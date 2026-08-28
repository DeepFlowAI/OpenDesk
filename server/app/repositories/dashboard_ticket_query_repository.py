"""Read-only, scope-ready SQL primitives for custom dashboard ticket queries."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import and_, cast, func, or_, select, String as SAString, true
from sqlalchemy.dialects.postgresql import JSONB, array
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.fd_field_definition import FdFieldDefinition
from app.models.ticket import Ticket


SYSTEM_TICKET_COLUMNS = {
    "ticket_number": Ticket.ticket_number,
    "title": Ticket.title,
    "status": Ticket.status,
    "priority": Ticket.priority,
    "assignee": Ticket.agent_id,
    "assignee_group": Ticket.assignee_group_id,
    "created_by": Ticket.created_by_actor_name,
    "created_at": Ticket.created_at,
    "updated_at": Ticket.updated_at,
}


class DashboardTicketQueryRepository:
    """Execute validated aggregate queries against Ticket only."""

    @staticmethod
    async def list_field_definitions(
        db: AsyncSession,
        tenant_id: int,
    ) -> list[FdFieldDefinition]:
        query = select(FdFieldDefinition).where(
            FdFieldDefinition.tenant_id == tenant_id,
            or_(
                FdFieldDefinition.domain == "ticket",
                and_(
                    FdFieldDefinition.domain == "shared_pool",
                    FdFieldDefinition.applicable_modules.overlap(array(["ticket"])),
                ),
            ),
        )
        return list((await db.execute(query)).scalars().all())

    @staticmethod
    async def field_catalog_version(db: AsyncSession, tenant_id: int) -> str:
        # Count is part of the version so that deleting a field (which leaves
        # max(updated_at) unchanged) still invalidates cached run results.
        query = select(
            func.count(),
            func.max(FdFieldDefinition.updated_at),
        ).where(
            FdFieldDefinition.tenant_id == tenant_id,
            or_(
                FdFieldDefinition.domain == "ticket",
                and_(
                    FdFieldDefinition.domain == "shared_pool",
                    FdFieldDefinition.applicable_modules.overlap(array(["ticket"])),
                ),
            ),
        )
        row = (await db.execute(query)).one()
        count, latest = int(row[0]), row[1]
        stamp = latest.isoformat() if latest else "0"
        return f"{count}:{stamp}"

    @staticmethod
    async def candidate_count(
        db: AsyncSession,
        tenant_id: int,
        clauses: list[ColumnElement],
    ) -> int:
        query = select(func.count()).select_from(Ticket).where(
            Ticket.tenant_id == tenant_id,
            *clauses,
        )
        return int((await db.execute(query)).scalar_one())

    @staticmethod
    async def count(
        db: AsyncSession,
        tenant_id: int,
        clauses: list[ColumnElement],
    ) -> int:
        return await DashboardTicketQueryRepository.candidate_count(db, tenant_id, clauses)

    @staticmethod
    async def group_by(
        db: AsyncSession,
        tenant_id: int,
        clauses: list[ColumnElement],
        *,
        group_column: ColumnElement,
        aggregate_column: ColumnElement | None,
        aggregate: str,
        multi_select: bool,
        limit: int,
    ) -> list[dict]:
        aggregate_expression = _aggregate_expression(aggregate, aggregate_column)
        if multi_select:
            values = func.jsonb_array_elements_text(
                cast(group_column, JSONB)
            ).table_valued("value").lateral()
            query = (
                select(values.c.value.label("key"), aggregate_expression.label("value"))
                .select_from(Ticket)
                .join(values, true())
                .where(Ticket.tenant_id == tenant_id, *clauses)
                .group_by(values.c.value)
                .order_by(aggregate_expression.desc())
                .limit(limit)
            )
        else:
            query = (
                select(group_column.label("key"), aggregate_expression.label("value"))
                .select_from(Ticket)
                .where(Ticket.tenant_id == tenant_id, *clauses)
                .group_by(group_column)
                .order_by(aggregate_expression.desc())
                .limit(limit)
            )
        return [
            {"key": _json_value(row.key), "value": _json_value(row.value)}
            for row in (await db.execute(query)).all()
        ]

    @staticmethod
    async def timeseries(
        db: AsyncSession,
        tenant_id: int,
        clauses: list[ColumnElement],
        *,
        date_column: ColumnElement,
        aggregate_column: ColumnElement | None,
        aggregate: str,
        granularity: str,
        timezone_name: str,
        limit: int,
    ) -> list[dict]:
        bucket = func.date_trunc(
            granularity,
            func.timezone(timezone_name, date_column),
        )
        aggregate_expression = _aggregate_expression(aggregate, aggregate_column)
        query = (
            select(bucket.label("bucket"), aggregate_expression.label("value"))
            .select_from(Ticket)
            .where(Ticket.tenant_id == tenant_id, *clauses)
            .group_by(bucket)
            .order_by(bucket.asc())
            .limit(limit)
        )
        return [
            {"bucket": _json_value(row.bucket), "value": _json_value(row.value)}
            for row in (await db.execute(query)).all()
        ]

    @staticmethod
    async def list_rows(
        db: AsyncSession,
        tenant_id: int,
        clauses: list[ColumnElement],
        *,
        fields: list[tuple[str, ColumnElement]],
        limit: int,
    ) -> list[dict]:
        columns = [column.label(f"field_{index}") for index, (_, column) in enumerate(fields)]
        query = (
            select(*columns)
            .select_from(Ticket)
            .where(Ticket.tenant_id == tenant_id, *clauses)
            .order_by(Ticket.created_at.desc(), Ticket.id.desc())
            .limit(limit)
        )
        rows = (await db.execute(query)).all()
        return [
            {
                field_ref: _json_value(getattr(row, f"field_{index}"))
                for index, (field_ref, _) in enumerate(fields)
            }
            for row in rows
        ]


def build_filter_clause(
    column: ColumnElement,
    operator: str,
    value: object,
    *,
    multi_select: bool = False,
) -> ColumnElement:
    """Build a filter from an already authorized field and operator."""
    operator = operator.lower()
    if multi_select and operator in {"eq", "contains"}:
        return cast(column, JSONB).contains([value])
    if multi_select and operator == "in" and isinstance(value, list):
        return cast(column, JSONB).op("?|")(array([str(item) for item in value]))
    if multi_select and operator == "not_in" and isinstance(value, list):
        return ~cast(column, JSONB).op("?|")(array([str(item) for item in value]))
    if operator == "eq":
        return column == value
    if operator == "ne":
        return column != value
    if operator == "in" and isinstance(value, list):
        return column.in_(value)
    if operator == "not_in" and isinstance(value, list):
        return ~column.in_(value)
    if operator == "gt":
        return column > value
    if operator == "gte":
        return column >= value
    if operator == "lt":
        return column < value
    if operator == "lte":
        return column <= value
    if operator == "contains":
        return cast(column, SAString).ilike(f"%{value}%")
    if operator == "not_contains":
        return ~cast(column, SAString).ilike(f"%{value}%")
    if operator == "is_empty":
        return or_(column.is_(None), cast(column, SAString) == "")
    if operator == "is_not_empty":
        return and_(column.isnot(None), cast(column, SAString) != "")
    raise ValueError(f"Unsupported filter operator: {operator}")


def _aggregate_expression(
    aggregate: str,
    aggregate_column: ColumnElement | None,
) -> ColumnElement:
    if aggregate == "count":
        return func.count(Ticket.id)
    if aggregate_column is None:
        raise ValueError("A numeric value field is required")
    match aggregate:
        case "sum":
            return func.sum(aggregate_column)
        case "avg":
            return func.avg(aggregate_column)
        case "max":
            return func.max(aggregate_column)
        case "min":
            return func.min(aggregate_column)
        case _:
            raise ValueError("Unsupported aggregate")


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value
