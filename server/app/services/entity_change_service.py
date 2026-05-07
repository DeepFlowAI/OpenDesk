"""
EntityChange service — shared audit timeline helpers for user and organization.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User
from app.repositories.entity_change_repository import EntityChangeRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.entity_change import EntityChangeEntryItem, EntityChangeResponse


ENTITY_CHANGE_BATCH_FIELD_KEY = "__batch__"
ENTITY_CHANGE_CREATE_FIELD_KEY = "__create__"


class EntityChangeService:

    @staticmethod
    def normalize_change_value(value: object) -> object:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                str(k): EntityChangeService.normalize_change_value(v)
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [EntityChangeService.normalize_change_value(v) for v in value]
        return value

    @staticmethod
    def _actor_display_name(emp: Employee | None) -> str | None:
        if not emp:
            return None
        for attr in (emp.display_name, emp.nickname, emp.name):
            if attr and str(attr).strip():
                return str(attr).strip()
        return str(emp.username) if emp.username else None

    @staticmethod
    async def resolve_actor_name(
        db: AsyncSession,
        tenant_id: int,
        actor_id: int | None,
    ) -> str | None:
        if actor_id is None:
            return None
        employee = await EmployeeRepository.get_by_id(db, actor_id)
        if employee and employee.tenant_id == tenant_id:
            display_name = EntityChangeService._actor_display_name(employee)
            if display_name:
                return display_name
        return f"User #{actor_id}"

    @staticmethod
    def build_change_rows(
        *,
        entity_type: str,
        entity_id: int,
        current: object,
        tenant_id: int,
        update_data: dict,
        field_labels: dict[str, str],
        actor_id: int | None,
        actor_name: str | None,
    ) -> list[dict]:
        rows: list[dict] = []
        actor_type = "user" if actor_id is not None else "system"
        resolved_name = actor_name or (f"User #{actor_id}" if actor_id is not None else "System")

        for field_key, new_raw in update_data.items():
            if not hasattr(current, field_key):
                continue

            old_value = EntityChangeService.normalize_change_value(getattr(current, field_key))
            new_value = EntityChangeService.normalize_change_value(new_raw)
            if old_value == new_value:
                continue

            rows.append({
                "tenant_id": tenant_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "actor_name": resolved_name,
                "field_key": field_key,
                "field_label": field_labels.get(field_key, field_key),
                "field_source": entity_type,
                "old_value": old_value,
                "new_value": new_value,
            })
        return rows

    @staticmethod
    def pack_change_batch(field_rows: list[dict]) -> list[dict]:
        if not field_rows:
            return []
        first = field_rows[0]
        entries = [
            {
                "field_key": r["field_key"],
                "field_label": r["field_label"],
                "old_value": r["old_value"],
                "new_value": r["new_value"],
            }
            for r in field_rows
        ]
        return [
            {
                "tenant_id": first["tenant_id"],
                "entity_type": first["entity_type"],
                "entity_id": first["entity_id"],
                "actor_type": first["actor_type"],
                "actor_id": first["actor_id"],
                "actor_name": first["actor_name"],
                "field_key": ENTITY_CHANGE_BATCH_FIELD_KEY,
                "field_label": ENTITY_CHANGE_BATCH_FIELD_KEY,
                "field_source": first["entity_type"],
                "old_value": None,
                "new_value": entries,
            }
        ]

    @staticmethod
    def build_create_entries(
        *,
        entity: object,
        field_labels: dict[str, str],
        created_fields: list[str],
    ) -> list[dict]:
        entries: list[dict] = []
        seen: set[str] = set()
        for field_key in created_fields:
            if field_key in seen or not hasattr(entity, field_key):
                continue
            seen.add(field_key)
            value = EntityChangeService.normalize_change_value(getattr(entity, field_key))
            if value is None or value == "":
                continue
            entries.append({
                "field_key": field_key,
                "field_label": field_labels.get(field_key, field_key),
                "old_value": None,
                "new_value": value,
            })
        return entries

    @staticmethod
    def build_create_change_row(
        *,
        entity_type: str,
        entity_id: int,
        tenant_id: int,
        entries: list[dict],
        actor_id: int | None,
        actor_name: str | None,
    ) -> list[dict]:
        if not entries:
            return []
        actor_type = "user" if actor_id is not None else "system"
        resolved_name = actor_name or (f"User #{actor_id}" if actor_id is not None else "System")
        return [
            {
                "tenant_id": tenant_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "actor_name": resolved_name,
                "field_key": ENTITY_CHANGE_CREATE_FIELD_KEY,
                "field_label": ENTITY_CHANGE_CREATE_FIELD_KEY,
                "field_source": entity_type,
                "old_value": None,
                "new_value": entries,
            }
        ]

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        entity_type: str,
        entity_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        entity_model = User if entity_type == "user" else Organization
        entity = await db.get(entity_model, entity_id)
        if not entity or entity.tenant_id != tenant_id:
            raise NotFoundError(f"{entity_type.title()} not found")

        items, total = await EntityChangeRepository.get_paginated(
            db, tenant_id, entity_type, entity_id, page, per_page
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
            row = EntityChangeResponse.model_validate(c).model_dump()
            if c.field_key in (
                ENTITY_CHANGE_BATCH_FIELD_KEY,
                ENTITY_CHANGE_CREATE_FIELD_KEY,
            ) and isinstance(c.new_value, list):
                row["entries"] = [
                    EntityChangeEntryItem.model_validate(x).model_dump() for x in c.new_value
                ]
                row["old_value"] = None
                row["new_value"] = None
            else:
                row["entries"] = None
            aid = c.actor_id
            row["actor_avatar"] = None
            if aid is not None and c.actor_type == "user" and aid in emp_by_id:
                emp = emp_by_id[aid]
                label = EntityChangeService._actor_display_name(emp)
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
