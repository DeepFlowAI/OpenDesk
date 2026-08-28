"""Data access for tenant-scoped custom dashboards and snapshot slots."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_dashboard import CustomDashboard, CustomDashboardVersion


class CustomDashboardRepository:
    """Repository for custom dashboard persistence."""

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        *,
        page: int,
        per_page: int,
        keyword: str | None,
        status: str | None,
    ) -> tuple[list[tuple[CustomDashboard, CustomDashboardVersion]], int]:
        conditions = [CustomDashboard.tenant_id == tenant_id]
        if keyword:
            conditions.append(CustomDashboard.name.ilike(f"%{keyword}%"))
        if status:
            conditions.append(CustomDashboard.status == status)

        count_query = select(func.count()).select_from(CustomDashboard).where(*conditions)
        total = int((await db.execute(count_query)).scalar_one())
        query = (
            select(CustomDashboard, CustomDashboardVersion)
            .join(
                CustomDashboardVersion,
                (CustomDashboardVersion.dashboard_id == CustomDashboard.id)
                & (CustomDashboardVersion.kind == "draft"),
            )
            .where(*conditions)
            .order_by(CustomDashboard.sort_order.asc(), CustomDashboard.id.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        rows = list((await db.execute(query)).all())
        return rows, total

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        dashboard_id: int,
        tenant_id: int,
        *,
        for_update: bool = False,
    ) -> CustomDashboard | None:
        query = select(CustomDashboard).where(
            CustomDashboard.id == dashboard_id,
            CustomDashboard.tenant_id == tenant_id,
        )
        if for_update:
            query = query.with_for_update()
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def get_version(
        db: AsyncSession,
        dashboard_id: int,
        tenant_id: int,
        kind: str,
        *,
        for_update: bool = False,
    ) -> CustomDashboardVersion | None:
        query = select(CustomDashboardVersion).where(
            CustomDashboardVersion.dashboard_id == dashboard_id,
            CustomDashboardVersion.tenant_id == tenant_id,
            CustomDashboardVersion.kind == kind,
        )
        if for_update:
            query = query.with_for_update()
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def get_by_name(
        db: AsyncSession,
        tenant_id: int,
        name: str,
    ) -> CustomDashboard | None:
        query = select(CustomDashboard).where(
            CustomDashboard.tenant_id == tenant_id,
            CustomDashboard.name == name,
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def count_for_tenant(db: AsyncSession, tenant_id: int) -> int:
        query = select(func.count()).select_from(CustomDashboard).where(
            CustomDashboard.tenant_id == tenant_id
        )
        return int((await db.execute(query)).scalar_one())

    @staticmethod
    async def count_published_components(
        db: AsyncSession,
        tenant_id: int,
        *,
        exclude_dashboard_id: int | None = None,
    ) -> int:
        query = select(
            func.coalesce(func.sum(func.jsonb_array_length(CustomDashboardVersion.components)), 0)
        ).where(
            CustomDashboardVersion.tenant_id == tenant_id,
            CustomDashboardVersion.kind == "published",
        )
        if exclude_dashboard_id is not None:
            query = query.where(CustomDashboardVersion.dashboard_id != exclude_dashboard_id)
        return int((await db.execute(query)).scalar_one() or 0)

    @staticmethod
    async def get_max_sort_order(db: AsyncSession, tenant_id: int) -> int:
        query = select(func.coalesce(func.max(CustomDashboard.sort_order), 0)).where(
            CustomDashboard.tenant_id == tenant_id
        )
        return int((await db.execute(query)).scalar_one() or 0)

    @staticmethod
    async def create_dashboard(
        db: AsyncSession,
        data: dict,
    ) -> CustomDashboard:
        row = CustomDashboard(**data)
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def create_version(
        db: AsyncSession,
        data: dict,
    ) -> CustomDashboardVersion:
        row = CustomDashboardVersion(**data)
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def update_dashboard(
        db: AsyncSession,
        row: CustomDashboard,
        data: dict,
    ) -> None:
        for key, value in data.items():
            setattr(row, key, value)
        await db.flush()

    @staticmethod
    async def update_version(
        db: AsyncSession,
        row: CustomDashboardVersion,
        data: dict,
    ) -> None:
        for key, value in data.items():
            setattr(row, key, value)
        await db.flush()

    @staticmethod
    async def delete(db: AsyncSession, row: CustomDashboard) -> None:
        await db.delete(row)
        await db.flush()

    @staticmethod
    async def reorder(db: AsyncSession, tenant_id: int, ids: list[int]) -> int:
        result = await db.execute(
            select(CustomDashboard).where(
                CustomDashboard.tenant_id == tenant_id,
                CustomDashboard.id.in_(ids),
            )
        )
        rows = {row.id: row for row in result.scalars().all()}
        for sort_order, dashboard_id in enumerate(ids, start=1):
            row = rows.get(dashboard_id)
            if row is not None:
                row.sort_order = sort_order
        await db.flush()
        return len(rows)

    @staticmethod
    async def list_workspace(
        db: AsyncSession,
        tenant_id: int,
        keyword: str | None,
    ) -> list[tuple[CustomDashboard, CustomDashboardVersion]]:
        conditions = [
            CustomDashboard.tenant_id == tenant_id,
            CustomDashboard.status == "published",
            CustomDashboardVersion.kind == "published",
        ]
        if keyword:
            conditions.append(CustomDashboardVersion.name.ilike(f"%{keyword}%"))
        query = (
            select(CustomDashboard, CustomDashboardVersion)
            .join(
                CustomDashboardVersion,
                CustomDashboardVersion.dashboard_id == CustomDashboard.id,
            )
            .where(*conditions)
            .order_by(CustomDashboard.sort_order.asc(), CustomDashboard.id.asc())
        )
        return list((await db.execute(query)).all())

    @staticmethod
    async def list_versions_for_field_reference_check(
        db: AsyncSession,
        tenant_id: int,
    ) -> list[tuple[CustomDashboard, CustomDashboardVersion]]:
        query = (
            select(CustomDashboard, CustomDashboardVersion)
            .join(
                CustomDashboardVersion,
                CustomDashboardVersion.dashboard_id == CustomDashboard.id,
            )
            .where(CustomDashboard.tenant_id == tenant_id)
            .order_by(CustomDashboard.id, CustomDashboardVersion.kind)
        )
        return list((await db.execute(query)).all())
