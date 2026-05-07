"""
Employees router
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeListResponse,
    StatusUpdate,
)
from app.services.employee_service import EmployeeService

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.get("", response_model=EmployeeListResponse)
async def list_employees(
    page: int = 1,
    per_page: int = 10,
    keyword: str | None = None,
    q: str | None = None,
    role: Annotated[list[str] | None, Query()] = None,
    status: str | None = None,
    group_id: int | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List employees with filtering and pagination."""
    tenant_id = current_user["tenant_id"]
    search_keyword = keyword or q
    return await EmployeeService.list_employees(
        db, tenant_id, page, per_page, search_keyword, role, status, group_id
    )


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    body: EmployeeCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new employee."""
    tenant_id = current_user["tenant_id"]
    return await EmployeeService.create(db, tenant_id, body)


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get employee by ID."""
    tenant_id = current_user["tenant_id"]
    return await EmployeeService.get_by_id(db, tenant_id, employee_id)


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    body: EmployeeUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an employee."""
    tenant_id = current_user["tenant_id"]
    return await EmployeeService.update(db, tenant_id, employee_id, body)


@router.delete("/{employee_id}", status_code=status.HTTP_200_OK)
async def delete_employee(
    employee_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an employee."""
    tenant_id = current_user["tenant_id"]
    await EmployeeService.delete(db, tenant_id, employee_id)
    return {"message": "Deleted successfully"}


@router.patch("/{employee_id}/status", response_model=EmployeeResponse)
async def update_employee_status(
    employee_id: int,
    body: StatusUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle employee active status."""
    tenant_id = current_user["tenant_id"]
    return await EmployeeService.update_status(db, tenant_id, employee_id, body)
