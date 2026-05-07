"""
Session summary (conversation minutes) configuration router
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.cs_summary_config import (
    CsSummaryConfigResponse,
    CsSummaryConfigFieldCreate,
    CsSummaryConfigFieldUpdate,
    CsSummaryConfigFieldResponse,
    CsSummaryConfigFieldListResponse,
    CsSummaryFieldSortRequest,
    CsSummaryInteractionRuleCreate,
    CsSummaryInteractionRuleUpdate,
    CsSummaryInteractionRuleResponse,
    CsSummaryInteractionRuleListResponse,
    CsSummaryRuleSortRequest,
)
from app.services.cs_summary_config_service import CsSummaryConfigService
from app.schemas.cs_summary_usage import (
    CsSummaryUsageResponse,
    CsSummaryFieldValueUpdate,
    CsSummaryFieldValueResponse,
)
from app.services.cs_summary_usage_service import CsSummaryUsageService

router = APIRouter(prefix="/session-summary", tags=["SessionSummary"])


# ── Config ──

@router.get("/config", response_model=CsSummaryConfigResponse)
async def get_config(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get or create the session summary config for current tenant"""
    return await CsSummaryConfigService.get_or_create_config(db, user["tenant_id"])


# ── Usage ──

@router.get("/sessions/{conversation_id}", response_model=CsSummaryUsageResponse)
async def get_session_summary(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get conversation minutes fields, rules, and values for a conversation."""
    return await CsSummaryUsageService.get_summary(db, user["tenant_id"], conversation_id)


@router.patch("/sessions/{conversation_id}/fields", response_model=CsSummaryFieldValueResponse)
async def update_session_summary_field(
    conversation_id: int,
    body: CsSummaryFieldValueUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update a single conversation minutes field value."""
    return await CsSummaryUsageService.update_field(db, user["tenant_id"], conversation_id, body)


# ── Fields ──

@router.get("/config/fields", response_model=CsSummaryConfigFieldListResponse)
async def list_config_fields(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all fields in the session summary config"""
    return await CsSummaryConfigService.list_fields(db, user["tenant_id"])


@router.post("/config/fields", response_model=CsSummaryConfigFieldResponse, status_code=status.HTTP_201_CREATED)
async def add_config_field(
    body: CsSummaryConfigFieldCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Add a field to the session summary config"""
    return await CsSummaryConfigService.add_field(db, user["tenant_id"], body)


@router.put("/config/fields/sort", status_code=status.HTTP_200_OK)
async def sort_config_fields(
    body: CsSummaryFieldSortRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Reorder config fields"""
    await CsSummaryConfigService.sort_fields(db, user["tenant_id"], body)
    return {"message": "Sort updated"}


@router.put("/config/fields/{field_id}", response_model=CsSummaryConfigFieldResponse)
async def update_config_field(
    field_id: int,
    body: CsSummaryConfigFieldUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update a config field (toggle active/sort)"""
    return await CsSummaryConfigService.update_field(db, user["tenant_id"], field_id, body)


@router.delete("/config/fields/{field_id}", status_code=status.HTTP_200_OK)
async def delete_config_field(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Remove a field from the session summary config"""
    await CsSummaryConfigService.delete_field(db, user["tenant_id"], field_id)
    return {"message": "Deleted successfully"}


# ── Interaction Rules ──

@router.get("/config/interaction-rules", response_model=CsSummaryInteractionRuleListResponse)
async def list_interaction_rules(
    page: int = 1,
    per_page: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List interaction rules for session summary"""
    return await CsSummaryConfigService.list_rules(db, user["tenant_id"], page, per_page)


@router.post(
    "/config/interaction-rules",
    response_model=CsSummaryInteractionRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_interaction_rule(
    body: CsSummaryInteractionRuleCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create an interaction rule"""
    return await CsSummaryConfigService.create_rule(db, user["tenant_id"], body)


@router.put("/config/interaction-rules/sort", status_code=status.HTTP_200_OK)
async def sort_interaction_rules(
    body: CsSummaryRuleSortRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Reorder interaction rules"""
    await CsSummaryConfigService.sort_rules(db, user["tenant_id"], body)
    return {"message": "Sort updated"}


@router.get("/config/interaction-rules/{rule_id}", response_model=CsSummaryInteractionRuleResponse)
async def get_interaction_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get interaction rule by ID"""
    return await CsSummaryConfigService.get_rule(db, user["tenant_id"], rule_id)


@router.put("/config/interaction-rules/{rule_id}", response_model=CsSummaryInteractionRuleResponse)
async def update_interaction_rule(
    rule_id: int,
    body: CsSummaryInteractionRuleUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update an interaction rule"""
    return await CsSummaryConfigService.update_rule(db, user["tenant_id"], rule_id, body)


@router.delete("/config/interaction-rules/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_interaction_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete an interaction rule"""
    await CsSummaryConfigService.delete_rule(db, user["tenant_id"], rule_id)
    return {"message": "Deleted successfully"}
