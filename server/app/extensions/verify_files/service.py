"""
Verify file service — manages domain-verification files for Tenant Platform.

Files are stored only in the ``verify_files`` table (single source of truth).
The public serving route looks the content up by filename on demand, so there
is no on-disk copy and no shared volume to coordinate.
"""
import uuid
from math import ceil

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.verify_file_repository import VerifyFileRepository

from .schemas import (
    VerifyFileCreate,
    VerifyFileListResponse,
    VerifyFileResponse,
    VerifyFileUpdate,
)


def _to_response(row) -> VerifyFileResponse:
    return VerifyFileResponse(
        id=row.id,
        filename=row.filename,
        content=row.content,
        remark=row.remark,
        url=f"/{row.filename}",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class VerifyFileService:

    @staticmethod
    async def list_files(
        db: AsyncSession, page: int, per_page: int, q: str | None = None
    ) -> VerifyFileListResponse:
        total = await VerifyFileRepository.count_filtered(db, q=q)
        offset = (page - 1) * per_page
        items = await VerifyFileRepository.list_filtered(
            db, q=q, offset=offset, limit=per_page
        )
        pages = ceil(total / per_page) if total else 0
        return VerifyFileListResponse(
            items=[_to_response(item) for item in items],
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
        )

    @staticmethod
    async def get_file(db: AsyncSession, file_id: str) -> VerifyFileResponse:
        row = await VerifyFileRepository.get_by_id(db, file_id)
        if not row:
            raise NotFoundError("Verify file not found")
        return _to_response(row)

    @staticmethod
    async def create_file(db: AsyncSession, payload: VerifyFileCreate) -> VerifyFileResponse:
        # The unique index on lower(filename) is the authoritative duplicate
        # guard (incl. concurrent writes); the repository maps it to 409.
        row = await VerifyFileRepository.create(
            db,
            {
                "id": f"vf_{uuid.uuid4().hex[:12]}",
                "filename": payload.filename.strip(),
                "content": payload.content,
                "remark": (payload.remark or "").strip() or None,
            },
        )
        return _to_response(row)

    @staticmethod
    async def update_file(
        db: AsyncSession, file_id: str, payload: VerifyFileUpdate, update_fields: dict
    ) -> VerifyFileResponse:
        row = await VerifyFileRepository.get_by_id(db, file_id)
        if not row:
            raise NotFoundError("Verify file not found")
        data: dict = {}
        if "content" in update_fields:
            data["content"] = payload.content
        if "remark" in update_fields:
            data["remark"] = (payload.remark or "").strip() or None
        if data:
            row = await VerifyFileRepository.update(db, row, data)
        return _to_response(row)

    @staticmethod
    async def delete_file(db: AsyncSession, file_id: str) -> None:
        row = await VerifyFileRepository.get_by_id(db, file_id)
        if not row:
            raise NotFoundError("Verify file not found")
        await VerifyFileRepository.delete(db, row)

    @staticmethod
    async def get_content_by_filename(db: AsyncSession, filename: str) -> str | None:
        """Return the stored content for public root-path serving, or None."""
        row = await VerifyFileRepository.get_by_filename(db, filename)
        return row.content if row else None
