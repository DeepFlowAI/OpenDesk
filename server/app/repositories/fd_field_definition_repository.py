"""
Repository for fd_field_definitions, fd_field_options, fd_tree_nodes
"""
from sqlalchemy import and_, or_, select, func, update
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fd_field_definition import FdFieldDefinition
from app.models.fd_field_option import FdFieldOption
from app.models.fd_tree_node import FdTreeNode


class FdFieldDefinitionRepository:

    # ── Field Definition ──

    @staticmethod
    async def get_by_id(db: AsyncSession, definition_id: int) -> FdFieldDefinition | None:
        result = await db.execute(
            select(FdFieldDefinition)
            .options(selectinload(FdFieldDefinition.options), selectinload(FdFieldDefinition.tree_nodes))
            .where(FdFieldDefinition.id == definition_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        domain: str | None = None,
        status: str | None = None,
        page: int = 1,
        per_page: int = 50,
        source: str | None = None,
    ) -> tuple[list[FdFieldDefinition], int]:
        base_q = select(FdFieldDefinition).where(FdFieldDefinition.tenant_id == tenant_id)
        count_q = select(func.count()).select_from(FdFieldDefinition).where(FdFieldDefinition.tenant_id == tenant_id)

        if domain:
            base_q = base_q.where(FdFieldDefinition.domain == domain)
            count_q = count_q.where(FdFieldDefinition.domain == domain)
        if status:
            base_q = base_q.where(FdFieldDefinition.status == status)
            count_q = count_q.where(FdFieldDefinition.status == status)
        if source:
            base_q = base_q.where(FdFieldDefinition.source == source)
            count_q = count_q.where(FdFieldDefinition.source == source)

        total_result = await db.execute(count_q)
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            base_q
            .options(selectinload(FdFieldDefinition.options), selectinload(FdFieldDefinition.tree_nodes))
            .order_by(FdFieldDefinition.sort_order, FdFieldDefinition.id)
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def list_custom_for_unified_domain(
        db: AsyncSession,
        tenant_id: int,
        domain: str,
    ) -> list[FdFieldDefinition]:
        """
        Custom field rows for GET /field-definitions/unified.

        Ticket "domain" in the API is a virtual view: it includes not only
        rows with domain='ticket' (legacy) but also shared_pool definitions
        whose applicable_modules contains 'ticket' (the normal path for
        custom ticket fields).
        """
        base_q = (
            select(FdFieldDefinition)
            .options(
                selectinload(FdFieldDefinition.options),
                selectinload(FdFieldDefinition.tree_nodes),
            )
            .where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.source == "custom",
            )
        )
        if domain == "ticket":
            q = base_q.where(
                or_(
                    FdFieldDefinition.domain == "ticket",
                    and_(
                        FdFieldDefinition.domain == "shared_pool",
                        FdFieldDefinition.applicable_modules.overlap(array(["ticket"])),
                    ),
                )
            )
        else:
            q = base_q.where(FdFieldDefinition.domain == domain)

        result = await db.execute(
            q.order_by(FdFieldDefinition.sort_order, FdFieldDefinition.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> FdFieldDefinition:
        item = FdFieldDefinition(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: FdFieldDefinition, data: dict) -> FdFieldDefinition:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: FdFieldDefinition) -> None:
        await db.delete(item)
        await db.commit()

    @staticmethod
    async def batch_update_sort(db: AsyncSession, tenant_id: int, items: list[dict]) -> None:
        for item in items:
            await db.execute(
                update(FdFieldDefinition)
                .where(FdFieldDefinition.id == item["id"], FdFieldDefinition.tenant_id == tenant_id)
                .values(sort_order=item["sort_order"])
            )
        await db.commit()

    @staticmethod
    async def get_used_slots(
        db: AsyncSession, tenant_id: int, domain: str, prefix: str,
        applicable_modules: list[str] | None = None,
    ) -> set[str]:
        """Get all used slot_column values for a given tenant/domain/prefix combination."""
        q = (
            select(FdFieldDefinition.slot_column)
            .where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.slot_column.like(f"{prefix}_%"),
            )
        )
        if domain in ("user", "organization"):
            q = q.where(FdFieldDefinition.domain == domain)
        else:
            # shared_pool: collect slots used by any field that targets the same tables
            if applicable_modules:
                from sqlalchemy.dialects.postgresql import array
                q = q.where(
                    FdFieldDefinition.domain == "shared_pool",
                    FdFieldDefinition.applicable_modules.overlap(array(applicable_modules)),
                )
            else:
                q = q.where(FdFieldDefinition.domain == "shared_pool")

        result = await db.execute(q)
        return {row[0] for row in result.all()}

    @staticmethod
    async def get_ids_by_tenant(
        db: AsyncSession, tenant_id: int, ids: set[int],
    ) -> set[int]:
        """Return the subset of ids that exist and belong to the given tenant."""
        if not ids:
            return set()
        result = await db.execute(
            select(FdFieldDefinition.id).where(
                FdFieldDefinition.id.in_(ids),
                FdFieldDefinition.tenant_id == tenant_id,
            )
        )
        return {row[0] for row in result.all()}

    @staticmethod
    async def check_name_exists(db: AsyncSession, tenant_id: int, domain: str, name: str, exclude_id: int | None = None) -> bool:
        q = (
            select(func.count())
            .select_from(FdFieldDefinition)
            .where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.domain == domain,
                FdFieldDefinition.name == name,
            )
        )
        if exclude_id:
            q = q.where(FdFieldDefinition.id != exclude_id)
        result = await db.execute(q)
        return result.scalar_one() > 0

    # ── Field Options ──

    @staticmethod
    async def get_options(db: AsyncSession, field_definition_id: int) -> list[FdFieldOption]:
        result = await db.execute(
            select(FdFieldOption)
            .where(FdFieldOption.field_definition_id == field_definition_id)
            .order_by(FdFieldOption.sort_order, FdFieldOption.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_option_by_id(db: AsyncSession, option_id: int) -> FdFieldOption | None:
        return await db.get(FdFieldOption, option_id)

    @staticmethod
    async def create_option(db: AsyncSession, data: dict) -> FdFieldOption:
        item = FdFieldOption(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update_option(db: AsyncSession, item: FdFieldOption, data: dict) -> FdFieldOption:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete_option(db: AsyncSession, item: FdFieldOption) -> None:
        await db.delete(item)
        await db.commit()

    # ── Tree Nodes ──

    @staticmethod
    async def get_tree_nodes(db: AsyncSession, field_definition_id: int) -> list[FdTreeNode]:
        result = await db.execute(
            select(FdTreeNode)
            .where(FdTreeNode.field_definition_id == field_definition_id)
            .order_by(FdTreeNode.sort_order, FdTreeNode.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_tree_node_by_id(db: AsyncSession, node_id: int) -> FdTreeNode | None:
        return await db.get(FdTreeNode, node_id)

    @staticmethod
    async def create_tree_node(db: AsyncSession, data: dict) -> FdTreeNode:
        item = FdTreeNode(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update_tree_node(db: AsyncSession, item: FdTreeNode, data: dict) -> FdTreeNode:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete_tree_node(db: AsyncSession, item: FdTreeNode) -> None:
        await db.delete(item)
        await db.commit()
