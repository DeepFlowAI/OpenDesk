"""
Organization service — business logic for organization CRUD + list
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.excel import build_xlsx
from app.models.organization import Organization
from app.models.organization_view import OrganizationView
from app.models.fd_field_definition import FdFieldDefinition
from app.repositories.entity_change_repository import EntityChangeRepository
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationQueryRequest,
    OrganizationResponse,
    OrganizationExportRequest,
    OrganizationExportColumn,
)
from app.schemas.view_group import ViewGroupRequest
from app.services.audit_actor_service import AuditActorService
from app.services.entity_change_service import EntityChangeService
from app.services.fd_field_definition_service import coerce_slot_value


ORGANIZATION_EXPORT_MAX_ROWS = 5000


ORG_SYSTEM_FIELD_LABELS: dict[str, str] = {
    "public_id": "组织 ID",
    "name": "名称",
    "description": "描述",
    "created_by": "创建人",
    "updated_by": "更新人",
    "created_at": "创建时间",
    "updated_at": "更新时间",
    "__user_count": "用户数量",
}

ORGANIZATION_EXPORT_DEFAULT_COLUMNS = [
    OrganizationExportColumn(field_key="public_id", name="组织 ID", field_type="text"),
    OrganizationExportColumn(field_key="name", name="名称", field_type="text"),
    OrganizationExportColumn(field_key="__user_count", name="用户数量", field_type="number"),
    OrganizationExportColumn(field_key="updated_at", name="更新时间", field_type="datetime"),
]

ORGANIZATION_EXPORT_SYSTEM_FIELDS = {
    "public_id",
    "name",
    "description",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "__user_count",
    "user_count",
}


class OrganizationService:

    @staticmethod
    def _normalize_custom_field_value(val: object) -> object:
        if val is None:
            return None
        if isinstance(val, Decimal):
            return float(val)
        if isinstance(val, datetime):
            return val.isoformat()
        if isinstance(val, date):
            return val.isoformat()
        return val

    @staticmethod
    async def _get_slot_map(db: AsyncSession, tenant_id: int) -> dict[int, str]:
        """Build { field_definition_id: slot_column } for active custom fields in organization domain."""
        result = await db.execute(
            select(FdFieldDefinition.id, FdFieldDefinition.slot_column).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.status == "active",
                FdFieldDefinition.domain == "organization",
            )
        )
        return {row.id: row.slot_column for row in result.all()}

    @staticmethod
    async def _get_field_key_slot_map(db: AsyncSession, tenant_id: int) -> dict[str, str]:
        """Build { slot_column: field_key } reverse map for response enrichment."""
        result = await db.execute(
            select(FdFieldDefinition.id, FdFieldDefinition.field_key, FdFieldDefinition.slot_column).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.status == "active",
                FdFieldDefinition.domain == "organization",
            )
        )
        return {row.slot_column: (row.field_key or str(row.id)) for row in result.all()}

    @staticmethod
    async def _get_key_to_slot_map(db: AsyncSession, tenant_id: int) -> dict[str, str]:
        """Build { field_key and legacy field_id_str: slot_column } for writing custom fields."""
        result = await db.execute(
            select(FdFieldDefinition.id, FdFieldDefinition.field_key, FdFieldDefinition.slot_column).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.status == "active",
                FdFieldDefinition.domain == "organization",
            )
        )
        key_to_slot: dict[str, str] = {}
        for row in result.all():
            key_to_slot[str(row.id)] = row.slot_column
            if row.field_key:
                key_to_slot[row.field_key] = row.slot_column
        return key_to_slot

    @staticmethod
    async def _get_key_to_field_meta(db: AsyncSession, tenant_id: int) -> dict[str, dict[str, str]]:
        """Build { field_key and legacy field_id_str: {name, slot_column} } for organization custom fields."""
        result = await db.execute(
            select(
                FdFieldDefinition.id,
                FdFieldDefinition.field_key,
                FdFieldDefinition.name,
                FdFieldDefinition.slot_column,
            ).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.status == "active",
                FdFieldDefinition.domain == "organization",
            )
        )
        key_to_meta: dict[str, dict[str, str]] = {}
        for row in result.all():
            meta = {"name": row.name, "slot_column": row.slot_column}
            key_to_meta[str(row.id)] = meta
            if row.field_key:
                key_to_meta[row.field_key] = meta
        return key_to_meta

    @staticmethod
    async def _get_custom_field_option_lookup(
        db: AsyncSession,
        tenant_id: int,
        domain: str,
    ) -> dict[str, dict[str, str]]:
        """Build option label lookup for select custom fields."""
        result = await db.execute(
            select(FdFieldDefinition)
            .options(
                selectinload(FdFieldDefinition.options),
                selectinload(FdFieldDefinition.tree_nodes),
            )
            .where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.domain == domain,
                FdFieldDefinition.status == "active",
            )
        )
        lookup: dict[str, dict[str, str]] = {}
        for field in result.scalars().all():
            value_map: dict[str, str] = {}
            for option in field.options or []:
                if option.is_active:
                    value_map[option.value] = option.label
            for node in field.tree_nodes or []:
                if node.is_active:
                    value_map[node.value] = node.label
            type_options = field.type_config.get("options") if isinstance(field.type_config, dict) else None
            if isinstance(type_options, list):
                for option in type_options:
                    value = option.get("value") if isinstance(option, dict) else None
                    label = option.get("label") if isinstance(option, dict) else None
                    if value is not None and label is not None:
                        value_map[str(value)] = str(label)
            if value_map:
                lookup[field.field_key] = value_map
                lookup[str(field.id)] = value_map
        return lookup

    @staticmethod
    def _enrich_response(org: Organization, slot_to_key: dict[str, str], user_count: int = 0) -> dict:
        """Convert ORM organization to dict with custom_fields populated from slot columns."""
        resp = OrganizationResponse.model_validate(org).model_dump()
        custom_fields: dict[str, object] = {}
        for slot_col, field_key in slot_to_key.items():
            val = getattr(org, slot_col, None)
            if val is not None:
                custom_fields[field_key] = OrganizationService._normalize_custom_field_value(val)
        resp["custom_fields"] = custom_fields
        resp["user_count"] = user_count
        return resp

    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, org_id: int) -> dict:
        item = await OrganizationRepository.get_by_id(db, org_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Organization not found")
        slot_to_key = await OrganizationService._get_field_key_slot_map(db, tenant_id)
        user_count = await OrganizationRepository.count_users(db, tenant_id, org_id)
        return OrganizationService._enrich_response(item, slot_to_key, user_count)

    @staticmethod
    async def get_by_ref(db: AsyncSession, tenant_id: int, org_ref: str) -> dict:
        """Get an organization by public ID, with short-term numeric ID compatibility."""
        item = None
        if org_ref.isdigit():
            item = await OrganizationRepository.get_by_id(db, int(org_ref))
        else:
            item = await OrganizationRepository.get_by_public_id(db, org_ref)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Organization not found")
        slot_to_key = await OrganizationService._get_field_key_slot_map(db, tenant_id)
        user_count = await OrganizationRepository.count_users(db, tenant_id, item.id)
        return OrganizationService._enrich_response(item, slot_to_key, user_count)

    @staticmethod
    async def create_organization(
        db: AsyncSession,
        tenant_id: int,
        data: OrganizationCreate,
        actor_id: int | None = None,
    ) -> dict:
        key_to_slot = await OrganizationService._get_key_to_slot_map(db, tenant_id)

        model_data: dict = {
            "tenant_id": tenant_id,
            "name": data.name,
        }
        created_field_keys = ["name"]
        field_labels: dict[str, str] = dict(ORG_SYSTEM_FIELD_LABELS)
        if data.description is not None:
            model_data["description"] = data.description
            created_field_keys.append("description")

        key_to_meta = await OrganizationService._get_key_to_field_meta(db, tenant_id) if data.custom_fields else {}
        for cf_key, cf_val in data.custom_fields.items():
            field_meta = key_to_meta.get(cf_key)
            slot_col = field_meta["slot_column"] if field_meta else key_to_slot.get(cf_key)
            if slot_col:
                model_data[slot_col] = coerce_slot_value(slot_col, cf_val)
                created_field_keys.append(slot_col)
                if field_meta:
                    field_labels[slot_col] = field_meta["name"]

        display_actor_name = await EntityChangeService.resolve_actor_name(db, tenant_id, actor_id)
        audit_actor = await AuditActorService.resolve_current_employee(db, tenant_id, actor_id)
        model_data.update(AuditActorService.to_columns("created", audit_actor))
        model_data.update(AuditActorService.to_columns("updated", audit_actor))

        org = await OrganizationRepository.create(db, model_data, commit=False)
        create_entries = EntityChangeService.build_create_entries(
            entity=org,
            field_labels=field_labels,
            created_fields=created_field_keys,
        )
        create_rows = EntityChangeService.build_create_change_row(
            entity_type="organization",
            entity_id=org.id,
            tenant_id=tenant_id,
            entries=create_entries,
            actor_id=actor_id,
            actor_name=display_actor_name,
        )
        if create_rows:
            await EntityChangeRepository.create_many(db, create_rows, commit=False)
        await db.commit()
        await db.refresh(org)
        slot_to_key = await OrganizationService._get_field_key_slot_map(db, tenant_id)
        return OrganizationService._enrich_response(org, slot_to_key, 0)

    @staticmethod
    async def update_organization(
        db: AsyncSession,
        tenant_id: int,
        org_id: int,
        data: OrganizationUpdate,
        actor_id: int | None = None,
    ) -> dict:
        item = await OrganizationRepository.get_by_id(db, org_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Organization not found")

        update_data: dict = {}
        field_labels: dict[str, str] = dict(ORG_SYSTEM_FIELD_LABELS)
        for field in ("name", "description"):
            val = getattr(data, field, None)
            if val is not None:
                update_data[field] = val

        if data.custom_fields:
            key_to_meta = await OrganizationService._get_key_to_field_meta(db, tenant_id)
            for cf_key, cf_val in data.custom_fields.items():
                field_meta = key_to_meta.get(cf_key)
                slot_col = field_meta["slot_column"] if field_meta else None
                if slot_col:
                    update_data[slot_col] = coerce_slot_value(slot_col, cf_val)
                    field_labels[slot_col] = field_meta["name"]

        display_actor_name = await EntityChangeService.resolve_actor_name(db, tenant_id, actor_id)
        field_diff_rows = EntityChangeService.build_change_rows(
            entity_type="organization",
            entity_id=item.id,
            current=item,
            tenant_id=tenant_id,
            update_data=update_data,
            field_labels=field_labels,
            actor_id=actor_id,
            actor_name=display_actor_name,
        )
        change_rows = EntityChangeService.pack_change_batch(field_diff_rows)

        if update_data:
            audit_actor = await AuditActorService.resolve_current_employee(db, tenant_id, actor_id)
            update_data.update(AuditActorService.to_columns("updated", audit_actor))
            item = await OrganizationRepository.update(db, item, update_data, commit=False)
            if change_rows:
                await EntityChangeRepository.create_many(db, change_rows, commit=False)
            await db.commit()
            await db.refresh(item)

        slot_to_key = await OrganizationService._get_field_key_slot_map(db, tenant_id)
        user_count = await OrganizationRepository.count_users(db, tenant_id, org_id)
        return OrganizationService._enrich_response(item, slot_to_key, user_count)

    @staticmethod
    async def delete_organization(db: AsyncSession, tenant_id: int, org_id: int) -> None:
        item = await OrganizationRepository.get_by_id(db, org_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Organization not found")
        await OrganizationRepository.delete(db, item)

    @staticmethod
    async def query_organizations(db: AsyncSession, tenant_id: int, req: OrganizationQueryRequest) -> dict:
        slot_map = await OrganizationService._get_slot_map(db, tenant_id)
        slot_to_key = await OrganizationService._get_field_key_slot_map(db, tenant_id)

        view_conditions: list[dict] = []
        view_condition_logic = "and"
        group_field_col: str | None = None

        if req.view_id:
            view = await db.get(OrganizationView, req.view_id)
            if view and view.tenant_id == tenant_id and view.is_enabled:
                view_conditions = [c if isinstance(c, dict) else dict(c) for c in (view.conditions or [])]
                view_condition_logic = view.condition_logic or "and"
                if view.group_field_id:
                    group_field_col = slot_map.get(view.group_field_id)

        temp_conds = [c.model_dump() for c in req.temp_conditions] if req.temp_conditions else []

        items, total = await OrganizationRepository.query_paginated(
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

        enriched = []
        for org in items:
            user_count = await OrganizationRepository.count_users(db, tenant_id, org.id)
            enriched.append(OrganizationService._enrich_response(org, slot_to_key, user_count))

        pages = (total + req.per_page - 1) // req.per_page if req.per_page > 0 else 0
        return {
            "items": enriched,
            "total": total,
            "page": req.page,
            "per_page": req.per_page,
            "pages": pages,
        }

    @staticmethod
    async def export_organizations(
        db: AsyncSession,
        tenant_id: int,
        req: OrganizationExportRequest,
    ) -> tuple[bytes, str]:
        """Export organizations matching current list filters to an XLSX workbook."""
        slot_map = await OrganizationService._get_slot_map(db, tenant_id)
        slot_to_key = await OrganizationService._get_field_key_slot_map(db, tenant_id)

        view_conditions: list[dict] = []
        view_condition_logic = "and"
        group_field_col: str | None = None

        if req.view_id:
            view = await db.get(OrganizationView, req.view_id)
            if view and view.tenant_id == tenant_id and view.is_enabled:
                view_conditions = [c if isinstance(c, dict) else dict(c) for c in (view.conditions or [])]
                view_condition_logic = view.condition_logic or "and"
                if view.group_field_id:
                    group_field_col = slot_map.get(view.group_field_id)

        temp_conds = [c.model_dump() for c in req.temp_conditions] if req.temp_conditions else []
        items, total = await OrganizationRepository.query_paginated(
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
            page=1,
            per_page=ORGANIZATION_EXPORT_MAX_ROWS + 1,
        )
        if total > ORGANIZATION_EXPORT_MAX_ROWS:
            raise ValidationError("Too many records to export")

        columns = OrganizationService._normalize_export_columns(req.columns)
        option_lookup = await OrganizationService._get_custom_field_option_lookup(db, tenant_id, "organization")

        headers = [column.name for column in columns]
        enriched = []
        for organization in items:
            user_count = await OrganizationRepository.count_users(db, tenant_id, organization.id)
            enriched.append(OrganizationService._enrich_response(organization, slot_to_key, user_count))
        rows = [
            [
                OrganizationService._export_cell_value(row, column, option_lookup)
                for column in columns
            ]
            for row in enriched
        ]
        workbook = build_xlsx(headers, rows, sheet_name="Organizations")
        filename = f"organizations-export-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
        return workbook, filename

    @staticmethod
    def _normalize_export_columns(
        columns: list[OrganizationExportColumn],
    ) -> list[OrganizationExportColumn]:
        """Filter unsupported or internal columns from the client-provided list."""
        normalized: list[OrganizationExportColumn] = []
        for column in columns:
            if column.field_key == "id":
                continue
            if column.field_key and column.field_key in ORGANIZATION_EXPORT_SYSTEM_FIELDS:
                normalized.append(column)
                continue
            if column.field_id is not None or column.field_key:
                normalized.append(column)
        return normalized or ORGANIZATION_EXPORT_DEFAULT_COLUMNS

    @staticmethod
    def _export_cell_value(
        row: dict,
        column: OrganizationExportColumn,
        option_lookup: dict[str, dict[str, str]],
    ) -> str:
        key = column.field_key
        if key and key in ORGANIZATION_EXPORT_SYSTEM_FIELDS:
            value = row.get("user_count") if key == "__user_count" else row.get(key)
            if value is None:
                return ""
            if key in {"created_by", "updated_by"}:
                return OrganizationService._format_actor_value(value)
            return OrganizationService._format_export_value(value)

        custom_key = key if key and key not in ORGANIZATION_EXPORT_SYSTEM_FIELDS else None
        legacy_key = str(column.field_id) if column.field_id is not None else None
        lookup_key = custom_key or legacy_key or ""
        value = None
        custom_fields = row.get("custom_fields") or {}
        if isinstance(custom_fields, dict):
            if custom_key and custom_key in custom_fields:
                value = custom_fields[custom_key]
            elif legacy_key and legacy_key in custom_fields:
                value = custom_fields[legacy_key]
        return OrganizationService._format_export_value(value, option_lookup.get(lookup_key))

    @staticmethod
    def _format_actor_value(value: object) -> str:
        if isinstance(value, dict):
            return str(value.get("actor_name") or "")
        return ""

    @staticmethod
    def _format_export_value(value: object, options: dict[str, str] | None = None) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(value, date):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, list):
            return ", ".join(OrganizationService._format_export_value(item, options) for item in value)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        text = str(value)
        if options:
            if "," in text:
                return ", ".join(options.get(item.strip(), item.strip()) for item in text.split(","))
            return options.get(text, text)
        return text

    @staticmethod
    async def get_enabled_views(db: AsyncSession, tenant_id: int) -> list[OrganizationView]:
        result = await db.execute(
            select(OrganizationView)
            .where(OrganizationView.tenant_id == tenant_id, OrganizationView.is_enabled.is_(True))
            .order_by(OrganizationView.sort_order)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_view_counts(db: AsyncSession, tenant_id: int) -> dict:
        views = await OrganizationService.get_enabled_views(db, tenant_id)
        slot_map = await OrganizationService._get_slot_map(db, tenant_id)

        total_count = await OrganizationRepository.count_by_conditions(
            db, tenant_id, [], "and", slot_map
        )

        counts = []
        for v in views:
            conditions = [c if isinstance(c, dict) else dict(c) for c in (v.conditions or [])]
            count = await OrganizationRepository.count_by_conditions(
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
        """Aggregate organizations under a saved view by its group field."""
        view = await db.get(OrganizationView, view_id)
        if not view or view.tenant_id != tenant_id:
            raise NotFoundError("Organization view not found")

        if not view.group_field_id:
            return {"group_field": None, "items": [], "total": 0}

        slot_map = await OrganizationService._get_slot_map(db, tenant_id)
        group_field_col = slot_map.get(view.group_field_id)

        field_def = await db.get(FdFieldDefinition, view.group_field_id)
        if not field_def or field_def.tenant_id != tenant_id or not group_field_col:
            return {"group_field": None, "items": [], "total": 0}

        view_conditions = [c if isinstance(c, dict) else dict(c) for c in (view.conditions or [])]
        view_condition_logic = view.condition_logic or "and"
        temp_conds = [c.model_dump() for c in req.temp_conditions] if req.temp_conditions else []

        items, total = await OrganizationRepository.aggregate_by_group_field(
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
