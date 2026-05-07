"""
Employee selection router — read-only endpoints for employee queries (member selection)
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.employee_group import EmployeeSelectListResponse
from app.services.employee_group_service import EmployeeQueryService

router = APIRouter(prefix="/system-users", tags=["EmployeeSelect"])


@router.get("", response_model=EmployeeSelectListResponse)
async def list_employees_for_selection(
    page: int = 1,
    per_page: int = 20,
    keyword: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List active employees for member selection (paginated with optional search)."""
    tenant_id = current_user["tenant_id"]
    return await EmployeeQueryService.get_paginated(db, tenant_id, page, per_page, keyword)
