"""
Users router — end-user (visitor/customer) CRUD, list & detail APIs
"""
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user, get_redis, require_permission
from app.libs.excel import XLSX_MEDIA_TYPE, xlsx_content_disposition
from app.schemas.user import (
    UserResponse,
    UserCreate,
    UserUpdate,
    UserListResponse,
    UserQueryRequest,
    UserExportRequest,
    ViewCountsResponse,
)
from app.schemas.user_import import (
    UserImportErrorReportRequest,
    UserImportExecuteRequest,
    UserImportExecuteResponse,
    UserImportPreviewResponse,
)
from app.schemas.entity_change import EntityChangeListResponse
from app.schemas.user_view import UserViewResponse
from app.schemas.view_group import ViewGroupRequest, ViewGroupResponse
from app.services.entity_change_service import EntityChangeService
from app.services.user_import_service import UserImportService
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.post(
    "/query",
    response_model=UserListResponse,
    dependencies=[Depends(require_permission("crm.workspace.user.view"))],
)
async def query_users(
    body: UserQueryRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Query users with optional view-based system filters + temporary filters.
    System view filters are applied from view_id config;
    temp_conditions are additional client-side filters (session-only, not persisted).
    """
    tenant_id = current_user["tenant_id"]
    return await UserService.query_users(db, tenant_id, body)


@router.post(
    "/export",
    dependencies=[Depends(require_permission("crm.workspace.user.export"))],
)
async def export_users(
    body: UserExportRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export users matching current list context to an Excel file."""
    tenant_id = current_user["tenant_id"]
    content, filename = await UserService.export_users(db, tenant_id, body)
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": xlsx_content_disposition(filename)},
    )


@router.get(
    "/import/template",
    dependencies=[Depends(require_permission("crm.workspace.user.import"))],
)
async def download_user_import_template(
    locale: str = Query(default="zh", max_length=8),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a dynamic end-user import template."""
    tenant_id = current_user["tenant_id"]
    content, filename = await UserImportService.build_template(db, tenant_id, locale)
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": xlsx_content_disposition(filename)},
    )


@router.post(
    "/import/preview",
    response_model=UserImportPreviewResponse,
    dependencies=[Depends(require_permission("crm.workspace.user.import"))],
)
async def preview_user_import(
    file: UploadFile = File(...),
    locale: str = Query(default="zh", max_length=8),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Parse and validate an uploaded import file."""
    tenant_id = current_user["tenant_id"]
    content = await file.read()
    filename = file.filename or "import.xlsx"
    return await UserImportService.preview_import(
        db,
        redis,
        tenant_id,
        filename,
        content,
        locale,
    )


@router.post(
    "/import/execute",
    response_model=UserImportExecuteResponse,
    dependencies=[Depends(require_permission("crm.workspace.user.import"))],
)
async def execute_user_import(
    body: UserImportExecuteRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Create users from a validated import preview."""
    tenant_id = current_user["tenant_id"]
    return await UserImportService.execute_import(
        db,
        redis,
        tenant_id,
        body.preview_token,
        actor_id=current_user.get("user_id"),
    )


@router.post(
    "/import/error-report",
    dependencies=[Depends(require_permission("crm.workspace.user.import"))],
)
async def download_user_import_error_report(
    body: UserImportErrorReportRequest,
    locale: str = Query(default="zh", max_length=8),
):
    """Download an Excel file containing import errors."""
    content, filename = UserImportService.build_error_report(body, locale)
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": xlsx_content_disposition(filename)},
    )


@router.get(
    "/views/enabled",
    response_model=list[UserViewResponse],
    dependencies=[Depends(require_permission("crm.workspace.user.view"))],
)
async def list_enabled_views(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all enabled user views for the sidebar (ordered by sort_order)."""
    tenant_id = current_user["tenant_id"]
    return await UserService.get_enabled_views(db, tenant_id)


@router.get(
    "/views/counts",
    response_model=ViewCountsResponse,
    dependencies=[Depends(require_permission("crm.workspace.user.view"))],
)
async def get_view_counts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user count per enabled view + total (for sidebar numbers)."""
    tenant_id = current_user["tenant_id"]
    return await UserService.get_view_counts(db, tenant_id)


@router.post(
    "/views/{view_id}/groups",
    response_model=ViewGroupResponse,
    dependencies=[Depends(require_permission("crm.workspace.user.view"))],
)
async def get_view_groups(
    view_id: int,
    body: ViewGroupRequest | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate users under the given view by its configured group field."""
    tenant_id = current_user["tenant_id"]
    payload = body or ViewGroupRequest()
    return await UserService.get_view_groups(db, tenant_id, view_id, payload)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("crm.workspace.user.create"))],
)
async def create_user(
    body: UserCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new end user under the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await UserService.create_user(
        db,
        tenant_id,
        body,
        actor_id=current_user.get("user_id"),
    )


@router.get(
    "/{user_ref}",
    response_model=UserResponse,
    dependencies=[Depends(require_permission("crm.workspace.user.view"))],
)
async def get_user(
    user_ref: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single user by public ID, with numeric ID compatibility."""
    tenant_id = current_user["tenant_id"]
    return await UserService.get_by_ref(db, tenant_id, user_ref)


@router.get(
    "/{user_id}/changes",
    response_model=EntityChangeListResponse,
    dependencies=[Depends(require_permission("crm.workspace.user.view"))],
)
async def list_user_changes(
    user_id: int,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List field-level changes for a user."""
    tenant_id = current_user["tenant_id"]
    return await EntityChangeService.get_paginated(
        db,
        tenant_id,
        "user",
        user_id,
        page,
        per_page,
    )


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_permission("crm.workspace.user.edit"))],
)
async def update_user(
    user_id: int,
    body: UserUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing end user."""
    tenant_id = current_user["tenant_id"]
    return await UserService.update_user(
        db,
        tenant_id,
        user_id,
        body,
        actor_id=current_user.get("user_id"),
    )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("crm.workspace.user.delete"))],
)
async def delete_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an existing end user."""
    tenant_id = current_user["tenant_id"]
    await UserService.delete_user(db, tenant_id, user_id)
    return {"message": "Deleted successfully"}
