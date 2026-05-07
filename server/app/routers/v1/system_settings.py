"""
System settings router
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.system_settings import (
    SystemSettingsUpdate,
    OrganizationSettingsUpdate,
    SystemSettingsResponse,
)
from app.services.system_settings_service import SystemSettingsService

router = APIRouter(prefix="/system-settings", tags=["SystemSettings"])


@router.get("", response_model=SystemSettingsResponse)
async def get_system_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get system settings for the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await SystemSettingsService.get_settings(db, tenant_id)


@router.put("", response_model=SystemSettingsResponse)
async def update_system_settings(
    body: SystemSettingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update system settings for the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await SystemSettingsService.update_settings(db, tenant_id, body)


@router.put("/organization", response_model=SystemSettingsResponse)
async def update_organization_settings(
    body: OrganizationSettingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle organization feature for the current tenant."""
    tenant_id = current_user["tenant_id"]
    return await SystemSettingsService.update_organization_settings(db, tenant_id, body)
