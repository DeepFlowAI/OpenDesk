"""
Call summary configuration router
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.call_summary_config import (
    CallSummaryConfigResponse,
    CallSummaryConfigFieldCreate,
    CallSummaryConfigFieldUpdate,
    CallSummaryConfigFieldResponse,
    CallSummaryConfigFieldListResponse,
    CallSummaryFieldSortRequest,
    CallSummaryInteractionRuleCreate,
    CallSummaryInteractionRuleUpdate,
    CallSummaryInteractionRuleResponse,
    CallSummaryInteractionRuleListResponse,
    CallSummaryRuleSortRequest,
)
from app.schemas.call_summary_usage import (
    CallSummaryUsageResponse,
    CallSummaryFieldValueResponse,
    CallSummaryFieldValueUpdate,
)
from app.services.call_summary_config_service import CallSummaryConfigService
from app.services.call_summary_usage_service import CallSummaryUsageService

router = APIRouter(prefix="/call-summary", tags=["CallSummary"])


# -- Usage --

@router.get("/call-records/{call_record_id}", response_model=CallSummaryUsageResponse)
async def get_call_summary(
    call_record_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get call summary fields, rules, and values for a call record."""
    return await CallSummaryUsageService.get_summary(db, user["tenant_id"], call_record_id)


@router.patch("/call-records/{call_record_id}/fields", response_model=CallSummaryFieldValueResponse)
async def update_call_summary_field(
    call_record_id: int,
    body: CallSummaryFieldValueUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update one field value for a call record summary."""
    return await CallSummaryUsageService.update_field(db, user["tenant_id"], call_record_id, body)


# -- Config --

@router.get("/config", response_model=CallSummaryConfigResponse)
async def get_config(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get or create the call summary config for current tenant."""
    return await CallSummaryConfigService.get_or_create_config(db, user["tenant_id"])


# -- Fields --

@router.get("/config/fields", response_model=CallSummaryConfigFieldListResponse)
async def list_config_fields(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all fields in the call summary config."""
    return await CallSummaryConfigService.list_fields(db, user["tenant_id"])


@router.post("/config/fields", response_model=CallSummaryConfigFieldResponse, status_code=status.HTTP_201_CREATED)
async def add_config_field(
    body: CallSummaryConfigFieldCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Add a field to the call summary config."""
    return await CallSummaryConfigService.add_field(db, user["tenant_id"], body)


@router.put("/config/fields/sort", status_code=status.HTTP_200_OK)
async def sort_config_fields(
    body: CallSummaryFieldSortRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Reorder config fields."""
    await CallSummaryConfigService.sort_fields(db, user["tenant_id"], body)
    return {"message": "Sort updated"}


@router.put("/config/fields/{field_id}", response_model=CallSummaryConfigFieldResponse)
async def update_config_field(
    field_id: int,
    body: CallSummaryConfigFieldUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update a config field."""
    return await CallSummaryConfigService.update_field(db, user["tenant_id"], field_id, body)


@router.delete("/config/fields/{field_id}", status_code=status.HTTP_200_OK)
async def delete_config_field(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Remove a field from the call summary config."""
    await CallSummaryConfigService.delete_field(db, user["tenant_id"], field_id)
    return {"message": "Deleted successfully"}


# -- Interaction Rules --

@router.get("/config/interaction-rules", response_model=CallSummaryInteractionRuleListResponse)
async def list_interaction_rules(
    page: int = 1,
    per_page: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List interaction rules for call summary."""
    return await CallSummaryConfigService.list_rules(db, user["tenant_id"], page, per_page)


@router.post(
    "/config/interaction-rules",
    response_model=CallSummaryInteractionRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_interaction_rule(
    body: CallSummaryInteractionRuleCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create an interaction rule."""
    return await CallSummaryConfigService.create_rule(db, user["tenant_id"], body)


@router.put("/config/interaction-rules/sort", status_code=status.HTTP_200_OK)
async def sort_interaction_rules(
    body: CallSummaryRuleSortRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Reorder interaction rules."""
    await CallSummaryConfigService.sort_rules(db, user["tenant_id"], body)
    return {"message": "Sort updated"}


@router.get("/config/interaction-rules/{rule_id}", response_model=CallSummaryInteractionRuleResponse)
async def get_interaction_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get interaction rule by ID."""
    return await CallSummaryConfigService.get_rule(db, user["tenant_id"], rule_id)


@router.put("/config/interaction-rules/{rule_id}", response_model=CallSummaryInteractionRuleResponse)
async def update_interaction_rule(
    rule_id: int,
    body: CallSummaryInteractionRuleUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update an interaction rule."""
    return await CallSummaryConfigService.update_rule(db, user["tenant_id"], rule_id, body)


@router.delete("/config/interaction-rules/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_interaction_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete an interaction rule."""
    await CallSummaryConfigService.delete_rule(db, user["tenant_id"], rule_id)
    return {"message": "Deleted successfully"}
