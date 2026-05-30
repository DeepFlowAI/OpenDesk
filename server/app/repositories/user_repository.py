"""
User repository — data access for end users (formerly visitors)
"""
from __future__ import annotations

import logging
import re
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import Date, DateTime, Integer, Numeric, Float, select, func, String as SAString, or_, and_, cast
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import EMPTY_GROUP_VALUE
from app.models.user import User

logger = logging.getLogger(__name__)

USER_PUBLIC_ID_PREFIX = "usr_"
USER_PUBLIC_ID_RANDOM_LENGTH = 16
USER_PUBLIC_ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
USER_PUBLIC_ID_PATTERN = re.compile(r"^usr_[A-Za-z0-9_-]{16}$")
MAX_PUBLIC_ID_GENERATION_ATTEMPTS = 10

SYSTEM_FIELD_MAP: dict[str, str] = {
    "public_id": "public_id",
    "name": "name",
    "nickname": "name",          # system field "nickname" → column "name"
    "external_id": "external_id",
    "email": "email",
    "phone": "phone",
    "gender": "gender",
    "address": "address",
    "remark": "remark",
    "web_id": "web_id",
    "avatar_color": "avatar_color",
    "channel_id": "channel_id",
    "organization_id": "organization_id",
    "created_by": "created_by_actor_name",
    "updated_by": "updated_by_actor_name",
    "created_at": "created_at",
    "updated_at": "updated_at",
}


def _resolve_column(field_key: str | None, slot_column: str | None):
    """Return the SQLAlchemy column object for a given field reference."""
    if field_key and field_key in SYSTEM_FIELD_MAP:
        return getattr(User, SYSTEM_FIELD_MAP[field_key], None)
    if slot_column and hasattr(User, slot_column):
        return getattr(User, slot_column)
    return None


def is_valid_user_public_id(value: str | None) -> bool:
    return bool(value and USER_PUBLIC_ID_PATTERN.fullmatch(value))


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
    """Build a single SQLAlchemy filter clause from operator + value."""
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


class UserRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
        return await db.get(User, user_id)

    @staticmethod
    async def get_by_public_id(db: AsyncSession, public_id: str) -> User | None:
        result = await db.execute(select(User).where(User.public_id == public_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_ids(db: AsyncSession, tenant_id: int, user_ids: list[int]) -> list[User]:
        ids = sorted({user_id for user_id in user_ids if user_id is not None})
        if not ids:
            return []
        result = await db.execute(
            select(User).where(User.tenant_id == tenant_id, User.id.in_(ids))
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_with_phone(db: AsyncSession, tenant_id: int) -> list[User]:
        result = await db.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.phone.isnot(None),
                User.phone != "",
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def generate_public_id() -> str:
        suffix = "".join(secrets.choice(USER_PUBLIC_ID_ALPHABET) for _ in range(USER_PUBLIC_ID_RANDOM_LENGTH))
        return f"{USER_PUBLIC_ID_PREFIX}{suffix}"

    @staticmethod
    async def generate_unique_public_id(db: AsyncSession) -> str:
        for _ in range(MAX_PUBLIC_ID_GENERATION_ATTEMPTS):
            public_id = UserRepository.generate_public_id()
            if not await UserRepository.get_by_public_id(db, public_id):
                return public_id
        raise RuntimeError("Failed to generate a unique user public ID")

    @staticmethod
    async def get_by_external_id(
        db: AsyncSession, tenant_id: int, external_id: str
    ) -> User | None:
        result = await db.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: dict, commit: bool = True) -> User:
        public_id = data.get("public_id")
        if not is_valid_user_public_id(public_id if isinstance(public_id, str) else None):
            data = {**data, "public_id": await UserRepository.generate_unique_public_id(db)}
        item = User(**data)
        db.add(item)
        if commit:
            await db.commit()
            await db.refresh(item)
        else:
            await db.flush()
        return item

    @staticmethod
    async def get_or_create(
        db: AsyncSession, tenant_id: int, external_id: str, defaults: dict
    ) -> tuple[User, bool]:
        """Return (user, created). If exists return it; else create with defaults."""
        existing = await UserRepository.get_by_external_id(db, tenant_id, external_id)
        if existing:
            return existing, False
        data = {**defaults, "tenant_id": tenant_id, "external_id": external_id}
        user = await UserRepository.create(db, data)
        return user, True

    @staticmethod
    async def update(db: AsyncSession, user: User, data: dict, commit: bool = True) -> User:
        """Update user attributes from a flat dict (system fields + slot columns)."""
        for key, value in data.items():
            if hasattr(user, key):
                setattr(user, key, value)
        if commit:
            await db.commit()
            await db.refresh(user)
        else:
            await db.flush()
        return user

    @staticmethod
    async def delete(db: AsyncSession, user: User) -> None:
        await db.delete(user)
        await db.commit()

    @staticmethod
    def _build_conditions_filters(
        conditions: list[dict],
        condition_logic: str,
        slot_map: dict[int, str],
    ) -> list:
        """
        Translate a list of ConditionItem dicts into SQLAlchemy filter clauses.
        slot_map: { field_definition_id -> slot_column_name }
        """
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
    ) -> tuple[list[User], int]:
        """
        Query users with combined system-view filters + temp filters.
        """
        _slot_map = slot_map or {}
        base_where = [User.tenant_id == tenant_id]

        if search:
            base_where.append(
                or_(
                    User.public_id.ilike(f"%{search}%"),
                    User.name.ilike(f"%{search}%"),
                    User.external_id.ilike(f"%{search}%"),
                )
            )

        if view_conditions:
            base_where.extend(
                UserRepository._build_conditions_filters(
                    view_conditions, view_condition_logic, _slot_map
                )
            )

        if temp_conditions:
            base_where.extend(
                UserRepository._build_conditions_filters(
                    temp_conditions, temp_condition_logic, _slot_map
                )
            )

        if group_field_col and group_value is not None:
            col = getattr(User, group_field_col, None)
            if col is not None:
                if group_value == EMPTY_GROUP_VALUE:
                    base_where.append(col.is_(None))
                else:
                    base_where.append(col == group_value)

        count_q = select(func.count()).select_from(User).where(*base_where)
        total = (await db.execute(count_q)).scalar_one()

        order_col = getattr(User, sort_by, None) if sort_by else User.created_at
        if order_col is None:
            order_col = User.created_at
        order_expr = order_col.desc() if sort_order == "desc" else order_col.asc()

        offset = (page - 1) * per_page
        data_q = (
            select(User)
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
        """Count users matching specific conditions (for sidebar view counts)."""
        base_where = [User.tenant_id == tenant_id]
        if conditions:
            base_where.extend(
                UserRepository._build_conditions_filters(
                    conditions, condition_logic, slot_map
                )
            )
        q = select(func.count()).select_from(User).where(*base_where)
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
        """Group users by `group_field_col` and count per group.

        Returns (items, total). `items` is a list of {"value", "count"} dicts
        sorted by count desc, with the NULL group (if any) placed last.
        """
        _slot_map = slot_map or {}
        col = getattr(User, group_field_col, None)
        if col is None:
            return [], 0

        base_where = [User.tenant_id == tenant_id]

        if search:
            base_where.append(
                or_(
                    User.public_id.ilike(f"%{search}%"),
                    User.name.ilike(f"%{search}%"),
                    User.external_id.ilike(f"%{search}%"),
                )
            )

        if view_conditions:
            base_where.extend(
                UserRepository._build_conditions_filters(
                    view_conditions, view_condition_logic, _slot_map
                )
            )

        if temp_conditions:
            base_where.extend(
                UserRepository._build_conditions_filters(
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
