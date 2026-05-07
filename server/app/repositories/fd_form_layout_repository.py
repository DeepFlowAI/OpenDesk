"""
FdFormLayout repository — data access for form layouts

Hierarchy: Layout → Tab → Section → Field
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fd_form_layout import FdFormLayout
from app.models.fd_form_layout_tab import FdFormLayoutTab
from app.models.fd_form_layout_section import FdFormLayoutSection
from app.models.fd_form_layout_field import FdFormLayoutField


class FdFormLayoutRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, layout_id: int) -> FdFormLayout | None:
        result = await db.execute(
            select(FdFormLayout)
            .options(
                selectinload(FdFormLayout.tabs)
                .selectinload(FdFormLayoutTab.sections)
                .selectinload(FdFormLayoutSection.fields),
            )
            .where(FdFormLayout.id == layout_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_tenant(
        db: AsyncSession, tenant_id: int, page: int = 1, per_page: int = 50,
    ) -> tuple[list[FdFormLayout], int]:
        total_result = await db.execute(
            select(func.count()).select_from(FdFormLayout).where(FdFormLayout.tenant_id == tenant_id)
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(FdFormLayout)
            .where(FdFormLayout.tenant_id == tenant_id)
            .order_by(FdFormLayout.id)
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_by_scene(db: AsyncSession, tenant_id: int, scene: str) -> FdFormLayout | None:
        result = await db.execute(
            select(FdFormLayout)
            .options(
                selectinload(FdFormLayout.tabs)
                .selectinload(FdFormLayoutTab.sections)
                .selectinload(FdFormLayoutSection.fields),
            )
            .where(
                FdFormLayout.tenant_id == tenant_id,
                FdFormLayout.scene == scene,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _create_tabs_tree(
        db: AsyncSession, layout_id: int, tabs_data: list[dict],
    ) -> None:
        """Create the full tab → section → field tree."""
        for tidx, tab_data in enumerate(tabs_data):
            sections_data = tab_data.pop("sections", None) or []
            tab = FdFormLayoutTab(
                layout_id=layout_id,
                name=tab_data.get("name", f"Tab {tidx + 1}"),
                sort_order=tab_data.get("sort_order", tidx),
            )
            db.add(tab)
            await db.flush()

            for sidx, sec_data in enumerate(sections_data):
                fields_data = sec_data.pop("fields", None) or []
                section = FdFormLayoutSection(
                    tab_id=tab.id,
                    name=sec_data.get("name", f"Section {sidx + 1}"),
                    sort_order=sec_data.get("sort_order", sidx),
                    is_collapsed=sec_data.get("is_collapsed", False),
                )
                db.add(section)
                await db.flush()

                for fidx, field_data in enumerate(fields_data):
                    field = FdFormLayoutField(
                        section_id=section.id,
                        field_definition_id=field_data.get("field_definition_id"),
                        field_key=field_data.get("field_key"),
                        field_source=field_data.get("field_source", "ticket"),
                        default_state=field_data.get("default_state", "optional"),
                        column_span=field_data.get("column_span", 1),
                        sort_order=field_data.get("sort_order", fidx),
                    )
                    db.add(field)

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: dict) -> FdFormLayout:
        tabs_data = data.pop("tabs", None) or []

        layout = FdFormLayout(tenant_id=tenant_id, **data)
        db.add(layout)
        await db.flush()

        await FdFormLayoutRepository._create_tabs_tree(db, layout.id, tabs_data)

        await db.commit()
        return await FdFormLayoutRepository.get_by_id(db, layout.id)  # type: ignore

    @staticmethod
    async def update(
        db: AsyncSession, layout: FdFormLayout, data: dict,
    ) -> FdFormLayout:
        tabs_data = data.pop("tabs", None)

        for key, value in data.items():
            if hasattr(layout, key) and value is not None:
                setattr(layout, key, value)

        if tabs_data is not None:
            # Delete old tree (cascade deletes sections → fields)
            for tab in list(layout.tabs):
                await db.delete(tab)
            await db.flush()

            await FdFormLayoutRepository._create_tabs_tree(db, layout.id, tabs_data)

        await db.commit()
        return await FdFormLayoutRepository.get_by_id(db, layout.id)  # type: ignore

    @staticmethod
    async def delete(db: AsyncSession, layout: FdFormLayout) -> None:
        await db.delete(layout)
        await db.commit()
