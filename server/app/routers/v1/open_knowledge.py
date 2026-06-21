"""
Knowledge base Open API router authenticated by tenant API keys.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db
from app.db.open_api_deps import get_open_api_context
from app.schemas.knowledge import (
    KnowledgeDirectoryCreate,
    KnowledgeDirectoryListResponse,
    KnowledgeDirectoryMove,
    KnowledgeDirectoryResponse,
    KnowledgeDirectoryUpdate,
    KnowledgeDocumentCreate,
    KnowledgeDocumentDisplayStatus,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    KnowledgeDocumentStatus,
    KnowledgeDocumentUpdate,
)
from app.schemas.open_api import OpenApiContext
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/open/knowledge", tags=["OpenKnowledge"])


@router.get("/directories", response_model=KnowledgeDirectoryListResponse)
async def list_open_knowledge_directories(
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """List tenant knowledge directories as a tree."""
    return await KnowledgeService.list_directories(
        db,
        context.tenant_id,
        include_drafts=True,
    )


@router.post(
    "/directories",
    response_model=KnowledgeDirectoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_open_knowledge_directory(
    body: KnowledgeDirectoryCreate,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Create a knowledge directory through Open API."""
    return await KnowledgeService.create_directory(
        db,
        context.tenant_id,
        body,
        context.api_key_id,
        actor_type="api_key",
        actor_name=context.actor_name,
    )


@router.put("/directories/{directory_id}", response_model=KnowledgeDirectoryResponse)
async def update_open_knowledge_directory(
    directory_id: int,
    body: KnowledgeDirectoryUpdate,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Update a knowledge directory through Open API."""
    return await KnowledgeService.update_directory(
        db,
        context.tenant_id,
        directory_id,
        body,
        context.api_key_id,
        actor_type="api_key",
        actor_name=context.actor_name,
    )


@router.patch("/directories/{directory_id}/move", response_model=KnowledgeDirectoryResponse)
async def move_open_knowledge_directory(
    directory_id: int,
    body: KnowledgeDirectoryMove,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Move or reorder a knowledge directory through Open API."""
    return await KnowledgeService.move_directory(
        db,
        context.tenant_id,
        directory_id,
        body,
        context.api_key_id,
        actor_type="api_key",
        actor_name=context.actor_name,
    )


@router.delete("/directories/{directory_id}", status_code=status.HTTP_200_OK)
async def delete_open_knowledge_directory(
    directory_id: int,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Delete an empty knowledge directory through Open API."""
    await KnowledgeService.delete_directory(db, context.tenant_id, directory_id)
    return {"message": "Deleted successfully"}


@router.get("/documents", response_model=KnowledgeDocumentListResponse)
async def list_open_knowledge_documents(
    directory: int | None = None,
    q: str | None = None,
    status: KnowledgeDocumentStatus | None = None,
    display_status: KnowledgeDocumentDisplayStatus | None = None,
    page: int = 1,
    per_page: int = 20,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge documents through Open API."""
    return await KnowledgeService.list_documents(
        db,
        context.tenant_id,
        directory_id=directory,
        search=q,
        status=status,
        display_status=display_status,
        include_drafts=True,
        page=page,
        per_page=per_page,
    )


@router.post(
    "/documents",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_open_knowledge_document(
    body: KnowledgeDocumentCreate,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Create a knowledge document through Open API."""
    return await KnowledgeService.create_document(
        db,
        context.tenant_id,
        body,
        context.api_key_id,
        actor_type="api_key",
        actor_name=context.actor_name,
    )


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentResponse)
async def get_open_knowledge_document(
    document_id: int,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Get a knowledge document through Open API."""
    return await KnowledgeService.get_document(
        db,
        context.tenant_id,
        document_id,
        include_drafts=True,
    )


@router.put("/documents/{document_id}", response_model=KnowledgeDocumentResponse)
async def update_open_knowledge_document(
    document_id: int,
    body: KnowledgeDocumentUpdate,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Update a knowledge document through Open API."""
    return await KnowledgeService.update_document(
        db,
        context.tenant_id,
        document_id,
        body,
        context.api_key_id,
        actor_type="api_key",
        actor_name=context.actor_name,
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_200_OK)
async def delete_open_knowledge_document(
    document_id: int,
    context: OpenApiContext = Depends(get_open_api_context),
    db: AsyncSession = Depends(get_db),
):
    """Delete a knowledge document through Open API."""
    await KnowledgeService.delete_document(db, context.tenant_id, document_id)
    return {"message": "Deleted successfully"}
