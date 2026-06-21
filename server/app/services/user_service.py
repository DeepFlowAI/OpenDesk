"""
User service — business logic for end-user list / detail / create / update
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.excel import build_xlsx
from app.models.user import User
from app.models.user_view import UserView
from app.models.fd_field_definition import FdFieldDefinition
from app.repositories.entity_change_repository import EntityChangeRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate, UserQueryRequest, UserResponse, UserExportRequest, UserExportColumn
from app.schemas.view_group import ViewGroupRequest
from app.services.audit_actor_service import AuditActorService
from app.services.entity_change_service import EntityChangeService
from app.services.fd_field_definition_service import coerce_slot_value

USER_EXPORT_MAX_ROWS = 5000
USER_LEVEL_NORMAL = "normal"
USER_LEVEL_VIP = "vip"
USER_LEVEL_VALUES = {USER_LEVEL_NORMAL, USER_LEVEL_VIP}


USER_SYSTEM_FIELD_LABELS: dict[str, str] = {
    "public_id": "用户 ID",
    "name": "昵称",
    "nickname": "昵称",
    "external_id": "外部用户 ID",
    "email": "邮箱",
    "phone": "手机号",
    "gender": "性别",
    "level": "等级",
    "address": "地址",
    "remark": "备注",
    "web_id": "Web ID",
    "organization_id": "组织",
    "created_by": "创建人",
    "updated_by": "更新人",
    "created_at": "创建时间",
    "updated_at": "更新时间",
}

USER_EXPORT_DEFAULT_COLUMNS = [
    UserExportColumn(field_key="public_id", name="用户 ID", field_type="text"),
    UserExportColumn(field_key="name", name="昵称", field_type="text"),
    UserExportColumn(field_key="email", name="邮箱", field_type="email"),
    UserExportColumn(field_key="phone", name="手机号", field_type="phone"),
    UserExportColumn(field_key="organization_id", name="组织", field_type="text"),
    UserExportColumn(field_key="updated_at", name="更新时间", field_type="datetime"),
]

USER_EXPORT_SYSTEM_FIELDS = {
    "public_id",
    "name",
    "nickname",
    "external_id",
    "email",
    "phone",
    "gender",
    "level",
    "address",
    "remark",
    "web_id",
    "avatar_color",
    "channel_id",
    "organization_id",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
}

USER_EXPORT_KEY_ALIASES = {
    "nickname": "name",
}

GENDER_EXPORT_LABELS = {
    "male": {"zh": "男", "en": "Male"},
    "female": {"zh": "女", "en": "Female"},
    "unknown": {"zh": "未知", "en": "Unknown"},
    "other": {"zh": "其他", "en": "Other"},
}

USER_LEVEL_EXPORT_LABELS = {
    USER_LEVEL_NORMAL: {"zh": "普通", "en": "Normal"},
    USER_LEVEL_VIP: {"zh": "VIP", "en": "VIP"},
}


class UserService:

    @staticmethod
    def _normalize_level(value: object) -> str:
        if value is None or value == "":
            return USER_LEVEL_NORMAL
        level = str(value).strip()
        if level not in USER_LEVEL_VALUES:
            raise ValidationError("Invalid user level")
        return level

    @staticmethod
    def _normalize_custom_field_value(val: object) -> object:
        """
        Slot columns map to DB types (Numeric→Decimal, Date, DateTime) that are not valid
        for UserResponse.custom_fields; normalize so response_model validation succeeds.
        """
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
        """Build { field_definition_id: slot_column } for all active custom fields."""
        result = await db.execute(
            select(FdFieldDefinition.id, FdFieldDefinition.slot_column).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.status == "active",
            )
        )
        return {row.id: row.slot_column for row in result.all()}

    @staticmethod
    async def _get_field_key_slot_map(db: AsyncSession, tenant_id: int) -> dict[str, str]:
        """
        Build a mapping for custom fields used by the 'user' domain:
        { field_key_or_id_str: slot_column }
        Also returns reverse map: { slot_column: field_key_or_id_str }
        """
        result = await db.execute(
            select(
                FdFieldDefinition.id,
                FdFieldDefinition.field_key,
                FdFieldDefinition.slot_column,
                FdFieldDefinition.name,
            ).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.status == "active",
            )
        )
        rows = result.all()
        slot_to_key: dict[str, str] = {}
        for row in rows:
            key = row.field_key or str(row.id)
            slot_to_key[row.slot_column] = key
        return slot_to_key

    @staticmethod
    def _enrich_user_response(user: User, slot_to_key: dict[str, str]) -> dict:
        """Convert ORM user to dict with custom_fields populated from slot columns."""
        resp = UserResponse.model_validate(user).model_dump()
        custom_fields: dict[str, object] = {}
        for slot_col, field_key in slot_to_key.items():
            val = getattr(user, slot_col, None)
            if val is not None:
                custom_fields[field_key] = UserService._normalize_custom_field_value(val)
        resp["custom_fields"] = custom_fields
        return resp

    @staticmethod
    async def _get_key_to_slot_map(db: AsyncSession, tenant_id: int) -> dict[str, str]:
        """Build { field_key and legacy field_id_str: slot_column } for writing custom fields."""
        result = await db.execute(
            select(FdFieldDefinition.id, FdFieldDefinition.field_key, FdFieldDefinition.slot_column).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.status == "active",
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
        """Build { field_key and legacy field_id_str: {name, slot_column} } for user custom fields."""
        result = await db.execute(
            select(
                FdFieldDefinition.id,
                FdFieldDefinition.field_key,
                FdFieldDefinition.name,
                FdFieldDefinition.slot_column,
            ).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.status == "active",
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
    async def _validate_organization(db: AsyncSession, tenant_id: int, organization_id: int | None) -> None:
        """Ensure the selected organization belongs to the current tenant."""
        if organization_id is None:
            return
        organization = await OrganizationRepository.get_by_id(db, organization_id)
        if not organization or organization.tenant_id != tenant_id:
            raise NotFoundError("Organization not found")

    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, user_id: int):
        item = await UserRepository.get_by_id(db, user_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("User not found")
        slot_to_key = await UserService._get_field_key_slot_map(db, tenant_id)
        return UserService._enrich_user_response(item, slot_to_key)

    @staticmethod
    async def get_by_ref(db: AsyncSession, tenant_id: int, user_ref: str):
        """Get a user by public ID, with short-term numeric ID compatibility."""
        item = None
        if user_ref.isdigit():
            item = await UserRepository.get_by_id(db, int(user_ref))
        else:
            item = await UserRepository.get_by_public_id(db, user_ref)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("User not found")
        slot_to_key = await UserService._get_field_key_slot_map(db, tenant_id)
        return UserService._enrich_user_response(item, slot_to_key)

    @staticmethod
    async def create_user(
        db: AsyncSession,
        tenant_id: int,
        data: UserCreate,
        actor_id: int | None = None,
    ) -> dict:
        """Create a new end user under the given tenant."""
        key_to_slot = await UserService._get_key_to_slot_map(db, tenant_id)
        await UserService._validate_organization(db, tenant_id, data.organization_id)

        model_data: dict = {
            "tenant_id": tenant_id,
            "external_id": f"usr_{uuid.uuid4().hex[:16]}",
            "name": data.name,
            "level": UserService._normalize_level(data.level),
        }
        created_field_keys = ["name", "level"]
        field_labels: dict[str, str] = dict(USER_SYSTEM_FIELD_LABELS)
        for field in ("email", "phone", "gender", "address", "remark", "web_id", "organization_id"):
            val = getattr(data, field, None)
            if val is not None:
                model_data[field] = val
                created_field_keys.append(field)

        key_to_meta = await UserService._get_key_to_field_meta(db, tenant_id) if data.custom_fields else {}
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

        user = await UserRepository.create(db, model_data, commit=False)
        create_entries = EntityChangeService.build_create_entries(
            entity=user,
            field_labels=field_labels,
            created_fields=created_field_keys,
        )
        create_rows = EntityChangeService.build_create_change_row(
            entity_type="user",
            entity_id=user.id,
            tenant_id=tenant_id,
            entries=create_entries,
            actor_id=actor_id,
            actor_name=display_actor_name,
        )
        if create_rows:
            await EntityChangeRepository.create_many(db, create_rows, commit=False)
        await db.commit()
        await db.refresh(user)
        slot_to_key = await UserService._get_field_key_slot_map(db, tenant_id)
        return UserService._enrich_user_response(user, slot_to_key)

    @staticmethod
    async def update_user(
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        data: UserUpdate,
        actor_id: int | None = None,
    ) -> dict:
        """Update an existing end user."""
        item = await UserRepository.get_by_id(db, user_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("User not found")

        fields_set = data.model_fields_set
        update_data: dict = {}
        field_labels: dict[str, str] = dict(USER_SYSTEM_FIELD_LABELS)
        for field in ("name", "email", "phone", "gender", "level", "address", "remark", "web_id", "organization_id"):
            if field not in fields_set:
                continue
            val = getattr(data, field)
            if field == "name" and val is None:
                continue
            if field == "level":
                val = UserService._normalize_level(val)
            update_data[field] = val

        if "organization_id" in update_data:
            await UserService._validate_organization(db, tenant_id, update_data["organization_id"])

        if data.custom_fields:
            key_to_meta = await UserService._get_key_to_field_meta(db, tenant_id)
            for cf_key, cf_val in data.custom_fields.items():
                field_meta = key_to_meta.get(cf_key)
                slot_col = field_meta["slot_column"] if field_meta else None
                if slot_col:
                    update_data[slot_col] = coerce_slot_value(slot_col, cf_val)
                    field_labels[slot_col] = field_meta["name"]

        display_actor_name = await EntityChangeService.resolve_actor_name(db, tenant_id, actor_id)
        field_diff_rows = EntityChangeService.build_change_rows(
            entity_type="user",
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
            item = await UserRepository.update(db, item, update_data, commit=False)
            if change_rows:
                await EntityChangeRepository.create_many(db, change_rows, commit=False)
            await db.commit()
            await db.refresh(item)

        slot_to_key = await UserService._get_field_key_slot_map(db, tenant_id)
        return UserService._enrich_user_response(item, slot_to_key)

    @staticmethod
    async def delete_user(db: AsyncSession, tenant_id: int, user_id: int) -> None:
        """Delete an existing end user."""
        item = await UserRepository.get_by_id(db, user_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("User not found")
        await UserRepository.delete(db, item)

    @staticmethod
    async def query_users(db: AsyncSession, tenant_id: int, req: UserQueryRequest) -> dict:
        """Query users with view-based + temp filters."""
        slot_map = await UserService._get_slot_map(db, tenant_id)
        slot_to_key = await UserService._get_field_key_slot_map(db, tenant_id)

        view_conditions: list[dict] = []
        view_condition_logic = "and"
        group_field_col: str | None = None

        if req.view_id:
            view = await db.get(UserView, req.view_id)
            if view and view.tenant_id == tenant_id and view.is_enabled:
                view_conditions = [c if isinstance(c, dict) else dict(c) for c in (view.conditions or [])]
                view_condition_logic = view.condition_logic or "and"
                if view.group_field_id:
                    group_field_col = slot_map.get(view.group_field_id)

        temp_conds = [c.model_dump() for c in req.temp_conditions] if req.temp_conditions else []

        items, total = await UserRepository.query_paginated(
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

        enriched = [UserService._enrich_user_response(u, slot_to_key) for u in items]

        pages = (total + req.per_page - 1) // req.per_page if req.per_page > 0 else 0
        return {
            "items": enriched,
            "total": total,
            "page": req.page,
            "per_page": req.per_page,
            "pages": pages,
        }

    @staticmethod
    async def export_users(db: AsyncSession, tenant_id: int, req: UserExportRequest) -> tuple[bytes, str]:
        """Export users matching current list filters to an XLSX workbook."""
        slot_map = await UserService._get_slot_map(db, tenant_id)
        slot_to_key = await UserService._get_field_key_slot_map(db, tenant_id)

        view_conditions: list[dict] = []
        view_condition_logic = "and"
        group_field_col: str | None = None

        if req.view_id:
            view = await db.get(UserView, req.view_id)
            if view and view.tenant_id == tenant_id and view.is_enabled:
                view_conditions = [c if isinstance(c, dict) else dict(c) for c in (view.conditions or [])]
                view_condition_logic = view.condition_logic or "and"
                if view.group_field_id:
                    group_field_col = slot_map.get(view.group_field_id)

        temp_conds = [c.model_dump() for c in req.temp_conditions] if req.temp_conditions else []
        items, total = await UserRepository.query_paginated(
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
            per_page=USER_EXPORT_MAX_ROWS + 1,
        )
        if total > USER_EXPORT_MAX_ROWS:
            raise ValidationError("Too many records to export")

        columns = UserService._normalize_export_columns(req.columns)
        organization_names = await UserService._get_export_organization_names(db, tenant_id, items)
        option_lookup = await UserService._get_custom_field_option_lookup(db, tenant_id, "user")

        headers = [column.name for column in columns]
        enriched = [UserService._enrich_user_response(user, slot_to_key) for user in items]
        rows = [
            [
                UserService._export_cell_value(row, column, req.locale, organization_names, option_lookup)
                for column in columns
            ]
            for row in enriched
        ]
        workbook = build_xlsx(headers, rows, sheet_name="Users")
        filename = f"users-export-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
        return workbook, filename

    @staticmethod
    def _normalize_export_columns(columns: list[UserExportColumn]) -> list[UserExportColumn]:
        """Filter unsupported or internal columns from the client-provided list."""
        normalized: list[UserExportColumn] = []
        for column in columns:
            if column.field_key == "id":
                continue
            if column.field_key and column.field_key in USER_EXPORT_SYSTEM_FIELDS:
                normalized.append(column)
                continue
            if column.field_id is not None or column.field_key:
                normalized.append(column)
        return normalized or USER_EXPORT_DEFAULT_COLUMNS

    @staticmethod
    async def _get_export_organization_names(
        db: AsyncSession,
        tenant_id: int,
        users: list[User],
    ) -> dict[int, str]:
        org_ids = [user.organization_id for user in users if user.organization_id is not None]
        organizations = await OrganizationRepository.list_by_ids(db, tenant_id, org_ids)
        return {organization.id: organization.name for organization in organizations}

    @staticmethod
    def _export_cell_value(
        row: dict,
        column: UserExportColumn,
        locale: str,
        organization_names: dict[int, str],
        option_lookup: dict[str, dict[str, str]],
    ) -> str:
        key = column.field_key
        if key and key in USER_EXPORT_SYSTEM_FIELDS:
            real_key = USER_EXPORT_KEY_ALIASES.get(key, key)
            value = row.get(real_key)
            if value is None:
                return ""
            if key == "organization_id":
                return organization_names.get(int(value), str(value))
            if key == "gender":
                label = GENDER_EXPORT_LABELS.get(str(value))
                return label.get(locale, label["zh"]) if label else str(value)
            if key == "level":
                label = USER_LEVEL_EXPORT_LABELS.get(str(value))
                return label.get(locale, label["zh"]) if label else str(value)
            if key in {"created_by", "updated_by"}:
                return UserService._format_actor_value(value)
            return UserService._format_export_value(value)

        custom_key = key if key and key not in USER_EXPORT_SYSTEM_FIELDS else None
        legacy_key = str(column.field_id) if column.field_id is not None else None
        lookup_key = custom_key or legacy_key or ""
        value = None
        custom_fields = row.get("custom_fields") or {}
        if isinstance(custom_fields, dict):
            if custom_key and custom_key in custom_fields:
                value = custom_fields[custom_key]
            elif legacy_key and legacy_key in custom_fields:
                value = custom_fields[legacy_key]
        return UserService._format_export_value(value, option_lookup.get(lookup_key))

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
            return ", ".join(UserService._format_export_value(item, options) for item in value)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        text = str(value)
        if options:
            if "," in text:
                return ", ".join(options.get(item.strip(), item.strip()) for item in text.split(","))
            return options.get(text, text)
        return text

    @staticmethod
    async def get_enabled_views(db: AsyncSession, tenant_id: int) -> list[UserView]:
        """Get all enabled views for the tenant, ordered by sort_order."""
        result = await db.execute(
            select(UserView)
            .where(UserView.tenant_id == tenant_id, UserView.is_enabled.is_(True))
            .order_by(UserView.sort_order)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_view_counts(db: AsyncSession, tenant_id: int) -> dict:
        """Get user count per enabled view + total count (sidebar display)."""
        views = await UserService.get_enabled_views(db, tenant_id)
        slot_map = await UserService._get_slot_map(db, tenant_id)

        total_count = await UserRepository.count_by_conditions(
            db, tenant_id, [], "and", slot_map
        )

        counts = []
        for v in views:
            conditions = [c if isinstance(c, dict) else dict(c) for c in (v.conditions or [])]
            count = await UserRepository.count_by_conditions(
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
        """Aggregate users under a saved view by its configured group field."""
        view = await db.get(UserView, view_id)
        if not view or view.tenant_id != tenant_id:
            raise NotFoundError("User view not found")

        if not view.group_field_id:
            return {"group_field": None, "items": [], "total": 0}

        slot_map = await UserService._get_slot_map(db, tenant_id)
        group_field_col = slot_map.get(view.group_field_id)

        field_def = await db.get(FdFieldDefinition, view.group_field_id)
        if not field_def or field_def.tenant_id != tenant_id or not group_field_col:
            return {"group_field": None, "items": [], "total": 0}

        view_conditions = [c if isinstance(c, dict) else dict(c) for c in (view.conditions or [])]
        view_condition_logic = view.condition_logic or "and"
        temp_conds = [c.model_dump() for c in req.temp_conditions] if req.temp_conditions else []

        items, total = await UserRepository.aggregate_by_group_field(
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
