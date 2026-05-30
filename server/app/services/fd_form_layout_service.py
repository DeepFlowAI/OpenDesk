"""
FdFormLayout service — business logic for form layouts
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.fd_field_definition_repository import FdFieldDefinitionRepository
from app.repositories.fd_form_layout_repository import FdFormLayoutRepository
from app.schemas.fd_form_layout import FdFormLayoutCreate, FdFormLayoutUpdate
from app.services.tenant_init_service import init_tenant_data

RESTRICTED_SOURCES_FOR_NEW_TICKET = {"ticket_metadata", "user", "organization"}
# Post-create metadata / audit fields — not configurable on the new-ticket layout.
DISALLOWED_TICKET_KEYS_FOR_NEW_TICKET = frozenset(
    {"conversation_id", "call_record_id", "created_by", "updated_by"},
)
REFERENCE_FIELD_SOURCES = {"ticket_metadata", "user", "organization"}
REFERENCE_FIELD_ALLOWED_STATES = {"readonly", "hidden"}

MAX_TABS_PER_LAYOUT = 10
MAX_SECTIONS_PER_TAB = 20
MAX_FIELDS_PER_SECTION = 50
MAX_FIELDS_PER_LAYOUT = 200


def _iter_fields(tabs_data: list[dict]):
    """Yield (tab_name, section_name, field_dict) for every field in the tree."""
    for tab in tabs_data:
        tab_name = tab.get("name", "")
        for sec in tab.get("sections") or []:
            sec_name = sec.get("name", "")
            for field in sec.get("fields") or []:
                yield tab_name, sec_name, field


class FdFormLayoutService:

    # ── Validation: field source rules (existing) ──

    @staticmethod
    def _validate_field_sources(scene: str, tabs_data: list[dict] | None) -> None:
        """
        For new_ticket layouts, reject any field whose field_source is
        ticket_metadata / user / organization. Reference fields in detail
        layouts can only be readonly or hidden.
        """
        if not tabs_data:
            return
        for tab in tabs_data:
            for sec in tab.get("sections") or []:
                for field in sec.get("fields") or []:
                    src = field.get("field_source", "ticket")
                    if scene == "new_ticket" and src in RESTRICTED_SOURCES_FOR_NEW_TICKET:
                        raise ValidationError(
                            f"Field source '{src}' is not allowed in new_ticket layout"
                        )
                    if scene == "new_ticket" and src == "ticket":
                        fkey = field.get("field_key")
                        if fkey and fkey in DISALLOWED_TICKET_KEYS_FOR_NEW_TICKET:
                            raise ValidationError(
                                f"Field '{fkey}' is not allowed in new_ticket layout"
                            )
                    state = field.get("default_state", "optional")
                    if src in REFERENCE_FIELD_SOURCES and state not in REFERENCE_FIELD_ALLOWED_STATES:
                        raise ValidationError(
                            f"Reference field source '{src}' only supports readonly or hidden state"
                        )

    # ── Validation: defensive limits ──

    @staticmethod
    def _validate_layout_limits(tabs_data: list[dict] | None) -> None:
        if not tabs_data:
            return
        if len(tabs_data) > MAX_TABS_PER_LAYOUT:
            raise ValidationError(f"Maximum {MAX_TABS_PER_LAYOUT} tabs allowed per layout")

        total_fields = 0
        for tab in tabs_data:
            sections = tab.get("sections") or []
            if len(sections) > MAX_SECTIONS_PER_TAB:
                raise ValidationError(
                    f"Maximum {MAX_SECTIONS_PER_TAB} sections allowed per tab '{tab.get('name', '')}'"
                )
            for sec in sections:
                fields = sec.get("fields") or []
                if len(fields) > MAX_FIELDS_PER_SECTION:
                    raise ValidationError(
                        f"Maximum {MAX_FIELDS_PER_SECTION} fields allowed per section '{sec.get('name', '')}'"
                    )
                total_fields += len(fields)

        if total_fields > MAX_FIELDS_PER_LAYOUT:
            raise ValidationError(f"Maximum {MAX_FIELDS_PER_LAYOUT} fields allowed per layout")

    # ── Validation: structural integrity ──

    @staticmethod
    def _validate_layout_structure(tabs_data: list[dict] | None) -> None:
        if not tabs_data or len(tabs_data) == 0:
            raise ValidationError("Layout must have at least one tab")

        seen_fields: set[tuple] = set()

        for tab in tabs_data:
            sections = tab.get("sections") or []
            if len(sections) == 0:
                raise ValidationError(
                    f"Tab '{tab.get('name', '')}' must have at least one section"
                )

            for sec in sections:
                for field in sec.get("fields") or []:
                    fid = field.get("field_definition_id")
                    fkey = field.get("field_key")
                    if fid is None and not fkey:
                        raise ValidationError(
                            "Each field must have either field_definition_id or field_key"
                        )

                    src = field.get("field_source", "ticket")
                    key = (src, fkey, fid)
                    if key in seen_fields:
                        raise ValidationError(
                            f"Duplicate field in layout: source={src}, key={fkey}, definition_id={fid}"
                        )
                    seen_fields.add(key)

    # ── Validation: business rules (new) ──

    @staticmethod
    def _validate_business_rules(columns_per_row: int, tabs_data: list[dict] | None) -> None:
        """
        NOTE: 'required + hidden' conflict is already prevented by the
        Literal["required","optional","readonly","hidden"] single-value enum
        in the Schema layer — default_state can never be both values at once.
        """
        if not tabs_data:
            return
        for _tab_name, _sec_name, field in _iter_fields(tabs_data):
            col_span = field.get("column_span", 1)
            if col_span > columns_per_row:
                fkey = field.get("field_key") or field.get("field_definition_id")
                raise ValidationError(
                    f"Field '{fkey}' column_span ({col_span}) exceeds columns_per_row ({columns_per_row})"
                )

    # ── Validation: field definition existence ──

    @staticmethod
    async def _validate_field_references(
        db: AsyncSession, tenant_id: int, tabs_data: list[dict] | None,
    ) -> None:
        if not tabs_data:
            return

        all_def_ids: set[int] = set()
        for _tab_name, _sec_name, field in _iter_fields(tabs_data):
            fid = field.get("field_definition_id")
            if fid is not None:
                all_def_ids.add(fid)

        if not all_def_ids:
            return

        existing_ids = await FdFieldDefinitionRepository.get_ids_by_tenant(
            db, tenant_id, all_def_ids,
        )
        missing = all_def_ids - existing_ids
        if missing:
            raise ValidationError(
                f"Field definition IDs not found or not accessible: {sorted(missing)}"
            )

    # ── CRUD ──

    @staticmethod
    async def get_paginated(
        db: AsyncSession, tenant_id: int, page: int = 1, per_page: int = 50,
    ) -> dict:
        items, total = await FdFormLayoutRepository.get_by_tenant(db, tenant_id, page, per_page)

        # Lazy init: seed default layouts for tenants that have none
        if total == 0:
            await init_tenant_data(db, tenant_id)
            items, total = await FdFormLayoutRepository.get_by_tenant(db, tenant_id, page, per_page)

        pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def _get_layout_with_tenant_check(
        db: AsyncSession, layout_id: int, tenant_id: int,
    ):
        item = await FdFormLayoutRepository.get_by_id(db, layout_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Form layout not found")
        return item

    @staticmethod
    async def get_by_id(db: AsyncSession, layout_id: int, tenant_id: int):
        return await FdFormLayoutService._get_layout_with_tenant_check(db, layout_id, tenant_id)

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: FdFormLayoutCreate):
        payload = data.model_dump()
        tabs = payload.get("tabs")
        scene = payload.get("scene", "")
        columns_per_row = payload.get("columns_per_row", 1)

        FdFormLayoutService._validate_layout_limits(tabs)
        FdFormLayoutService._validate_layout_structure(tabs)
        FdFormLayoutService._validate_field_sources(scene, tabs)
        FdFormLayoutService._validate_business_rules(columns_per_row, tabs)
        await FdFormLayoutService._validate_field_references(db, tenant_id, tabs)

        return await FdFormLayoutRepository.create(db, tenant_id, payload)

    @staticmethod
    async def update(db: AsyncSession, layout_id: int, tenant_id: int, data: FdFormLayoutUpdate):
        item = await FdFormLayoutService._get_layout_with_tenant_check(db, layout_id, tenant_id)
        payload = data.model_dump(exclude_unset=True)
        tabs = payload.get("tabs")

        if tabs is not None:
            columns_per_row = payload.get("columns_per_row", item.columns_per_row)
            FdFormLayoutService._validate_layout_limits(tabs)
            FdFormLayoutService._validate_layout_structure(tabs)
            FdFormLayoutService._validate_field_sources(item.scene, tabs)
            FdFormLayoutService._validate_business_rules(columns_per_row, tabs)
            await FdFormLayoutService._validate_field_references(db, tenant_id, tabs)

        return await FdFormLayoutRepository.update(db, item, payload)

    @staticmethod
    async def delete(db: AsyncSession, layout_id: int, tenant_id: int) -> None:
        item = await FdFormLayoutService._get_layout_with_tenant_check(db, layout_id, tenant_id)
        await FdFormLayoutRepository.delete(db, item)
