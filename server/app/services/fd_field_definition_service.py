"""
Service for field definition management with slot allocation.

System fields are hardcoded in app.constants.system_fields (not stored in
fd_field_definitions).  Per-tenant overrides for system fields live in
fd_system_field_overrides.  Custom fields are fully persisted in
fd_field_definitions.

The list API merges system fields + overrides + custom fields into a single
unified response.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.system_fields import get_system_fields, get_system_field, SystemFieldDef
from app.constants.metadata_fields import get_metadata_fields, MetadataFieldDef
from app.core.exceptions import NotFoundError, ValidationError, ConflictError
from app.enums import FieldDomain, FieldType, FieldSource
from app.repositories.fd_field_definition_repository import FdFieldDefinitionRepository
from app.repositories.fd_system_field_override_repository import FdSystemFieldOverrideRepository
from app.schemas.fd_field_definition import (
    FdFieldDefinitionCreate,
    FdFieldDefinitionUpdate,
    FdFieldOptionCreate,
    FdFieldOptionUpdate,
    FdTreeNodeCreate,
    FdTreeNodeUpdate,
    SortRequest,
    SystemFieldOverrideUpdate,
    UnifiedFieldResponse,
)

FIELD_TYPE_TO_SLOT_PREFIX: dict[str, str] = {
    FieldType.SINGLE_LINE_TEXT: "str",
    FieldType.EMAIL: "str",
    FieldType.PHONE: "str",
    FieldType.URL: "str",
    FieldType.TIME: "str",
    FieldType.SINGLE_SELECT: "str",
    FieldType.SINGLE_SELECT_TREE: "str",
    FieldType.MULTI_LINE_TEXT: "text",
    FieldType.RICH_TEXT: "text",
    FieldType.NUMBER: "num",
    FieldType.DATE: "date",
    FieldType.DATETIME: "datetime",
    FieldType.MULTI_SELECT: "json",
    FieldType.MULTI_SELECT_TREE: "json",
    FieldType.FILE: "json",
}

SLOT_CAPACITY: dict[str, int] = {
    "str": 20, "text": 5, "num": 10, "date": 5, "datetime": 5, "json": 10,
}


def _slot_prefix(slot_column: str) -> str | None:
    """Extract the slot family prefix (str/text/num/date/datetime/json) from a slot column name."""
    if not slot_column or "_" not in slot_column:
        return None
    return slot_column.rsplit("_", 1)[0]


def coerce_slot_value(slot_column: str, value: Any) -> Any:
    """
    Coerce a raw JSON value from the API layer to the Python type expected by
    the slot column's DB type.

    Slot prefixes:
      - str/text  → string (cast non-string scalars via str(); empty → None)
      - num       → int / float / Decimal (empty string → None; invalid → None)
      - date      → datetime.date (accepts ISO date / datetime prefix)
      - datetime  → datetime.datetime (accepts ISO datetime, naive allowed)
      - json      → pass-through (JSONB accepts any JSON-serializable value)

    Returns ``None`` for empty strings / unparseable values so that callers
    simply skip persisting them instead of producing driver-level type errors.
    """
    if value is None:
        return None

    prefix = _slot_prefix(slot_column)
    if prefix is None:
        return value

    if prefix in ("str", "text"):
        if isinstance(value, str):
            return value if value != "" else None
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float, Decimal)):
            return str(value)
        return None

    if prefix == "num":
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float, Decimal)):
            return value
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            try:
                return Decimal(s)
            except (InvalidOperation, ValueError):
                return None
        return None

    if prefix == "date":
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            try:
                return date.fromisoformat(s[:10])
            except ValueError:
                return None
        return None

    if prefix == "datetime":
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day)
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                try:
                    return datetime.fromisoformat(s[:10])
                except ValueError:
                    return None
        return None

    if prefix == "json":
        return value

    return value

SELECT_TYPES = {FieldType.SINGLE_SELECT, FieldType.MULTI_SELECT}
TREE_TYPES = {FieldType.SINGLE_SELECT_TREE, FieldType.MULTI_SELECT_TREE}


def _localize_system_type_config(sfd: SystemFieldDef, locale: str) -> dict:
    """
    Expose a single `label` per option to clients (API locale) and keep `color`.
    Source options may use `label` (zh) + optional `label_en` + `value` + `color`.
    `label_en` is not sent to the client.
    """
    base = sfd.type_config or {}
    if sfd.field_type not in ("single_select", "multi_select"):
        return {**base}
    opts = base.get("options")
    if not isinstance(opts, list):
        return {**base}
    use_en = (locale or "zh") == "en"
    new_opts: list[dict] = []
    for o in opts:
        if not isinstance(o, dict):
            new_opts.append(o)
            continue
        label = o.get("label") or ""
        if use_en and o.get("label_en"):
            label = o["label_en"]
        out: dict = {"label": label, "value": o.get("value")}
        if o.get("color") is not None:
            out["color"] = o["color"]
        for k, v in o.items():
            if k in ("label", "value", "label_en", "color"):
                continue
            out[k] = v
        new_opts.append(out)
    return {**base, "options": new_opts}


def _system_options_to_field_options(type_config: dict) -> list[dict]:
    options = type_config.get("options")
    if not isinstance(options, list):
        return []

    field_options: list[dict] = []
    for idx, option in enumerate(options):
        if not isinstance(option, dict):
            continue
        value = option.get("value")
        label = option.get("label")
        if value is None or label is None:
            continue
        field_options.append({
            "id": None,
            "field_definition_id": None,
            "label": str(label),
            "value": str(value),
            "color": option.get("color"),
            "sort_order": idx,
            "is_active": True,
            "created_at": None,
            "updated_at": None,
        })
    return field_options


def _system_field_to_unified(
    sfd: SystemFieldDef,
    domain: str,
    locale: str = "zh",
    override: "FdSystemFieldOverride | None" = None,
) -> dict:
    """Convert a hardcoded SystemFieldDef into UnifiedFieldResponse dict."""
    name = sfd.name_zh if locale == "zh" else sfd.name_en
    show = override.show_in_workspace if (override and override.show_in_workspace is not None) else sfd.default_show_in_workspace
    sort = override.sort_order if (override and override.sort_order is not None) else sfd.default_sort_order
    st = override.status if (override and override.status is not None) else "active"
    type_config = _localize_system_type_config(sfd, locale)

    return {
        "key": sfd.key,
        "id": None,
        "domain": domain,
        "source": "system",
        "name": name,
        "description": sfd.description,
        "help_text": sfd.help_text,
        "field_type": sfd.field_type,
        "type_config": type_config,
        "applicable_modules": None,
        "slot_column": None,
        "show_in_workspace": show,
        "sort_order": sort,
        "status": st,
        "options": _system_options_to_field_options(type_config),
        "tree_nodes": [],
        "created_at": None,
        "updated_at": None,
    }


def _metadata_field_to_unified(
    mfd: "MetadataFieldDef",
    domain: str,
    locale: str = "zh",
) -> dict:
    """Convert a hardcoded MetadataFieldDef into UnifiedFieldResponse dict."""
    return {
        "key": mfd.key,
        "id": None,
        "domain": domain,
        "source": "metadata",
        "name": mfd.name_zh if locale == "zh" else mfd.name_en,
        "description": mfd.description,
        "help_text": None,
        "field_type": mfd.field_type,
        "type_config": mfd.type_config,
        "applicable_modules": None,
        "slot_column": None,
        "show_in_workspace": True,
        "sort_order": mfd.default_sort_order,
        "status": "active",
        "options": [],
        "tree_nodes": [],
        "created_at": None,
        "updated_at": None,
    }


def _custom_field_to_unified(item: "FdFieldDefinition") -> dict:
    """Convert an ORM FdFieldDefinition into UnifiedFieldResponse dict."""
    return {
        "key": None,
        "id": item.id,
        "domain": item.domain,
        "source": item.source,
        "name": item.name,
        "description": item.description,
        "help_text": item.help_text,
        "field_type": item.field_type,
        "type_config": item.type_config,
        "applicable_modules": item.applicable_modules,
        "slot_column": item.slot_column,
        "show_in_workspace": item.show_in_workspace,
        "sort_order": item.sort_order,
        "status": item.status,
        "options": item.options,
        "tree_nodes": item.tree_nodes,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


class FdFieldDefinitionService:

    @staticmethod
    async def _allocate_slot(
        db: AsyncSession,
        tenant_id: int,
        domain: str,
        field_type: str,
        applicable_modules: list[str] | None = None,
    ) -> str:
        prefix = FIELD_TYPE_TO_SLOT_PREFIX.get(field_type)
        if not prefix:
            raise ValidationError(f"Unsupported field_type: {field_type}")

        max_slot = SLOT_CAPACITY[prefix]
        used_slots = await FdFieldDefinitionRepository.get_used_slots(
            db, tenant_id, domain, prefix, applicable_modules,
        )

        for i in range(1, max_slot + 1):
            candidate = f"{prefix}_{i}"
            if candidate not in used_slots:
                return candidate

        raise ValidationError(f"No available {prefix}_* slot. Max capacity {max_slot} reached.")

    @staticmethod
    async def _validate_field_type(field_type: str) -> None:
        valid_types = {t.value for t in FieldType}
        if field_type not in valid_types:
            raise ValidationError(f"Invalid field_type: {field_type}")

    @staticmethod
    async def _validate_domain(domain: str) -> None:
        valid_domains = {d.value for d in FieldDomain}
        if domain not in valid_domains:
            raise ValidationError(f"Invalid domain: {domain}")

    # ── System field list (constants only, no custom fields) ──

    @staticmethod
    def get_system_field_list(domain: str, locale: str = "zh") -> dict:
        """Return all system field definitions for a domain (from constants, no DB query)."""
        system_defs = get_system_fields(domain)
        items: list[dict] = []
        for sfd in system_defs:
            type_config = _localize_system_type_config(sfd, locale)
            items.append({
                "key": sfd.key,
                "id": None,
                "domain": domain,
                "source": "system",
                "name": sfd.name_zh if locale == "zh" else sfd.name_en,
                "description": sfd.description,
                "help_text": sfd.help_text,
                "field_type": sfd.field_type,
                "type_config": type_config,
                "applicable_modules": None,
                "slot_column": None,
                "show_in_workspace": sfd.default_show_in_workspace,
                "sort_order": sfd.default_sort_order,
                "status": "active",
                "options": _system_options_to_field_options(type_config),
                "tree_nodes": [],
                "created_at": None,
                "updated_at": None,
            })
        return {"items": items, "total": len(items)}

    # ── Unified list (system + custom) ──

    @staticmethod
    async def get_unified_list(
        db: AsyncSession,
        tenant_id: int,
        domain: str,
        locale: str = "zh",
        include_metadata: bool = False,
    ) -> dict:
        """Return all fields (system + custom) for a domain, merged and sorted."""
        system_defs = get_system_fields(domain)
        overrides = await FdSystemFieldOverrideRepository.get_all_for_tenant_domain(
            db, tenant_id, domain,
        )
        override_map = {o.field_key: o for o in overrides}

        system_items: list[dict] = []
        for sfd in system_defs:
            ov = override_map.get(sfd.key)
            item_dict = _system_field_to_unified(sfd, domain, locale, ov)
            st = item_dict.get("status", "active")
            if st != "deleted":
                system_items.append(item_dict)

        custom_rows = await FdFieldDefinitionRepository.list_custom_for_unified_domain(
            db, tenant_id, domain,
        )
        custom_items = [_custom_field_to_unified(r) for r in custom_rows]

        merged = system_items + custom_items
        merged.sort(key=lambda x: (x["sort_order"], x["key"] or "", x["id"] or 0))

        if include_metadata:
            metadata_items = [
                _metadata_field_to_unified(mfd, domain, locale)
                for mfd in get_metadata_fields()
            ]
            merged = merged + metadata_items

        return {
            "items": merged,
            "total": len(merged),
            "page": 1,
            "per_page": len(merged),
            "pages": 1,
        }

    # ── Field Definition CRUD (custom fields only) ──

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        domain: str | None = None,
        status: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> dict:
        items, total = await FdFieldDefinitionRepository.get_paginated(
            db, tenant_id, domain, status, page, per_page,
        )
        pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, definition_id: int) -> "FdFieldDefinition":
        item = await FdFieldDefinitionRepository.get_by_id(db, definition_id)
        if not item:
            raise NotFoundError("Field definition not found")
        return item

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: FdFieldDefinitionCreate) -> "FdFieldDefinition":
        await FdFieldDefinitionService._validate_domain(data.domain)
        await FdFieldDefinitionService._validate_field_type(data.field_type)

        if data.domain == FieldDomain.SHARED_POOL and not data.applicable_modules:
            raise ValidationError("applicable_modules is required for shared_pool domain")

        name_exists = await FdFieldDefinitionRepository.check_name_exists(
            db, tenant_id, data.domain, data.name,
        )
        if name_exists:
            raise ConflictError(f"Field name '{data.name}' already exists in domain '{data.domain}'")

        slot_column = await FdFieldDefinitionService._allocate_slot(
            db, tenant_id, data.domain, data.field_type, data.applicable_modules,
        )

        options_data = data.options or []
        tree_nodes_data = data.tree_nodes or []
        create_data = data.model_dump(exclude={"options", "tree_nodes"})
        create_data["tenant_id"] = tenant_id
        create_data["slot_column"] = slot_column
        create_data["source"] = "custom"

        # New custom fields default to sort_order=0 in the schema, which sorts
        # before system fields (e.g. user domain starts at 1). Place at the end.
        unified_snapshot = await FdFieldDefinitionService.get_unified_list(
            db, tenant_id, data.domain, locale="zh", include_metadata=False,
        )
        max_sort = max((row["sort_order"] for row in unified_snapshot["items"]), default=0)
        create_data["sort_order"] = max_sort + 1

        definition = await FdFieldDefinitionRepository.create(db, create_data)

        if data.field_type in SELECT_TYPES and options_data:
            for opt in options_data:
                await FdFieldDefinitionRepository.create_option(
                    db, {**opt.model_dump(), "field_definition_id": definition.id},
                )

        if data.field_type in TREE_TYPES and tree_nodes_data:
            created_tree_ids: list[int] = []
            for i, node in enumerate(tree_nodes_data):
                d = node.model_dump()
                parent_id = None
                pi = d.get("parent_index")
                if pi is not None:
                    if pi < 0 or pi >= i:
                        raise ValidationError(
                            f"invalid parent_index {pi} for tree node at index {i}",
                        )
                    parent_id = created_tree_ids[pi]
                elif d.get("parent_id") is not None:
                    parent_id = d["parent_id"]
                row = await FdFieldDefinitionRepository.create_tree_node(
                    db,
                    {
                        "field_definition_id": definition.id,
                        "label": d["label"],
                        "value": d["value"],
                        "parent_id": parent_id,
                        "sort_order": d.get("sort_order", 0),
                    },
                )
                created_tree_ids.append(row.id)

        await db.refresh(definition, attribute_names=["options", "tree_nodes"])
        return await FdFieldDefinitionRepository.get_by_id(db, definition.id)

    @staticmethod
    async def update(
        db: AsyncSession, definition_id: int, tenant_id: int, data: FdFieldDefinitionUpdate,
    ) -> "FdFieldDefinition":
        item = await FdFieldDefinitionRepository.get_by_id(db, definition_id)
        if not item:
            raise NotFoundError("Field definition not found")
        if item.tenant_id != tenant_id:
            raise NotFoundError("Field definition not found")

        update_data = data.model_dump(exclude_unset=True)

        if data.name is not None and data.name != item.name:
            name_exists = await FdFieldDefinitionRepository.check_name_exists(
                db, tenant_id, item.domain, data.name, exclude_id=definition_id,
            )
            if name_exists:
                raise ConflictError(f"Field name '{data.name}' already exists")

        return await FdFieldDefinitionRepository.update(db, item, update_data)

    @staticmethod
    async def delete(db: AsyncSession, definition_id: int, tenant_id: int) -> None:
        item = await FdFieldDefinitionRepository.get_by_id(db, definition_id)
        if not item:
            raise NotFoundError("Field definition not found")
        if item.tenant_id != tenant_id:
            raise NotFoundError("Field definition not found")
        if item.source == FieldSource.SYSTEM:
            raise ValidationError("Cannot delete system field")

        await FdFieldDefinitionRepository.delete(db, item)

    @staticmethod
    async def batch_sort(db: AsyncSession, tenant_id: int, domain: str, data: SortRequest) -> None:
        """Sort both system fields (by key) and custom fields (by id)."""
        custom_items = []
        system_items = []
        for item in data.items:
            if item.key:
                system_items.append({"field_key": item.key, "sort_order": item.sort_order})
            elif item.id:
                custom_items.append({"id": item.id, "sort_order": item.sort_order})

        if custom_items:
            await FdFieldDefinitionRepository.batch_update_sort(db, tenant_id, custom_items)

        if system_items:
            await FdSystemFieldOverrideRepository.batch_upsert_sort(
                db, tenant_id, domain, system_items,
            )

    # ── System field overrides ──

    @staticmethod
    async def update_system_field_override(
        db: AsyncSession,
        tenant_id: int,
        domain: str,
        field_key: str,
        data: SystemFieldOverrideUpdate,
    ) -> dict:
        sfd = get_system_field(domain, field_key)
        if not sfd:
            raise NotFoundError(f"System field '{field_key}' not found in domain '{domain}'")

        override = await FdSystemFieldOverrideRepository.upsert(
            db, tenant_id, domain, field_key, data.model_dump(exclude_unset=True),
        )
        return _system_field_to_unified(sfd, domain, "zh", override)

    # ── Options ──

    @staticmethod
    async def get_options(db: AsyncSession, definition_id: int) -> list:
        return await FdFieldDefinitionRepository.get_options(db, definition_id)

    @staticmethod
    async def create_option(
        db: AsyncSession, definition_id: int, tenant_id: int, data: FdFieldOptionCreate,
    ):
        definition = await FdFieldDefinitionService.get_by_id(db, definition_id)
        if definition.tenant_id != tenant_id:
            raise NotFoundError("Field definition not found")
        if definition.field_type not in SELECT_TYPES:
            raise ValidationError("Options are only for select-type fields")

        return await FdFieldDefinitionRepository.create_option(
            db, {**data.model_dump(), "field_definition_id": definition_id},
        )

    @staticmethod
    async def update_option(
        db: AsyncSession, option_id: int, tenant_id: int, data: FdFieldOptionUpdate,
    ):
        option = await FdFieldDefinitionRepository.get_option_by_id(db, option_id)
        if not option:
            raise NotFoundError("Option not found")

        definition = await FdFieldDefinitionRepository.get_by_id(db, option.field_definition_id)
        if not definition or definition.tenant_id != tenant_id:
            raise NotFoundError("Option not found")

        return await FdFieldDefinitionRepository.update_option(
            db, option, data.model_dump(exclude_unset=True),
        )

    @staticmethod
    async def delete_option(db: AsyncSession, option_id: int, tenant_id: int) -> None:
        option = await FdFieldDefinitionRepository.get_option_by_id(db, option_id)
        if not option:
            raise NotFoundError("Option not found")

        definition = await FdFieldDefinitionRepository.get_by_id(db, option.field_definition_id)
        if not definition or definition.tenant_id != tenant_id:
            raise NotFoundError("Option not found")

        await FdFieldDefinitionRepository.delete_option(db, option)

    # ── Tree Nodes ──

    @staticmethod
    async def get_tree_nodes(db: AsyncSession, definition_id: int) -> list:
        return await FdFieldDefinitionRepository.get_tree_nodes(db, definition_id)

    @staticmethod
    async def create_tree_node(
        db: AsyncSession, definition_id: int, tenant_id: int, data: FdTreeNodeCreate,
    ):
        definition = await FdFieldDefinitionService.get_by_id(db, definition_id)
        if definition.tenant_id != tenant_id:
            raise NotFoundError("Field definition not found")
        if definition.field_type not in TREE_TYPES:
            raise ValidationError("Tree nodes are only for tree-type fields")

        return await FdFieldDefinitionRepository.create_tree_node(
            db, {**data.model_dump(), "field_definition_id": definition_id},
        )

    @staticmethod
    async def update_tree_node(
        db: AsyncSession, node_id: int, tenant_id: int, data: FdTreeNodeUpdate,
    ):
        node = await FdFieldDefinitionRepository.get_tree_node_by_id(db, node_id)
        if not node:
            raise NotFoundError("Tree node not found")

        definition = await FdFieldDefinitionRepository.get_by_id(db, node.field_definition_id)
        if not definition or definition.tenant_id != tenant_id:
            raise NotFoundError("Tree node not found")

        return await FdFieldDefinitionRepository.update_tree_node(
            db, node, data.model_dump(exclude_unset=True),
        )

    @staticmethod
    async def delete_tree_node(db: AsyncSession, node_id: int, tenant_id: int) -> None:
        node = await FdFieldDefinitionRepository.get_tree_node_by_id(db, node_id)
        if not node:
            raise NotFoundError("Tree node not found")

        definition = await FdFieldDefinitionRepository.get_by_id(db, node.field_definition_id)
        if not definition or definition.tenant_id != tenant_id:
            raise NotFoundError("Tree node not found")

        await FdFieldDefinitionRepository.delete_tree_node(db, node)
