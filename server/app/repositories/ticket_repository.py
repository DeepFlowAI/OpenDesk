"""
Ticket repository — data access for tickets
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import Date, DateTime, Integer, Numeric, Float, select, func, String as SAString, or_, and_, cast
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import EMPTY_GROUP_VALUE
from app.models.ticket import Ticket

logger = logging.getLogger(__name__)

SYSTEM_FIELD_MAP: dict[str, str] = {
    "ticket_number": "ticket_number",
    "title": "title",
    "description": "description",
    "status": "status",
    "priority": "priority",
    "assignee": "agent_id",
    "assignee_group": "assignee_group_id",
    "user_id": "user_id",
    "conversation_id": "conversation_id",
    "call_record_id": "call_record_id",
    "agent_id": "agent_id",
    "layout_id": "layout_id",
    "created_by": "created_by_actor_name",
    "updated_by": "updated_by_actor_name",
    "created_at": "created_at",
    "updated_at": "updated_at",
}


def _resolve_column(field_key: str | None, slot_column: str | None):
    if field_key and field_key in SYSTEM_FIELD_MAP:
        return getattr(Ticket, SYSTEM_FIELD_MAP[field_key], None)
    if slot_column and hasattr(Ticket, slot_column):
        return getattr(Ticket, slot_column)
    return None


def _coerce_filter_value(col, value):
    """Coerce JSON filter values to the SQL column type before comparison."""
    if value is None:
        return None
    if isinstance(value, list):
        return [_coerce_filter_value(col, item) for item in value]

    col_type = getattr(col, "type", None)
    try:
        if isinstance(col_type, DateTime):
            if isinstance(value, datetime):
                return value
            if isinstance(value, date):
                return datetime(value.year, value.month, value.day)
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(col_type, Date):
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, date):
                return value
            if isinstance(value, str):
                return date.fromisoformat(value[:10])
        if isinstance(col_type, Numeric):
            if isinstance(value, bool):
                return int(value)
            return Decimal(str(value))
        if isinstance(col_type, (Integer, Float)):
            if isinstance(value, bool):
                return int(value)
            return float(value) if isinstance(col_type, Float) else int(value)
    except (ValueError, TypeError, InvalidOperation):
        return value
    return value


def _build_condition_clause(col, operator: str, value):
    if col is None:
        return None
    op = operator.lower()
    coerced_value = _coerce_filter_value(col, value)
    if op in ("eq", "equals", "="):
        return col == coerced_value
    if op in ("ne", "not_equals", "!="):
        return col != coerced_value
    if op in ("contains", "like"):
        return col.ilike(f"%{coerced_value}%")
    if op in ("not_contains", "not_like"):
        return ~col.ilike(f"%{coerced_value}%")
    if op in ("starts_with",):
        return col.ilike(f"{coerced_value}%")
    if op in ("ends_with",):
        return col.ilike(f"%{coerced_value}")
    if op in ("gt", ">"):
        return col > coerced_value
    if op in ("gte", ">="):
        return col >= coerced_value
    if op in ("lt", "<"):
        return col < coerced_value
    if op in ("lte", "<="):
        return col <= coerced_value
    if op in ("is_empty", "is_null"):
        return or_(col.is_(None), cast(col, SAString) == "")
    if op in ("is_not_empty", "is_not_null"):
        return and_(col.isnot(None), cast(col, SAString) != "")
    if op in ("in",) and isinstance(coerced_value, list):
        return col.in_(coerced_value)
    if op in ("not_in",) and isinstance(coerced_value, list):
        return ~col.in_(coerced_value)
    logger.warning("Unsupported operator %s, skipping", operator)
    return None


def _generate_ticket_number() -> str:
    now = datetime.now(timezone.utc)
    return f"TK{now.strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"


class TicketRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, ticket_id: int) -> Ticket | None:
        return await db.get(Ticket, ticket_id)

    @staticmethod
    async def list_by_conversation_id(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
    ) -> list[Ticket]:
        result = await db.execute(
            select(Ticket)
            .where(Ticket.tenant_id == tenant_id)
            .where(Ticket.conversation_id == conversation_id)
            .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_by_call_record_id(
        db: AsyncSession,
        tenant_id: int,
        call_record_id: int,
    ) -> list[Ticket]:
        result = await db.execute(
            select(Ticket)
            .where(Ticket.tenant_id == tenant_id)
            .where(Ticket.call_record_id == call_record_id)
            .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(
        db: AsyncSession,
        data: dict,
        commit: bool = True,
    ) -> Ticket:
        if not data.get("ticket_number"):
            data["ticket_number"] = _generate_ticket_number()
        item = Ticket(**data)
        db.add(item)
        if commit:
            await db.commit()
            await db.refresh(item)
        else:
            await db.flush()
        return item

    @staticmethod
    async def update(
        db: AsyncSession,
        ticket: Ticket,
        data: dict,
        commit: bool = True,
    ) -> Ticket:
        for key, value in data.items():
            if hasattr(ticket, key):
                setattr(ticket, key, value)
        if commit:
            await db.commit()
            await db.refresh(ticket)
        else:
            await db.flush()
        return ticket

    @staticmethod
    async def delete(db: AsyncSession, ticket: Ticket) -> None:
        await db.delete(ticket)
        await db.commit()

    @staticmethod
    def _build_conditions_filters(
        conditions: list[dict],
        condition_logic: str,
        slot_map: dict[int, str],
    ) -> list:
        clauses = []
        for cond in conditions:
            field_key = cond.get("field_key")
            field_id = cond.get("field_id")
            operator = cond.get("operator", "eq")
            value = cond.get("value")

            slot_col = slot_map.get(field_id) if field_id else None
            col = _resolve_column(field_key, slot_col)
            if col is None:
                continue
            clause = _build_condition_clause(col, operator, value)
            if clause is not None:
                clauses.append(clause)

        if not clauses:
            return []
        if condition_logic == "or":
            return [or_(*clauses)]
        return clauses

    @staticmethod
    async def query_paginated(
        db: AsyncSession,
        tenant_id: int,
        *,
        search: str | None = None,
        view_conditions: list[dict] | None = None,
        view_condition_logic: str = "and",
        temp_conditions: list[dict] | None = None,
        temp_condition_logic: str = "and",
        group_field_col: str | None = None,
        group_value: str | None = None,
        slot_map: dict[int, str] | None = None,
        sort_by: str | None = None,
        sort_order: str = "desc",
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Ticket], int]:
        _slot_map = slot_map or {}
        base_where = [Ticket.tenant_id == tenant_id]

        if search:
            base_where.append(
                or_(
                    Ticket.title.ilike(f"%{search}%"),
                    Ticket.ticket_number.ilike(f"%{search}%"),
                    Ticket.description.ilike(f"%{search}%"),
                )
            )

        if view_conditions:
            base_where.extend(
                TicketRepository._build_conditions_filters(
                    view_conditions, view_condition_logic, _slot_map
                )
            )

        if temp_conditions:
            base_where.extend(
                TicketRepository._build_conditions_filters(
                    temp_conditions, temp_condition_logic, _slot_map
                )
            )

        if group_field_col and group_value is not None:
            col = getattr(Ticket, group_field_col, None)
            if col is not None:
                if group_value == EMPTY_GROUP_VALUE:
                    base_where.append(col.is_(None))
                else:
                    base_where.append(col == group_value)

        count_q = select(func.count()).select_from(Ticket).where(*base_where)
        total = (await db.execute(count_q)).scalar_one()

        order_col = getattr(Ticket, sort_by, None) if sort_by else Ticket.updated_at
        if order_col is None:
            order_col = Ticket.updated_at
        order_expr = order_col.desc() if sort_order == "desc" else order_col.asc()

        offset = (page - 1) * per_page
        data_q = (
            select(Ticket)
            .where(*base_where)
            .order_by(order_expr)
            .offset(offset)
            .limit(per_page)
        )
        rows = (await db.execute(data_q)).scalars().all()
        return list(rows), total

    @staticmethod
    async def count_by_conditions(
        db: AsyncSession,
        tenant_id: int,
        conditions: list[dict],
        condition_logic: str,
        slot_map: dict[int, str],
    ) -> int:
        base_where = [Ticket.tenant_id == tenant_id]
        if conditions:
            base_where.extend(
                TicketRepository._build_conditions_filters(
                    conditions, condition_logic, slot_map
                )
            )
        q = select(func.count()).select_from(Ticket).where(*base_where)
        return (await db.execute(q)).scalar_one()

    @staticmethod
    async def aggregate_by_group_field(
        db: AsyncSession,
        tenant_id: int,
        *,
        group_field_col: str,
        search: str | None = None,
        view_conditions: list[dict] | None = None,
        view_condition_logic: str = "and",
        temp_conditions: list[dict] | None = None,
        temp_condition_logic: str = "and",
        slot_map: dict[int, str] | None = None,
    ) -> tuple[list[dict], int]:
        """Group tickets by `group_field_col` and count per group.

        Returns (items, total). `items` is a list of {"value", "count"} dicts
        sorted by count desc, with the NULL group (if any) placed last.
        `total` equals the sum of all group counts (i.e. the list total under
        the same filter set, ignoring `group_value`).
        """
        _slot_map = slot_map or {}
        col = getattr(Ticket, group_field_col, None)
        if col is None:
            return [], 0

        base_where = [Ticket.tenant_id == tenant_id]

        if search:
            base_where.append(
                or_(
                    Ticket.title.ilike(f"%{search}%"),
                    Ticket.ticket_number.ilike(f"%{search}%"),
                    Ticket.description.ilike(f"%{search}%"),
                )
            )

        if view_conditions:
            base_where.extend(
                TicketRepository._build_conditions_filters(
                    view_conditions, view_condition_logic, _slot_map
                )
            )

        if temp_conditions:
            base_where.extend(
                TicketRepository._build_conditions_filters(
                    temp_conditions, temp_condition_logic, _slot_map
                )
            )

        q = (
            select(col, func.count())
            .where(*base_where)
            .group_by(col)
        )
        rows = (await db.execute(q)).all()

        items: list[dict] = []
        null_count = 0
        for value, count in rows:
            if value is None:
                null_count = int(count)
            else:
                items.append({"value": str(value), "count": int(count)})

        items.sort(key=lambda x: x["count"], reverse=True)
        if null_count > 0:
            items.append({"value": None, "count": null_count})

        total = sum(item["count"] for item in items)
        return items, total
