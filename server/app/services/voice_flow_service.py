"""
Voice flow service
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.voice_flow_repository import VoiceFlowRepository
from app.schemas.voice_flow import VoiceFlowCreate, VoiceFlowUpdate


class VoiceFlowService:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 10,
        keyword: str | None = None,
        include_deleted: bool = False,
    ) -> dict:
        rows, total = await VoiceFlowRepository.get_paginated(
            db, tenant_id, page, per_page, keyword, include_deleted
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        items = [
            {
                "id": r.id,
                "name": r.name,
                "enabled": r.enabled,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def list_for_select(db: AsyncSession, tenant_id: int) -> dict:
        rows = await VoiceFlowRepository.list_for_select(db, tenant_id)
        return {"items": [{"id": r.id, "name": r.name} for r in rows]}

    @staticmethod
    async def get_by_id(db: AsyncSession, flow_id: int, tenant_id: int) -> dict:
        row = await VoiceFlowRepository.get_by_id(db, flow_id, tenant_id)
        if not row:
            raise NotFoundError("Voice flow not found")
        return {
            "id": row.id,
            "name": row.name,
            "enabled": row.enabled,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: VoiceFlowCreate) -> dict:
        payload = {"tenant_id": tenant_id, "name": data.name, "enabled": data.enabled}
        row = await VoiceFlowRepository.create(db, payload)
        return await VoiceFlowService.get_by_id(db, row.id, tenant_id)

    @staticmethod
    async def update(db: AsyncSession, flow_id: int, tenant_id: int, data: VoiceFlowUpdate) -> dict:
        row = await VoiceFlowRepository.get_by_id(db, flow_id, tenant_id)
        if not row:
            raise NotFoundError("Voice flow not found")
        await VoiceFlowRepository.update(db, row, {"name": data.name, "enabled": data.enabled})
        return await VoiceFlowService.get_by_id(db, flow_id, tenant_id)

    @staticmethod
    async def delete(db: AsyncSession, flow_id: int, tenant_id: int) -> None:
        row = await VoiceFlowRepository.get_by_id(db, flow_id, tenant_id)
        if not row:
            raise NotFoundError("Voice flow not found")
        await VoiceFlowRepository.soft_delete(db, row)
