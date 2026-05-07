"""
TicketView service — business logic for ticket view management
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.ticket_view_repository import TicketViewRepository
from app.schemas.ticket_view import (
    TicketViewCreate,
    TicketViewUpdate,
    TicketViewSortRequest,
)


class TicketViewService:

    @staticmethod
    async def get_paginated(
        db: AsyncSession, tenant_id: int, page: int = 1, per_page: int = 50
    ) -> dict:
        items, total = await TicketViewRepository.get_paginated(
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
        item = await TicketViewRepository.get_by_id(db, view_id, tenant_id)
        if not item:
            raise NotFoundError("Ticket view not found")
        return item

    @staticmethod
    async def create(
        db: AsyncSession, tenant_id: int, data: TicketViewCreate
    ):
        max_sort = await TicketViewRepository.max_sort_order(db, tenant_id)
        payload = data.model_dump()
        payload["tenant_id"] = tenant_id
        payload["sort_order"] = max_sort + 1
        payload["conditions"] = [c.model_dump() for c in data.conditions]
        payload["columns_config"] = [c.model_dump() for c in data.columns_config]
        return await TicketViewRepository.create(db, payload)

    @staticmethod
    async def update(
        db: AsyncSession, view_id: int, tenant_id: int, data: TicketViewUpdate
    ):
        item = await TicketViewRepository.get_by_id(db, view_id, tenant_id)
        if not item:
            raise NotFoundError("Ticket view not found")

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
        return await TicketViewRepository.update(db, item, update_data)

    @staticmethod
    async def delete(db: AsyncSession, view_id: int, tenant_id: int) -> None:
        item = await TicketViewRepository.get_by_id(db, view_id, tenant_id)
        if not item:
            raise NotFoundError("Ticket view not found")
        await TicketViewRepository.delete(db, item)

    @staticmethod
    async def toggle_enabled(
        db: AsyncSession, view_id: int, tenant_id: int, is_enabled: bool
    ):
        item = await TicketViewRepository.get_by_id(db, view_id, tenant_id)
        if not item:
            raise NotFoundError("Ticket view not found")
        return await TicketViewRepository.update(db, item, {"is_enabled": is_enabled})

    @staticmethod
    async def update_sort(
        db: AsyncSession, tenant_id: int, data: TicketViewSortRequest
    ) -> None:
        if not data.items:
            raise ValidationError("Sort items cannot be empty")
        items = [{"id": i.id, "sort_order": i.sort_order} for i in data.items]
        await TicketViewRepository.bulk_update_sort(db, tenant_id, items)
