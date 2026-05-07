"""
Ticket service — business logic for ticket CRUD + list
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.ticket import Ticket
from app.models.ticket_view import TicketView
from app.models.fd_field_definition import FdFieldDefinition
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.employee_group_repository import EmployeeGroupRepository
from app.repositories.ticket_change_repository import TicketChangeRepository
from app.repositories.ticket_repository import TicketRepository
from app.models.employee import Employee
from app.schemas.ticket import (
    TicketCreate,
    TicketUpdate,
    TicketQueryRequest,
    TicketResponse,
)
from app.schemas.view_group import ViewGroupRequest
from app.services.audit_actor_service import AuditActorService
from app.services.fd_field_definition_service import coerce_slot_value
from app.enums import ApplicableModule


SYSTEM_FIELD_LABELS: dict[str, str] = {
    "ticket_number": "编号",
    "title": "标题",
    "description": "描述",
    "status": "状态",
    "priority": "优先级",
    "user_id": "关联用户",
    "conversation_id": "关联会话",
    "agent_id": "负责人",
    "assignee_group_id": "负责组",
    "layout_id": "布局",
    "created_by": "创建人",
    "updated_by": "更新人",
}

# One DB row per save: multi-field diffs are stored in new_value as a list (see _pack_change_batch).
TICKET_CHANGE_BATCH_FIELD_KEY = "__batch__"
TICKET_CHANGE_CREATE_FIELD_KEY = "__create__"

SYSTEM_FIELD_ALIASES: dict[str, str] = {
    "assignee": "agent_id",
    "assignee_group": "assignee_group_id",
}


class TicketService:

    @staticmethod
    async def _validate_conversation(db: AsyncSession, tenant_id: int, conversation_id: int) -> None:
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")

    @staticmethod
    async def _validate_assignee_values(
        db: AsyncSession,
        tenant_id: int,
        assignee_group_id: int | None,
        agent_id: int | None,
    ) -> None:
        if assignee_group_id is not None:
            group = await EmployeeGroupRepository.get_by_id(db, assignee_group_id)
            if not group or group.tenant_id != tenant_id:
                raise ValidationError("Assignee group not found")

        if agent_id is not None:
            employee = await EmployeeRepository.get_by_id(db, agent_id)
            if not employee or employee.tenant_id != tenant_id or not employee.is_active:
                raise ValidationError("Assignee not found")

        if assignee_group_id is not None and agent_id is not None:
            is_member = await EmployeeGroupRepository.has_member(db, assignee_group_id, agent_id)
            if not is_member:
                raise ValidationError("所选负责人不属于该负责组")

    @staticmethod
    def _apply_system_field_aliases(
        target: dict,
        custom_fields: dict[str, object] | None,
        explicit_fields: set[str],
        changed_fields: list[str] | None = None,
    ) -> None:
        if not custom_fields:
            return
        for alias, column in SYSTEM_FIELD_ALIASES.items():
            if alias not in custom_fields or column in explicit_fields:
                continue
            target[column] = custom_fields[alias]
            if changed_fields is not None:
                changed_fields.append(column)

    @staticmethod
    async def _get_slot_map(db: AsyncSession, tenant_id: int) -> dict[int, str]:
        ticket_mod = ApplicableModule.TICKET.value
        result = await db.execute(
            select(FdFieldDefinition.id, FdFieldDefinition.slot_column).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.status == "active",
                or_(
                    FdFieldDefinition.domain == "ticket",
                    and_(
                        FdFieldDefinition.domain == "shared_pool",
                        FdFieldDefinition.applicable_modules.overlap(array([ticket_mod])),
                    ),
                ),
            )
        )
        return {row.id: row.slot_column for row in result.all()}

    @staticmethod
    async def _get_field_key_slot_map(db: AsyncSession, tenant_id: int) -> dict[str, str]:
        ticket_mod = ApplicableModule.TICKET.value
        result = await db.execute(
            select(FdFieldDefinition.id, FdFieldDefinition.slot_column).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.status == "active",
                or_(
                    FdFieldDefinition.domain == "ticket",
                    and_(
                        FdFieldDefinition.domain == "shared_pool",
                        FdFieldDefinition.applicable_modules.overlap(array([ticket_mod])),
                    ),
                ),
            )
        )
        return {row.slot_column: str(row.id) for row in result.all()}

    @staticmethod
    async def _get_key_to_slot_map(db: AsyncSession, tenant_id: int) -> dict[str, str]:
        ticket_mod = ApplicableModule.TICKET.value
        result = await db.execute(
            select(FdFieldDefinition.id, FdFieldDefinition.slot_column).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.status == "active",
                or_(
                    FdFieldDefinition.domain == "ticket",
                    and_(
                        FdFieldDefinition.domain == "shared_pool",
                        FdFieldDefinition.applicable_modules.overlap(array([ticket_mod])),
                    ),
                ),
            )
        )
        return {str(row.id): row.slot_column for row in result.all()}

    @staticmethod
    async def _get_key_to_field_meta(db: AsyncSession, tenant_id: int) -> dict[str, dict[str, str]]:
        ticket_mod = ApplicableModule.TICKET.value
        result = await db.execute(
            select(FdFieldDefinition.id, FdFieldDefinition.name, FdFieldDefinition.slot_column).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.status == "active",
                or_(
                    FdFieldDefinition.domain == "ticket",
                    and_(
                        FdFieldDefinition.domain == "shared_pool",
                        FdFieldDefinition.applicable_modules.overlap(array([ticket_mod])),
                    ),
                ),
            )
        )
        return {
            str(row.id): {"name": row.name, "slot_column": row.slot_column}
            for row in result.all()
        }

    @staticmethod
    def _normalize_change_value(value: object) -> object:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                str(k): TicketService._normalize_change_value(v)
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [TicketService._normalize_change_value(v) for v in value]
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
    async def _resolve_actor_name(
        db: AsyncSession,
        tenant_id: int,
        actor_id: int | None,
    ) -> str | None:
        if actor_id is None:
            return None
        employee = await EmployeeRepository.get_by_id(db, actor_id)
        if employee and employee.tenant_id == tenant_id:
            display_name = TicketService._actor_display_name(employee)
            if display_name:
                return display_name
        return f"User #{actor_id}"

    @staticmethod
    def _build_change_rows(
        *,
        ticket: Ticket,
        tenant_id: int,
        update_data: dict,
        field_labels: dict[str, str],
        actor_id: int | None,
        actor_name: str | None,
    ) -> list[dict]:
        rows: list[dict] = []
        actor_type = "user" if actor_id is not None else "system"
        resolved_name = actor_name
        if actor_id is not None and not resolved_name:
            resolved_name = f"User #{actor_id}"
        if actor_id is None:
            resolved_name = "System"

        for field_key, new_raw in update_data.items():
            if not hasattr(ticket, field_key):
                continue

            old_value = TicketService._normalize_change_value(getattr(ticket, field_key))
            new_value = TicketService._normalize_change_value(new_raw)
            if old_value == new_value:
                continue

            rows.append({
                "tenant_id": tenant_id,
                "ticket_id": ticket.id,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "actor_name": resolved_name,
                "field_key": field_key,
                "field_label": field_labels.get(field_key, field_key),
                "field_source": "ticket",
                "old_value": old_value,
                "new_value": new_value,
            })
        return rows

    @staticmethod
    def _pack_change_batch(field_rows: list[dict]) -> list[dict]:
        """Pack all field diffs from one update into a single ticket_changes row."""
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
                "ticket_id": first["ticket_id"],
                "actor_type": first["actor_type"],
                "actor_id": first["actor_id"],
                "actor_name": first["actor_name"],
                "field_key": TICKET_CHANGE_BATCH_FIELD_KEY,
                "field_label": TICKET_CHANGE_BATCH_FIELD_KEY,
                "field_source": "ticket",
                "old_value": None,
                "new_value": entries,
            }
        ]

    @staticmethod
    def _build_create_entries(
        *,
        ticket: Ticket,
        field_labels: dict[str, str],
        created_fields: list[str],
    ) -> list[dict]:
        entries: list[dict] = []
        seen: set[str] = set()
        for field_key in ["ticket_number", *created_fields]:
            if field_key in seen or not hasattr(ticket, field_key):
                continue
            seen.add(field_key)
            value = TicketService._normalize_change_value(getattr(ticket, field_key))
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
    def _build_create_change_row(
        *,
        ticket: Ticket,
        tenant_id: int,
        entries: list[dict],
        actor_id: int | None,
        actor_name: str | None,
    ) -> list[dict]:
        if not entries:
            return []
        actor_type = "user" if actor_id is not None else "system"
        resolved_name = actor_name
        if actor_id is not None and not resolved_name:
            resolved_name = f"User #{actor_id}"
        if actor_id is None:
            resolved_name = "System"
        return [
            {
                "tenant_id": tenant_id,
                "ticket_id": ticket.id,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "actor_name": resolved_name,
                "field_key": TICKET_CHANGE_CREATE_FIELD_KEY,
                "field_label": TICKET_CHANGE_CREATE_FIELD_KEY,
                "field_source": "ticket",
                "old_value": None,
                "new_value": entries,
            }
        ]

    @staticmethod
    def _enrich_response(ticket: Ticket, slot_to_key: dict[str, str]) -> dict:
        resp = TicketResponse.model_validate(ticket).model_dump()
        custom_fields: dict[str, object] = {}
        for slot_col, field_key in slot_to_key.items():
            val = getattr(ticket, slot_col, None)
            if val is not None:
                custom_fields[field_key] = TicketService._normalize_change_value(val)
        resp["custom_fields"] = custom_fields
        return resp

    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, ticket_id: int) -> dict:
        item = await TicketRepository.get_by_id(db, ticket_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Ticket not found")
        slot_to_key = await TicketService._get_field_key_slot_map(db, tenant_id)
        return TicketService._enrich_response(item, slot_to_key)

    @staticmethod
    async def create_ticket(
        db: AsyncSession,
        tenant_id: int,
        data: TicketCreate,
        actor_id: int | None = None,
    ) -> dict:
        key_to_slot = await TicketService._get_key_to_slot_map(db, tenant_id)

        model_data: dict = {
            "tenant_id": tenant_id,
            "title": data.title,
            "status": data.status,
        }
        created_field_keys = ["title", "status"]
        field_labels: dict[str, str] = dict(SYSTEM_FIELD_LABELS)
        explicit_fields = set(data.model_fields_set)
        for field in (
            "description",
            "priority",
            "layout_id",
            "conversation_id",
            "user_id",
            "agent_id",
            "assignee_group_id",
        ):
            val = getattr(data, field, None)
            if val is not None:
                if field == "conversation_id":
                    await TicketService._validate_conversation(db, tenant_id, val)
                model_data[field] = val
                created_field_keys.append(field)

        TicketService._apply_system_field_aliases(
            model_data,
            data.custom_fields,
            explicit_fields,
            created_field_keys,
        )
        await TicketService._validate_assignee_values(
            db,
            tenant_id,
            model_data.get("assignee_group_id"),
            model_data.get("agent_id"),
        )

        key_to_meta = await TicketService._get_key_to_field_meta(db, tenant_id) if data.custom_fields else {}
        for cf_key, cf_val in data.custom_fields.items():
            slot_col = key_to_slot.get(cf_key)
            if slot_col:
                model_data[slot_col] = coerce_slot_value(slot_col, cf_val)
                created_field_keys.append(slot_col)
                field_meta = key_to_meta.get(cf_key)
                if field_meta:
                    field_labels[slot_col] = field_meta["name"]

        display_actor_name = await TicketService._resolve_actor_name(db, tenant_id, actor_id)
        audit_actor = await AuditActorService.resolve_current_employee(db, tenant_id, actor_id)
        model_data.update(AuditActorService.to_columns("created", audit_actor))
        model_data.update(AuditActorService.to_columns("updated", audit_actor))
        created_field_keys.extend(["created_by", "updated_by"])

        ticket = await TicketRepository.create(db, model_data, commit=False)
        create_entries = TicketService._build_create_entries(
            ticket=ticket,
            field_labels=field_labels,
            created_fields=created_field_keys,
        )
        create_rows = TicketService._build_create_change_row(
            ticket=ticket,
            tenant_id=tenant_id,
            entries=create_entries,
            actor_id=actor_id,
            actor_name=display_actor_name,
        )
        if create_rows:
            await TicketChangeRepository.create_many(db, create_rows, commit=False)
        await db.commit()
        await db.refresh(ticket)
        slot_to_key = await TicketService._get_field_key_slot_map(db, tenant_id)
        return TicketService._enrich_response(ticket, slot_to_key)

    @staticmethod
    async def update_ticket(
        db: AsyncSession,
        tenant_id: int,
        ticket_id: int,
        data: TicketUpdate,
        actor_id: int | None = None,
    ) -> dict:
        item = await TicketRepository.get_by_id(db, ticket_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Ticket not found")

        update_data: dict = {}
        field_labels: dict[str, str] = dict(SYSTEM_FIELD_LABELS)
        explicit_fields = set(data.model_fields_set)
        for field in ("title", "description", "status", "priority", "conversation_id", "user_id"):
            val = getattr(data, field, None)
            if val is not None:
                if field == "conversation_id":
                    await TicketService._validate_conversation(db, tenant_id, val)
                update_data[field] = val

        for field in ("agent_id", "assignee_group_id"):
            if field in explicit_fields:
                update_data[field] = getattr(data, field, None)

        TicketService._apply_system_field_aliases(
            update_data,
            data.custom_fields,
            explicit_fields,
        )

        final_assignee_group_id = update_data.get("assignee_group_id", item.assignee_group_id)
        final_agent_id = update_data.get("agent_id", item.agent_id)
        await TicketService._validate_assignee_values(
            db,
            tenant_id,
            final_assignee_group_id,
            final_agent_id,
        )

        if data.custom_fields:
            key_to_meta = await TicketService._get_key_to_field_meta(db, tenant_id)
            for cf_key, cf_val in data.custom_fields.items():
                field_meta = key_to_meta.get(cf_key)
                slot_col = field_meta["slot_column"] if field_meta else None
                if slot_col:
                    update_data[slot_col] = coerce_slot_value(slot_col, cf_val)
                    field_labels[slot_col] = field_meta["name"]

        display_actor_name = await TicketService._resolve_actor_name(db, tenant_id, actor_id)

        field_diff_rows = TicketService._build_change_rows(
            ticket=item,
            tenant_id=tenant_id,
            update_data=update_data,
            field_labels=field_labels,
            actor_id=actor_id,
            actor_name=display_actor_name,
        )
        change_rows = TicketService._pack_change_batch(field_diff_rows)
        if update_data:
            audit_actor = await AuditActorService.resolve_current_employee(db, tenant_id, actor_id)
            update_data.update(AuditActorService.to_columns("updated", audit_actor))

        if update_data and change_rows:
            item = await TicketRepository.update(db, item, update_data, commit=False)
            await TicketChangeRepository.create_many(db, change_rows, commit=False)
            await db.commit()
            await db.refresh(item)
        elif update_data:
            item = await TicketRepository.update(db, item, update_data)

        slot_to_key = await TicketService._get_field_key_slot_map(db, tenant_id)
        return TicketService._enrich_response(item, slot_to_key)

    @staticmethod
    async def delete_ticket(db: AsyncSession, tenant_id: int, ticket_id: int) -> None:
        item = await TicketRepository.get_by_id(db, ticket_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Ticket not found")
        await TicketRepository.delete(db, item)

    @staticmethod
    async def query_tickets(db: AsyncSession, tenant_id: int, req: TicketQueryRequest) -> dict:
        slot_map = await TicketService._get_slot_map(db, tenant_id)
        slot_to_key = await TicketService._get_field_key_slot_map(db, tenant_id)

        view_conditions: list[dict] = []
        view_condition_logic = "and"
        group_field_col: str | None = None

        if req.view_id:
            view = await db.get(TicketView, req.view_id)
            if view and view.tenant_id == tenant_id and view.is_enabled:
                view_conditions = [c if isinstance(c, dict) else dict(c) for c in (view.conditions or [])]
                view_condition_logic = view.condition_logic or "and"
                if view.group_field_id:
                    group_field_col = slot_map.get(view.group_field_id)

        temp_conds = [c.model_dump() for c in req.temp_conditions] if req.temp_conditions else []

        items, total = await TicketRepository.query_paginated(
            db,
            tenant_id,
            search=req.search,
            view_conditions=view_conditions,
            view_condition_logic=view_condition_logic,
            temp_conditions=temp_conds,
            temp_condition_logic=req.temp_condition_logic,
            group_field_col=group_field_col,
            group_value=req.group_value,
            slot_map=slot_map,
            sort_by=req.sort_by,
            sort_order=req.sort_order,
            page=req.page,
            per_page=req.per_page,
        )

        enriched = [TicketService._enrich_response(t, slot_to_key) for t in items]
        pages = (total + req.per_page - 1) // req.per_page if req.per_page > 0 else 0
        return {
            "items": enriched,
            "total": total,
            "page": req.page,
            "per_page": req.per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_enabled_views(db: AsyncSession, tenant_id: int) -> list[TicketView]:
        result = await db.execute(
            select(TicketView)
            .where(TicketView.tenant_id == tenant_id, TicketView.is_enabled.is_(True))
            .order_by(TicketView.sort_order)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_view_counts(db: AsyncSession, tenant_id: int) -> dict:
        views = await TicketService.get_enabled_views(db, tenant_id)
        slot_map = await TicketService._get_slot_map(db, tenant_id)

        total_count = await TicketRepository.count_by_conditions(
            db, tenant_id, [], "and", slot_map
        )

        counts = []
        for v in views:
            conditions = [c if isinstance(c, dict) else dict(c) for c in (v.conditions or [])]
            count = await TicketRepository.count_by_conditions(
                db, tenant_id, conditions, v.condition_logic or "and", slot_map
            )
            counts.append({"view_id": v.id, "count": count})
        return {"total_count": total_count, "items": counts}

    @staticmethod
    async def get_view_groups(
        db: AsyncSession,
        tenant_id: int,
        view_id: int,
        req: ViewGroupRequest,
    ) -> dict:
        """Aggregate tickets under a saved view by its configured group field."""
        view = await db.get(TicketView, view_id)
        if not view or view.tenant_id != tenant_id:
            raise NotFoundError("Ticket view not found")

        if not view.group_field_id:
            return {"group_field": None, "items": [], "total": 0}

        slot_map = await TicketService._get_slot_map(db, tenant_id)
        group_field_col = slot_map.get(view.group_field_id)

        field_def = await db.get(FdFieldDefinition, view.group_field_id)
        if not field_def or field_def.tenant_id != tenant_id or not group_field_col:
            return {"group_field": None, "items": [], "total": 0}

        view_conditions = [c if isinstance(c, dict) else dict(c) for c in (view.conditions or [])]
        view_condition_logic = view.condition_logic or "and"
        temp_conds = [c.model_dump() for c in req.temp_conditions] if req.temp_conditions else []

        items, total = await TicketRepository.aggregate_by_group_field(
            db,
            tenant_id,
            group_field_col=group_field_col,
            search=req.search,
            view_conditions=view_conditions,
            view_condition_logic=view_condition_logic,
            temp_conditions=temp_conds,
            temp_condition_logic=req.temp_condition_logic,
            slot_map=slot_map,
        )

        return {
            "group_field": {
                "id": field_def.id,
                "field_type": field_def.field_type,
                "name": field_def.name,
            },
            "items": items,
            "total": total,
        }
