"""
Field definition management routes.

Provides two listing approaches:
  - GET /field-definitions/unified?domain=...  → system + custom merged
  - GET /field-definitions                     → custom-only (legacy/internal)
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.fd_field_definition import (
    FdFieldDefinitionCreate,
    FdFieldDefinitionUpdate,
    FdFieldDefinitionResponse,
    FdFieldDefinitionListResponse,
    UnifiedFieldListResponse,
    SystemFieldListResponse,
    FdFieldOptionCreate,
    FdFieldOptionUpdate,
    FdFieldOptionResponse,
    FdTreeNodeCreate,
    FdTreeNodeUpdate,
    FdTreeNodeResponse,
    SortRequest,
    SystemFieldOverrideUpdate,
)
from app.services.fd_field_definition_service import FdFieldDefinitionService

router = APIRouter(prefix="/field-definitions", tags=["FieldDefinitions"])


# ── Unified list (system + custom) ──


@router.get("/unified", response_model=UnifiedFieldListResponse)
async def list_unified_fields(
    domain: str = Query(..., description="Field domain (user / organization / shared_pool)"),
    locale: str = Query("zh", description="Locale for system field names (zh / en)"),
    include_metadata: bool = Query(False, description="Include always-visible metadata fields (created_at, updated_at)"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all fields (system + custom) for a domain, merged."""
    return await FdFieldDefinitionService.get_unified_list(
        db, tenant_id=user["tenant_id"], domain=domain, locale=locale,
        include_metadata=include_metadata,
    )


# ── System field definitions (read-only constants) ──


@router.get("/system/{domain}", response_model=SystemFieldListResponse)
async def list_system_fields(
    domain: str,
    locale: str = Query("zh", description="Locale for system field names (zh / en)"),
    user: dict = Depends(get_current_user),
):
    """List all system field definitions for a domain (hardcoded constants with defaults)."""
    return FdFieldDefinitionService.get_system_field_list(domain=domain, locale=locale)


# ── System field overrides ──


@router.patch("/system/{domain}/{field_key}")
async def update_system_field_override(
    domain: str,
    field_key: str,
    body: SystemFieldOverrideUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update per-tenant override for a system field (show_in_workspace, sort_order, status)."""
    return await FdFieldDefinitionService.update_system_field_override(
        db, tenant_id=user["tenant_id"], domain=domain, field_key=field_key, data=body,
    )


# ── Sort (supports both system key and custom id) ──


@router.put("/sort")
async def sort_field_definitions(
    domain: str = Query(..., description="Domain to sort"),
    body: SortRequest = ...,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Batch update sort order for system + custom fields."""
    await FdFieldDefinitionService.batch_sort(
        db, tenant_id=user["tenant_id"], domain=domain, data=body,
    )
    return {"message": "Sort order updated"}


# ── Field Definition CRUD (custom fields only) ──


@router.get("", response_model=FdFieldDefinitionListResponse)
async def list_field_definitions(
    domain: str | None = None,
    status_filter: str | None = None,
    page: int = 1,
    per_page: int = 50,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List custom field definitions filtered by domain (excludes system fields)."""
    return await FdFieldDefinitionService.get_paginated(
        db, tenant_id=user["tenant_id"], domain=domain, status=status_filter,
        page=page, per_page=per_page,
    )


@router.post("", response_model=FdFieldDefinitionResponse, status_code=status.HTTP_201_CREATED)
async def create_field_definition(
    body: FdFieldDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a new custom field definition with automatic slot allocation."""
    return await FdFieldDefinitionService.create(db, tenant_id=user["tenant_id"], data=body)


@router.get("/{definition_id}", response_model=FdFieldDefinitionResponse)
async def get_field_definition(
    definition_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get field definition detail with options/tree nodes."""
    return await FdFieldDefinitionService.get_by_id(db, definition_id)


@router.put("/{definition_id}", response_model=FdFieldDefinitionResponse)
async def update_field_definition(
    definition_id: int,
    body: FdFieldDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update field definition (field_type is immutable)."""
    return await FdFieldDefinitionService.update(
        db, definition_id, tenant_id=user["tenant_id"], data=body,
    )


@router.delete("/{definition_id}", status_code=status.HTTP_200_OK)
async def delete_field_definition(
    definition_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete a custom field definition (system fields cannot be deleted)."""
    await FdFieldDefinitionService.delete(db, definition_id, tenant_id=user["tenant_id"])
    return {"message": "Deleted successfully"}


# ── Options ──


@router.get("/{definition_id}/options", response_model=list[FdFieldOptionResponse])
async def list_options(
    definition_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List options for a select-type field."""
    return await FdFieldDefinitionService.get_options(db, definition_id)


@router.post(
    "/{definition_id}/options",
    response_model=FdFieldOptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_option(
    definition_id: int,
    body: FdFieldOptionCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Add an option to a select-type field."""
    return await FdFieldDefinitionService.create_option(
        db, definition_id, tenant_id=user["tenant_id"], data=body,
    )


@router.put("/{definition_id}/options/{option_id}", response_model=FdFieldOptionResponse)
async def update_option(
    definition_id: int,
    option_id: int,
    body: FdFieldOptionUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update an option."""
    return await FdFieldDefinitionService.update_option(
        db, option_id, tenant_id=user["tenant_id"], data=body,
    )


@router.delete("/{definition_id}/options/{option_id}", status_code=status.HTTP_200_OK)
async def delete_option(
    definition_id: int,
    option_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete an option."""
    await FdFieldDefinitionService.delete_option(db, option_id, tenant_id=user["tenant_id"])
    return {"message": "Deleted successfully"}


# ── Tree Nodes ──


@router.get("/{definition_id}/tree-nodes", response_model=list[FdTreeNodeResponse])
async def list_tree_nodes(
    definition_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get tree nodes for a tree-type field."""
    return await FdFieldDefinitionService.get_tree_nodes(db, definition_id)


@router.post(
    "/{definition_id}/tree-nodes",
    response_model=FdTreeNodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tree_node(
    definition_id: int,
    body: FdTreeNodeCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Add a tree node to a tree-type field."""
    return await FdFieldDefinitionService.create_tree_node(
        db, definition_id, tenant_id=user["tenant_id"], data=body,
    )


@router.put("/{definition_id}/tree-nodes/{node_id}", response_model=FdTreeNodeResponse)
async def update_tree_node(
    definition_id: int,
    node_id: int,
    body: FdTreeNodeUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update a tree node."""
    return await FdFieldDefinitionService.update_tree_node(
        db, node_id, tenant_id=user["tenant_id"], data=body,
    )


@router.delete("/{definition_id}/tree-nodes/{node_id}", status_code=status.HTTP_200_OK)
async def delete_tree_node(
    definition_id: int,
    node_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete a tree node."""
    await FdFieldDefinitionService.delete_tree_node(db, node_id, tenant_id=user["tenant_id"])
    return {"message": "Deleted successfully"}
