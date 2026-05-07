"""
ServiceHours router — CRUD endpoints for service hour configurations
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.service_hours import (
    ServiceHoursCreate,
    ServiceHoursUpdate,
    ServiceHoursResponse,
)
from app.services.service_hours_service import ServiceHoursService

router = APIRouter(prefix="/service-hours", tags=["ServiceHours"])


@router.get("", response_model=list[ServiceHoursResponse])
async def list_service_hours(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all service hours for the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await ServiceHoursService.list_by_tenant(db, tenant_id)


@router.post("", response_model=ServiceHoursResponse, status_code=status.HTTP_201_CREATED)
async def create_service_hours(
    body: ServiceHoursCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new service hours configuration."""
    tenant_id = current_user["tenant_id"]
    return await ServiceHoursService.create(db, tenant_id, body)


@router.get("/{service_hours_id}", response_model=ServiceHoursResponse)
async def get_service_hours(
    service_hours_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get service hours by ID."""
    tenant_id = current_user["tenant_id"]
    return await ServiceHoursService.get_by_id(db, service_hours_id, tenant_id)


@router.put("/{service_hours_id}", response_model=ServiceHoursResponse)
async def update_service_hours(
    service_hours_id: int,
    body: ServiceHoursUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update service hours configuration."""
    tenant_id = current_user["tenant_id"]
    return await ServiceHoursService.update(db, service_hours_id, tenant_id, body)


@router.delete("/{service_hours_id}", status_code=status.HTTP_200_OK)
async def delete_service_hours(
    service_hours_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete service hours configuration."""
    tenant_id = current_user["tenant_id"]
    await ServiceHoursService.delete(db, service_hours_id, tenant_id)
    return {"message": "Deleted successfully"}
