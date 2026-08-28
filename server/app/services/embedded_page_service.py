"""
Embedded page service.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.embedded_page import EmbeddedPage
from app.repositories.embedded_page_repository import EmbeddedPageRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.embedded_page import EmbeddedPageCreate, EmbeddedPageUpdate


class EmbeddedPageService:
    @staticmethod
    def _to_response(row: EmbeddedPage, *, default_focus_overridden: bool = False) -> dict:
        return {
            "id": row.id,
            "location": row.location,
            "name": row.name,
            "page_type": row.page_type,
            "url": row.url,
            "react_code": row.react_code,
            "config": row.config or {},
            "enabled": row.enabled,
            "default_focus": row.default_focus,
            "sort_order": row.sort_order,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "default_focus_overridden": default_focus_overridden,
        }

    @staticmethod
    def _to_workspace_item(row: EmbeddedPage) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "page_type": row.page_type,
            "url": row.url,
            "react_code": row.react_code,
            "config": row.config or {},
            "default_focus": row.default_focus,
            "sort_order": row.sort_order,
        }

    @staticmethod
    async def list_pages(db: AsyncSession, tenant_id: int, location: str) -> dict:
        rows = await EmbeddedPageRepository.list_by_location(db, tenant_id, location)
        return {
            "items": [EmbeddedPageService._to_response(row) for row in rows],
            "total": len(rows),
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, page_id: int, tenant_id: int) -> dict:
        row = await EmbeddedPageRepository.get_by_id(db, page_id, tenant_id)
        if not row:
            raise NotFoundError("Embedded page not found")
        return EmbeddedPageService._to_response(row)

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: EmbeddedPageCreate) -> dict:
        payload = data.model_dump()
        payload["tenant_id"] = tenant_id
        row = await EmbeddedPageRepository.create(db, payload)
        overridden = 0
        if row.default_focus:
            overridden = await EmbeddedPageRepository.clear_default_focus_others(
                db, tenant_id, row.location, row.id
            )
        await db.commit()
        await db.refresh(row)
        return EmbeddedPageService._to_response(row, default_focus_overridden=overridden > 0)

    @staticmethod
    async def update(db: AsyncSession, page_id: int, tenant_id: int, data: EmbeddedPageUpdate) -> dict:
        row = await EmbeddedPageRepository.get_by_id(db, page_id, tenant_id)
        if not row:
            raise NotFoundError("Embedded page not found")
        payload = data.model_dump()
        # Location is fixed by the management entry; never move a page.
        payload.pop("location", None)
        row = await EmbeddedPageRepository.update(db, row, payload)
        overridden = 0
        if row.default_focus:
            overridden = await EmbeddedPageRepository.clear_default_focus_others(
                db, tenant_id, row.location, row.id
            )
        await db.commit()
        await db.refresh(row)
        return EmbeddedPageService._to_response(row, default_focus_overridden=overridden > 0)

    @staticmethod
    async def delete(db: AsyncSession, page_id: int, tenant_id: int) -> None:
        row = await EmbeddedPageRepository.get_by_id(db, page_id, tenant_id)
        if not row:
            raise NotFoundError("Embedded page not found")
        await EmbeddedPageRepository.delete(db, row)

    @staticmethod
    async def list_workspace_pages(db: AsyncSession, tenant_id: int, agent_id: int, location: str) -> dict:
        rows = await EmbeddedPageRepository.list_enabled_by_location(db, tenant_id, location)
        employee = await EmployeeRepository.get_by_id(db, agent_id)
        agent = {
            "id": agent_id,
            "name": (employee.display_name or employee.name) if employee else "",
            "email": (employee.email or "") if employee else "",
        }
        return {
            "items": [EmbeddedPageService._to_workspace_item(row) for row in rows],
            "agent": agent,
        }
