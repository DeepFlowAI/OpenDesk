"""
Organizations router — organization CRUD, list & detail APIs
"""
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user, get_redis, require_permission
from app.libs.excel import XLSX_MEDIA_TYPE, xlsx_content_disposition
from app.schemas.organization import (
    OrganizationResponse,
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationListResponse,
    OrganizationQueryRequest,
    OrganizationExportRequest,
    OrgViewCountsResponse,
)
from app.schemas.organization_import import (
    OrganizationImportErrorReportRequest,
    OrganizationImportExecuteRequest,
    OrganizationImportExecuteResponse,
    OrganizationImportPreviewResponse,
)
from app.schemas.entity_change import EntityChangeListResponse
from app.schemas.organization_view import OrganizationViewResponse
from app.schemas.view_group import ViewGroupRequest, ViewGroupResponse
from app.services.entity_change_service import EntityChangeService
from app.services.organization_import_service import OrganizationImportService
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.get(
    "/import/template",
    dependencies=[Depends(require_permission("crm.workspace.org.import"))],
)
async def download_organization_import_template(
    locale: str = Query(default="zh", max_length=8),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a dynamic organization import template."""
    tenant_id = current_user["tenant_id"]
    content, filename = await OrganizationImportService.build_template(db, tenant_id, locale)
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": xlsx_content_disposition(filename)},
    )


@router.post(
    "/import/preview",
    response_model=OrganizationImportPreviewResponse,
    dependencies=[Depends(require_permission("crm.workspace.org.import"))],
)
async def preview_organization_import(
    file: UploadFile = File(...),
    locale: str = Query(default="zh", max_length=8),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Parse and validate an uploaded organization import file."""
    tenant_id = current_user["tenant_id"]
    content = await file.read()
    filename = file.filename or "import.xlsx"
    return await OrganizationImportService.preview_import(
        db,
        redis,
        tenant_id,
        filename,
        content,
        locale,
    )


@router.post(
    "/import/execute",
    response_model=OrganizationImportExecuteResponse,
    dependencies=[Depends(require_permission("crm.workspace.org.import"))],
)
async def execute_organization_import(
    body: OrganizationImportExecuteRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Create organizations from a validated import preview."""
    tenant_id = current_user["tenant_id"]
    return await OrganizationImportService.execute_import(
        db,
        redis,
        tenant_id,
        body.preview_token,
        actor_id=current_user.get("user_id"),
    )


@router.post(
    "/import/error-report",
    dependencies=[Depends(require_permission("crm.workspace.org.import"))],
)
async def download_organization_import_error_report(
    body: OrganizationImportErrorReportRequest,
    locale: str = Query(default="zh", max_length=8),
):
    """Download an Excel file containing organization import errors."""
    content, filename = OrganizationImportService.build_error_report(body, locale)
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": xlsx_content_disposition(filename)},
    )


@router.post(
    "/query",
    response_model=OrganizationListResponse,
    dependencies=[Depends(require_permission("crm.workspace.org.view"))],
)
async def query_organizations(
    body: OrganizationQueryRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query organizations with optional view-based system filters + temporary filters."""
    tenant_id = current_user["tenant_id"]
    return await OrganizationService.query_organizations(db, tenant_id, body)


@router.post(
    "/export",
    dependencies=[Depends(require_permission("crm.workspace.org.export"))],
)
async def export_organizations(
    body: OrganizationExportRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export organizations matching current list context to an Excel file."""
    tenant_id = current_user["tenant_id"]
    content, filename = await OrganizationService.export_organizations(db, tenant_id, body)
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": xlsx_content_disposition(filename)},
    )


@router.get(
    "/views/enabled",
    response_model=list[OrganizationViewResponse],
    dependencies=[Depends(require_permission("crm.workspace.org.view"))],
)
async def list_enabled_views(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all enabled organization views for the sidebar."""
    tenant_id = current_user["tenant_id"]
    return await OrganizationService.get_enabled_views(db, tenant_id)


@router.get(
    "/views/counts",
    response_model=OrgViewCountsResponse,
    dependencies=[Depends(require_permission("crm.workspace.org.view"))],
)
async def get_view_counts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get organization count per enabled view + total."""
    tenant_id = current_user["tenant_id"]
    return await OrganizationService.get_view_counts(db, tenant_id)


@router.post(
    "/views/{view_id}/groups",
    response_model=ViewGroupResponse,
    dependencies=[Depends(require_permission("crm.workspace.org.view"))],
)
async def get_view_groups(
    view_id: int,
    body: ViewGroupRequest | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate organizations under the given view by its configured group field."""
    tenant_id = current_user["tenant_id"]
    payload = body or ViewGroupRequest()
    return await OrganizationService.get_view_groups(db, tenant_id, view_id, payload)


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("crm.workspace.org.create"))],
)
async def create_organization(
    body: OrganizationCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new organization under the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await OrganizationService.create_organization(
        db,
        tenant_id,
        body,
        actor_id=current_user.get("user_id"),
    )


@router.get(
    "/{org_ref}",
    response_model=OrganizationResponse,
    dependencies=[Depends(require_permission("crm.workspace.org.view"))],
)
async def get_organization(
    org_ref: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single organization by public ID, with numeric ID compatibility."""
    tenant_id = current_user["tenant_id"]
    return await OrganizationService.get_by_ref(db, tenant_id, org_ref)


@router.get(
    "/{org_id}/changes",
    response_model=EntityChangeListResponse,
    dependencies=[Depends(require_permission("crm.workspace.org.view"))],
)
async def list_organization_changes(
    org_id: int,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List field-level changes for an organization."""
    tenant_id = current_user["tenant_id"]
    return await EntityChangeService.get_paginated(
        db,
        tenant_id,
        "organization",
        org_id,
        page,
        per_page,
    )


@router.put(
    "/{org_id}",
    response_model=OrganizationResponse,
    dependencies=[Depends(require_permission("crm.workspace.org.edit"))],
)
async def update_organization(
    org_id: int,
    body: OrganizationUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing organization."""
    tenant_id = current_user["tenant_id"]
    return await OrganizationService.update_organization(
        db,
        tenant_id,
        org_id,
        body,
        actor_id=current_user.get("user_id"),
    )


@router.delete(
    "/{org_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("crm.workspace.org.delete"))],
)
async def delete_organization(
    org_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an organization."""
    tenant_id = current_user["tenant_id"]
    await OrganizationService.delete_organization(db, tenant_id, org_id)


@router.get(
    "/{org_ref}/users",
    response_model=dict,
    dependencies=[Depends(require_permission("crm.workspace.user.view"))],
)
async def list_organization_users(
    org_ref: str,
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List users belonging to this organization (paginated)."""
    from app.services.user_service import UserService
    from app.schemas.user import UserQueryRequest

    tenant_id = current_user["tenant_id"]
    # Verify organization exists and resolve public ID to the internal FK.
    org = await OrganizationService.get_by_ref(db, tenant_id, org_ref)
    if not org:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Organization not found")
    org_id = org["id"]

    req = UserQueryRequest(
        search=search,
        temp_conditions=[{
            "field_key": "organization_id",
            "field_id": None,
            "operator": "eq",
            "value": org_id,
        }],
        temp_condition_logic="and",
        page=page,
        per_page=per_page,
    )
    return await UserService.query_users(db, tenant_id, req)
