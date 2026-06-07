"""
Role router.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_any_permission, require_permission
from app.schemas.permission import EffectivePrincipal
from app.schemas.role import (
    PermissionTreeResponse,
    RoleCreate,
    RoleListResponse,
    RoleOptionsResponse,
    RoleResponse,
    RoleUpdate,
)
from app.services.role_service import RoleService

router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get("", response_model=RoleListResponse)
async def list_roles(
    page: int = 1,
    per_page: int = 10,
    keyword: str | None = None,
    type: str | None = None,
    principal: EffectivePrincipal = Depends(require_permission("org.role.manage")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = principal.tenant_id
    return await RoleService.list_roles(db, tenant_id, page, per_page, keyword, type)


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate,
    principal: EffectivePrincipal = Depends(require_permission("org.role.manage")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = principal.tenant_id
    return await RoleService.create(db, tenant_id, body)


@router.get("/options", response_model=RoleOptionsResponse)
async def role_options(
    principal: EffectivePrincipal = Depends(
        require_any_permission(["org.employee.create", "org.employee.edit", "org.role.manage"])
    ),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = principal.tenant_id
    return await RoleService.get_options(db, tenant_id)


@router.get("/permission-tree", response_model=PermissionTreeResponse)
async def permission_tree(
    _principal: EffectivePrincipal = Depends(require_permission("org.role.manage")),
):
    return RoleService.get_permission_tree()


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int,
    principal: EffectivePrincipal = Depends(require_permission("org.role.manage")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = principal.tenant_id
    return await RoleService.get_by_id(db, tenant_id, role_id)


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    body: RoleUpdate,
    principal: EffectivePrincipal = Depends(require_permission("org.role.manage")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = principal.tenant_id
    return await RoleService.update(db, tenant_id, role_id, body)


@router.delete("/{role_id}", status_code=status.HTTP_200_OK)
async def delete_role(
    role_id: int,
    principal: EffectivePrincipal = Depends(require_permission("org.role.manage")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = principal.tenant_id
    await RoleService.delete(db, tenant_id, role_id)
    return {"message": "Deleted successfully"}
