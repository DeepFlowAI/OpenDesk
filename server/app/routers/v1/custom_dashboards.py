"""Custom dashboard management and workspace routers."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.db.deps import (
    get_current_principal_short_session,
    get_db,
    get_redis,
    require_all_permissions,
    require_all_permissions_short_session,
    require_permission,
)
from app.schemas.custom_dashboard import (
    CustomDashboardCopyRequest,
    CustomDashboardCreate,
    CustomDashboardListResponse,
    CustomDashboardReorderRequest,
    CustomDashboardResponse,
    CustomDashboardUpdate,
    WorkspaceDashboardListResponse,
    WorkspaceDashboardResponse,
)
from app.schemas.permission import EffectivePrincipal
from app.schemas.custom_dashboard_run import (
    CustomDashboardRunRequest,
    CustomDashboardRunResponse,
)
from app.services.custom_dashboard_run_service import CustomDashboardRunService
from app.services.custom_dashboard_service import CustomDashboardService


router = APIRouter(prefix="/custom-dashboards", tags=["CustomDashboards"])
workspace_router = APIRouter(
    prefix="/workspace/custom-dashboards",
    tags=["WorkspaceCustomDashboards"],
)
run_router = APIRouter(prefix="/custom-dashboard-runs", tags=["CustomDashboardRuns"])

ManagePrincipal = Annotated[
    EffectivePrincipal,
    Depends(require_permission("report.dashboard.manage")),
]
ViewPrincipal = Annotated[
    EffectivePrincipal,
    Depends(
        require_all_permissions(
            ["report.dashboard.view", "ticket.workspace.view"]
        )
    ),
]
PreviewRunPrincipal = Annotated[
    EffectivePrincipal,
    Depends(
        require_all_permissions_short_session(
            ["report.dashboard.manage", "ticket.workspace.view"]
        )
    ),
]
WorkspaceRunPrincipal = Annotated[
    EffectivePrincipal,
    Depends(
        require_all_permissions_short_session(
            ["report.dashboard.view", "ticket.workspace.view"]
        )
    ),
]
CancelPrincipal = Annotated[
    EffectivePrincipal,
    Depends(get_current_principal_short_session),
]


@router.get("", response_model=CustomDashboardListResponse)
async def list_custom_dashboards(
    principal: ManagePrincipal,
    db: AsyncSession = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    keyword: str | None = None,
    status_filter: Annotated[
        Literal["draft", "published", "disabled"] | None,
        Query(alias="status"),
    ] = None,
) -> dict:
    """List tenant dashboards for management."""
    return await CustomDashboardService.get_paginated(
        db,
        principal.tenant_id,
        page=page,
        per_page=per_page,
        keyword=keyword,
        status=status_filter,
    )


@router.post(
    "",
    response_model=CustomDashboardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_custom_dashboard(
    body: CustomDashboardCreate,
    principal: ManagePrincipal,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a draft dashboard."""
    return await CustomDashboardService.create(db, principal.tenant_id, body)


