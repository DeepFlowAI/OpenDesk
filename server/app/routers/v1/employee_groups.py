"""
EmployeeGroup router — CRUD endpoints for employee group management
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_permission
from app.schemas.permission import EffectivePrincipal
from app.schemas.employee_group import (
    EmployeeGroupCreate,
    EmployeeGroupUpdate,
    EmployeeGroupResponse,
    EmployeeGroupListResponse,
)
from app.services.employee_group_service import EmployeeGroupService

router = APIRouter(prefix="/employee-groups", tags=["EmployeeGroups"])


@router.get("", response_model=EmployeeGroupListResponse)
async def list_employee_groups(
    page: int = 1,
    per_page: int = 10,
    keyword: str | None = None,
    q: str | None = None,
    member_id: int | None = None,
    principal: EffectivePrincipal = Depends(require_permission("org.group.manage")),
    db: AsyncSession = Depends(get_db),
):
    """List employee groups with pagination and optional keyword search."""
    tenant_id = principal.tenant_id
    search_keyword = keyword or q
    return await EmployeeGroupService.get_paginated(
        db, tenant_id, page, per_page, search_keyword, member_id
    )


@router.post("", response_model=EmployeeGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_employee_group(
    body: EmployeeGroupCreate,
    principal: EffectivePrincipal = Depends(require_permission("org.group.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new employee group with optional members."""
    tenant_id = principal.tenant_id
    return await EmployeeGroupService.create(db, tenant_id, body)


@router.get("/{group_id}", response_model=EmployeeGroupResponse)
async def get_employee_group(
    group_id: int,
    principal: EffectivePrincipal = Depends(require_permission("org.group.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Get employee group detail with members."""
    tenant_id = principal.tenant_id
    return await EmployeeGroupService.get_by_id(db, group_id, tenant_id)


@router.put("/{group_id}", response_model=EmployeeGroupResponse)
async def update_employee_group(
    group_id: int,
    body: EmployeeGroupUpdate,
    principal: EffectivePrincipal = Depends(require_permission("org.group.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Update employee group (full replace including members)."""
    tenant_id = principal.tenant_id
    return await EmployeeGroupService.update(db, group_id, tenant_id, body)


@router.delete("/{group_id}", status_code=status.HTTP_200_OK)
async def delete_employee_group(
    group_id: int,
    principal: EffectivePrincipal = Depends(require_permission("org.group.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Delete employee group."""
    tenant_id = principal.tenant_id
    await EmployeeGroupService.delete(db, group_id, tenant_id)
    return {"message": "Deleted successfully"}
