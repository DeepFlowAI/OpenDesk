"""
Verify file router — domain-verification file API for Tenant Platform.

Authenticated via X-API-Key (same key as /api/v1/tenants).
"""
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_platform_auth import verify_tenant_api_key
from app.db.deps import get_db

from .schemas import (
    VerifyFileCreate,
    VerifyFileListResponse,
    VerifyFileResponse,
    VerifyFileUpdate,
)
from .service import VerifyFileService


router = APIRouter(
    prefix="/verify-files",
    tags=["Verify Files"],
    dependencies=[Depends(verify_tenant_api_key)],
)

# Public serving router (no API key). nginx rewrites root requests like
# `/XFu51qFh2n.txt` to `/internal/verify-files/XFu51qFh2n.txt` and proxies them
# here; the content is looked up by filename in the database on demand.
public_router = APIRouter(tags=["Verify Files (public)"])


@public_router.get("/internal/verify-files/{filename}", include_in_schema=False)
async def serve_verify_file(
    filename: str,
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    content = await VerifyFileService.get_content_by_filename(db, filename)
    if content is None:
        return PlainTextResponse("Not Found", status_code=status.HTTP_404_NOT_FOUND)
    return PlainTextResponse(content)


@router.get("", response_model=VerifyFileListResponse)
async def list_verify_files(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> VerifyFileListResponse:
    return await VerifyFileService.list_files(db, page=page, per_page=per_page, q=q)


@router.post("", response_model=VerifyFileResponse, status_code=status.HTTP_201_CREATED)
async def create_verify_file(
    payload: VerifyFileCreate,
    db: AsyncSession = Depends(get_db),
) -> VerifyFileResponse:
    return await VerifyFileService.create_file(db, payload)


@router.get("/{file_id}", response_model=VerifyFileResponse)
async def get_verify_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
) -> VerifyFileResponse:
    return await VerifyFileService.get_file(db, file_id)


@router.put("/{file_id}", response_model=VerifyFileResponse)
async def update_verify_file(
    file_id: str,
    payload: VerifyFileUpdate,
    db: AsyncSession = Depends(get_db),
) -> VerifyFileResponse:
    update_fields = payload.model_dump(exclude_unset=True)
    return await VerifyFileService.update_file(
        db, file_id, payload, update_fields=update_fields
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_verify_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await VerifyFileService.delete_file(db, file_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