@router.post("/reorder")
async def reorder_custom_dashboards(
    body: CustomDashboardReorderRequest,
    principal: ManagePrincipal,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update tenant dashboard order."""
    await CustomDashboardService.reorder(db, principal.tenant_id, body.ids)
    return {"message": "Reordered successfully"}


@router.get("/{dashboard_id}", response_model=CustomDashboardResponse)
async def get_custom_dashboard(
    dashboard_id: int,
    principal: ManagePrincipal,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the current draft and publish summary."""
    return await CustomDashboardService.get_by_id(
        db,
        dashboard_id,
        principal.tenant_id,
    )


@router.put("/{dashboard_id}", response_model=CustomDashboardResponse)
async def update_custom_dashboard(
    dashboard_id: int,
    body: CustomDashboardUpdate,
    principal: ManagePrincipal,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Save the current draft without changing the published snapshot."""
    return await CustomDashboardService.update(
        db,
        dashboard_id,
        principal.tenant_id,
        body,
    )


@router.delete("/{dashboard_id}")
async def delete_custom_dashboard(
    dashboard_id: int,
    principal: ManagePrincipal,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Permanently delete a tenant dashboard."""
    await CustomDashboardService.delete(db, dashboard_id, principal.tenant_id)
    return {"message": "Deleted successfully"}


@router.post("/{dashboard_id}/publish", response_model=CustomDashboardResponse)
async def publish_custom_dashboard(
    dashboard_id: int,
    principal: ManagePrincipal,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Replace the current published snapshot with the draft."""
    return await CustomDashboardService.publish(db, dashboard_id, principal.tenant_id)


@router.post("/{dashboard_id}/disable", response_model=CustomDashboardResponse)
async def disable_custom_dashboard(
    dashboard_id: int,
    principal: ManagePrincipal,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Disable workspace access while retaining the published snapshot."""
    return await CustomDashboardService.disable(db, dashboard_id, principal.tenant_id)


@router.post("/{dashboard_id}/enable", response_model=CustomDashboardResponse)
async def enable_custom_dashboard(
    dashboard_id: int,
    principal: ManagePrincipal,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Restore workspace access to the latest published snapshot."""
    return await CustomDashboardService.enable(db, dashboard_id, principal.tenant_id)


@router.post(
    "/{dashboard_id}/copy",
    response_model=CustomDashboardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def copy_custom_dashboard(
    dashboard_id: int,
    body: CustomDashboardCopyRequest,
    principal: ManagePrincipal,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Copy the current draft into a new draft dashboard."""
    return await CustomDashboardService.copy(
        db,
        dashboard_id,
        principal.tenant_id,
        body,
    )


@workspace_router.get("", response_model=WorkspaceDashboardListResponse)
async def list_workspace_custom_dashboards(
    principal: ViewPrincipal,
    db: AsyncSession = Depends(get_db),
    keyword: str | None = None,
) -> dict:
    """List active published dashboards visible in the workspace."""
    return await CustomDashboardService.list_workspace(
        db,
        principal.tenant_id,
        keyword,
    )


@workspace_router.get("/{dashboard_id}", response_model=WorkspaceDashboardResponse)
async def get_workspace_custom_dashboard(
    dashboard_id: int,
    principal: ViewPrincipal,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a published dashboard without exposing component source code."""
    return await CustomDashboardService.get_workspace_detail(
        db,
        dashboard_id,
        principal.tenant_id,
    )


@router.post("/{dashboard_id}/preview", response_model=CustomDashboardRunResponse)
async def preview_custom_dashboard_component(
    dashboard_id: int,
    body: CustomDashboardRunRequest,
    principal: PreviewRunPrincipal,
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Run one component from the current draft in an isolated sandbox."""
    return await CustomDashboardRunService.run_managed(
        redis,
        principal,
        dashboard_id=dashboard_id,
        request=body,
        preview=True,
    )


@workspace_router.post("/{dashboard_id}/run", response_model=CustomDashboardRunResponse)
async def run_workspace_custom_dashboard_component(
    dashboard_id: int,
    body: CustomDashboardRunRequest,
    principal: WorkspaceRunPrincipal,
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Run one component from the current published snapshot."""
    return await CustomDashboardRunService.run_managed(
        redis,
        principal,
        dashboard_id=dashboard_id,
        request=body,
        preview=False,
    )


@run_router.post("/{request_id}/cancel")
async def cancel_custom_dashboard_run(
    request_id: UUID,
    principal: CancelPrincipal,
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Cancel a component run owned by the current employee."""
    _assert_can_run_dashboard(principal)
    await CustomDashboardRunService.cancel_run(redis, principal, request_id)
    return {"message": "Cancellation requested"}


@run_router.post("/pages/{page_run_id}/cancel")
async def cancel_custom_dashboard_page_run(
    page_run_id: UUID,
    principal: CancelPrincipal,
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Cancel all component runs for a page batch owned by the employee."""
    _assert_can_run_dashboard(principal)
    await CustomDashboardRunService.cancel_page(redis, principal, page_run_id)
    return {"message": "Cancellation requested"}


def _assert_can_run_dashboard(principal: EffectivePrincipal) -> None:
    if not principal.has_permission("ticket.workspace.view") or not principal.has_any_permission(
        ["report.dashboard.view", "report.dashboard.manage"]
    ):
        raise ForbiddenError("Permission denied")
