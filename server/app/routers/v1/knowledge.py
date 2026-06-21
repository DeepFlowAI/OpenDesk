"""
Knowledge base router.
"""
from typing import Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_redis, require_permission
from app.libs.excel import XLSX_MEDIA_TYPE, xlsx_content_disposition
from app.schemas.knowledge import (
    KnowledgeDirectoryCreate,
    KnowledgeDirectoryListResponse,
    KnowledgeDirectoryMove,
    KnowledgeDirectoryResponse,
    KnowledgeDirectoryUpdate,
    KnowledgeDocumentCreate,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    KnowledgeDocumentUpdate,
)
from app.schemas.knowledge_import import (
    KnowledgeImportExecuteRequest,
    KnowledgeImportExecuteResponse,
    KnowledgeImportPreviewResponse,
)
from app.schemas.permission import EffectivePrincipal
from app.services.knowledge_import_service import KnowledgeImportService
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


@router.get(
    "/import/template",
    dependencies=[Depends(require_permission("knowledge.workspace.import"))],
)
async def download_knowledge_import_template(
    locale: str = Query(default="zh", max_length=8),
):
    """Download a knowledge import template."""
    content, filename = await KnowledgeImportService.build_template(locale)
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": xlsx_content_disposition(filename)},
    )


@router.get(
    "/export",
    dependencies=[Depends(require_permission("knowledge.workspace.export"))],
)
async def export_knowledge_documents(
    directory: int | None = None,
    q: str | None = None,
    locale: str = Query(default="zh", max_length=8),
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.export")),
    db: AsyncSession = Depends(get_db),
):
    """Export knowledge documents matching the current list filters."""
    content, filename = await KnowledgeImportService.export_documents(
        db,
        principal.tenant_id,
        principal,
        directory_id=directory,
        search=q,
        locale=locale,
    )
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": xlsx_content_disposition(filename)},
    )


@router.post(
    "/import/preview",
    response_model=KnowledgeImportPreviewResponse,
    dependencies=[Depends(require_permission("knowledge.workspace.import"))],
)
async def preview_knowledge_import(
    file: UploadFile = File(...),
    locale: str = Query(default="zh", max_length=8),
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.import")),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Parse and validate an uploaded knowledge import file."""
    content = await file.read()
    filename = file.filename or "import.xlsx"
    return await KnowledgeImportService.preview_import(
        db,
        redis,
        principal.tenant_id,
        filename,
        content,
        locale,
    )


@router.post(
    "/import/execute",
    response_model=KnowledgeImportExecuteResponse,
    dependencies=[Depends(require_permission("knowledge.workspace.import"))],
)
async def execute_knowledge_import(
    body: KnowledgeImportExecuteRequest,
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.import")),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Create or update knowledge documents from a validated preview."""
    return await KnowledgeImportService.execute_import(
        db,
        redis,
        principal.tenant_id,
        body.preview_token,
        actor_id=principal.user_id,
    )


@router.get(
    "/directories",
    response_model=KnowledgeDirectoryListResponse,
    dependencies=[Depends(require_permission("knowledge.workspace.view"))],
)
async def list_knowledge_directories(
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.view")),
    db: AsyncSession = Depends(get_db),
):
    """List tenant knowledge directories as a tree."""
    return await KnowledgeService.list_directories(db, principal.tenant_id, principal)


@router.post(
    "/directories",
    response_model=KnowledgeDirectoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("knowledge.workspace.directory.manage"))],
)
async def create_knowledge_directory(
    body: KnowledgeDirectoryCreate,
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.directory.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a knowledge directory."""
    return await KnowledgeService.create_directory(db, principal.tenant_id, body, principal.user_id)


@router.put(
    "/directories/{directory_id}",
    response_model=KnowledgeDirectoryResponse,
    dependencies=[Depends(require_permission("knowledge.workspace.directory.manage"))],
)
async def update_knowledge_directory(
    directory_id: int,
    body: KnowledgeDirectoryUpdate,
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.directory.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Update a knowledge directory."""
    return await KnowledgeService.update_directory(db, principal.tenant_id, directory_id, body, principal.user_id)


@router.patch(
    "/directories/{directory_id}/move",
    response_model=KnowledgeDirectoryResponse,
    dependencies=[Depends(require_permission("knowledge.workspace.directory.manage"))],
)
async def move_knowledge_directory(
    directory_id: int,
    body: KnowledgeDirectoryMove,
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.directory.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Move or reorder a knowledge directory."""
    return await KnowledgeService.move_directory(db, principal.tenant_id, directory_id, body, principal.user_id)


@router.delete(
    "/directories/{directory_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("knowledge.workspace.directory.manage"))],
)
async def delete_knowledge_directory(
    directory_id: int,
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.directory.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Delete an empty knowledge directory."""
    await KnowledgeService.delete_directory(db, principal.tenant_id, directory_id)
    return {"message": "Deleted successfully"}


@router.get(
    "/documents",
    response_model=KnowledgeDocumentListResponse,
    dependencies=[Depends(require_permission("knowledge.workspace.view"))],
)
async def list_knowledge_documents(
    directory: int | None = None,
    q: str | None = None,
    display_status: Literal["draft", "published", "expired"] | None = None,
    page: int = 1,
    per_page: int = 20,
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.view")),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge documents."""
    return await KnowledgeService.list_documents(
        db,
        principal.tenant_id,
        principal,
        directory_id=directory,
        search=q,
        display_status=display_status,
        page=page,
        per_page=per_page,
    )


@router.post(
    "/documents",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("knowledge.workspace.document.create"))],
)
async def create_knowledge_document(
    body: KnowledgeDocumentCreate,
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.document.create")),
    db: AsyncSession = Depends(get_db),
):
    """Create a knowledge document."""
    return await KnowledgeService.create_document(db, principal.tenant_id, body, principal.user_id)


@router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentResponse,
    dependencies=[Depends(require_permission("knowledge.workspace.view"))],
)
async def get_knowledge_document(
    document_id: int,
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.view")),
    db: AsyncSession = Depends(get_db),
):
    """Get a knowledge document."""
    return await KnowledgeService.get_document(db, principal.tenant_id, document_id, principal)


@router.put(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentResponse,
    dependencies=[Depends(require_permission("knowledge.workspace.document.edit"))],
)
async def update_knowledge_document(
    document_id: int,
    body: KnowledgeDocumentUpdate,
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.document.edit")),
    db: AsyncSession = Depends(get_db),
):
    """Update a knowledge document."""
    return await KnowledgeService.update_document(db, principal.tenant_id, document_id, body, principal.user_id)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("knowledge.workspace.document.delete"))],
)
async def delete_knowledge_document(
    document_id: int,
    principal: EffectivePrincipal = Depends(require_permission("knowledge.workspace.document.delete")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a knowledge document."""
    await KnowledgeService.delete_document(db, principal.tenant_id, document_id)
    return {"message": "Deleted successfully"}
