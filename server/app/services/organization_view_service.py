"""
OrganizationView service — business logic for organization view management
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.organization_view_repository import OrganizationViewRepository
from app.schemas.organization_view import (
    OrganizationViewCreate,
    OrganizationViewUpdate,
    OrganizationViewSortRequest,
)


class OrganizationViewService:

    @staticmethod
    async def get_paginated(
        db: AsyncSession, tenant_id: int, page: int = 1, per_page: int = 50
    ) -> dict:
        items, total = await OrganizationViewRepository.get_paginated(
            db, tenant_id, page, per_page
        )
        pages = (total + per_page - 1) // per_page
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, view_id: int, tenant_id: int):
        item = await OrganizationViewRepository.get_by_id(db, view_id, tenant_id)
        if not item:
            raise NotFoundError("Organization view not found")
        return item

    @staticmethod
    async def create(
        db: AsyncSession, tenant_id: int, data: OrganizationViewCreate
    ):
        max_sort = await OrganizationViewRepository.max_sort_order(db, tenant_id)
        payload = data.model_dump()
        payload["tenant_id"] = tenant_id
        payload["sort_order"] = max_sort + 1
        # Serialize nested pydantic models to dicts for JSONB storage
        payload["conditions"] = [c.model_dump() for c in data.conditions]
        payload["columns_config"] = [c.model_dump() for c in data.columns_config]
        return await OrganizationViewRepository.create(db, payload)

    @staticmethod
    async def update(
        db: AsyncSession, view_id: int, tenant_id: int, data: OrganizationViewUpdate
    ):
        item = await OrganizationViewRepository.get_by_id(db, view_id, tenant_id)
        if not item:
            raise NotFoundError("Organization view not found")

        update_data = data.model_dump(exclude_unset=True)
        if "conditions" in update_data and update_data["conditions"] is not None:
            update_data["conditions"] = [
                c.model_dump() if hasattr(c, "model_dump") else c
                for c in data.conditions
            ]
        if "columns_config" in update_data and update_data["columns_config"] is not None:
            update_data["columns_config"] = [
                c.model_dump() if hasattr(c, "model_dump") else c
                for c in data.columns_config
            ]
        return await OrganizationViewRepository.update(db, item, update_data)

    @staticmethod
    async def delete(db: AsyncSession, view_id: int, tenant_id: int) -> None:
        item = await OrganizationViewRepository.get_by_id(db, view_id, tenant_id)
        if not item:
            raise NotFoundError("Organization view not found")
        await OrganizationViewRepository.delete(db, item)

    @staticmethod
    async def toggle_enabled(
        db: AsyncSession, view_id: int, tenant_id: int, is_enabled: bool
    ):
        item = await OrganizationViewRepository.get_by_id(db, view_id, tenant_id)
        if not item:
            raise NotFoundError("Organization view not found")
        return await OrganizationViewRepository.update(db, item, {"is_enabled": is_enabled})

    @staticmethod
    async def update_sort(
        db: AsyncSession, tenant_id: int, data: OrganizationViewSortRequest
    ) -> None:
        if not data.items:
            raise ValidationError("Sort items cannot be empty")
        items = [{"id": i.id, "sort_order": i.sort_order} for i in data.items]
        await OrganizationViewRepository.bulk_update_sort(db, tenant_id, items)
